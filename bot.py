"""
bot.py - Winter Arc Discord Bot Main Entrypoint

Features:
- Enrollment Gate: Commands only respond to enrolled users; unenrolled users are prompted to /enroll
- Dedicated Channel Automation: Scheduled messages (05:00, 16:30, 00:00 IST) post only to the designated channel
- Role Pings: Automated notifications ping the configured Winter Arc role (no private DMs)
- Slash commands: /enroll, /leave_arc, /ping, /today, /log, /leaderboard, /stats, /history, /profile, /test_reminder
- Admin commands: /admin set_channel, /admin set_role, /admin overview, /admin task_add, /admin task_toggle, /admin tasks_list
"""

import os
import sys
import logging
from datetime import datetime, date
from zoneinfo import ZoneInfo
from typing import Optional, List

import discord
from discord import app_commands
from dotenv import load_dotenv

import database as db
from scheduler import WinterArcScheduler, BOT_TZ

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("winter_arc.bot")

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
TEST_GUILD_ID = os.getenv("TEST_GUILD_ID")
DEFAULT_ROLE_ID = int(os.getenv("WINTER_ARC_ROLE_ID", "1550511682344845352"))


def make_progress_bar(current: float, target: float, length: int = 10) -> str:
    if target <= 0:
        return "🟩" * length
    ratio = min(max(current / target, 0.0), 1.0)
    filled = int(round(ratio * length))
    empty = length - filled
    return "🟩" * filled + "⬜" * empty


def format_rank_badge(idx: int) -> str:
    if idx == 0:
        return "`#1` 👑"
    elif idx == 1:
        return "`#2` ⚔️"
    elif idx == 2:
        return "`#3` 🛡️"
    else:
        return f"`#{idx+1:>2}` ▫️"


def build_daily_leaderboard_embed() -> discord.Embed:
    now = datetime.now(BOT_TZ)
    today_str = now.strftime("%Y-%m-%d")
    date_display = now.strftime("%A, %B %d, %Y")
    data = db.get_daily_leaderboard(today_str)

    lines = []
    for idx, entry in enumerate(data):
        rank = format_rank_badge(idx)
        pct = int(entry["completion_rate"] * 100)
        star = " ⭐" if entry["perfect_day"] else ""
        lines.append(f"{rank} **{entry['username']}** — `{entry['points']} / 500 PTS` ({pct}%){star}")

    if not lines:
        lines.append("_No participants enrolled yet. Use `/enroll` to join!_")

    embed = discord.Embed(
        title="🏆 WINTER ARC — AMAROK'S DAILY STANDINGS",
        description=(
            f"📅 **{date_display}**\n"
            f"_Daily progress resets and locks at 00:00 IST._\n\n"
            + "\n".join(lines)
        ),
        color=0xF1C40F
    )
    embed.set_footer(text="Updated live • Amarok's Discipline Standings")
    return embed


def build_overall_leaderboard_embed() -> discord.Embed:
    data = db.get_overall_leaderboard()

    lines = []
    for idx, entry in enumerate(data):
        rank = format_rank_badge(idx)
        streak_part = f" • 🔥 `{entry['streak']}d`" if entry.get("streak", 0) > 0 else ""
        perfect_part = f" • ⭐ `{entry['perfect_days']} clean`" if entry.get("perfect_days", 0) > 0 else ""
        lines.append(f"{rank} **{entry['username']}** — `{entry['total_points']:,} PTS`{streak_part}{perfect_part}")

    if not lines:
        lines.append("_No participants enrolled yet. Use `/enroll` to join!_")

    embed = discord.Embed(
        title="🏆 WINTER ARC — AMAROK'S OVERALL STANDINGS",
        description=(
            "🌐 **All-Time Discipline Leaderboard**\n"
            "_Ranked by total points accumulated across all completed challenges._\n\n"
            + "\n".join(lines)
        ),
        color=0x3498DB
    )
    embed.set_footer(text="Updated live • Amarok's Discipline Standings")
    return embed


class LeaderboardView(discord.ui.View):
    def __init__(self, current_tab: str = "daily"):
        super().__init__(timeout=None)
        self.current_tab = current_tab
        self._update_buttons()

    def _update_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "lb_btn_daily":
                    child.style = discord.ButtonStyle.primary if self.current_tab == "daily" else discord.ButtonStyle.secondary
                elif child.custom_id == "lb_btn_overall":
                    child.style = discord.ButtonStyle.primary if self.current_tab == "overall" else discord.ButtonStyle.secondary

    @discord.ui.button(label="Daily", emoji="📅", style=discord.ButtonStyle.primary, custom_id="lb_btn_daily")
    async def daily_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "daily"
        self._update_buttons()
        embed = build_daily_leaderboard_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Overall", emoji="🌐", style=discord.ButtonStyle.secondary, custom_id="lb_btn_overall")
    async def overall_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "overall"
        self._update_buttons()
        embed = build_overall_leaderboard_embed()
        await interaction.response.edit_message(embed=embed, view=self)


