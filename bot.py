"""
bot.py - Winter Arc Discord Bot Main Entrypoint

Features:
- Slash commands: /ping, /today, /log, /leaderboard, /stats, /history, /profile, /reminders, /test_reminder
- Admin commands: /admin (task management, channel configuration)
- Interactive buttons for reminder management
- Immediate guild slash-command synchronization for local testing
"""

import os
import sys
import math
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
DAILY_RESULTS_CHANNEL_ID = os.getenv("DAILY_RESULTS_CHANNEL_ID", "0")


def make_progress_bar(current: float, target: float, length: int = 10) -> str:
    """Generates a visual progress bar e.g. [🟩🟩🟩⬜⬜⬜⬜⬜⬜⬜]"""
    if target <= 0:
        return "🟩" * length
    ratio = min(max(current / target, 0.0), 1.0)
    filled = int(round(ratio * length))
    empty = length - filled
    return "🟩" * filled + "⬜" * empty


# ==========================================
# Interactive Views
# ==========================================

class RemindersView(discord.ui.View):
    """Interactive Discord buttons allowing users to toggle reminder settings without typing commands."""

    def __init__(self, discord_id: int):
        super().__init__(timeout=180)
        self.discord_id = discord_id
        self._sync_buttons()

    def _sync_buttons(self):
        user = db.get_user_by_discord_id(self.discord_id)
        morning_on = bool(user["morning_reminder"]) if user else True
        afternoon_on = bool(user["afternoon_reminder"]) if user else True

        self.morning_button.label = f"🌅 05:00 Morning: {'ON' if morning_on else 'OFF'}"
        self.morning_button.style = discord.ButtonStyle.success if morning_on else discord.ButtonStyle.secondary

        self.afternoon_button.label = f"⏰ 16:30 Afternoon: {'ON' if afternoon_on else 'OFF'}"
        self.afternoon_button.style = discord.ButtonStyle.success if afternoon_on else discord.ButtonStyle.secondary

    @discord.ui.button(label="🌅 05:00 Morning: ON", style=discord.ButtonStyle.success, custom_id="btn_toggle_morning")
    async def morning_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.discord_id:
            await interaction.response.send_message("This menu is for another user.", ephemeral=True)
            return

        user = db.get_user_by_discord_id(self.discord_id)
        current = bool(user["morning_reminder"]) if user else True
        db.update_reminder_preferences(self.discord_id, morning=not current)
        self._sync_buttons()

        embed = build_reminders_embed(self.discord_id, interaction.user.name)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⏰ 16:30 Afternoon: ON", style=discord.ButtonStyle.success, custom_id="btn_toggle_afternoon")
    async def afternoon_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.discord_id:
            await interaction.response.send_message("This menu is for another user.", ephemeral=True)
            return

        user = db.get_user_by_discord_id(self.discord_id)
        current = bool(user["afternoon_reminder"]) if user else True
        db.update_reminder_preferences(self.discord_id, afternoon=not current)
        self._sync_buttons()

        embed = build_reminders_embed(self.discord_id, interaction.user.name)
        await interaction.response.edit_message(embed=embed, view=self)


def build_reminders_embed(discord_id: int, username: str) -> discord.Embed:
    user = db.get_or_create_user(discord_id, username)
    m_status = "🟢 Enabled" if user["morning_reminder"] else "🔴 Disabled"
    a_status = "🟢 Enabled" if user["afternoon_reminder"] else "🔴 Disabled"

    embed = discord.Embed(
        title="⚙️ Winter Arc Reminder Settings",
        description="Configure your daily accountability notifications below.\nAll times in **Asia/Kolkata (IST)**.",
        color=0x2ECC71
    )
    embed.add_field(name="🌅 Morning Kickoff (05:00 IST)", value=f"Status: **{m_status}**\nDaily motivation and task targets.", inline=False)
    embed.add_field(name="⏰ Afternoon Check-in (16:30 IST)", value=f"Status: **{a_status}**\nPersonalized progress check and remaining goals.", inline=False)
    embed.set_footer(text="Click the buttons below to toggle your preferences.")
    return embed


# ==========================================
# Discord Client & Command Tree
# ==========================================

