"""
cogs/admin.py - Server Administration and Diagnostic Slash Commands

Contains administrative controls for Winter Arc:
- Channel & role configuration (/admin set_channel, /admin set_role)
- Server status dashboard (/admin overview)
- Dynamic discipline management (/admin task_add, /admin task_toggle, /admin tasks_list)
- Scheduled broadcast previews (/test_reminder)
"""

import os
import gc
import logging
import resource
from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import BOT_TZ, DB_PATH
from helpers import (
    task_autocomplete,
    all_tasks_autocomplete,
    unit_autocomplete,
    target_autocomplete,
    max_points_autocomplete,
)

logger = logging.getLogger("winter_arc.cogs.admin")


class AdminCog(commands.Cog, name="Admin Commands"):
    """Server administrator controls and task configuration."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    admin_group = app_commands.Group(
        name="admin",
        description="Winter Arc server administration (Requires Administrator).",
        default_permissions=discord.Permissions(administrator=True)
    )

    @admin_group.command(name="set_channel", description="Set the dedicated channel for scheduled announcements.")
    @app_commands.describe(channel="Select the dedicated Winter Arc text channel")
    async def admin_set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
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

    @admin_group.command(name="set_role", description="Set the Winter Arc role to ping during announcements.")
    @app_commands.describe(role="Select the role to ping (e.g. @Winter Arc)")
    async def admin_set_role(self, interaction: discord.Interaction, role: discord.Role):
        if not interaction.guild:
            await interaction.response.send_message("This command must be run within a server.", ephemeral=True)
            return

        db.set_server_role(interaction.guild.id, role.id)
        embed = discord.Embed(
            title="✅ Ping Role Configured",
            description=(
                f"Scheduled announcements in the dedicated channel will now mention {role.mention}.\n"
                "Users who run `/enroll` will also automatically receive this role."
            ),
            color=0x2ECC71
        )
        await interaction.response.send_message(embed=embed)

    @admin_group.command(name="overview", description="View server configuration, enrolled members, and disciplines.")
    async def admin_overview(self, interaction: discord.Interaction):
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

        desc = (
            "**Server Configuration**\n"
            f"• 📢 **Dedicated Channel**: {channel_display}\n"
            f"• 🔔 **Ping Role**: {role_display}\n\n"
            f"**Enrolled Members ({len(enrolled)})**\n"
            + ("\n".join(warrior_lines) if warrior_lines else "_No members enrolled yet._")
            + "\n\n**Active Disciplines**\n"
            + ("\n".join(task_lines) if task_lines else "_No active tasks._")
        )

        embed = discord.Embed(
            title="⚙️ Winter Arc — Server Overview",
            description=desc,
            color=0x34495E
        )
        embed.set_footer(text="Admin: /admin set_channel • /admin set_role • /admin task_add")
        await interaction.response.send_message(embed=embed)

    @admin_group.command(name="task_add", description="Add a new challenge discipline to the database.")
    @app_commands.describe(
        name="Task name (e.g. Plank, Water)",
        target="Daily target amount (e.g. 5)",
        unit="Measurement unit (e.g. minutes, liters, reps)",
        max_points="Maximum points achievable for 100% completion (e.g. 100)",
        description="Optional description of the task"
    )
    @app_commands.autocomplete(
        unit=unit_autocomplete,
        target=target_autocomplete,
        max_points=max_points_autocomplete
    )
    async def admin_task_add(self, interaction: discord.Interaction, name: str, target: float, unit: str, max_points: int, description: str = ""):
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
    @app_commands.autocomplete(name=all_tasks_autocomplete)
    async def admin_task_toggle(self, interaction: discord.Interaction, name: str):
        try:
            task = db.toggle_task(name)
            status_str = "Enabled 🟢" if task["active"] else "Disabled 🔴"
            await interaction.response.send_message(f"Task **{task['name']}** is now **{status_str}**.")
        except ValueError as e:
            await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)

    @admin_group.command(name="tasks_list", description="List all challenge disciplines.")
    async def admin_tasks_list(self, interaction: discord.Interaction):
        all_tasks = db.get_all_tasks()
        lines = []
        for t in all_tasks:
            status_icon = "🟢" if t["active"] else "🔴"
            lines.append(f"{status_icon} **{t['name']}**: target `{t['target']} {t['unit']}`, max `{t['max_points']} pts`")

        embed = discord.Embed(
            title="📋 Winter Arc — Disciplines",
            description="\n".join(lines) if lines else "_No tasks registered._",
            color=0x3498DB
        )
        await interaction.response.send_message(embed=embed)

    # ==========================================
    # Diagnostic & Testing Command
    # ==========================================

    @app_commands.command(name="test_reminder", description="Admin: Preview scheduled announcements or DMs.")
    @app_commands.describe(reminder_type="Select announcement type to test")
    @app_commands.choices(reminder_type=[
        app_commands.Choice(name="Morning Kickoff (05:00 Channel)", value="morning"),
        app_commands.Choice(name="Afternoon Group Check-in (16:30 Channel)", value="afternoon"),
        app_commands.Choice(name="Sunday State of the Pack (20:00 Channel)", value="sunday"),
        app_commands.Choice(name="Midnight Finalization (00:00 Channel)", value="midnight"),
        app_commands.Choice(name="Personal Morning Briefing (Direct DM)", value="morning_dm"),
        app_commands.Choice(name="Personal Evening Streak Alert (Direct DM)", value="evening_dm"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def test_reminder(self, interaction: discord.Interaction, reminder_type: str):
        await interaction.response.defer(ephemeral=True)
        scheduler = getattr(self.bot, "scheduler", None)
        if not scheduler:
            await interaction.followup.send("Scheduler is not active.", ephemeral=True)
            return

        channel = interaction.channel
        role_ping = ""
        if interaction.guild:
            ch, ping = scheduler._get_target_channel_and_ping(interaction.guild)
            if ch:
                channel = ch
                role_ping = ping

        if reminder_type == "morning":
            await scheduler.broadcast_morning_kickoff(target_channel=channel, role_ping=role_ping)
            await interaction.followup.send(f"✅ Dispatched Morning Kickoff preview to {channel.mention}.", ephemeral=True)
        elif reminder_type == "afternoon":
            await scheduler.broadcast_afternoon_checkin(target_channel=channel, role_ping=role_ping)
            await interaction.followup.send(f"✅ Dispatched Afternoon Check-in preview to {channel.mention}.", ephemeral=True)
        elif reminder_type == "sunday":
            await scheduler.broadcast_sunday_state_of_the_pack(target_channel=channel, role_ping=role_ping)
            await interaction.followup.send(f"✅ Dispatched Sunday State of the Pack preview to {channel.mention}.", ephemeral=True)
        elif reminder_type == "midnight":
            await scheduler.broadcast_midnight_finalization(target_channel=channel, role_ping=role_ping)
            await interaction.followup.send(f"✅ Dispatched Midnight Podium preview to {channel.mention}.", ephemeral=True)
        elif reminder_type == "morning_dm":
            from ui.embeds import build_dm_morning_embed
            from config import BOT_TZ
            active_tasks = db.get_active_tasks()
            today_str = datetime.now(BOT_TZ).strftime("%A, %B %d, %Y")
            streak = db.calculate_streak(interaction.user.id)
            dm_embed = build_dm_morning_embed(active_tasks, streak, today_str)
            try:
                await interaction.user.send(embed=dm_embed)
                await interaction.followup.send("✅ Dispatched Morning Briefing DM directly to your inbox.", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send("❌ Could not send DM. Please allow direct messages from server members.", ephemeral=True)
        elif reminder_type == "evening_dm":
            from ui.embeds import build_dm_evening_embed
            from config import BOT_TZ
            today_str = datetime.now(BOT_TZ).strftime("%Y-%m-%d")
            prog = db.get_user_daily_progress(interaction.user.id, today_str)
            streak = db.calculate_streak(interaction.user.id, today_str)
            shield_status = db.get_user_shield_status(interaction.user.id)
            dm_embed = build_dm_evening_embed(interaction.user, prog, streak, shield_status)
            try:
                await interaction.user.send(embed=dm_embed)
                await interaction.followup.send("✅ Dispatched Evening Streak Alert DM directly to your inbox.", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send("❌ Could not send DM. Please allow direct messages from server members.", ephemeral=True)

    @admin_group.command(name="health", description="Inspect server memory, database footprint, and host resources.")
    async def admin_health(self, interaction: discord.Interaction):
        """Displays real-time memory usage (RSS), database file sizes, and allows manual GC compaction."""
        metrics = get_system_health_metrics(self.bot)
        embed = build_health_embed(metrics)
        view = HealthView(self.bot)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


def get_system_health_metrics(bot: commands.Bot) -> dict:
    """Collects real-time process memory, disk, and bot metrics."""
    try:
        # ru_maxrss on Linux is in kilobytes
        usage_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        ram_mb = round(usage_kb / 1024.0, 2)
    except Exception:
        ram_mb = 0.0

    db_size_kb = 0.0
    wal_size_kb = 0.0
    if os.path.exists(DB_PATH):
        db_size_kb = round(os.path.getsize(DB_PATH) / 1024.0, 1)
    wal_path = f"{DB_PATH}-wal"
    if os.path.exists(wal_path):
        wal_size_kb = round(os.path.getsize(wal_path) / 1024.0, 1)

    uptime_str = "Unknown"
    if hasattr(bot, "start_time") and bot.start_time:
        delta = datetime.now(timezone.utc) - bot.start_time
        hours, rem = divmod(int(delta.total_seconds()), 3600)
        mins, secs = divmod(rem, 60)
        uptime_str = f"{hours}h {mins}m {secs}s"

    enrolled_count = len(db.get_enrolled_users())
    latency_ms = round(bot.latency * 1000, 1) if bot.latency else 0.0

    return {
        "ram_mb": ram_mb,
        "db_size_kb": db_size_kb,
        "wal_size_kb": wal_size_kb,
        "uptime": uptime_str,
        "enrolled_count": enrolled_count,
        "latency_ms": latency_ms,
    }


def build_health_embed(metrics: dict, extra_note: str = "") -> discord.Embed:
    """Builds a diagnostic status card tailored for Wispbyte low-RAM container limits."""
    ram = metrics["ram_mb"]
    ram_pct = int((ram / 512.0) * 100) if ram else 0

    desc = (
        "**Host Environment**: Wispbyte Free Tier (Linux Container)\n\n"
        f"📊 **Memory (RAM RSS)**: **{ram} MB** / ~512 MB ({ram_pct}% container limit)\n"
        f"🗄️ **Database Disk Footprint**: **{metrics['db_size_kb']} KB** *(WAL: {metrics['wal_size_kb']} KB)*\n"
        f"⚡ **Gateway Latency**: **{metrics['latency_ms']} ms**\n"
        f"⏱️ **Bot Uptime**: **{metrics['uptime']}**\n"
        f"👥 **Enrolled Warriors**: **{metrics['enrolled_count']}**\n\n"
        "🛡️ *Optimizations active: SQLite ~2MB cache cap, message cache 100, AI client singletons.*"
    )
    if extra_note:
        desc += f"\n\n{extra_note}"

    embed = discord.Embed(
        title="🖥️ Winter Arc — Server & Memory Health",
        description=desc,
        color=0x2ECC71 if ram < 250 else 0xE67E22
    )
    embed.set_footer(text="Wispbyte Resource Monitor • Click button below to free unused RAM")
    return embed


class HealthView(discord.ui.View):
    """Interactive view allowing administrators to force garbage collection."""
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=180.0)
        self.bot = bot

    @discord.ui.button(label="🧹 Collect GC & Free RAM", style=discord.ButtonStyle.secondary, custom_id="btn_collect_gc")
    async def collect_gc_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        collected = gc.collect()
        metrics = get_system_health_metrics(self.bot)
        embed = build_health_embed(metrics, extra_note=f"✅ Cleaned **{collected}** cyclic references from memory.")
        await interaction.response.edit_message(embed=embed, view=self)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