# ==========================================
# Discord Client & Command Tree
# ==========================================

class WinterArcBot(discord.Client):
    def __init__(self):
        # Default intents are sufficient for slash commands and role assignment
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.scheduler: Optional[WinterArcScheduler] = None

    async def setup_hook(self):
        db.init_db()
        logger.info("SQLite database initialized and seed tasks confirmed.")

        self.add_view(LeaderboardView())
        logger.info("Registered persistent LeaderboardView.")

        self.scheduler = WinterArcScheduler(self)
        self.scheduler.start()

        # Synchronize clean global commands
        await self.tree.sync()
        logger.info("Slash commands synchronized globally.")

    async def on_ready(self):
        logger.info(f"Logged in successfully as {self.user} (ID: {self.user.id})")
        activity = discord.Activity(type=discord.ActivityType.watching, name="The Winter is Coming... | /help")
        await self.change_presence(status=discord.Status.online, activity=activity)

        # Clear any guild-specific command copies to prevent duplicate commands in Discord UI
        for guild in self.guilds:
            try:
                self.tree.clear_commands(guild=guild)
                await self.tree.sync(guild=guild)
                logger.info(f"🧹 Cleared guild-level duplicate commands for '{guild.name}' ({guild.id})")
            except Exception as e:
                logger.warning(f"Could not clear guild commands for '{guild.name}': {e}")

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # Detect if this message is a reply to one of the bot's messages or mentions the bot
        is_reply_to_bot = False
        if message.reference and message.reference.message_id:
            ref = message.reference.resolved
            if not isinstance(ref, discord.Message):
                try:
                    ref = await message.channel.fetch_message(message.reference.message_id)
                except Exception:
                    ref = None
            if ref and ref.author.id == self.user.id:
                is_reply_to_bot = True

        is_bot_mentioned = (self.user in message.mentions) if self.user else False
        is_amarok_named = "amarok" in (message.content.lower() if message.content else "")

        if is_reply_to_bot or is_bot_mentioned or is_amarok_named:
            content_lower = message.content.lower() if message.content else ""
            reactions = ["🐺"]  # Mascot wolf (Amarok)

            if any(w in content_lower for w in ["done", "completed", "finish", "crushed", "locked in", "lets go", "let's go", "win"]):
                reactions.extend(["🔥", "⚔️"])
            elif any(w in content_lower for w in ["run", "pushup", "pullup", "squat", "situp", "workout", "reps", "km", "lift"]):
                reactions.extend(["💪", "⚔️"])
            elif any(w in content_lower for w in ["cold", "winter", "ice", "freeze", "snow"]):
                reactions.extend(["❄️", "⚡"])
            else:
                reactions.append("❄️")

            for r in reactions[:2]:
                try:
                    await message.add_reaction(r)
                except Exception as e:
                    logger.debug(f"Could not react {r} to message {message.id}: {e}")


bot = WinterArcBot()


async def safe_react(interaction: discord.Interaction, *emojis: str):
    """Safely adds reactions to the bot's own slash command response."""
    try:
        msg = await interaction.original_response()
        for e in emojis:
            await msg.add_reaction(e)
    except Exception:
        pass


# ==========================================
# Global Slash Command Error Handler
# ==========================================

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    orig_error = getattr(error, "original", error)
    logger.error(f"Error in command '{interaction.command.name if interaction.command else 'unknown'}': {orig_error}", exc_info=orig_error)
    msg = f"⚠️ Error executing command: `{orig_error}`"
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        logger.error(f"Failed to deliver error response to user: {e}")


# ==========================================
# Enrollment Gate Guard
# ==========================================