class WinterArcBot(discord.Client):
    def __init__(self):
        # Default intents are sufficient for slash commands and DMs
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.scheduler: Optional[WinterArcScheduler] = None

    async def setup_hook(self):
        # 1. Initialize SQLite Database
        db.init_db()
        logger.info("SQLite database initialized and seed tasks confirmed.")

        # 2. Setup Background Scheduler
        res_channel_id = int(DAILY_RESULTS_CHANNEL_ID) if DAILY_RESULTS_CHANNEL_ID and DAILY_RESULTS_CHANNEL_ID.isdigit() else 0
        self.scheduler = WinterArcScheduler(self, results_channel_id=res_channel_id)
        self.scheduler.start()

        # 3. Synchronize Slash Commands
        # If TEST_GUILD_ID is provided, sync immediately to that guild for fast local testing
        if TEST_GUILD_ID and TEST_GUILD_ID.strip().isdigit():
            guild = discord.Object(id=int(TEST_GUILD_ID.strip()))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(f"Slash commands synchronized instantaneously to Test Guild: {TEST_GUILD_ID}")

        # Also sync globally
        await self.tree.sync()
        logger.info("Slash commands synchronized globally.")

    async def on_ready(self):
        logger.info(f"Logged in successfully as {self.user} (ID: {self.user.id})")
        activity = discord.Activity(type=discord.ActivityType.watching, name="the Winter Arc | /today")
        await self.change_presence(status=discord.Status.online, activity=activity)

        # Instant guild sync to all joined servers so commands show up in Discord immediately
        for guild in self.guilds:
            try:
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logger.info(f"⚡ Instant-synced {len(synced)} slash commands to server: '{guild.name}' (ID: {guild.id})")
            except Exception as e:
                logger.warning(f"Could not sync to guild '{guild.name}' ({guild.id}): {e}")


bot = WinterArcBot()


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
# Core Slash Commands
# ==========================================

@bot.tree.command(name="ping", description="Check whether Winter Arc bot is online and measure latency.")
async def ping(interaction: discord.Interaction):
    latency_ms = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Winter Arc is operational.\n**Gateway Latency**: `{latency_ms} ms`\n**Timezone**: `{BOT_TZ}`",
        color=0x2ECC71
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="today", description="View your progress, targets, points, and streak for today.")
@app_commands.describe(member="Optional: View another member's progress")
async def today(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target_user = member or interaction.user
    user_db = db.get_or_create_user(target_user.id, target_user.name)

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

    embed.set_footer(text="Log your activity with /log | Check standings with /leaderboard")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="log", description="Log activity towards a task (e.g. 30 push-ups, 5 km running).")
@app_commands.describe(
    task="Select the task to log",
    amount="Amount completed (e.g. 30 reps or 5 km)"
)
@app_commands.autocomplete(task=task_autocomplete)
async def log_activity_cmd(interaction: discord.Interaction, task: str, amount: float):
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

    # Format response
    cur = int(result["new_total"]) if result["new_total"].is_integer() else result["new_total"]
    tgt = int(result["target"]) if result["target"].is_integer() else result["target"]
    amt = int(amount) if amount.is_integer() else amount

    bar = make_progress_bar(result["new_total"], result["target"], length=10)
    delta_str = f"+{result['points_earned_delta']} pts" if result['points_earned_delta'] > 0 else "Max points already capped"

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
        embed.set_footer(text="🎉 Goal accomplished for this task today! Keep going!")
    else:
        embed.set_footer(text="Keep it up! Use /today to view full progress.")

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
            lines.append("_No activity logged today yet. Be the first with `/log`!_")

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
        embed.set_footer(text="Accumulated points for the entire calendar month.")
        await interaction.response.send_message(embed=embed)


@bot.tree.command(name="stats", description="View all-time statistics, lifetime volume, and records.")
@app_commands.describe(member="Optional: View another member's statistics")
async def stats(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target_user = member or interaction.user
    db.get_or_create_user(target_user.id, target_user.name)

    data = db.get_user_stats(target_user.id)
    if not data:
        await interaction.response.send_message("No profile found for user.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"📈 WARRIOR STATS — {target_user.display_name}",
        color=0x9B59B6
    )
    embed.add_field(
        name="Overview",
        value=(
            f"🔥 **Current Streak**: `{data['current_streak']} days`\n"
            f"⭐ **Perfect Days**: `{data['perfect_days']} days`\n"
            f"📅 **Active Days**: `{data['active_days']} days`\n"
            f"💎 **Lifetime Points**: `{data['lifetime_points']:,} pts`"
        ),
        inline=False
    )

    volume_lines = []
    for t in data["task_totals"]:
        vol = int(t["total_volume"]) if t["total_volume"].is_integer() else t["total_volume"]
        volume_lines.append(f"• **{t['name']}**: {vol:,} {t['unit']}")

    if volume_lines:
        embed.add_field(name="🏋️ Lifetime Volume", value="\n".join(volume_lines), inline=False)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="history", description="View your point history over the past 7 days.")
async def history(interaction: discord.Interaction):
    db.get_or_create_user(interaction.user.id, interaction.user.name)
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


