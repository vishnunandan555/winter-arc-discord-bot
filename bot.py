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


def make_progress_bar(current: float, target: float, length: int = 10) -> str:
    if target <= 0:
        return "🟩" * length
    ratio = min(max(current / target, 0.0), 1.0)
    filled = int(round(ratio * length))
    empty = length - filled
    return "🟩" * filled + "⬜" * empty


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

        self.scheduler = WinterArcScheduler(self)
        self.scheduler.start()

        if TEST_GUILD_ID and TEST_GUILD_ID.strip().isdigit():
            guild = discord.Object(id=int(TEST_GUILD_ID.strip()))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(f"Slash commands synchronized instantaneously to Test Guild: {TEST_GUILD_ID}")

        await self.tree.sync()
        logger.info("Slash commands synchronized globally.")

    async def on_ready(self):
        logger.info(f"Logged in successfully as {self.user} (ID: {self.user.id})")
        activity = discord.Activity(type=discord.ActivityType.watching, name="the Winter Arc | /today")
        await self.change_presence(status=discord.Status.online, activity=activity)

        # Instant guild sync so commands appear immediately across all servers
        for guild in self.guilds:
            try:
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logger.info(f"⚡ Instant-synced {len(synced)} slash commands to server: '{guild.name}' (ID: {guild.id})")
            except Exception as e:
                logger.warning(f"Could not sync to guild '{guild.name}' ({guild.id}): {e}")


bot = WinterArcBot()


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


# ==========================================
# Enrollment & Core User Commands
# ==========================================

@bot.tree.command(name="enroll", description="Enroll in the Winter Arc challenge and receive the warrior role.")
async def enroll(interaction: discord.Interaction):
    is_already = db.is_user_enrolled(interaction.user.id)
    user_record = db.enroll_user(interaction.user.id, interaction.user.name)

    # Attempt to assign the configured Winter Arc role
    role_msg = ""
    if interaction.guild:
        settings = db.get_server_settings(interaction.guild.id)
        role_id = settings.get("role_id", 0)
        if role_id:
            role = interaction.guild.get_role(role_id)
            if role and isinstance(interaction.user, discord.Member):
                try:
                    await interaction.user.add_roles(role)
                    role_msg = f"\n🛡️ Added role: **{role.name}**"
                except discord.Forbidden:
                    role_msg = f"\n⚠️ *(Could not assign {role.name} role — check bot role hierarchy)*"

    active_tasks = db.get_active_tasks()
    task_lines = [f"• **{t['name']}**: `{t['target']} {t['unit']}` ({t['max_points']} pts)" for t in active_tasks]

    title = "⚔️ Enrolled in Winter Arc!" if not is_already else "⚔️ Enrollment Re-activated!"
    embed = discord.Embed(
        title=title,
        description=(
            f"Welcome to the brotherhood of discipline, **{interaction.user.display_name}**.{role_msg}\n\n"
            "**The Ground Rules:**\n"
            "• Complete your daily targets every day.\n"
            "• Points are capped to prevent cheating — focus on consistency.\n"
            "• Check in at 05:00 and 16:30; day results lock in at 00:00 IST.\n"
            "• Use **/log** to record activity and **/today** to check progress."
        ),
        color=0x2ECC71
    )
    embed.add_field(name="📋 Daily Challenge Disciplines", value="\n".join(task_lines) if task_lines else "None configured.", inline=False)
    embed.set_footer(text="Your journey begins now. Lock in.")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="leave_arc", description="Unenroll from the Winter Arc challenge.")