async def require_enrolled(interaction: discord.Interaction) -> bool:
    """Verifies that the user is enrolled in Winter Arc before allowing command execution."""
    if not db.is_user_enrolled(interaction.user.id):
        embed = discord.Embed(
            title="🚫 Not Enrolled in Winter Arc",
            description=(
                f"Hey {interaction.user.mention}, you haven't joined the Winter Arc yet!\n\n"
                "**How to join:**\n"
                "Type **/enroll** to enter the challenge, receive the role, and start logging workouts."
            ),
            color=0xE74C3C
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False
    return True


# ==========================================
# Task Autocomplete Helper
# ==========================================

async def task_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    tasks = db.get_active_tasks()
    choices = []
    for t in tasks:
        if current.lower() in t["name"].lower():
            choices.append(app_commands.Choice(name=f"{t['name']} (target: {t['target']} {t['unit']})", value=t["name"]))
    return choices[:25]


async def get_or_create_arc_role(guild: discord.Guild) -> Optional[discord.Role]:
    """Finds configured role, or finds an existing 'Winter Arc' role, or auto-creates one."""
    settings = db.get_server_settings(guild.id)
    role_id = settings.get("role_id", 0) or DEFAULT_ROLE_ID
    if role_id:
        role = guild.get_role(role_id)
        if role:
            return role

    # Fallback 1: Look for existing role named "Winter Arc"
    for r in guild.roles:
        if r.name.lower() in ["winter arc", "winterarc", "the winter arc"]:
            db.set_server_role(guild.id, r.id)
            return r

    # Fallback 2: Auto-create "Winter Arc" role if bot has Manage Roles permission
    if guild.me.guild_permissions.manage_roles:
        try:
            new_role = await guild.create_role(
                name="Winter Arc",
                color=discord.Color.from_rgb(0, 210, 255),  # Frost Cyan
                hoist=True,
                mentionable=True,
                reason="Auto-created by Winter Arc Bot for challenge participants."
            )
            db.set_server_role(guild.id, new_role.id)
            logger.info(f"Auto-created 'Winter Arc' role (ID {new_role.id}) in '{guild.name}'")
            return new_role
        except Exception as e:
            logger.warning(f"Could not auto-create Winter Arc role in {guild.name}: {e}")

    return None


# ==========================================
# Enrollment & Core User Commands
# ==========================================

@bot.tree.command(name="enroll", description="Enroll in the Winter Arc challenge and receive the warrior role.")
async def enroll(interaction: discord.Interaction):
    is_already = db.is_user_enrolled(interaction.user.id)
    user_record = db.enroll_user(interaction.user.id, interaction.user.name)

    # Attempt to assign the Winter Arc role
    role_msg = ""
    if interaction.guild and isinstance(interaction.user, discord.Member):
        role = await get_or_create_arc_role(interaction.guild)
        if role:
            try:
                await interaction.user.add_roles(role)
                role_msg = f"\n🛡️ Granted role: **{role.name}**"
            except discord.Forbidden:
                role_msg = (
                    f"\n⚠️ *(Could not assign {role.name} role — make sure the bot's own role "
                    f"is dragged ABOVE {role.name} in Server Settings -> Roles)*"
                )
            except Exception as e:
                role_msg = f"\n⚠️ *(Could not assign role: {e})*"
        else:
            role_msg = "\nℹ️ *(Admin: run `/admin set_role` or grant the bot 'Manage Roles' to auto-assign)*"

    active_tasks = db.get_active_tasks()
    task_lines = [f"• **{t['name']}**: `{t['target']} {t['unit']}` ({t['max_points']} pts)" for t in active_tasks]

    title = "⚔️ Enrolled in Winter Arc!" if not is_already else "⚔️ Enrollment Re-activated!"
    embed = discord.Embed(
        title=title,
        description=(
            f"Welcome to Amarok's pack, **{interaction.user.display_name}**.{role_msg}\n\n"
            "**The Ground Rules:**\n"
            "• Complete your daily targets every day.\n"
            "• Points are capped to prevent cheating — focus on consistency.\n"
            "• Check in at 05:00 and 16:30; day results lock in at 00:00 IST.\n"
            "• Use **/log** to record activity and **/today** to check progress."
        ),
        color=0x2ECC71
    )
    embed.add_field(name="📋 Daily Challenge Disciplines", value="\n".join(task_lines) if task_lines else "None configured.", inline=False)
    embed.set_footer(text="Amarok demands discipline. Lock in.")
    await interaction.response.send_message(embed=embed)
    await safe_react(interaction, "🐺", "⚔️")


@bot.tree.command(name="leave_arc", description="Unenroll from the Winter Arc challenge.")
async def leave_arc(interaction: discord.Interaction):
    if not db.is_user_enrolled(interaction.user.id):
        await interaction.response.send_message("You are not currently enrolled in Winter Arc.", ephemeral=True)
        return

    db.unenroll_user(interaction.user.id)

    # Remove role if present
    if interaction.guild and isinstance(interaction.user, discord.Member):
        role = await get_or_create_arc_role(interaction.guild)
        if role and role in interaction.user.roles:
            try:
                await interaction.user.remove_roles(role)
            except Exception:
                pass

    embed = discord.Embed(
        title="🏳️ Unenrolled from Winter Arc",
        description=f"{interaction.user.mention} has stepped away from Amarok's pack.\nYour historical data is preserved. Run `/enroll` anytime to rejoin.",
        color=0x7F8C8D
    )
    embed.set_footer(text="Amarok will remember your records. Return when ready.")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="ping", description="Check whether Winter Arc bot is online and measure gateway latency.")
