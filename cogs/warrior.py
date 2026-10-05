"""
cogs/warrior.py - User Slash Commands for Winter Arc Bot

Contains commands for enrolled participants:
- Enrollment lifecycle (/enroll, /leave_arc)
- Daily tracking (/today, /log, /set)
- Profile & progression (/profile, /ranks)
- Competition & history (/leaderboard, /stats, /history)
- General utilities (/help, /ping)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Optional, Dict, List, Union
import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import BOT_TZ, MAX_SINGLE_SET_LIMITS
from helpers import (
    require_enrolled,
    task_autocomplete,
    log_amount_autocomplete,
    set_amount_autocomplete,
    history_days_autocomplete,
    get_or_create_arc_role,
    safe_react,
    format_num,
)
from levels import check_level_up
from ui.embeds import (
    build_today_embed,
    build_tasks_embed,
    build_log_embed,
    format_log_reply,
    build_set_embed,
    format_set_reply,
    build_stats_embed,
    build_history_embed,
    build_profile_embed,
    build_ranks_embed,
    build_help_embed,
    build_daily_leaderboard_embed,
    build_weekly_leaderboard_embed,
    build_monthly_leaderboard_embed,
    build_overall_leaderboard_embed,
    build_shield_status_embed,
    build_shield_automated_info_embed,
    build_shield_activated_embed,
    build_settings_embed,
    build_grind_embed,
    format_grind_reply,
    build_quicklog_embed,
    build_recap_embed,
    build_server_records_embed,
    format_embed_as_text,
    build_streak_consistency_embed,
    build_full_calendar_embed,
    build_quick_streak_embed,
    STREAK_LEGEND_SUBTEXT,
)
from ui.views import (
    LeaderboardView,
    SettingsView,
    HelpView,
    RecapView,
    ServerRecordsView,
    StreakConsistencyView,
    CallCapConfirmView,
    CouncilVotingView,
    COUNCIL_SUMMONED_GIFS,
)
from ai import gemini_service, groq_service
from tips import dispatch_tip

logger = logging.getLogger("winter_arc.cogs.warrior")


class WarriorCog(commands.Cog, name="Warrior Commands"):
    """Core workout tracking, progression, and social commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        cmd = interaction.command.name if interaction.command else "unknown"
        orig = getattr(error, "original", error)
        if (isinstance(orig, discord.errors.NotFound) and getattr(orig, "code", None) == 10062) or interaction.is_expired():
            logger.warning(
                f"Warrior command '/{cmd}' interaction expired or was cancelled by Discord (404 Unknown interaction). User: {interaction.user} (ID: {interaction.user.id})"
            )
            return

        if isinstance(error, app_commands.CommandOnCooldown):
            logger.info(f"Warrior command '/{cmd}' by {interaction.user} rejected: on cooldown ({error.retry_after:.1f}s remaining).")
            msg = f"⏳ You're on cooldown. Try again in `{error.retry_after:.1f}s`."
        elif isinstance(error, app_commands.MissingPermissions):
            logger.warning(f"Warrior command '/{cmd}' by {interaction.user} rejected: missing permissions.")
            msg = "🚫 You do not have permission to execute this command."
        elif isinstance(error, app_commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            logger.warning(f"Warrior command '/{cmd}' cannot execute: bot missing permissions: {missing}")
            msg = f"🚫 I am missing the required permissions to execute this command: `{missing}`."
        elif isinstance(error, app_commands.CheckFailure):
            logger.info(f"Warrior command '/{cmd}' by {interaction.user} rejected: check failed.")
            msg = "❌ Command check failed. If you haven't enrolled yet, use `/enroll` first."
        else:
            logger.error(
                f"Error in warrior command '/{cmd}' for {interaction.user} (ID: {interaction.user.id}): {error}",
                exc_info=error
            )
            msg = "❌ An unexpected error occurred while processing this command."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception as send_err:
            logger.warning(f"Could not deliver error response to user {interaction.user.id} for '/{cmd}': {send_err}")

    # ==========================================
    # Enrollment Commands
    # ==========================================

    @app_commands.command(name="enroll", description="Enroll in the Winter Arc challenge.")
    async def enroll(self, interaction: discord.Interaction):
        logger.info(f"Slash command '/enroll' invoked by {interaction.user} (ID: {interaction.user.id})")
        is_already = db.is_user_enrolled(interaction.user.id)
        db.enroll_user(interaction.user.id, interaction.user.name)

        # Attempt to assign the Winter Arc role
        role_msg = ""
        if interaction.guild and isinstance(interaction.user, discord.Member):
            role = await get_or_create_arc_role(interaction.guild)
            if role:
                try:
                    await interaction.user.add_roles(role)
                    role_msg = f"\n🛡️ Role assigned: **{role.name}**"
                except discord.Forbidden:
                    role_msg = (
                        f"\n⚠️ *(Could not assign {role.name} — please ensure bot's role is higher in Server Settings)*"
                    )
                except Exception as e:
                    role_msg = f"\n⚠️ *(Could not assign role: {e})*"
            else:
                role_msg = "\nℹ️ *(Admin: run `/admin set_role` or grant 'Manage Roles' to auto-assign)*"

        active_tasks = db.get_active_tasks()
        task_lines = [
            f"• **{t['name']}**: `{format_num(t['target'])} {t['unit']}` *(max {t['max_points']} pts)*"
            for t in active_tasks
        ]
        disciplines_block = "\n".join(task_lines) if task_lines else "_No disciplines configured._"

        title = "⚔️ Enrolled in Winter Arc" if not is_already else "⚔️ Enrollment Re-activated"
        embed = discord.Embed(
            title=title,
            description=(
                f"Welcome to the Winter Arc, **{interaction.user.display_name}**.{role_msg}\n\n"
                "**Daily Disciplines (500 pts max)**\n"
                f"{disciplines_block}\n\n"
                "**Core Commands**\n"
                "• `/help` — All available commands & their guides\n"
                "• `/today` — View daily progress & streak\n"
                "• `/log [task] [amount]` — Log completed reps or km\n"
                "• `/set [task] [amount]` — Set count directly *(or 0 to reset)*\n"
                "• `/profile` — View rank & 12-level progression\n"
                "• `/leaderboard` — View daily & overall standings"
            ),
            color=0x2ECC71
        )
        embed.set_footer(text="Day resets at 00:00 IST • Daily standard: 500 points")
        await interaction.response.send_message(embed=embed)
        await safe_react(interaction, "🐺", "⚔️")
        asyncio.create_task(
            dispatch_tip(interaction, interaction.user.id, interaction.user.display_name)
        )

    @app_commands.command(name="leave_arc", description="Unenroll from the Winter Arc challenge.")
    async def leave_arc(self, interaction: discord.Interaction):
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
            description=f"{interaction.user.mention} has unenrolled from Winter Arc.\nYour history is saved. Run `/enroll` anytime to rejoin.",
            color=0x7F8C8D
        )
        embed.set_footer(text="Winter Arc")
        await interaction.response.send_message(embed=embed)
        asyncio.create_task(
            dispatch_tip(interaction, interaction.user.id, interaction.user.display_name)
        )

    # ==========================================
    # Information & Utility Commands
    # ==========================================

    @app_commands.command(name="ping", description="Check bot status and gateway latency.")
    async def ping(self, interaction: discord.Interaction):
        latency_ms = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Winter Arc is operational.\n\n• **Gateway Latency**: `{latency_ms} ms`\n• **Timezone**: `{BOT_TZ}`",
            color=0x2ECC71
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="help", description="View commands, challenge rules, and AI logging manual.")
    async def help_cmd(self, interaction: discord.Interaction):
        embed = build_help_embed(category="overview")
        view = HelpView()
        await interaction.response.send_message(embed=embed, view=view)
        asyncio.create_task(
            dispatch_tip(interaction, interaction.user.id, interaction.user.display_name)
        )

    # ==========================================
    # Daily Tracking Commands
    # ==========================================

    @app_commands.command(name="today", description="View today's progress, points, and streak.")
    @app_commands.describe(member="Optional: View another member's progress")
    async def today(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target_user = member or interaction.user
        logger.info(f"Slash command '/today' invoked by {interaction.user} (target: {target_user.display_name})")

        if target_user.id == interaction.user.id:
            if not await require_enrolled(interaction):
                return
        else:
            if not db.is_user_enrolled(target_user.id):
                await interaction.response.send_message(f"❌ {target_user.display_name} is not enrolled in Winter Arc.", ephemeral=True)
                return

        await interaction.response.defer()

        now = datetime.now(BOT_TZ)
        today_str = now.strftime("%Y-%m-%d")
        date_display = now.strftime("%A, %B %d, %Y")

        progress = db.get_user_daily_progress(target_user.id, today_str)
        streak = db.calculate_streak(target_user.id, today_str)

        embed = build_today_embed(target_user, progress, streak, date_display)
        await interaction.followup.send(embed=embed)

        cmd_out = format_embed_as_text(embed)

        asyncio.create_task(
            dispatch_tip(interaction, target_user.id, target_user.display_name)
        )

        asyncio.create_task(
            groq_service.dispatch_interaction_nudge(
                interaction=interaction,
                user_id=target_user.id,
                user_name=target_user.display_name,
                command_name="today",
                command_output=cmd_out,
                progression={
                    "points": progress.get("total_points", 0),
                    "max_points": progress.get("max_possible_points", 500),
                    "pct": int(round(progress.get("overall_completion_rate", 0) * 100)),
                    "streak": streak,
                    "completed_tasks": [t["name"] for t in progress.get("tasks", []) if t.get("completed")],
                    "pending_tasks": [t["name"] for t in progress.get("tasks", []) if not t.get("completed")],
                    "task_status": [f"{t['name']} ({format_num(t['current_amount'])}/{format_num(t['target'])} {t['unit']})" for t in progress.get("tasks", [])],
                }
            )
        )

        if progress["perfect_day"]:
            await safe_react(interaction, "⭐", "🔥")
        else:
            await safe_react(interaction, "🐺", "❄️")

    @app_commands.command(name="tasks", description="View all daily disciplines with progress bars, targets, and exercise descriptions.")
    @app_commands.describe(member="Optional: View another member's tasks & disciplines")
    async def tasks_cmd(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target_user = member or interaction.user

        if target_user.id == interaction.user.id:
            if not await require_enrolled(interaction):
                return
        else:
            if not db.is_user_enrolled(target_user.id):
                await interaction.response.send_message(f"❌ {target_user.display_name} is not enrolled in Winter Arc.", ephemeral=True)
                return

        await interaction.response.defer()

        now = datetime.now(BOT_TZ)
        today_str = now.strftime("%Y-%m-%d")
        date_display = now.strftime("%A, %B %d, %Y")

        progress = db.get_user_daily_progress(target_user.id, today_str)
        streak = db.calculate_streak(target_user.id, today_str)

        embed = build_tasks_embed(target_user, progress, streak, date_display)
        await interaction.followup.send(embed=embed)

        cmd_out = format_embed_as_text(embed)

        asyncio.create_task(
            dispatch_tip(interaction, target_user.id, target_user.display_name)
        )

        asyncio.create_task(
            groq_service.dispatch_interaction_nudge(
                interaction=interaction,
                user_id=target_user.id,
                user_name=target_user.display_name,
                command_name="tasks",
                command_output=cmd_out,
                progression={
                    "points": progress.get("total_points", 0),
                    "max_points": progress.get("max_possible_points", 500),
                    "pct": int(round(progress.get("overall_completion_rate", 0) * 100)),
                    "streak": streak,
                    "completed_tasks": [t["name"] for t in progress.get("tasks", []) if t.get("completed")],
                    "pending_tasks": [t["name"] for t in progress.get("tasks", []) if not t.get("completed")],
                    "task_status": [f"{t['name']} ({format_num(t['current_amount'])}/{format_num(t['target'])} {t['unit']})" for t in progress.get("tasks", [])],
                }
            )
        )

        if progress["perfect_day"]:
            await safe_react(interaction, "⭐", "🔥")
        else:
            await safe_react(interaction, "🐺", "❄️")

    @app_commands.command(name="log", description="Add completed reps or km to today's count.")
    @app_commands.describe(
        task="Select the task to log",
        amount="Amount completed (e.g. 30 reps or 5 km)"
    )
    @app_commands.autocomplete(task=task_autocomplete, amount=log_amount_autocomplete)
    async def log_activity_cmd(self, interaction: discord.Interaction, task: str, amount: float):
        logger.info(f"Slash command '/log' invoked by {interaction.user}: {task} +{amount}")
        if not await require_enrolled(interaction):
            return

        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be greater than 0.", ephemeral=True)
            return
        task_obj = db.get_task_by_name(task)
        if not task_obj:
            await interaction.response.send_message(
                f"❌ Task '{task}' not found. Available tasks: Push-ups, Pull-ups, Squats, Sit-ups, Running.",
                ephemeral=True
            )
            return

        task_canonical = task_obj["name"]
        task_key = task_canonical.lower().strip()
        max_allowed = MAX_SINGLE_SET_LIMITS.get(task_key, 50.0)
        if amount > max_allowed:
            unit_display = "km" if "run" in task_key else "reps"
            logger.warning(f"/log rejected for {interaction.user}: {amount} {unit_display} for {task_canonical} exceeds limit {max_allowed}")
            await interaction.response.send_message(
                f"❌ **Unrealistic Volume Rejected**: `{format_num(amount)} {unit_display}` in a single go exceeds the realistic single-set limit (max `{format_num(max_allowed)} {unit_display}`). "
                f"Log your completed sets individually as you finish them.",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        today_str = datetime.now(BOT_TZ).strftime("%Y-%m-%d")
        old_points = db.get_user_lifetime_points(interaction.user.id)

        try:
            result = db.log_activity(
                discord_id=interaction.user.id,
                username=interaction.user.name,
                task_name=task_canonical,
                amount=amount,
                log_date=today_str
            )
        except ValueError as e:
            logger.warning(f"/log validation error for {interaction.user} on {task}: {e}")
            await interaction.followup.send(f"❌ {str(e)}", ephemeral=True)
            return

        new_points = db.get_user_lifetime_points(interaction.user.id)
        level_up_info = check_level_up(old_points, new_points)
        pts_added = result.get('points_added', result.get('points_earned_delta', 0))
        daily_total = result.get('new_points', result.get('daily_points_total', 0))
        logger.info(f"/log successful for {interaction.user}: {task_canonical} +{amount} (+{pts_added} pts, daily total: {daily_total} pts)")

        reply_msg = format_log_reply(result, amount, level_up_info=level_up_info)
        await interaction.followup.send(content=reply_msg)

        task_new = format_num(result['new_total'])
        task_tgt = format_num(result['target'])
        unit = result.get('unit', 'reps')

        asyncio.create_task(
            dispatch_tip(interaction, interaction.user.id, interaction.user.display_name)
        )

        asyncio.create_task(
            groq_service.dispatch_interaction_nudge(
                interaction=interaction,
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
                command_name="log",
                extra_info=f"Logged +{format_num(amount)} {unit} to {task_canonical} (discipline total: {task_new}/{task_tgt} {unit})",
                command_output=reply_msg
            )
        )

        if level_up_info:
            await safe_react(interaction, "🎉", "🐺")
        else:
            await safe_react(interaction, "🐺", "💪")

    @app_commands.command(name="set", description="Override today's count (or set 0 to reset).")
    @app_commands.describe(
        task="Select the task to set/override",
        amount="Exact total to set for today (e.g. 50, or 0 to reset)"
    )
    @app_commands.autocomplete(task=task_autocomplete, amount=set_amount_autocomplete)
    async def set_activity_cmd(self, interaction: discord.Interaction, task: str, amount: float):
        logger.info(f"Slash command '/set' invoked by {interaction.user}: {task} set to {amount}")
        if not await require_enrolled(interaction):
            return

        if amount < 0:
            await interaction.response.send_message("❌ Amount cannot be negative.", ephemeral=True)
            return
        if amount > 5000:
            await interaction.response.send_message("❌ Amount exceeds reasonable single entry limit (5,000).", ephemeral=True)
            return

        task_obj = db.get_task_by_name(task)
        if not task_obj:
            await interaction.response.send_message(
                f"❌ Task '{task}' not found. Available tasks: Push-ups, Pull-ups, Squats, Sit-ups, Running.",
                ephemeral=True
            )
            return

        task_canonical = task_obj["name"]
        await interaction.response.defer()

        today_str = datetime.now(BOT_TZ).strftime("%Y-%m-%d")
        old_points = db.get_user_lifetime_points(interaction.user.id)

        try:
            result = db.set_activity(
                discord_id=interaction.user.id,
                username=interaction.user.name,
                task_name=task_canonical,
                target_amount=amount,
                log_date=today_str
            )
        except ValueError as e:
            logger.warning(f"/set validation error for {interaction.user} on {task}: {e}")
            await interaction.followup.send(f"❌ {str(e)}", ephemeral=True)
            return

        new_points = db.get_user_lifetime_points(interaction.user.id)
        level_up_info = check_level_up(old_points, new_points)
        pts_old = result.get('old_points', 0)
        pts_new = result.get('new_points', result.get('task_points_total', 0))
        logger.info(f"/set successful for {interaction.user}: {task_canonical} set to {amount} (points: {pts_old} -> {pts_new})")

        reply_msg = format_set_reply(result, amount, level_up_info=level_up_info)
        await interaction.followup.send(content=reply_msg)

        asyncio.create_task(
            dispatch_tip(interaction, interaction.user.id, interaction.user.display_name)
        )

        if level_up_info:
            await safe_react(interaction, "🎉", "🐺")
        elif result["is_target_reached"]:
            await safe_react(interaction, "⭐", "🔥")
        else:
            await safe_react(interaction, "🐺", "🔄")

    # ==========================================
    # Profile & Progression Commands
    # ==========================================

    @app_commands.command(name="profile", description="View member profile, rank, and 12-level progression.")
    @app_commands.describe(member="Optional: View another member's profile and rank card")
    async def profile(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target_user = member or interaction.user
        if target_user.id == interaction.user.id:
            if not await require_enrolled(interaction):
                return
        else:
            if not db.is_user_enrolled(target_user.id):
                await interaction.response.send_message(f"❌ {target_user.display_name} is not enrolled.", ephemeral=True)
                return

        await interaction.response.defer()

        user = db.get_user_by_discord_id(target_user.id)
        today_str = datetime.now(BOT_TZ).strftime("%Y-%m-%d")
        streak = db.calculate_streak(target_user.id, today_str)
        stats_data = db.get_user_stats(target_user.id)
        all_time_rank, total_warriors = db.get_user_all_time_rank(target_user.id)
        today_progress = db.get_user_daily_progress(target_user.id, today_str)

        embed = build_profile_embed(
            target_user,
            user,
            streak,
            stats_data,
            all_time_rank=all_time_rank,
            total_warriors=total_warriors,
            today_progress=today_progress
        )
        await interaction.followup.send(embed=embed)

        cmd_out = format_embed_as_text(embed)

        asyncio.create_task(
            dispatch_tip(interaction, target_user.id, target_user.display_name)
        )

        asyncio.create_task(
            groq_service.dispatch_interaction_nudge(
                interaction=interaction,
                user_id=target_user.id,
                user_name=target_user.display_name,
                command_name="profile",
                extra_info=f"Rank #{all_time_rank} of {total_warriors}",
                command_output=cmd_out
            )
        )

    @app_commands.command(name="ranks", description="View the 12-tier discipline progression hierarchy and requirements.")
    async def ranks(self, interaction: discord.Interaction):
        lifetime_points = db.get_user_lifetime_points(interaction.user.id)
        embed = build_ranks_embed(lifetime_points)
        await interaction.response.send_message(embed=embed)

        cmd_out = format_embed_as_text(embed)

        asyncio.create_task(
            dispatch_tip(interaction, interaction.user.id, interaction.user.display_name)
        )

        asyncio.create_task(
            groq_service.dispatch_interaction_nudge(
                interaction=interaction,
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
                command_name="ranks",
                command_output=cmd_out
            )
        )

    # ==========================================
    # Competition & History Commands
    # ==========================================

    @app_commands.command(name="leaderboard", description="View daily, monthly, and overall standings.")
    @app_commands.describe(timeframe="Select leaderboard timeframe to view directly (default: Daily)")
    @app_commands.choices(timeframe=[
        app_commands.Choice(name="📅 Daily (Today's live standings)", value="daily"),
        app_commands.Choice(name="📆 Weekly (Mon–Sun week standings)", value="weekly"),
        app_commands.Choice(name="🗓️ Monthly (Current phase standings)", value="monthly"),
        app_commands.Choice(name="🌐 All-Time (Overall campaign podium)", value="overall"),
    ])
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: i.user.id)
    async def leaderboard(self, interaction: discord.Interaction, timeframe: Optional[app_commands.Choice[str]] = None):
        await interaction.response.defer()
        selected_tab = timeframe.value if timeframe else "daily"

        if selected_tab == "weekly":
            embed = build_weekly_leaderboard_embed()
        elif selected_tab == "monthly":
            embed = build_monthly_leaderboard_embed()
        elif selected_tab == "overall":
            embed = build_overall_leaderboard_embed()
        else:
            embed = build_daily_leaderboard_embed()

        view = LeaderboardView(current_tab=selected_tab)
        await interaction.followup.send(embed=embed, view=view)
        await safe_react(interaction, "🏆")

        cmd_out = format_embed_as_text(embed)

        asyncio.create_task(
            dispatch_tip(interaction, interaction.user.id, interaction.user.display_name)
        )

        asyncio.create_task(
            groq_service.dispatch_interaction_nudge(
                interaction=interaction,
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
                command_name="leaderboard",
                command_output=cmd_out
            )
        )

    @app_commands.command(name="stats", description="Explore server benchmarks, peak records, and community volume.")
    @app_commands.describe(phase="Select a specific phase or view all-time overall records (default: Overall)")
    @app_commands.choices(phase=[
        app_commands.Choice(name="Overall (All-Time)", value="overall"),
        app_commands.Choice(name="Phase 1: FIRST FROST", value="phase_1"),
        app_commands.Choice(name="Phase 2: THE HUNT", value="phase_2"),
        app_commands.Choice(name="Phase 3: THE ENDGAME", value="phase_3"),
    ])
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: i.user.id)
    async def stats(self, interaction: discord.Interaction, phase: Optional[app_commands.Choice[str]] = None):
        if not await require_enrolled(interaction):
            return

        await interaction.response.defer()

        chosen_val = phase.value if phase else "overall"
        phase_id = None
        if chosen_val.startswith("phase_"):
            try:
                phase_id = int(chosen_val.split("_")[1])
            except ValueError:
                phase_id = None

        data = db.get_server_records(phase_id)
        embed = build_server_records_embed(data, phase_id=phase_id)
        view = ServerRecordsView(author_id=interaction.user.id, current_selection=chosen_val)
        await interaction.followup.send(embed=embed, view=view)

        cmd_out = format_embed_as_text(embed)

        asyncio.create_task(
            dispatch_tip(interaction, interaction.user.id, interaction.user.display_name)
        )

        asyncio.create_task(
            groq_service.dispatch_interaction_nudge(
                interaction=interaction,
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
                command_name="stats",
                extra_info=f"Viewing {chosen_val} stats",
                command_output=cmd_out
            )
        )

    @app_commands.command(name="history", description="View point and completion history.")
    @app_commands.describe(days="Timeframe to inspect (e.g. 7, 14, 30 days)")
    @app_commands.autocomplete(days=history_days_autocomplete)
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: i.user.id)
    async def history(self, interaction: discord.Interaction, days: Optional[int] = 7):
        if not await require_enrolled(interaction):
            return

        await interaction.response.defer()
        days_count = max(1, min(days or 7, 90))
        hist = db.get_user_history(interaction.user.id, days=days_count)
        embed = build_history_embed(interaction.user, hist)
        await interaction.followup.send(embed=embed)

        cmd_out = format_embed_as_text(embed)

        asyncio.create_task(
            dispatch_tip(interaction, interaction.user.id, interaction.user.display_name)
        )

        asyncio.create_task(
            groq_service.dispatch_interaction_nudge(
                interaction=interaction,
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
                command_name="history",
                extra_info=f"Inspected last {days_count} days history",
                command_output=cmd_out
            )
        )

    @app_commands.command(name="recap", description="Explore detailed performance recaps by phase and overall campaign.")
    @app_commands.describe(
        user="The member to view the recap for (defaults to yourself)",
        phase="Select specific phase or overall campaign recap (defaults to active phase)"
    )
    @app_commands.choices(phase=[
        app_commands.Choice(name="Phase 1: FIRST FROST", value="phase_1"),
        app_commands.Choice(name="Phase 2: THE HUNT", value="phase_2"),
        app_commands.Choice(name="Phase 3: THE ENDGAME", value="phase_3"),
        app_commands.Choice(name="Overall (All-Time Campaign)", value="overall"),
    ])
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: i.user.id)
    async def recap(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None,
        phase: Optional[app_commands.Choice[str]] = None
    ):
        target = user or interaction.user
        if not await require_enrolled(interaction):
            return

        target_record = db.get_user_by_discord_id(target.id)
        if not target_record or not target_record.get("enrolled"):
            name = "You are" if target.id == interaction.user.id else f"{target.display_name} is"
            await interaction.response.send_message(f"🚫 {name} not enrolled in the Winter Arc.", ephemeral=True)
            return

        await interaction.response.defer()

        selected_phase = phase.value if phase else None
        if selected_phase == "overall":
            stats = db.get_user_overall_recap(target.id)
            embed = build_recap_embed(target, stats, is_overall=True)
            view = RecapView(target_user=target, author_id=interaction.user.id, current_selection="overall")
            extra_tag = "Overall campaign recap"
        elif selected_phase and selected_phase.startswith("phase_"):
            p_id = int(selected_phase.split("_")[1])
            stats = db.get_user_phase_stats(target.id, p_id)
            embed = build_recap_embed(target, stats, is_overall=False)
            view = RecapView(target_user=target, author_id=interaction.user.id, current_selection=selected_phase)
            extra_tag = f"Phase {p_id} recap"
        else:
            from phases import get_current_phase
            curr_phase = get_current_phase()
            p_id = curr_phase["id"] if curr_phase else 1
            stats = db.get_user_phase_stats(target.id, p_id)
            embed = build_recap_embed(target, stats, is_overall=False)
            view = RecapView(target_user=target, author_id=interaction.user.id, current_selection=f"phase_{p_id}")
            extra_tag = f"Phase {p_id} recap"

        await interaction.followup.send(embed=embed, view=view)

        cmd_out = format_embed_as_text(embed)

        asyncio.create_task(
            dispatch_tip(interaction, target.id, target.display_name)
        )

        asyncio.create_task(
            groq_service.dispatch_interaction_nudge(
                interaction=interaction,
                user_id=target.id,
                user_name=target.display_name,
                command_name="recap",
                extra_info=extra_tag,
                command_output=cmd_out
            )
        )

    @app_commands.command(name="streak", description="View your habit consistency calendar and overall arc progress.")
    @app_commands.describe(member="Optional: Check another member's streak and calendar")
    async def streak_cmd(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None
    ):
        target_user = member or interaction.user
        if target_user.id == interaction.user.id:
            if not await require_enrolled(interaction):
                return
        else:
            if not db.is_user_enrolled(target_user.id):
                await interaction.response.send_message(f"❌ {target_user.display_name} is not enrolled in Winter Arc.", ephemeral=True)
                return

        await interaction.response.defer()

        consistency_data = db.get_user_monthly_consistency(target_user.id)
        embed = build_streak_consistency_embed(target_user, consistency_data)
        view = StreakConsistencyView(
            target_user=target_user,
            author_id=interaction.user.id,
            current_view="current"
        )
        await interaction.followup.send(embed=embed, view=view)
        await safe_react(interaction, "🔥", "🐺")

        cmd_out = format_embed_as_text(embed)

        asyncio.create_task(
            dispatch_tip(interaction, target_user.id, target_user.display_name)
        )

        h = consistency_data.get("highlights", {})
        asyncio.create_task(
            groq_service.dispatch_interaction_nudge(
                interaction=interaction,
                user_id=target_user.id,
                user_name=target_user.display_name,
                command_name="streak",
                extra_info=f"Streak {h.get('current_streak', 0)}d (Peak: {h.get('highest_streak', 0)}d), Consistency: {h.get('consistency_pct', 0)}%, Shields: {h.get('shields_left', 0)}/2",
                command_output=cmd_out
            )
        )

    # ==========================================
    # Streak Shield & Protection Commands
    # ==========================================

    shield_group = app_commands.Group(
        name="shield",
        description="Streak Shield protection and recovery controls."
    )

    @shield_group.command(name="status", description="View Streak Shield inventory, protection status, and next unlock.")
    async def shield_status_cmd(self, interaction: discord.Interaction):
        if not await require_enrolled(interaction):
            return

        status = db.get_user_shield_status(interaction.user.id)
        embed = build_shield_status_embed(interaction.user, status)
        await interaction.response.send_message(embed=embed)

        cmd_out = format_embed_as_text(embed)

        asyncio.create_task(
            dispatch_tip(interaction, interaction.user.id, interaction.user.display_name)
        )

        asyncio.create_task(
            groq_service.dispatch_interaction_nudge(
                interaction=interaction,
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
                command_name="shield-status",
                command_output=cmd_out
            )
        )

    @shield_group.command(name="use", description="Streak Shields are 100% automated at midnight. View your active protection.")
    @app_commands.describe(
        target_date="Optional: Target day query ('today' or 'yesterday')",
        reason="Optional: Note or inquiry reason"
    )
    @app_commands.choices(target_date=[
        app_commands.Choice(name="Today", value="today"),
        app_commands.Choice(name="Yesterday", value="yesterday"),
    ])
    async def shield_use_cmd(
        self,
        interaction: discord.Interaction,
        target_date: Optional[app_commands.Choice[str]] = None,
        reason: Optional[str] = None
    ):
        if not await require_enrolled(interaction):
            return

        status = db.get_user_shield_status(interaction.user.id)
        embed = build_shield_automated_info_embed(interaction.user, status)
        await interaction.response.send_message(embed=embed)
        await safe_react(interaction, "🛡️", "❄️")

        cmd_out = format_embed_as_text(embed)

        asyncio.create_task(
            dispatch_tip(interaction, interaction.user.id, interaction.user.display_name)
        )

        asyncio.create_task(
            groq_service.dispatch_interaction_nudge(
                interaction=interaction,
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
                command_name="shield-use",
                extra_info=f"Automated shield inquiry (inventory: {status['frost_shields']}/2, streak: {status['current_streak']}d)",
                command_output=cmd_out
            )
        )

    # ==========================================
    # Personal Direct Messaging Settings
    # ==========================================

    @app_commands.command(name="settings", description="Configure personal DM notifications and accountability.")
    @app_commands.describe(dms="Quick toggle to enable/disable all DM notifications")
    async def settings_cmd(self, interaction: discord.Interaction, dms: Optional[bool] = None):
        if not await require_enrolled(interaction):
            return

        if dms is not None:
            settings = db.update_user_dm_settings(interaction.user.id, dm_reminders=dms)
        else:
            settings = db.get_user_dm_settings(interaction.user.id)

        embed = build_settings_embed(interaction.user, settings)
        view = SettingsView(interaction.user.id, settings)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        asyncio.create_task(
            dispatch_tip(interaction, interaction.user.id, interaction.user.display_name)
        )

    # ==========================================
    # AI Discipline & Quick-Logging Commands
    # ==========================================

    @app_commands.command(name="grind", description="Log daily deep work, studying, or engineering practice.")
    @app_commands.describe(
        text="Describe the technical problem, hours spent, or conceptual breakthrough"
    )
    async def grind_cmd(self, interaction: discord.Interaction, text: str):
        logger.info(f"Slash command '/grind' invoked by {interaction.user}: '{text[:60]}...'")
        if not await require_enrolled(interaction):
            return

        # Check disciplinary probation
        probation = db.get_grind_probation(interaction.user.id)
        if probation["is_blocked"]:
            rem = probation["remaining_days"]
            days_str = f" for **{rem} more day(s)**" if rem else ""
            await interaction.response.send_message(
                f"🚫 **Access Suspended**: Your `/grind` access has been locked{days_str} by an admin.\n"
                "Focus on your core physical disciplines.",
                ephemeral=True
            )
            return

        now = datetime.now(BOT_TZ)
        today_str = now.strftime("%Y-%m-%d")

        # Check if already submitted today
        existing = db.get_user_daily_grind(interaction.user.id, today_str)
        if existing:
            await interaction.response.send_message(
                "❌ You have already logged your daily **/grind** for today. Next entry unlocks at 00:00 IST.",
                ephemeral=True
            )
            return

        if len(text.strip()) < 10:
            await interaction.response.send_message(
                "❌ Too short. Describe the study session, technical problem, or engineering work you tackled.",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        # Evaluate via Gemini
        try:
            evaluation = await gemini_service.evaluate_grind(text)
        except gemini_service.GeminiServiceError as e:
            logger.warning(f"/grind evaluation unavailable for {interaction.user}: {e}")
            await interaction.followup.send(
                f"⚠️ **AI Evaluation Unavailable**\n{str(e)}\n\n"
                "ℹ️ *Your daily grind submission has NOT been consumed. You can run `/grind` again when the service is back, or inform an admin.*",
                ephemeral=True
            )
            return
        except Exception as e:
            logger.error(f"Unexpected /grind error for {interaction.user}: {e}", exc_info=True)
            await interaction.followup.send(
                "⚠️ **Evaluation Error**: Could not complete evaluation due to an unexpected service error.\n\n"
                "ℹ️ *Your daily grind submission was NOT consumed. Please try again shortly or inform an admin.*",
                ephemeral=True
            )
            return

        logger.info(f"/grind evaluated for {interaction.user}: {evaluation.get('verdict')} (+{evaluation.get('points')} pts, tag: {evaluation.get('key_learning')})")

        # Record in database
        try:
            db.record_grind_entry(
                discord_id=interaction.user.id,
                date_str=today_str,
                raw_input=text,
                verdict=evaluation["verdict"],
                points=evaluation["points"],
                key_learning=evaluation["key_learning"],
                commentary=evaluation["commentary"]
            )
        except ValueError as e:
            await interaction.followup.send(f"❌ {str(e)}", ephemeral=True)
            return

        reply_msg = format_grind_reply(evaluation)
        await interaction.followup.send(reply_msg)

        if evaluation["verdict"] == "ACCEPTED":
            await safe_react(interaction, "⚔️", "🧠")
        elif evaluation["verdict"] == "ROASTED":
            await safe_react(interaction, "🔥", "💀")

            # AI flagged buzzwords/fluff: summon the Council directly after the reply!
            if interaction.guild and interaction.channel and interaction.user.id not in CouncilVotingView.active_trials:
                settings = db.get_server_settings(interaction.guild.id)
                role_id = settings.get("role_id")
                role_ping = f"<@&{role_id}> " if role_id else ""
                pts = evaluation["points"]

                council_content = (
                    f"{role_ping}🚨 **The Council Has Been Summoned** 🚨\n\n"
                    f"*Amarok has called cap on {interaction.user.mention}'s grind log of*\n"
                    f"```{text}```\n"
                    f"*worth {pts} points.*\n\n"
                    f"⚔️ **Summoner**: 🐺 Amarok (Sentinel)\n"
                    f"⚖️ **Accused**: {interaction.user.mention}\n"
                    f"🎯 **Stake**: {pts} Points\n\n"
                    "⏳ Cast your vote below. Decision resolves when the timer concludes."
                )

                import random
                gif_url = random.choice(COUNCIL_SUMMONED_GIFS)
                gif_embed = discord.Embed(color=0xE74C3C)
                gif_embed.set_image(url=gif_url)

                voting_view = CouncilVotingView(
                    accused=interaction.user,
                    challenger=self.bot.user,
                    grind_entry={"raw_input": text, "points": pts},
                    timeout=600.0
                )
                CouncilVotingView.active_trials.add(interaction.user.id)

                try:
                    msg = await interaction.channel.send(content=council_content, embed=gif_embed, view=voting_view)
                    voting_view.message = msg
                except Exception as e:
                    logger.error(f"Failed to post AI-summoned Council trial: {e}", exc_info=True)
                    CouncilVotingView.active_trials.discard(interaction.user.id)

        asyncio.create_task(
            dispatch_tip(interaction, interaction.user.id, interaction.user.display_name)
        )

        asyncio.create_task(
            groq_service.dispatch_interaction_nudge(
                interaction=interaction,
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
                command_name="grind",
                extra_info=f"Deep work grind logged ({evaluation.get('verdict')}: +{evaluation.get('points')} pts - {evaluation.get('key_learning')})",
                command_output=reply_msg
            )
        )

    @app_commands.command(name="callcap", description="Challenge a member's daily grind log and summon the Council.")
    @app_commands.describe(target="The member whose grind log you want to challenge")
    async def callcap_cmd(self, interaction: discord.Interaction, target: discord.Member):
        logger.info(f"Slash command '/callcap' invoked by {interaction.user} against {target}")
        if not interaction.guild:
            await interaction.response.send_message("❌ This command must be used within a server text channel.", ephemeral=True)
            return

        if not await require_enrolled(interaction):
            return

        if target.id in CouncilVotingView.active_trials:
            await interaction.response.send_message(f"⏳ A Council trial is already active for {target.mention}.", ephemeral=True)
            return

        if target.id == interaction.user.id:
            await interaction.response.send_message("❌ You cannot call cap on yourself!", ephemeral=True)
            return

        if not db.is_user_enrolled(target.id):
            await interaction.response.send_message(f"❌ {target.mention} is not currently enrolled in Winter Arc.", ephemeral=True)
            return

        today_str = datetime.now(BOT_TZ).strftime("%Y-%m-%d")
        grind_entry = db.get_user_daily_grind(target.id, today_str)
        if not grind_entry:
            await interaction.response.send_message(f"❌ {target.mention} has not logged a `/grind` entry today.", ephemeral=True)
            return

        if grind_entry.get("points", 0) <= 0:
            await interaction.response.send_message(f"❌ {target.mention}'s grind log has 0 points (already rejected or capped).", ephemeral=True)
            return

        snippet = grind_entry["raw_input"]
        if len(snippet) > 200:
            snippet = snippet[:197] + "..."
        pts = grind_entry["points"]

        prompt_text = (
            "🛡️ **Winter Arc — Council Summoning Verification**\n\n"
            f"**Accused**: {target.mention}\n"
            f'**Claimed Log**: *"{snippet}"*\n'
            f"**Points at Stake**: {pts} pts\n\n"
            "Are you certain this log is not legit and wish to summon a formal Council vote?\n\n"
            "📜 **Honor Code Notice**:\n"
            '> *"Bringing down brothers out of jealousy or petty rivalry is against the philosophy of Winter Arc. A warrior of honor does not abuse the Council."*'
        )

        view = CallCapConfirmView(
            challenger=interaction.user,
            target=target,
            grind_entry=grind_entry
        )

        await interaction.response.send_message(
            content=prompt_text,
            view=view,
            ephemeral=True
        )

    @app_commands.command(name="quick", description="Natural language workout logging (e.g. 'did 45 pushups and ran 5k').")
    @app_commands.describe(text="Natural language workout text (e.g. '40 pushups, 12 pullups, ran 5k')")
    async def quick_cmd(self, interaction: discord.Interaction, text: str):
        logger.info(f"Slash command '/quick' invoked by {interaction.user}: '{text}'")
        if not await require_enrolled(interaction):
            return

        if len(text.strip()) < 3:
            await interaction.response.send_message("❌ Please specify your completed exercises and amounts.", ephemeral=True)
            return

        await interaction.response.defer()

        active_tasks = db.get_active_tasks()
        parsed = await groq_service.parse_quicklog(text, active_tasks)

        if parsed.get("suspicious"):
            logger.warning(f"/quick rejected for {interaction.user} as suspicious single-set volume: '{text}'")
            await interaction.followup.send(
                "❌ Max per set is 50 reps (or 10 km). If you did multiple sets, log them separately (e.g. '30 pushups, 30 pushups').",
                ephemeral=True
            )
            return

        matches = parsed.get("matches", [])
        if not matches:
            logger.info(f"/quick could not detect active disciplines from '{text}' for {interaction.user}")
            task_names = ", ".join(t["name"] for t in active_tasks)
            await interaction.followup.send(
                f"❌ Could not detect any active disciplines. Active tasks: **{task_names}**.",
                ephemeral=True
            )
            return

        today_str = datetime.now(BOT_TZ).strftime("%Y-%m-%d")
        old_points = db.get_user_lifetime_points(interaction.user.id)
        log_results = []
        for m in matches:
            try:
                res = db.log_activity(
                    discord_id=interaction.user.id,
                    username=interaction.user.name,
                    task_name=m["task_name"],
                    amount=m["amount"],
                    log_date=today_str
                )
                log_results.append(res)
            except Exception as e:
                logger.warning(f"Error logging quick item {m}: {e}")

        if not log_results:
            await interaction.followup.send("❌ An error occurred while logging entries.", ephemeral=True)
            return

        new_points = db.get_user_lifetime_points(interaction.user.id)
        level_up_info = check_level_up(old_points, new_points)
        logger.info(f"/quick successfully logged {len(log_results)} disciplines for {interaction.user}")

        embed = build_quicklog_embed(
            user=interaction.user,
            log_results=log_results,
            commentary=parsed.get("commentary", "Discipline logged."),
            unrecognized=parsed.get("unrecognized", []),
            level_up_info=level_up_info
        )
        await interaction.followup.send(embed=embed)
        if level_up_info:
            await safe_react(interaction, "🎉", "🐺")
        else:
            await safe_react(interaction, "🐺", "⚡")

        cmd_out = format_embed_as_text(embed)

        asyncio.create_task(
            dispatch_tip(interaction, interaction.user.id, interaction.user.display_name)
        )

        asyncio.create_task(
            groq_service.dispatch_interaction_nudge(
                interaction=interaction,
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
                command_name="quick",
                extra_info=f"Quick logged: {text}",
                command_output=cmd_out
            )
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(WarriorCog(bot))