async def leave_arc(interaction: discord.Interaction):
    if not db.is_user_enrolled(interaction.user.id):
        await interaction.response.send_message("You are not currently enrolled in Winter Arc.", ephemeral=True)
        return

    db.unenroll_user(interaction.user.id)

    # Remove role if possible
    if interaction.guild:
        settings = db.get_server_settings(interaction.guild.id)
        role_id = settings.get("role_id", 0)
        if role_id:
            role = interaction.guild.get_role(role_id)
            if role and isinstance(interaction.user, discord.Member):
                try:
                    await interaction.user.remove_roles(role)
                except Exception:
                    pass

    embed = discord.Embed(
        title="🏳️ Unenrolled from Winter Arc",
        description=f"{interaction.user.mention} has stepped away from the Winter Arc.\nYour historical data is preserved. Run `/enroll` anytime to rejoin.",
        color=0x7F8C8D
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="ping", description="Check whether Winter Arc bot is online and measure gateway latency.")
async def ping(interaction: discord.Interaction):
    latency_ms = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Winter Arc is operational.\n**Gateway Latency**: `{latency_ms} ms`\n**Timezone**: `{BOT_TZ}`",
        color=0x2ECC71
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="help", description="View the Winter Arc command guide, schedule, and rules.")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="❄️ Winter Arc — Command Manual",
        description=(
            "**Discipline is Destiny.** Welcome to the Winter Arc accountability bot.\n"
            "Track daily workout disciplines, earn capped points, build streaks, and stay accountable.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0x3498DB
    )

    embed.add_field(
        name="🛡️ Enrollment",
        value=(
            "• **/enroll** — Join the Winter Arc challenge and receive the warrior role.\n"
            "• **/leave_arc** — Step away and unenroll from the challenge."
        ),
        inline=False
    )

    embed.add_field(
        name="⚔️ Daily Workout Tracking (Enrolled Warriors)",
        value=(
            "• **/today** — View your daily targets, progress bars (`🟩🟩⬜`), points, and streak.\n"
            "• **/log** `task` `amount` — Record reps or km completed (e.g. `/log Push-ups 30`).\n"
            "• **/profile** — View your warrior profile card, streak, and joined date.\n"
            "• **/history** — Inspect your daily point history over the past 7 days.\n"
            "• **/stats** `[member]` — View lifetime totals, all-time volume, and perfect days."
        ),
        inline=False
    )

    embed.add_field(
        name="🏆 Standings & Health",
        value=(
            "• **/leaderboard** `[day | month]` — View daily or monthly podium rankings.\n"
            "• **/ping** — Check bot status and gateway latency."
        ),
        inline=False
    )

    embed.add_field(
        name="⚙️ Server Admin Controls (Requires Administrator)",
        value=(
            "• **/admin overview** — Complete dashboard of channel, role, enrolled warriors & disciplines.\n"
            "• **/admin set_channel** `channel` — Set dedicated channel for scheduled broadcasts.\n"
            "• **/admin set_role** `role` — Set role to ping for announcements & auto-role on `/enroll`.\n"
            "• **/admin task_add** — Dynamically register a new discipline.\n"
            "• **/admin task_toggle** — Enable or disable an existing discipline.\n"
            "• **/admin tasks_list** — List all registered tasks.\n"
            "• **/test_reminder** `type` — Preview morning, afternoon, or midnight posts."
        ),
        inline=False
    )

    embed.add_field(
        name="⏰ Daily Schedule (Asia/Kolkata IST)",
        value=(
            "• **05:00 IST** — 🌅 Morning Kickoff (Daily targets & motivation)\n"
            "• **16:30 IST** — ⏰ Afternoon Group Check-in (Standings check)\n"
            "• **00:00 IST** — 🌙 Midnight Finalization (Day locks & podium announced)"
        ),
        inline=False
    )

    embed.set_footer(text="Tip: Automated messages only post in the dedicated channel set by /admin set_channel.")
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

    task_icons = {"push-ups": "💪", "pull-ups": "🧗", "squats": "🦵", "running": "🏃"}

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
    embed.set_footer(text="Record reps with /log | View rankings with /leaderboard")
    await interaction.response.send_message(embed=embed)


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


@bot.tree.command(name="leaderboard", description="View daily or monthly Winter Arc leaderboards.")
@app_commands.describe(period="Choose time period: day or month")
@app_commands.choices(period=[
    app_commands.Choice(name="Daily (Today)", value="day"),
    app_commands.Choice(name="Monthly (Current Month)", value="month"),
])
async def leaderboard(interaction: discord.Interaction, period: str = "day"):
    now = datetime.now(BOT_TZ)

    if period == "day":
        today_str = now.strftime("%Y-%m-%d")
        display_title = f"🏆 DAILY LEADERBOARD — {now.strftime('%B %d, %Y').upper()}"
        data = db.get_daily_leaderboard(today_str)
        medals = ["🥇", "🥈", "🥉"]

        lines = []
        for idx, entry in enumerate(data):
            medal = medals[idx] if idx < 3 else f"`#{idx+1}`"
            pct = int(entry["completion_rate"] * 100)
            star = " ⭐" if entry["perfect_day"] else ""
            lines.append(f"{medal} **{entry['username']}** — **{entry['points']} pts** ({pct}%){star}")

        if not lines:
            lines.append("_No activity logged today yet. Use `/enroll` and `/log` to be first!_")

        embed = discord.Embed(title=display_title, description="\n".join(lines), color=0xF1C40F)
        embed.set_footer(text="Finalizes automatically at 00:00 IST.")
        await interaction.response.send_message(embed=embed)

    else:
        month_name = now.strftime("%B %Y").upper()
        display_title = f"🏆 MONTHLY LEADERBOARD — {month_name}"
        data = db.get_monthly_leaderboard(now.year, now.month)
        medals = ["🥇", "🥈", "🥉"]

        lines = []
        for idx, entry in enumerate(data):
            medal = medals[idx] if idx < 3 else f"`#{idx+1}`"
            lines.append(
                f"{medal} **{entry['username']}** — **{entry['total_points']:,} pts** "
                f"({entry['perfect_days']} perfect days, {entry['recorded_days']} active days)"
            )

        if not lines:
            lines.append("_No monthly records found yet._")

        embed = discord.Embed(title=display_title, description="\n".join(lines), color=0xE67E22)
        embed.set_footer(text="Accumulated points for the calendar month.")
        await interaction.response.send_message(embed=embed)


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
        title=f"📈 WARRIOR STATS — {target_user.display_name}",
        color=0x9B59B6
    )
    embed.add_field(
        name="Overview",
        value=(
            f"🔥 **Current Streak**: `{data.get('current_streak', 0)} days`\n"
            f"⭐ **Perfect Days**: `{data.get('perfect_days', 0)} days`\n"
            f"📅 **Active Days**: `{data.get('active_days', 0)} days`\n"
            f"💎 **Lifetime Points**: `{data.get('lifetime_points', 0):,} pts`"
        ),
        inline=False
    )

    volume_lines = []
    for t in data.get("task_totals", []):
        vol = int(t["total_volume"]) if t["total_volume"].is_integer() else t["total_volume"]
        volume_lines.append(f"• **{t['name']}**: {vol:,} {t['unit']}")

    if volume_lines:
        embed.add_field(name="🏋️ Lifetime Volume", value="\n".join(volume_lines), inline=False)

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
    embed.set_footer(text="Winter Arc • Discipline is Destiny")
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