async def ping(interaction: discord.Interaction):
    latency_ms = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Amarok is alert and operational.\n**Gateway Latency**: `{latency_ms} ms`\n**Timezone**: `{BOT_TZ}`",
        color=0x2ECC71
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="help", description="View the Winter Arc manual, commands, and rules.")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="❄️ WINTER ARC // AMAROK COMMAND DIRECTORY",
        description=(
            "**500 Points Daily • Consistency Beats Motivation**\n"
            "Track daily workout sets, build streaks, and stay accountable with Amarok's pack."
        ),
        color=0x2B2D31
    )

    disciplines_text = (
        "```yaml\n"
        "Push-ups  : 100 reps   (1 pt / rep  -> 100 max)\n"
        "Pull-ups  : 100 reps   (1 pt / rep  -> 100 max)\n"
        "Squats    : 100 reps   (1 pt / rep  -> 100 max)\n"
        "Sit-ups   : 100 reps   (1 pt / rep  -> 100 max)\n"
        "Running   : 10 km      (1 pt / 100m -> 100 max)\n"
        "Daily Max : 500 PTS    (Hit all 5 for Clean Day)\n"
        "```"
    )
    embed.add_field(name="Daily Disciplines", value=disciplines_text, inline=False)

    tracking_text = (
        "• `/enroll` — Join the Winter Arc and get the role\n"
        "• `/today` — View your current progress bars, points, and streak\n"
        "• `/log [task] [amount]` — Add reps or km to today's count\n"
        "• `/set [task] [amount]` — Override count directly *(or `0` to reset typos)*\n"
        "• `/leave_arc` — Unenroll from the challenge"
    )
    embed.add_field(name="Workout Tracking", value=tracking_text, inline=False)

    stats_text = (
        "• `/leaderboard` — Interactive Daily & Overall all-time podium\n"
        "• `/stats` — Lifetime volume, 100% clean days, and total points\n"
        "• `/history` — 7-day score completion timeline\n"
        "• `/profile` — Member card, streak, and joined date\n"
        "• `/ping` — Check bot response latency"
    )
    embed.add_field(name="Performance & Standings", value=stats_text, inline=False)

    schedule_text = (
        "`05:00 IST` Kickoff • `16:30 IST` Check-in • `00:00 IST` Day Finalized\n"
        "*Broadcasts exclusively in the dedicated channel set by admins.*"
    )
    embed.add_field(name="Automated Schedule", value=schedule_text, inline=False)

    embed.set_footer(text="Winter Arc • Guarded by Amarok • Discipline is Destiny")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="today", description="View your progress, targets, points, and streak for today.")