@bot.tree.command(name="reminders", description="Interactive settings to toggle 05:00 Morning and 16:30 Afternoon reminders.")
async def reminders_cmd(interaction: discord.Interaction):
    db.get_or_create_user(interaction.user.id, interaction.user.name)
    embed = build_reminders_embed(interaction.user.id, interaction.user.name)
    view = RemindersView(interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.tree.command(name="profile", description="View your user profile card and settings.")
async def profile(interaction: discord.Interaction):
    user = db.get_or_create_user(interaction.user.id, interaction.user.name)
    streak = db.calculate_streak(interaction.user.id)
    stats_data = db.get_user_stats(interaction.user.id)

    m_status = "ON" if user["morning_reminder"] else "OFF"
    a_status = "ON" if user["afternoon_reminder"] else "OFF"

    embed = discord.Embed(
        title=f"🛡️ Profile — {interaction.user.display_name}",
        color=0x1ABC9C
    )
    if interaction.user.avatar:
        embed.set_thumbnail(url=interaction.user.avatar.url)

    embed.add_field(name="Joined Arc", value=f"`{user['joined_at'][:10]}`", inline=True)
    embed.add_field(name="Current Streak", value=f"🔥 `{streak} days`", inline=True)
    embed.add_field(name="Lifetime Points", value=f"💎 `{stats_data['lifetime_points']:,}`", inline=True)
    embed.add_field(name="Reminders", value=f"05:00: `{m_status}` | 16:30: `{a_status}`", inline=False)
    embed.set_footer(text="Toggle reminders anytime with /reminders")

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="test_reminder", description="Preview and test morning, afternoon, or midnight announcements immediately.")
@app_commands.describe(reminder_type="Select reminder type to test")
@app_commands.choices(reminder_type=[
    app_commands.Choice(name="Morning Kickoff (05:00 preview)", value="morning"),
    app_commands.Choice(name="Afternoon Check-in (16:30 preview)", value="afternoon"),
    app_commands.Choice(name="Midnight Finalization (00:00 preview)", value="midnight"),
])
async def test_reminder(interaction: discord.Interaction, reminder_type: str):
    await interaction.response.defer(ephemeral=True)
    if not bot.scheduler:
        await interaction.followup.send("Scheduler is not running.", ephemeral=True)
        return

    if reminder_type == "morning":
        await bot.scheduler.send_morning_reminder(target_user=interaction.user)
        await interaction.followup.send("✅ Sent you a direct message preview of the **05:00 Morning Kickoff**.", ephemeral=True)
    elif reminder_type == "afternoon":
        await bot.scheduler.send_afternoon_reminder(target_user=interaction.user)
        await interaction.followup.send("✅ Sent you a direct message preview of the **16:30 Afternoon Check-in**.", ephemeral=True)
    elif reminder_type == "midnight":
        embed = await bot.scheduler.run_midnight_job()
        await interaction.followup.send(content="✅ Executed midnight finalization routine. Result embed:", embed=embed, ephemeral=True)


# ==========================================
# Admin Management Commands
# ==========================================

admin_group = app_commands.Group(name="admin", description="Winter Arc administration commands (Requires Administrator).")


@admin_group.command(name="task_add", description="Add a new challenge task to the database.")
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
    active_tasks = db.get_active_tasks()
    lines = []
    for t in active_tasks:
        lines.append(f"• **{t['name']}**: target `{t['target']} {t['unit']}`, max `{t['max_points']} pts` (Active: {bool(t['active'])})")

    embed = discord.Embed(
        title="📋 Challenge Tasks List",
        description="\n".join(lines) if lines else "_No tasks registered._",
        color=0x3498DB
    )
    await interaction.response.send_message(embed=embed)


@admin_group.command(name="set_results_channel", description="Set the channel where 00:00 midnight daily results are posted.")
@app_commands.describe(channel="Select channel for daily results broadcast")
@app_commands.default_permissions(administrator=True)
async def admin_set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if bot.scheduler:
        bot.scheduler.results_channel_id = channel.id
    await interaction.response.send_message(f"✅ Daily results will now be broadcast in {channel.mention}.")


bot.tree.add_command(admin_group)


# ==========================================
# Main Execution
# ==========================================

if __name__ == "__main__":
    if not TOKEN:
        logger.error(
            "\n"
            "==========================================================\n"
            "❌ ERROR: DISCORD_TOKEN is not set in your .env file!\n\n"
            "1. Open .env in your project folder:\n"
            "   /home/vishnunandan555/Projects/winter-arc-bot/.env\n"
            "2. Paste your bot token from the Discord Developer Portal:\n"
            "   DISCORD_TOKEN=your_real_token_here\n"
            "3. Run: python bot.py\n"
            "==========================================================\n"
        )
        sys.exit(1)

    bot.run(TOKEN)
