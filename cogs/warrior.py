"""
cogs/warrior.py - User Slash Commands for Winter Arc Bot

Contains commands for enrolled participants:
- Enrollment lifecycle (/enroll, /leave_arc)
- Daily tracking (/today, /log, /set)
- Profile & progression (/profile, /ranks)
- Competition & history (/leaderboard, /stats, /history)
- General utilities (/help, /ping)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import BOT_TZ
from helpers import (
    require_enrolled,
    task_autocomplete,
    log_amount_autocomplete,
    set_amount_autocomplete,
    history_days_autocomplete,
    get_or_create_arc_role,
    safe_react,
)
from levels import check_level_up
from ui.embeds import (
    build_today_embed,
    build_log_embed,
    build_set_embed,
    build_stats_embed,
    build_history_embed,
    build_profile_embed,
    build_ranks_embed,
    build_help_embed,
    build_daily_leaderboard_embed,
    build_shield_status_embed,
    build_shield_activated_embed,
    build_settings_embed,
    build_grind_embed,
    build_quicklog_embed,
)
from ui.views import LeaderboardView, SettingsView
from ai import gemini_service, groq_service

logger = logging.getLogger("winter_arc.cogs.warrior")


class WarriorCog(commands.Cog, name="Warrior Commands"):
    """Core workout tracking, progression, and social commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ==========================================
    # Enrollment Commands
    # ==========================================

    @app_commands.command(name="enroll", description="Enroll in the Winter Arc challenge.")
    async def enroll(self, interaction: discord.Interaction):
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
            f"• **{t['name']}**: `{int(t['target']) if t['target'].is_integer() else t['target']} {t['unit']}` *(max {t['max_points']} pts)*"
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
                "• `/today` — View daily progress & streak\n"
                "• `/log [task] [amount]` — Log completed reps or km\n"
                "• `/set [task] [amount]` — Set count directly *(or 0 to reset)*\n"
                "• `/profile` — View rank & 12-level progression\n"
                "• `/leaderboard` — View daily & overall standings"
            ),
            color=0x2ECC71
        )
        embed.set_footer(text="Winter Arc • Consistency Beats Motivation")
        await interaction.response.send_message(embed=embed)
        await safe_react(interaction, "🐺", "⚔️")

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

    @app_commands.command(name="help", description="View commands and challenge rules.")
    async def help_cmd(self, interaction: discord.Interaction):
        embed = build_help_embed()
        await interaction.response.send_message(embed=embed)

    # ==========================================
    # Daily Tracking Commands
    # ==========================================

    @app_commands.command(name="today", description="View today's progress, points, and streak.")
    @app_commands.describe(member="Optional: View another member's progress")
    async def today(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target_user = member or interaction.user

        if target_user.id == interaction.user.id:
            if not await require_enrolled(interaction):
                return
        else:
            if not db.is_user_enrolled(target_user.id):
                await interaction.response.send_message(f"❌ {target_user.display_name} is not enrolled in Winter Arc.", ephemeral=True)
                return

        now = datetime.now(BOT_TZ)
        today_str = now.strftime("%Y-%m-%d")
        date_display = now.strftime("%A, %B %d, %Y")

        progress = db.get_user_daily_progress(target_user.id, today_str)
        streak = db.calculate_streak(target_user.id, today_str)

        embed = build_today_embed(target_user, progress, streak, date_display)
        await interaction.response.send_message(embed=embed)

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
        if not await require_enrolled(interaction):
            return

        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be greater than 0.", ephemeral=True)
            return
        if amount > 5000:
            await interaction.response.send_message("❌ Amount exceeds reasonable single log limit (5,000).", ephemeral=True)
            return

        today_str = datetime.now(BOT_TZ).strftime("%Y-%m-%d")
        old_points = db.get_user_lifetime_points(interaction.user.id)

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

        new_points = db.get_user_lifetime_points(interaction.user.id)
        level_up_info = check_level_up(old_points, new_points)

        embed = build_log_embed(result, amount, level_up_info=level_up_info)
        await interaction.response.send_message(embed=embed)

        if level_up_info:
            await safe_react(interaction, "🎉", "🐺")
        elif result["is_target_reached"]:
            await safe_react(interaction, "⭐", "🔥")
        else:
            await safe_react(interaction, "🐺", "💪")

    @app_commands.command(name="set", description="Override today's count (or set 0 to reset).")
    @app_commands.describe(
        task="Select the task to set/override",
        amount="Exact total to set for today (e.g. 50, or 0 to reset)"
    )
    @app_commands.autocomplete(task=task_autocomplete, amount=set_amount_autocomplete)
    async def set_activity_cmd(self, interaction: discord.Interaction, task: str, amount: float):
        if not await require_enrolled(interaction):
            return

        if amount < 0:
            await interaction.response.send_message("❌ Amount cannot be negative.", ephemeral=True)
            return
        if amount > 5000:
            await interaction.response.send_message("❌ Amount exceeds reasonable single entry limit (5,000).", ephemeral=True)
            return

        today_str = datetime.now(BOT_TZ).strftime("%Y-%m-%d")
        old_points = db.get_user_lifetime_points(interaction.user.id)

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

        new_points = db.get_user_lifetime_points(interaction.user.id)
        level_up_info = check_level_up(old_points, new_points)

        embed = build_set_embed(result, amount, level_up_info=level_up_info)
        await interaction.response.send_message(embed=embed)

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

        user = db.get_user_by_discord_id(target_user.id)
        streak = db.calculate_streak(target_user.id)
        stats_data = db.get_user_stats(target_user.id)

        embed = build_profile_embed(target_user, user, streak, stats_data)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ranks", description="View the 12-level Winter Pack hierarchy and requirements.")
    async def ranks(self, interaction: discord.Interaction):
        lifetime_points = db.get_user_lifetime_points(interaction.user.id)
        embed = build_ranks_embed(lifetime_points)
        await interaction.response.send_message(embed=embed)

    # ==========================================
    # Competition & History Commands
    # ==========================================

    @app_commands.command(name="leaderboard", description="View daily, monthly, and overall standings.")
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: i.user.id)
    async def leaderboard(self, interaction: discord.Interaction):
        embed = build_daily_leaderboard_embed()
        view = LeaderboardView(current_tab="daily")
        await interaction.response.send_message(embed=embed, view=view)
        await safe_react(interaction, "🏆")

    @app_commands.command(name="stats", description="View lifetime volume and performance statistics.")
    @app_commands.describe(member="Optional: View another member's statistics")
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: i.user.id)
    async def stats(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target_user = member or interaction.user
        if target_user.id == interaction.user.id:
            if not await require_enrolled(interaction):
                return
        else:
            if not db.is_user_enrolled(target_user.id):
                await interaction.response.send_message(f"❌ {target_user.display_name} is not enrolled.", ephemeral=True)
                return

        data = db.get_user_stats(target_user.id)
        embed = build_stats_embed(target_user, data)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="history", description="View point and completion history.")
    @app_commands.describe(days="Timeframe to inspect (e.g. 7, 14, 30 days)")
    @app_commands.autocomplete(days=history_days_autocomplete)
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: i.user.id)
    async def history(self, interaction: discord.Interaction, days: Optional[int] = 7):
        if not await require_enrolled(interaction):
            return

        days_count = max(1, min(days or 7, 90))
        hist = db.get_user_history(interaction.user.id, days=days_count)
        embed = build_history_embed(interaction.user, hist)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="streak", description="Quickly look up current streak and shield protection status.")
    @app_commands.describe(member="Optional: Check another warrior's streak")
    async def streak_cmd(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target_user = member or interaction.user
        if target_user.id == interaction.user.id:
            if not await require_enrolled(interaction):
                return
        else:
            if not db.is_user_enrolled(target_user.id):
                await interaction.response.send_message(f"❌ {target_user.display_name} is not enrolled in Winter Arc.", ephemeral=True)
                return

        today_str = datetime.now(BOT_TZ).strftime("%Y-%m-%d")
        streak = db.calculate_streak(target_user.id, today_str)
        shield_status = db.get_user_shield_status(target_user.id)
        stats = db.get_user_stats(target_user.id)

        next_milestone = ((streak // 7) + 1) * 7
        days_to_milestone = next_milestone - streak

        desc = (
            f"**{target_user.display_name}** • Streak Status\n\n"
            f"🔥 **Current Streak**: **{streak} days**\n"
            f"⭐ **Clean Days (100%)**: **{stats.get('perfect_days', 0)}**\n"
            f"🛡️ **Frost Shields**: **{shield_status['inventory']}/2 available**\n"
            f"⏳ **Next Shield Milestone**: **{days_to_milestone} day(s)** (at Day {next_milestone})\n\n"
            + ("🛡️ *Protected by Frost Shield today!*" if shield_status["is_shielded_today"] else "⚡ *Maintain daily discipline to defend the flame.*")
        )
        embed = discord.Embed(
            title="🔥 Winter Arc — Streak Status",
            description=desc,
            color=0xE67E22 if streak > 0 else 0x95A5A6
        )
        embed.set_footer(text="Consistency Beats Motivation • Defend your streak")
        await interaction.response.send_message(embed=embed)
        await safe_react(interaction, "🔥", "🐺")

    # ==========================================
    # Frost Shield & Streak Protection Commands
    # ==========================================

    shield_group = app_commands.Group(
        name="shield",
        description="Frost Shield streak protection and recovery controls."
    )

    @shield_group.command(name="status", description="View Frost Shield inventory, protection status, and next unlock.")
    async def shield_status_cmd(self, interaction: discord.Interaction):
        if not await require_enrolled(interaction):
            return

        status = db.get_user_shield_status(interaction.user.id)
        embed = build_shield_status_embed(interaction.user, status)
        await interaction.response.send_message(embed=embed)

    @shield_group.command(name="use", description="Activate a Frost Shield to protect your streak today or yesterday.")
    @app_commands.describe(
        target_date="Target day to protect: 'today' or 'yesterday'",
        reason="Optional reason for recovery day (e.g. Muscle Recovery, Travel, Illness)"
    )
    @app_commands.choices(target_date=[
        app_commands.Choice(name="Today", value="today"),
        app_commands.Choice(name="Yesterday", value="yesterday"),
    ])
    async def shield_use_cmd(
        self,
        interaction: discord.Interaction,
        target_date: Optional[app_commands.Choice[str]] = None,
        reason: Optional[str] = "Intentional active recovery"
    ):
        if not await require_enrolled(interaction):
            return

        date_choice = target_date.value if target_date else "today"
        today = datetime.now(BOT_TZ).date()
        date_str = (today - timedelta(days=1)).isoformat() if date_choice == "yesterday" else today.isoformat()

        try:
            result = db.activate_frost_shield(interaction.user.id, target_date=date_str, reason=reason)
            embed = build_shield_activated_embed(interaction.user, result)
            await interaction.response.send_message(embed=embed)
            await safe_react(interaction, "🛡️", "❄️")
        except ValueError as e:
            await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)

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

    # ==========================================
    # AI Discipline & Quick-Logging Commands
    # ==========================================

    @app_commands.command(name="grind", description="Submit daily academic/engineering friction for Amarok's evaluation.")
    @app_commands.describe(text="Your daily intellectual friction (academics, LeetCode, deep work, math, systems)")
    async def grind_cmd(self, interaction: discord.Interaction, text: str):
        if not await require_enrolled(interaction):
            return

        now = datetime.now(BOT_TZ)
        today_str = now.strftime("%Y-%m-%d")

        # Check if already submitted today
        existing = db.get_user_daily_grind(interaction.user.id, today_str)
        if existing:
            await interaction.response.send_message(
                "❌ You have already submitted your daily **/grind** evaluation for today. Next submission unlocks at 00:00 IST.",
                ephemeral=True
            )
            return

        if len(text.strip()) < 10:
            await interaction.response.send_message(
                "❌ Your reflection is too short. Describe what real friction or engineering/academic depth you tackled.",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        # Evaluate via Gemini
        evaluation = await gemini_service.evaluate_grind(text)

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

        prog = db.get_user_daily_progress(interaction.user.id, today_str)
        embed = build_grind_embed(interaction.user, evaluation, prog["total_points"])
        await interaction.followup.send(embed=embed)

        if evaluation["verdict"] == "ACCEPTED":
            await safe_react(interaction, "⚔️", "🧠")
        elif evaluation["verdict"] == "ROASTED":
            await safe_react(interaction, "🔥", "💀")

    @app_commands.command(name="quick", description="Natural language workout logging (e.g. 'did 45 pushups and ran 5k').")
    @app_commands.describe(text="Natural language workout text (e.g. '40 pushups, 12 pullups, ran 5k')")
    async def quick_cmd(self, interaction: discord.Interaction, text: str):
        if not await require_enrolled(interaction):
            return

        if len(text.strip()) < 3:
            await interaction.response.send_message("❌ Please specify your completed exercises and amounts.", ephemeral=True)
            return

        await interaction.response.defer()

        active_tasks = db.get_active_tasks()
        parsed = await groq_service.parse_quicklog(text, active_tasks)

        if parsed.get("suspicious"):
            await interaction.followup.send(
                "❌ **Log Rejected**: Amarok detected unrealistic volume. Log your actual completed numbers.",
                ephemeral=True
            )
            return

        matches = parsed.get("matches", [])
        if not matches:
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


async def setup(bot: commands.Bot):
    await bot.add_cog(WarriorCog(bot))