@app_commands.describe(member="Optional: View another enrolled member's progress")
async def today(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target_user = member or interaction.user

    # If checking self, enforce enrollment
    if target_user.id == interaction.user.id:
        if not await require_enrolled(interaction):
            return
    else:
        # Checking another user
        if not db.is_user_enrolled(target_user.id):
            await interaction.response.send_message(f"❌ {target_user.display_name} is not enrolled in Winter Arc.", ephemeral=True)
            return

    now = datetime.now(BOT_TZ)
    today_str = now.strftime("%Y-%m-%d")
    date_display = now.strftime("%B %d, %Y").upper()

    progress = db.get_user_daily_progress(target_user.id, today_str)
    streak = db.calculate_streak(target_user.id, today_str)

    embed = discord.Embed(
        title=f"❄️ WINTER ARC — {date_display}",
        description=f"Warrior: **{target_user.display_name}**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        color=0x1ABC9C if progress["perfect_day"] else 0x3498DB
    )

    task_icons = {"push-ups": "💪", "sit-ups": "🧘", "squats": "🦵", "running": "🏃", "pull-ups": "🧗"}

    for t in progress["tasks"]:
        icon = task_icons.get(t["name"].lower(), "🎯")
        cur = int(t["current_amount"]) if t["current_amount"].is_integer() else t["current_amount"]
        tgt = int(t["target"]) if t["target"].is_integer() else t["target"]
        bar = make_progress_bar(t["current_amount"], t["target"], length=8)
        status_check = "✅" if t["completed"] else ""
        embed.add_field(
            name=f"{icon} {t['name']} {status_check}",
            value=f"`{bar}` **{cur} / {tgt} {t['unit']}**\nPoints: **{t['points_earned']} / {t['max_points']}**",
            inline=False
        )

    pct = int(progress["overall_completion_rate"] * 100)
    embed.add_field(
        name="📊 Daily Summary",
        value=(
            f"**Points**: `{progress['total_points']} / {progress['max_possible_points']}`\n"
            f"**Completion**: `{pct}%`\n"
            f"**Current Streak**: 🔥 `{streak} days`"
        ),
        inline=False
    )
    embed.set_footer(text="Record reps with /log | Rankings with /leaderboard • Amarok's Pack")
    await interaction.response.send_message(embed=embed)
    if progress["perfect_day"]:
        await safe_react(interaction, "⭐", "🔥")
    else:
        await safe_react(interaction, "🐺", "❄️")


@bot.tree.command(name="log", description="Log activity towards a task (e.g. 30 push-ups, 5 km running).")
@app_commands.describe(
    task="Select the task to log",
    amount="Amount completed (e.g. 30 reps or 5 km)"
)
@app_commands.autocomplete(task=task_autocomplete)
async def log_activity_cmd(interaction: discord.Interaction, task: str, amount: float):
    if not await require_enrolled(interaction):
        return

    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be greater than 0.", ephemeral=True)
        return
    if amount > 5000:
        await interaction.response.send_message("❌ Amount exceeds reasonable single log limit (5,000).", ephemeral=True)
        return

    now = datetime.now(BOT_TZ)
    today_str = now.strftime("%Y-%m-%d")

    try:
        result = db.log_activity(
            discord_id=interaction.user.id,
            username=interaction.user.name,
            task_name=task,
            amount=amount,
            log_date=today_str
        )
    except ValueError as e:
        await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)
        return

    cur = int(result["new_total"]) if result["new_total"].is_integer() else result["new_total"]
    tgt = int(result["target"]) if result["target"].is_integer() else result["target"]
    amt = int(amount) if amount.is_integer() else amount

    bar = make_progress_bar(result["new_total"], result["target"], length=10)
    delta_str = f"+{result['points_earned_delta']} pts" if result['points_earned_delta'] > 0 else "Max points capped"

    embed = discord.Embed(
        title=f"✅ Logged: {result['task_name']}",
        color=0x2ECC71
    )
    embed.add_field(
        name="Activity",
        value=f"Added: **+{amt} {result['unit']}**\nTotal: **{cur} / {tgt} {result['unit']}**\n`{bar}`",
        inline=False
    )
    embed.add_field(
        name="Scoring",
        value=(
            f"Task Points: **{result['task_points_total']} / {result['task_max_points']}** (`{delta_str}`)\n"
            f"Daily Points: **{result['daily_points_total']} / {result['daily_points_max']}**"
        ),
        inline=False
    )

    if result["is_target_reached"] and result["previous_total"] < result["target"]:
        embed.set_footer(text="🎉 Target completed for this task today! Keep going!")
    else:
        embed.set_footer(text="Keep it up! Use /today to view full status.")

    await interaction.response.send_message(embed=embed)
    if result["is_target_reached"]:
        await safe_react(interaction, "⭐", "🔥")
    else:
        await safe_react(interaction, "🐺", "💪")


