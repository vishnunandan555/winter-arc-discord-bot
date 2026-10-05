"""
cogs/admin.py - Server Administration and Diagnostic Slash Commands

Contains administrative controls for Winter Arc:
- Channel & role configuration (/admin set_channel, /admin set_role)
- Server status dashboard (/admin overview)
- Dynamic discipline management (/admin task_add, /admin task_toggle, /admin tasks_list)
- Scheduled broadcast previews (/test_reminder)
"""

from __future__ import annotations

import os
import gc
import logging
import resource
from typing import Any, Optional, Dict, List, Union
from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import BOT_TZ, DB_PATH, LOG_FILE_PATH, LOG_LEVEL_NAME
from ui.views import RobustView, CouncilVotingView
from helpers import (
    task_autocomplete,
    all_tasks_autocomplete,
    unit_autocomplete,
    target_autocomplete,
    max_points_autocomplete,
    dm_target_autocomplete,
    dm_template_autocomplete,
)

logger = logging.getLogger("winter_arc.cogs.admin")


class AdminCog(commands.Cog, name="Admin Commands"):
    """Server administrator controls and task configuration."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        cmd = interaction.command.name if interaction.command else "unknown"
        orig = getattr(error, "original", error)
        if (isinstance(orig, discord.errors.NotFound) and getattr(orig, "code", None) == 10062) or interaction.is_expired():
            logger.warning(f"Admin command '/admin {cmd}' interaction expired or cancelled by Discord. User: {interaction.user}")
            return

        if isinstance(error, app_commands.MissingPermissions):
            logger.warning(f"Admin command '/admin {cmd}' rejected for {interaction.user}: missing administrator permissions.")
            msg = "🚫 You need **Administrator** permissions to execute this command."
        elif isinstance(error, app_commands.CommandOnCooldown):
            logger.info(f"Admin command '/admin {cmd}' rejected for {interaction.user}: on cooldown ({error.retry_after:.1f}s).")
            msg = f"⏳ Command on cooldown. Try again in `{error.retry_after:.1f}s`."
        else:
            logger.error(
                f"Error in admin command '/admin {cmd}' invoked by {interaction.user} (ID: {interaction.user.id}): {error}",
                exc_info=error
            )
            msg = f"❌ An error occurred executing `/admin {cmd}`: `{str(error)[:100]}`"

        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception as send_err:
            logger.warning(f"Could not deliver admin error response to {interaction.user.id}: {send_err}")

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

        try:
            task = db.add_task(name=name, target=target, unit=unit, max_points=max_points, description=description)
        except ValueError as e:
            await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)
            return

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
        task_obj = db.get_task_by_name(name)
        target_name = task_obj["name"] if task_obj else name
        try:
            task = db.toggle_task(target_name)
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

    @admin_group.command(name="grind", description="Manage a member's /grind access and disciplinary status.")
    @app_commands.describe(
        what="Choose whether to block or unlock /grind access",
        member="The member to block or unlock",
        days="Suspension duration in days (applicable only for block, optional)",
        reason="Optional explanation for the action (omitted from message if blank)"
    )
    @app_commands.choices(what=[
        app_commands.Choice(name="block", value="block"),
        app_commands.Choice(name="unlock", value="unlock"),
    ])
    async def admin_grind(
        self,
        interaction: discord.Interaction,
        what: app_commands.Choice[str],
        member: discord.Member,
        days: Optional[int] = None,
        reason: Optional[str] = None
    ):
        if not interaction.guild:
            await interaction.response.send_message("This command must be run within a server.", ephemeral=True)
            return

        if member.bot:
            await interaction.response.send_message("❌ Bots cannot be placed on grind probation.", ephemeral=True)
            return

        settings = db.get_server_settings(interaction.guild.id)
        channel_id = settings.get("channel_id")
        target_channel = interaction.guild.get_channel(channel_id) if channel_id else interaction.channel

        clean_reason = reason.strip() if reason and reason.strip() else None

        if what.value == "block":
            duration_days = days if (days and days > 0) else None
            db.set_grind_probation(member.id, days=duration_days)
            # Strip today's grind points if any
            db.cap_user_grind(member.id)
            # Dismiss any active Council trial for this member
            CouncilVotingView.active_trials.discard(member.id)

            duration_str = f"**Duration**: `{duration_days} day(s)`\n" if duration_days else "**Duration**: `Indefinite (until unlocked)`\n"
            reason_str = f"**Reason**: *{clean_reason}*\n" if clean_reason else ""

            embed = discord.Embed(
                title="🚫 Grind Access Suspended",
                description=(
                    f"{member.mention} has had their `/grind` access suspended by server administration.\n\n"
                    f"{duration_str}"
                    f"{reason_str}\n"
                    "Focus on the iron, the road, and pure discipline."
                ),
                color=0xE74C3C
            )
            embed.set_footer(text="Winter Arc Discipline & Integrity")

            if target_channel:
                await target_channel.send(embed=embed)

            await interaction.response.send_message(
                f"✅ Suspended `/grind` access for {member.mention}." + (f" ({duration_days} days)" if duration_days else " (indefinite)"),
                ephemeral=True
            )

        elif what.value == "unlock":
            db.clear_grind_probation(member.id)

            reason_str = f"**Reason**: *{clean_reason}*\n" if clean_reason else ""

            embed = discord.Embed(
                title="🛡️ Grind Access Restored",
                description=(
                    f"{member.mention}'s `/grind` access has been restored.\n\n"
                    f"{reason_str}\n"
                    "Stay authentic, log true effort, and honor the code."
                ),
                color=0x2ECC71
            )
            embed.set_footer(text="Winter Arc Discipline & Integrity")

            if target_channel:
                await target_channel.send(embed=embed)

            await interaction.response.send_message(
                f"✅ Restored `/grind` access for {member.mention}.",
                ephemeral=True
            )

    @admin_group.command(name="sync", description="Synchronize and deduplicate slash commands.")
    @app_commands.describe(clean="Clear guild-scoped duplicate commands and rely on global commands (default: True)")
    async def admin_sync(self, interaction: discord.Interaction, clean: bool = True):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("❌ This command must be run within a server.", ephemeral=True)
            return

        try:
            if clean:
                self.bot.tree.clear_commands(guild=interaction.guild)
                await self.bot.tree.sync(guild=interaction.guild)
                synced = await self.bot.tree.sync()
                await interaction.followup.send(
                    f"🧹 **Deduplication Complete!**\n"
                    f"Purged guild-level duplicates from **{interaction.guild.name}**.\n"
                    f"Synchronized **{len(synced)}** clean global commands.\n"
                    f"*(Tip: Press `Ctrl + R` in Discord to refresh your client UI.)*",
                    ephemeral=True
                )
            else:
                self.bot.tree.copy_global_to(guild=interaction.guild)
                synced = await self.bot.tree.sync(guild=interaction.guild)
                await self.bot.tree.sync()
                await interaction.followup.send(
                    f"✅ **Guild Slash Command Sync Complete!**\n"
                    f"Synchronized **{len(synced)}** slash commands directly to **{interaction.guild.name}**.",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Failed to sync slash commands via /admin sync: {e}", exc_info=e)
            await interaction.followup.send(f"❌ Failed to sync slash commands: {e}", ephemeral=True)

    # ==========================================
    # Diagnostic & Testing Command
    # ==========================================

    @app_commands.command(name="test_reminder", description="Admin: Preview scheduled announcements or DMs.")
    @app_commands.describe(reminder_type="Select announcement type to test")
    @app_commands.choices(reminder_type=[
        app_commands.Choice(name="Morning Kickoff (05:00 Channel)", value="morning"),
        app_commands.Choice(name="Afternoon Group Check-in (16:30 Channel)", value="afternoon"),
        app_commands.Choice(name="Evening Streak Alert (21:00 Channel)", value="evening"),
        app_commands.Choice(name="Sunday State of the Pack (20:00 Channel)", value="sunday"),
        app_commands.Choice(name="Midnight Finalization (00:00 Channel)", value="midnight"),
        app_commands.Choice(name="Phase Conclusion Ceremony (Channel)", value="phase_ceremony"),
        app_commands.Choice(name="Personal Morning Briefing (Direct DM)", value="morning_dm"),
        app_commands.Choice(name="Personal Evening Streak Alert (Direct DM)", value="evening_dm"),
        app_commands.Choice(name="Reactive Groq Observation (Follow-up Nudge)", value="groq_nudge"),
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

        user_streak = db.calculate_streak(interaction.user.id)
        user_history = db.get_user_history(interaction.user.id, days=5)
        user_logs = db.get_user_recent_logs(interaction.user.id, limit=3)
        user_grinds = db.get_user_recent_grinds(interaction.user.id, limit=2)
        tester_context = {
            "username": interaction.user.display_name,
            "streak": user_streak,
            "recent_logs": user_logs,
            "recent_grinds": user_grinds,
        }

        if reminder_type == "morning":
            await scheduler.broadcast_morning_kickoff(
                target_channel=channel,
                role_ping=role_ping,
                user_context=tester_context,
                recent_history=user_history
            )
            await interaction.followup.send(f"✅ Dispatched Morning Kickoff preview with dynamic AI quote to {channel.mention}.", ephemeral=True)
        elif reminder_type == "afternoon":
            await scheduler.broadcast_afternoon_checkin(
                target_channel=channel,
                role_ping=role_ping,
                user_context=tester_context,
                recent_history=user_history
            )
            await interaction.followup.send(f"✅ Dispatched Afternoon Check-in preview with dynamic AI quote to {channel.mention}.", ephemeral=True)
        elif reminder_type == "evening":
            await scheduler.broadcast_evening_checkin(
                target_channel=channel,
                role_ping=role_ping,
                user_context=tester_context,
                recent_history=user_history
            )
            await interaction.followup.send(f"✅ Dispatched Evening Streak Alert preview with dynamic AI quote to {channel.mention}.", ephemeral=True)
        elif reminder_type == "sunday":
            await scheduler.broadcast_sunday_state_of_the_pack(target_channel=channel, role_ping=role_ping)
            await interaction.followup.send(f"✅ Dispatched Sunday State of the Pack preview to {channel.mention}.", ephemeral=True)
        elif reminder_type == "midnight":
            await scheduler.broadcast_midnight_finalization(target_channel=channel, role_ping=role_ping)
            await interaction.followup.send(f"✅ Dispatched Midnight Podium preview to {channel.mention}.", ephemeral=True)
        elif reminder_type == "phase_ceremony":
            from phases import get_current_phase
            curr_phase = get_current_phase()
            await scheduler.broadcast_phase_conclusion(curr_phase, target_channel=channel, role_ping=role_ping)
            await interaction.followup.send(f"✅ Dispatched Phase Conclusion Ceremony for **{curr_phase['name']}** to {channel.mention}.", ephemeral=True)
        elif reminder_type == "morning_dm":
            from ui.embeds import build_dm_morning_embed
            from config import BOT_TZ
            from ai import gemini_service
            active_tasks = db.get_active_tasks()
            today_str = datetime.now(BOT_TZ).strftime("%A, %B %d, %Y")
            quote = ""
            try:
                quote = await gemini_service.generate_reminder_motivation(
                    reminder_type="morning",
                    user_context=tester_context,
                    recent_history=user_history
                )
            except Exception as e:
                logger.debug(f"Could not generate test morning DM quote: {e}")

            dm_embed = build_dm_morning_embed(active_tasks, user_streak, today_str, quote=quote)
            try:
                await interaction.user.send(embed=dm_embed)
                await interaction.followup.send("✅ Dispatched Morning Briefing DM preview with dynamic AI quote to your inbox.", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send("❌ Could not send DM. Please allow direct messages from server members.", ephemeral=True)
        elif reminder_type == "evening_dm":
            from ui.embeds import build_dm_evening_embed
            from config import BOT_TZ
            from ai import gemini_service
            today_str = datetime.now(BOT_TZ).strftime("%Y-%m-%d")
            prog = db.get_user_daily_progress(interaction.user.id, today_str)
            shield_status = db.get_user_shield_status(interaction.user.id)
            quote = ""
            try:
                tester_context["today_points"] = prog.get("total_points", 0)
                quote = await gemini_service.generate_reminder_motivation(
                    reminder_type="evening",
                    user_context=tester_context,
                    recent_history=user_history
                )
            except Exception as e:
                logger.debug(f"Could not generate test evening DM quote: {e}")

            dm_embed = build_dm_evening_embed(interaction.user, prog, user_streak, shield_status, quote=quote)
            try:
                await interaction.user.send(embed=dm_embed)
                await interaction.followup.send("✅ Dispatched Evening Streak Alert DM preview with dynamic AI quote to your inbox.", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send("❌ Could not send DM. Please allow direct messages from server members.", ephemeral=True)
        elif reminder_type == "groq_nudge":
            from ai import groq_service
            await interaction.followup.send("✅ Simulating reactive accountability nudge...", ephemeral=True)
            await groq_service.dispatch_channel_nudge(
                channel=channel,
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
                command_name="today",
                extra_info="Simulated from /test_reminder",
                force=True
            )

    @app_commands.command(name="nuke", description="Purge all messages in this channel (Server Owner only).")
    @app_commands.guild_only()
    async def nuke(self, interaction: discord.Interaction):
        """Purges all messages in the current channel with owner-only button confirmation."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command must be run within a server.", ephemeral=True)
            return

        if interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message(
                "🚫 **Permission Denied**: Only the **Server Owner** can execute the `/nuke` command.",
                ephemeral=True
            )
            return

        bot_perms = interaction.channel.permissions_for(interaction.guild.me)
        if not bot_perms.manage_messages:
            await interaction.response.send_message(
                "❌ **Missing Bot Permission**: The bot needs the **Manage Messages** permission in this channel to delete messages.\n\n"
                "👉 Please enable **Manage Messages** for the bot's role in Server Settings -> Roles or Channel Permissions.",
                ephemeral=True
            )
            return

        from ui.views import NukeConfirmView
        from helpers import auto_dismiss_ephemeral
        import asyncio

        msg_text = (
            "⚠️ **Are you sure you want to nuke this channel?**\n"
            "All messages in this channel will be permanently deleted."
        )
        embed = discord.Embed()
        embed.set_image(url="https://media.tenor.com/UbtVks4zby0AAAAC/ghost.gif")
        view = NukeConfirmView(owner_id=interaction.guild.owner_id)
        await interaction.response.send_message(content=msg_text, embed=embed, view=view, ephemeral=True)
        asyncio.create_task(auto_dismiss_ephemeral(interaction, delay=60))

    @admin_group.command(name="health", description="Inspect server memory, database footprint, and host resources.")
    async def admin_health(self, interaction: discord.Interaction):
        """Displays real-time memory usage (RSS), database file sizes, and allows manual GC compaction."""
        metrics = get_system_health_metrics(self.bot)
        embed = build_health_embed(metrics)
        view = HealthView(self.bot)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @admin_group.command(name="dm", description="Privately send a template or announcement to a member or the entire server.")
    @app_commands.describe(
        target="Choose 'all' to broadcast to everyone, or select/mention a specific member",
        message="Select a pre-configured template (or type a custom message)",
        extra_note="Optional extra note to append to the message"
    )
    @app_commands.autocomplete(
        target=dm_target_autocomplete,
        message=dm_template_autocomplete
    )
    async def admin_dm(
        self,
        interaction: discord.Interaction,
        target: str,
        message: str,
        extra_note: Optional[str] = None
    ):
        """Sends a private message to a specific member or all server members using selectable templates."""
        if not interaction.guild:
            await interaction.response.send_message("This command must be run within a server.", ephemeral=True)
            return

        from config import DEFAULT_CHANNEL_ID
        import asyncio
        import re

        try:
            from dm_templates import build_message_from_template, DM_TEMPLATES
        except ImportError:
            DM_TEMPLATES = {}

            def build_message_from_template(tmpl_key, username, ch_id, extra_text=None):
                embed = discord.Embed(
                    title="📩 Message from Winter Arc Staff",
                    description=tmpl_key,
                    color=0x3498DB
                )
                if extra_text:
                    embed.description += f"\n\n{extra_text}"
                embed.set_footer(text="Winter Arc 2026")
                return embed

        await interaction.response.defer(ephemeral=True)

        settings = db.get_server_settings(interaction.guild.id)
        channel_id = settings.get("channel_id") or DEFAULT_CHANNEL_ID

        clean_target = target.strip()
        template_name = DM_TEMPLATES.get(message, {}).get("name", "Custom Message")

        # Case 1: Send to ALL members
        if clean_target.lower() == "all":
            members = [m for m in interaction.guild.members if not m.bot]
            if len(members) <= 1:
                try:
                    members = [m async for m in interaction.guild.fetch_members(limit=None) if not m.bot]
                except Exception as e:
                    logger.warning(f"Could not fetch full member list with fetch_members: {e}")

            if not members:
                await interaction.followup.send("❌ No human server members found to message.", ephemeral=True)
                return

            await interaction.followup.send(
                f"🚀 **Initiating DM Broadcast to {len(members)} server members...**\n"
                f"• Template: **{template_name}**\n"
                "• Pacing: Safe rate-limiting active (~1.5s per member).\n"
                "• A completion summary will be sent to your DMs when finished.",
                ephemeral=True
            )

            sent_count = 0
            closed_dms = 0
            failed_count = 0

            logger.info(f"Admin {interaction.user} initiated DM broadcast ('{message}') to {len(members)} member(s).")

            for member in members:
                if member.bot:
                    continue
                try:
                    embed = build_message_from_template(message, member.display_name, channel_id, extra_text=extra_note)
                    await member.send(embed=embed)
                    sent_count += 1
                    logger.info(f"Delivered DM to {member.display_name} ({member.id})")
                except discord.Forbidden:
                    closed_dms += 1
                    logger.debug(f"Cannot deliver DM to {member.display_name} (DMs closed)")
                except Exception as e:
                    failed_count += 1
                    logger.warning(f"Failed to deliver DM to {member.display_name}: {e}")

                await asyncio.sleep(1.5)

            summary_msg = (
                f"🏁 **Winter Arc DM Broadcast Completed!**\n\n"
                f"• 📋 **Template**: {template_name}\n"
                f"• 📨 **Delivered to Inbox**: **{sent_count}** members\n"
                f"• 🔒 **DMs Disabled/Closed**: **{closed_dms}** members\n"
                + (f"• ⚠️ **Errors**: **{failed_count}**\n" if failed_count > 0 else "")
                + f"• 👥 **Total Processed**: **{len(members)}** members"
            )

            try:
                await interaction.user.send(summary_msg)
            except Exception:
                logger.info("Admin has DMs closed; could not deliver final summary DM.")
            return

        # Case 2: Specific member(s) target
        resolved_members: dict = {}

        # 1. Search for all numeric IDs in clean_target
        id_matches = re.findall(r'\b\d{15,21}\b|\b\d+\b', clean_target)
        for id_str in id_matches:
            uid = int(id_str)
            m = interaction.guild.get_member(uid)
            if not m:
                try:
                    m = await interaction.guild.fetch_member(uid)
                except Exception:
                    m = None
            if not m:
                try:
                    m = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
                except Exception:
                    m = None
            if m and not getattr(m, "bot", False):
                resolved_members[m.id] = m

        # 2. Search for comma-separated usernames or display names
        tokens = [t.strip().lstrip("@") for t in re.split(r'[,]+', clean_target) if t.strip()]
        for token in tokens:
            needle = token.lower()
            if not needle:
                continue
            for m in interaction.guild.members:
                if not m.bot and (m.name.lower() == needle or m.display_name.lower() == needle):
                    resolved_members[m.id] = m
                    break

        if not resolved_members:
            await interaction.followup.send(
                f"❌ Could not find any valid server members matching `{clean_target}`.\n"
                "Please select members from the autocomplete list or mention them (e.g. `@user1, @user2`).",
                ephemeral=True
            )
            return

        # Deliver to all resolved members
        sent_count = 0
        closed_dms = []
        failed_count = 0

        for target_member in resolved_members.values():
            try:
                embed = build_message_from_template(message, target_member.display_name, channel_id, extra_text=extra_note)
                await target_member.send(embed=embed)
                sent_count += 1
                logger.info(f"Delivered DM to {target_member.display_name} ({target_member.id})")
            except discord.Forbidden:
                closed_dms.append(target_member.display_name)
            except Exception as e:
                failed_count += 1
                logger.warning(f"Failed to deliver DM to {target_member.id}: {e}")
            if len(resolved_members) > 2:
                await asyncio.sleep(1.0)

        # Build clean confirmation response
        recipients_display = ", ".join(str(getattr(m, "mention", f"<@{m.id}>")) for m in resolved_members.values())
        if len(resolved_members) == 1:
            single_m = list(resolved_members.values())[0]
            single_mention = str(getattr(single_m, "mention", f"<@{single_m.id}>"))
            if closed_dms:
                resp_text = f"❌ Could not deliver DM. **{single_m.display_name}** has direct messages disabled from server members."
            elif sent_count > 0:
                resp_text = (
                    f"✅ **Private DM Delivered!**\n"
                    f"• Recipient: {single_mention} (`{single_m.display_name}`)\n"
                    f"• Template: **{template_name}**"
                )
            else:
                resp_text = f"❌ Failed to deliver message to {single_mention}."
        else:
            lines = [
                f"✅ **Private DMs Delivered to {sent_count}/{len(resolved_members)} Selected Members!**",
                f"• Template: **{template_name}**",
                f"• Selected Recipients: {recipients_display}",
            ]
            if closed_dms:
                lines.append(f"• ⚠️ Closed DMs ({len(closed_dms)}): {', '.join(closed_dms)}")
            if failed_count:
                lines.append(f"• ❌ Failed: {failed_count}")
            resp_text = "\n".join(lines)

        from helpers import auto_dismiss_ephemeral
        msg = await interaction.followup.send(resp_text, ephemeral=True)
        asyncio.create_task(auto_dismiss_ephemeral(interaction, delay=60, message=msg))


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

    log_size_kb = 0.0
    if os.path.exists(LOG_FILE_PATH):
        log_size_kb = round(os.path.getsize(LOG_FILE_PATH) / 1024.0, 1)

    return {
        "ram_mb": ram_mb,
        "db_size_kb": db_size_kb,
        "wal_size_kb": wal_size_kb,
        "log_size_kb": log_size_kb,
        "log_level": LOG_LEVEL_NAME,
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
        f"📜 **Active Log File**: **{metrics['log_size_kb']} KB** *(Level: `{metrics['log_level']}`)*\n"
        f"⚡ **Gateway Latency**: **{metrics['latency_ms']} ms**\n"
        f"⏱️ **Bot Uptime**: **{metrics['uptime']}**\n"
        f"👥 **Enrolled Warriors**: **{metrics['enrolled_count']}**\n\n"
        "🛡️ *Optimizations active: SQLite ~2MB cache cap, message cache 100, AI client singletons, rotating logs.*"
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


class HealthView(RobustView):
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