@bot.tree.command(name="set", description="Directly set or reset your today's total for a task (e.g. fix a typo or reset to 0).")
@app_commands.describe(
    task="Select the task to set/override",
    amount="Exact total to set for today (e.g. 50, or 0 to reset)"
)
@app_commands.autocomplete(task=task_autocomplete)
async def set_activity_cmd(interaction: discord.Interaction, task: str, amount: float):
    if not await require_enrolled(interaction):
        return

    if amount < 0:
        await interaction.response.send_message("❌ Amount cannot be negative.", ephemeral=True)
        return
    if amount > 5000:
        await interaction.response.send_message("❌ Amount exceeds reasonable single entry limit (5,000).", ephemeral=True)
        return

    now = datetime.now(BOT_TZ)
    today_str = now.strftime("%Y-%m-%d")

    try:
        result = db.set_activity(
            discord_id=interaction.user.id,
            username=interaction.user.name,
            task_name=task,
            target_amount=amount,
            log_date=today_str
        )
    except ValueError as e:
        await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)
        return

    cur = int(result["new_total"]) if result["new_total"].is_integer() else result["new_total"]
    tgt = int(result["target"]) if result["target"].is_integer() else result["target"]
    prev = int(result["previous_total"]) if result["previous_total"].is_integer() else result["previous_total"]

    bar = make_progress_bar(result["new_total"], result["target"], length=10)

    embed = discord.Embed(
        title=f"🔄 Set: {result['task_name']}",
        description=f"Adjusted today's total from **{prev} {result['unit']}** ➔ **{cur} {result['unit']}**.",
        color=0x3498DB
    )
    embed.add_field(
        name="Total Progress",
        value=f"Count: **{cur} / {tgt} {result['unit']}**\n`{bar}`",
        inline=False
    )
    embed.add_field(
        name="Scoring",
        value=(
            f"Task Points: **{result['task_points_total']} / {result['task_max_points']}**\n"
            f"Daily Points: **{result['daily_points_total']} / {result['daily_points_max']}**"
        ),
        inline=False
    )

    if amount == 0:
        embed.set_footer(text="Reset to 0. Log your actual sets with /log or /set.")
    else:
        embed.set_footer(text="Updated. Use /today to view full status.")

    await interaction.response.send_message(embed=embed)
    if result["is_target_reached"]:
        await safe_react(interaction, "⭐", "🔥")
    else:
        await safe_react(interaction, "🐺", "🔄")


@bot.tree.command(name="leaderboard", description="View daily or all-time Winter Arc podium standings.")
async def leaderboard(interaction: discord.Interaction):
    embed = build_daily_leaderboard_embed()
    view = LeaderboardView(current_tab="daily")
    await interaction.response.send_message(embed=embed, view=view)
    await safe_react(interaction, "🏆")


@bot.tree.command(name="stats", description="View all-time statistics, lifetime volume, and records.")
@app_commands.describe(member="Optional: View another member's statistics")
async def stats(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target_user = member or interaction.user
    if target_user.id == interaction.user.id:
        if not await require_enrolled(interaction):
            return
    else:
        if not db.is_user_enrolled(target_user.id):
            await interaction.response.send_message(f"❌ {target_user.display_name} is not enrolled in Winter Arc.", ephemeral=True)
            return

    data = db.get_user_stats(target_user.id)
    embed = discord.Embed(
        title=f"⚡ PERFORMANCE RECORD — {target_user.display_name.upper()}",
        color=0x2ECC71 if data.get('current_streak', 0) > 0 else 0x34495E
    )
    embed.add_field(
        name="Consistency & Discipline",
        value=(
            f"• **Current Streak**: `{data.get('current_streak', 0)} Days`\n"
            f"• **100% Clean Days**: `{data.get('perfect_days', 0)} Days`\n"
            f"• **Active Sessions**: `{data.get('active_days', 0)} Days`\n"
            f"• **Total Points**: `{data.get('lifetime_points', 0):,} PTS`"
        ),
        inline=False
    )

    volume_lines = []
    for t in data.get("task_totals", []):
        vol = int(t["total_volume"]) if t["total_volume"].is_integer() else t["total_volume"]
        volume_lines.append(f"• **{t['name']}**: `{vol:,} {t['unit']}`")

    if volume_lines:
        embed.add_field(name="Aggregate Volume", value="\n".join(volume_lines), inline=False)

    embed.set_footer(text="Winter Arc • Tested by Amarok • Consistency Beats Motivation")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="history", description="View your point history over the past 7 days.")
async def history(interaction: discord.Interaction):
    if not await require_enrolled(interaction):
        return

    hist = db.get_user_history(interaction.user.id, days=7)
    lines = []
    for d in reversed(hist):
        pct = int(d["completion_rate"] * 100)
        star = " ⭐" if d["perfect_day"] else ""
        lines.append(f"`{d['date']}`: **{d['points']} / {d['max_points']} pts** ({pct}%){star}")

    embed = discord.Embed(
        title=f"📜 7-Day History — {interaction.user.display_name}",
        description="\n".join(lines) if lines else "_No history recorded yet._",
        color=0x34495E
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="profile", description="View your warrior card, joined date, and current streak.")
async def profile(interaction: discord.Interaction):
    if not await require_enrolled(interaction):
        return

    user = db.get_user_by_discord_id(interaction.user.id)
    streak = db.calculate_streak(interaction.user.id)
    stats_data = db.get_user_stats(interaction.user.id)

    embed = discord.Embed(
        title=f"🛡️ Warrior Card — {interaction.user.display_name}",
        color=0x1ABC9C
    )
    if interaction.user.avatar:
        embed.set_thumbnail(url=interaction.user.avatar.url)

    embed.add_field(name="Enrolled Since", value=f"`{user['joined_at'][:10]}`", inline=True)
    embed.add_field(name="Current Streak", value=f"🔥 `{streak} days`", inline=True)
    embed.add_field(name="Lifetime Points", value=f"💎 `{stats_data['lifetime_points']:,}`", inline=True)
    embed.set_footer(text="Warrior of Amarok's Pack • Discipline is Destiny")
    await interaction.response.send_message(embed=embed)


# ==========================================
# Admin Management Commands
# ==========================================

admin_group = app_commands.Group(name="admin", description="Winter Arc administration commands (Requires Administrator).")


@admin_group.command(name="set_channel", description="Set the dedicated channel where daily scheduled messages are broadcast.")
@app_commands.describe(channel="Select the dedicated Winter Arc text channel")
@app_commands.default_permissions(administrator=True)
async def admin_set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.guild:
        await interaction.response.send_message("This command must be run within a server.", ephemeral=True)
        return

    db.set_server_channel(interaction.guild.id, channel.id)
    embed = discord.Embed(
        title="✅ Dedicated Channel Configured",
        description=(
            f"Winter Arc will now post automated daily messages exclusively in {channel.mention}.\n\n"
            "• **05:00 IST**: Morning Kickoff\n"
            "• **16:30 IST**: Afternoon Group Check-in\n"
            "• **00:00 IST**: Midnight Podium Results\n\n"
            "_The bot will stay silent in all other channels unless directly prompted with a command._"
        ),
        color=0x2ECC71
    )
    await interaction.response.send_message(embed=embed)


@admin_group.command(name="set_role", description="Set the Winter Arc role to ping during daily scheduled announcements.")
@app_commands.describe(role="Select the role to ping (e.g. @Winter Arc)")
@app_commands.default_permissions(administrator=True)
async def admin_set_role(interaction: discord.Interaction, role: discord.Role):
    if not interaction.guild:
        await interaction.response.send_message("This command must be run within a server.", ephemeral=True)
        return

    db.set_server_role(interaction.guild.id, role.id)
    embed = discord.Embed(
        title="✅ Ping Role Configured",
        description=f"Scheduled announcements in the dedicated channel will now mention {role.mention}.\nUsers who run `/enroll` will also automatically receive this role.",
        color=0x2ECC71
    )
    await interaction.response.send_message(embed=embed)


@admin_group.command(name="overview", description="Server admin dashboard: inspect channel, role, enrolled members, and tasks.")
@app_commands.default_permissions(administrator=True)
async def admin_overview(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("This command must be run within a server.", ephemeral=True)
        return

    settings = db.get_server_settings(interaction.guild.id)
    channel_id = settings.get("channel_id", 0)
    role_id = settings.get("role_id", 0)

    channel = interaction.guild.get_channel(channel_id) if channel_id else None
    role = interaction.guild.get_role(role_id) if role_id else None

    channel_display = channel.mention if channel else "`Not Configured ⚠️` (use `/admin set_channel`)"
    role_display = role.mention if role else "`Not Configured ⚠️` (use `/admin set_role`)"

    enrolled = db.get_enrolled_users()
    today_str = datetime.now(BOT_TZ).strftime("%Y-%m-%d")

    warrior_lines = []
    for u in enrolled:
        prog = db.get_user_daily_progress(u["discord_id"], today_str)
        streak = db.calculate_streak(u["discord_id"], today_str)
        warrior_lines.append(f"• **{u['username']}** — `{prog['total_points']} pts` today | Streak: 🔥 `{streak}d`")

    active_tasks = db.get_active_tasks()
    task_lines = [f"• **{t['name']}**: target `{t['target']} {t['unit']}`, max `{t['max_points']} pts`" for t in active_tasks]

    embed = discord.Embed(
        title="🛡️ Winter Arc Server Overview Dashboard",
        color=0x34495E
    )
    embed.add_field(name="📢 Dedicated Channel", value=channel_display, inline=True)
    embed.add_field(name="🔔 Ping Role", value=role_display, inline=True)
    embed.add_field(name=f"👥 Enrolled Warriors ({len(enrolled)})", value="\n".join(warrior_lines) if warrior_lines else "_No users enrolled yet._", inline=False)
    embed.add_field(name="📋 Active Disciplines", value="\n".join(task_lines) if task_lines else "_No active tasks._", inline=False)
    embed.set_footer(text="Admin controls: /admin set_channel | /admin set_role | /admin task_add")

    await interaction.response.send_message(embed=embed)


@admin_group.command(name="task_add", description="Add a new challenge discipline to the database.")
@app_commands.describe(
    name="Task name (e.g. Plank, Water)",
    target="Daily target amount (e.g. 5)",
    unit="Measurement unit (e.g. minutes, liters, reps)",
    max_points="Maximum points achievable for 100% completion (e.g. 100)",
    description="Optional description of the task"
)
@app_commands.default_permissions(administrator=True)
async def admin_task_add(interaction: discord.Interaction, name: str, target: float, unit: str, max_points: int, description: str = ""):
    if target <= 0 or max_points <= 0:
        await interaction.response.send_message("❌ Target and max_points must be greater than 0.", ephemeral=True)
        return

    task = db.add_task(name=name, target=target, unit=unit, max_points=max_points, description=description)
    embed = discord.Embed(
        title="✅ Task Registered / Updated",
        description=(
            f"**Name**: {task['name']}\n"
            f"**Target**: {task['target']} {task['unit']}\n"
            f"**Max Points**: {task['max_points']}\n"
            f"**Active**: {'Yes' if task['active'] else 'No'}"
        ),
        color=0x2ECC71
    )
    await interaction.response.send_message(embed=embed)


@admin_group.command(name="task_toggle", description="Enable or disable an existing challenge task.")
@app_commands.describe(name="Task name to enable/disable")
@app_commands.autocomplete(name=task_autocomplete)
@app_commands.default_permissions(administrator=True)
async def admin_task_toggle(interaction: discord.Interaction, name: str):
    try:
        task = db.toggle_task(name)
        status_str = "Enabled 🟢" if task["active"] else "Disabled 🔴"
        await interaction.response.send_message(f"Task **{task['name']}** is now **{status_str}**.")
    except ValueError as e:
        await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)


@admin_group.command(name="tasks_list", description="List all challenge tasks in the database.")
@app_commands.default_permissions(administrator=True)
async def admin_tasks_list(interaction: discord.Interaction):
    all_tasks = db.get_all_tasks()
    lines = []
    for t in all_tasks:
        status_icon = "🟢" if t["active"] else "🔴"
        lines.append(f"{status_icon} **{t['name']}**: target `{t['target']} {t['unit']}`, max `{t['max_points']} pts`")

    embed = discord.Embed(
        title="📋 Challenge Tasks Master List",
        description="\n".join(lines) if lines else "_No tasks registered._",
        color=0x3498DB
    )
    await interaction.response.send_message(embed=embed)


bot.tree.add_command(admin_group)


# ==========================================
# Testing & Diagnostics
# ==========================================

@bot.tree.command(name="test_reminder", description="Preview morning, afternoon, or midnight announcements in the dedicated channel.")
@app_commands.describe(reminder_type="Select announcement type to test")
@app_commands.choices(reminder_type=[
    app_commands.Choice(name="Morning Kickoff (05:00)", value="morning"),
    app_commands.Choice(name="Afternoon Group Check-in (16:30)", value="afternoon"),
    app_commands.Choice(name="Midnight Finalization (00:00)", value="midnight"),
])
@app_commands.default_permissions(administrator=True)
async def test_reminder(interaction: discord.Interaction, reminder_type: str):
    await interaction.response.defer(ephemeral=True)
    if not bot.scheduler:
        await interaction.followup.send("Scheduler is not active.", ephemeral=True)
        return

    # Determine destination: dedicated channel if set, otherwise current channel
    channel = interaction.channel
    role_ping = ""
    if interaction.guild:
        ch, ping = bot.scheduler._get_target_channel_and_ping(interaction.guild)
        if ch:
            channel = ch
            role_ping = ping

    if reminder_type == "morning":
        await bot.scheduler.broadcast_morning_kickoff(target_channel=channel, role_ping=role_ping)
        await interaction.followup.send(f"✅ Dispatched Morning Kickoff preview to {channel.mention}.", ephemeral=True)
    elif reminder_type == "afternoon":
        await bot.scheduler.broadcast_afternoon_checkin(target_channel=channel, role_ping=role_ping)
        await interaction.followup.send(f"✅ Dispatched Afternoon Check-in preview to {channel.mention}.", ephemeral=True)
    elif reminder_type == "midnight":
        embed = await bot.scheduler.broadcast_midnight_finalization(target_channel=channel, role_ping=role_ping)
        await interaction.followup.send(f"✅ Dispatched Midnight Podium preview to {channel.mention}.", ephemeral=True)


# ==========================================
# Main Execution
# ==========================================

if __name__ == "__main__":
    if not TOKEN:
        logger.error("❌ ERROR: DISCORD_TOKEN is not set in your .env file!")
        sys.exit(1)

    bot.run(TOKEN)
