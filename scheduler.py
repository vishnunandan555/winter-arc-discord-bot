"""
scheduler.py - Dedicated Channel Scheduler for Winter Arc Bot (Asia/Kolkata)

Runs background checks every 30 seconds for:
- 05:00 IST: Morning challenge kickoff with role ping in dedicated channel
- 16:30 IST: Afternoon check-in with group progress and role ping in dedicated channel
- 21:00 IST: Evening streak warning with role ping in dedicated channel
- Sun 10:00 IST: Weekly Community Recap with role ping in dedicated channel
- 00:00 IST: Midnight day finalization, podium broadcast, and month-end Phase Conclusion ceremonies
"""

import os
import logging
import asyncio
import gc
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
import discord
from discord.ext import tasks

import database as db
from config import BOT_TZ, DEFAULT_ROLE_ID
from ui.embeds import (
    build_morning_kickoff_embed,
    build_morning_kickoff_message,
    build_afternoon_checkin_embed,
    build_afternoon_checkin_message,
    build_evening_checkin_embed,
    build_evening_checkin_message,
    build_podium_embed,
    build_midnight_finalization_message,
    build_dm_morning_embed,
    build_dm_morning_message,
    build_dm_afternoon_embed,
    build_dm_afternoon_message,
    build_dm_evening_embed,
    build_dm_evening_message,
    build_weekly_state_of_the_pack_embed,
    build_weekly_recap_message,
    build_phase_podium_embed,
    build_phase_conclusion_message,
)
from ai import gemini_service
from phases import is_last_day_of_phase, get_next_phase, get_current_phase, get_phase_progress

logger = logging.getLogger("winter_arc.scheduler")


def get_now_ist() -> datetime:
    return datetime.now(BOT_TZ)


class WinterArcScheduler:
    """Automated daily broadcast scheduler for dedicated server channels and personal DMs."""

    def __init__(self, bot: discord.Client, db_path: str = db.DB_PATH):
        self.bot = bot
        self.db_path = db_path
        self._presence_index = 0
        self._last_morning_date = db.get_bot_state("last_morning_date", db_path=self.db_path)
        self._last_afternoon_date = db.get_bot_state("last_afternoon_date", db_path=self.db_path)
        self._last_evening_date = db.get_bot_state("last_evening_date", db_path=self.db_path)
        self._last_sunday_date = db.get_bot_state("last_sunday_date", db_path=self.db_path)
        self._last_midnight_date = db.get_bot_state("last_midnight_date", db_path=self.db_path)

    def start(self):
        if not self.ticker_loop.is_running():
            self.ticker_loop.start()
            logger.info("Scheduler ticker loop started (evaluating every 30s in Asia/Kolkata).")
        if not self.maintenance_and_presence_loop.is_running():
            self.maintenance_and_presence_loop.start()
            logger.info("Maintenance & presence loop started (evaluating every 5m).")

    def stop(self):
        if self.ticker_loop.is_running():
            self.ticker_loop.stop()
            logger.info("Scheduler ticker loop stopped.")
        if self.maintenance_and_presence_loop.is_running():
            self.maintenance_and_presence_loop.stop()
            logger.info("Maintenance & presence loop stopped.")

    # ==========================================
    # Main Ticker Loop (Every 30 seconds)
    # ==========================================

    @tasks.loop(seconds=30.0)
    async def ticker_loop(self):
        try:
            now = get_now_ist()
            today_str = now.date().isoformat()

            # 1. 05:00 - 05:05 IST - Morning Kickoff & Personal DMs
            if now.hour == 5 and now.minute < 5 and self._last_morning_date != today_str:
                self._last_morning_date = today_str
                db.set_bot_state("last_morning_date", today_str, db_path=self.db_path)
                logger.info(f"Triggering Morning Kickoff for {today_str}...")
                await self.broadcast_morning_kickoff()
                await self.dispatch_morning_dms()

            # 2. 16:30 - 16:35 IST - Afternoon Check-in
            if now.hour == 16 and 30 <= now.minute < 35 and self._last_afternoon_date != today_str:
                self._last_afternoon_date = today_str
                db.set_bot_state("last_afternoon_date", today_str, db_path=self.db_path)
                logger.info(f"Triggering Afternoon Check-in for {today_str}...")
                await self.broadcast_afternoon_checkin()
                await self.dispatch_afternoon_dms()

            # 3. 21:00 - 21:05 IST - Evening Streak Warning Channel Broadcast & Personal DMs (3h before midnight)
            if now.hour == 21 and now.minute < 5 and self._last_evening_date != today_str:
                self._last_evening_date = today_str
                db.set_bot_state("last_evening_date", today_str, db_path=self.db_path)
                logger.info(f"Triggering Evening Streak Warning for {today_str}...")
                await self.broadcast_evening_checkin()
                await self.dispatch_evening_dms()

            # 3.5 Sunday 10:00 - 10:05 IST - Weekly State of the Pack
            if now.weekday() == 6 and now.hour == 10 and now.minute < 5 and self._last_sunday_date != today_str:
                self._last_sunday_date = today_str
                db.set_bot_state("last_sunday_date", today_str, db_path=self.db_path)
                logger.info(f"Triggering Sunday State of the Pack for {today_str}...")
                await self.broadcast_sunday_state_of_the_pack()

            # 4. 00:00 - 00:05 IST - Midnight Finalization & Podium
            if now.hour == 0 and now.minute < 5 and self._last_midnight_date != today_str:
                self._last_midnight_date = today_str
                db.set_bot_state("last_midnight_date", today_str, db_path=self.db_path)
                logger.info(f"Triggering Midnight Finalization at {today_str}...")
                await self.broadcast_midnight_finalization()
        except Exception as e:
            logger.error(f"Error executing scheduler ticker loop iteration: {e}", exc_info=e)

    @ticker_loop.before_loop
    async def before_ticker(self):
        await self.bot.wait_until_ready()
        logger.info("Scheduler ticker loop synchronized with Discord Gateway.")

    @ticker_loop.error
    async def ticker_loop_error(self, error: Exception):
        logger.critical(f"Critical unhandled error in scheduler ticker_loop: {error}", exc_info=error)
        await asyncio.sleep(10)
        if not self.ticker_loop.is_running():
            logger.info("Restarting scheduler ticker_loop following unhandled exception...")
            try:
                self.ticker_loop.restart()
            except Exception as restart_err:
                logger.error(f"Failed to restart ticker_loop: {restart_err}", exc_info=restart_err)

    # ==========================================
    # Maintenance & Presence Loop (Every 5 minutes)
    # ==========================================

    @tasks.loop(minutes=5.0)
    async def maintenance_and_presence_loop(self):
        """Rotates presence and executes lightweight heap compaction."""
        # 1. Dynamic Presence Rotation
        try:
            enrolled_users = db.get_enrolled_users(db_path=self.db_path)
            count = len(enrolled_users)

            statuses = [
                discord.Activity(type=discord.ActivityType.listening, name="/help • Winter Arc"),
                discord.Activity(type=discord.ActivityType.watching, name=f"{count} Enrolled Warriors"),
                discord.Activity(type=discord.ActivityType.competing, name="Winter Arc (500 pts daily)"),
                discord.Activity(type=discord.ActivityType.playing, name="Defend the Flame | /streak"),
            ]
            activity = statuses[self._presence_index % len(statuses)]
            self._presence_index += 1
            await self.bot.change_presence(activity=activity, status=discord.Status.online)
        except Exception as e:
            logger.debug(f"Could not rotate presence: {e}")

        # 2. Automated Low-Memory Heap Compaction
        try:
            collected = gc.collect()
            if collected > 100:
                logger.debug(f"Automated GC sweep collected {collected} unreferenced objects.")
        except Exception as e:
            logger.debug(f"Error during GC sweep: {e}")

    @maintenance_and_presence_loop.before_loop
    async def before_maintenance(self):
        await self.bot.wait_until_ready()

    @maintenance_and_presence_loop.error
    async def maintenance_loop_error(self, error: Exception):
        logger.critical(f"Critical unhandled error in maintenance_and_presence_loop: {error}", exc_info=error)
        await asyncio.sleep(10)
        if not self.maintenance_and_presence_loop.is_running():
            logger.info("Restarting maintenance_and_presence_loop following unhandled exception...")
            try:
                self.maintenance_and_presence_loop.restart()
            except Exception as restart_err:
                logger.error(f"Failed to restart maintenance_and_presence_loop: {restart_err}", exc_info=restart_err)

    # ==========================================
    # Channel & Ping Resolution
    # ==========================================

    def _get_target_channel_and_ping(self, guild: discord.Guild):
        """Returns the configured dedicated TextChannel and role ping string for a guild."""
        target_channel = None
        settings = db.get_server_settings(guild.id, db_path=self.db_path)
        channel_id = settings.get("channel_id")
        if channel_id:
            target_channel = guild.get_channel(channel_id)

        # Fallback 1: check WINTER_ARC_CHANNEL_ID, DAILY_RESULTS_CHANNEL_ID, or LOG_CHANNEL_ID env vars or config
        if not target_channel:
            from config import DEFAULT_CHANNEL_ID
            env_id = os.getenv("WINTER_ARC_CHANNEL_ID") or os.getenv("DAILY_RESULTS_CHANNEL_ID") or os.getenv("LOG_CHANNEL_ID") or str(DEFAULT_CHANNEL_ID)
            if env_id and env_id.strip().isdigit() and int(env_id.strip()) != 0:
                target_channel = guild.get_channel(int(env_id.strip()))

        # Fallback 2: Auto-discover #winter-arc, #bot_chat, or #server_logs
        if not target_channel:
            for keyword in ["winter-arc", "bot_chat", "server_logs"]:
                for ch in guild.text_channels:
                    if keyword in ch.name.lower():
                        perms = ch.permissions_for(guild.me)
                        if perms.send_messages:
                            target_channel = ch
                            break
                if target_channel:
                    break

        if not target_channel or not isinstance(target_channel, discord.TextChannel):
            return None, ""

        role_ping = ""
        role_id = settings.get("role_id", 0) or DEFAULT_ROLE_ID
        if role_id:
            role = guild.get_role(role_id)
            if role:
                role_ping = f"{role.mention} "

        if not role_ping:
            for r in guild.roles:
                if r.name.lower() in ["winter arc", "winterarc", "the winter arc"]:
                    role_ping = f"{r.mention} "
                    break
        return target_channel, role_ping

    # ==========================================
    # Broadcast Methods
    # ==========================================

    async def _send_chunked_message(
        self,
        channel: discord.TextChannel,
        content: str,
        allowed_mentions: Optional[discord.AllowedMentions] = None
    ):
        """Sends content to a text channel, safely splitting into chunks under 2000 chars if necessary."""
        if len(content) <= 2000:
            await channel.send(content=content, allowed_mentions=allowed_mentions)
            return

        paragraphs = content.split("\n\n")
        current_chunk = ""
        for p in paragraphs:
            if len(current_chunk) + len(p) + 2 > 1950:
                if current_chunk:
                    await channel.send(content=current_chunk.strip(), allowed_mentions=allowed_mentions)
                    current_chunk = ""
            current_chunk += p + "\n\n"
        if current_chunk.strip():
            await channel.send(content=current_chunk.strip(), allowed_mentions=allowed_mentions)

    async def broadcast_morning_kickoff(
        self,
        target_channel: discord.TextChannel = None,
        role_ping: str = "",
        user_context: Optional[Dict[str, Any]] = None,
        recent_history: Optional[List[Dict[str, Any]]] = None,
        override_quote: Optional[str] = None,
    ):
        """Sends morning daily motivation and active challenge targets to dedicated channel."""
        active_tasks = db.get_active_tasks()
        now = get_now_ist()
        date_display = now.strftime("%A, %B %d, %Y")

        quote = override_quote or ""
        if not quote:
            try:
                quote = await gemini_service.generate_reminder_motivation(
                    reminder_type="morning",
                    user_context=user_context,
                    recent_history=recent_history,
                )
            except Exception as e:
                logger.debug(f"Could not generate AI morning quote: {e}")

        curr_phase = get_current_phase()
        phase_progress = get_phase_progress(curr_phase) if curr_phase else None
        allowed_mentions = discord.AllowedMentions(users=True, roles=True, everyone=False)

        if target_channel:
            msg = build_morning_kickoff_message(
                active_tasks=active_tasks,
                date_display=date_display,
                curr_phase=curr_phase,
                phase_progress=phase_progress,
                quote=quote,
                role_ping=role_ping,
            )
            await self._send_chunked_message(target_channel, msg, allowed_mentions=allowed_mentions)
            return

        for guild in self.bot.guilds:
            channel, ping = self._get_target_channel_and_ping(guild)
            if channel:
                try:
                    msg = build_morning_kickoff_message(
                        active_tasks=active_tasks,
                        date_display=date_display,
                        curr_phase=curr_phase,
                        phase_progress=phase_progress,
                        quote=quote,
                        role_ping="",
                    )
                    await self._send_chunked_message(channel, msg, allowed_mentions=allowed_mentions)
                except Exception as e:
                    logger.warning(f"Could not send morning kickoff to {channel.name} in {guild.name}: {e}")

    async def broadcast_afternoon_checkin(
        self,
        target_channel: discord.TextChannel = None,
        role_ping: str = "",
        user_context: Optional[Dict[str, Any]] = None,
        recent_history: Optional[List[Dict[str, Any]]] = None,
        override_quote: Optional[str] = None,
    ):
        """Sends afternoon check-in showing enrolled group progress to dedicated channel."""
        now = get_now_ist()
        today_str = now.strftime("%Y-%m-%d")
        enrolled_users = db.get_enrolled_users()

        quote = override_quote or ""
        if not quote:
            try:
                quote = await gemini_service.generate_reminder_motivation(
                    reminder_type="afternoon",
                    user_context=user_context,
                    recent_history=recent_history,
                )
            except Exception as e:
                logger.debug(f"Could not generate AI afternoon quote: {e}")

        allowed_mentions = discord.AllowedMentions(users=True, roles=True, everyone=False)

        if target_channel:
            msg = build_afternoon_checkin_message(
                enrolled_users=enrolled_users,
                today_str=today_str,
                quote=quote,
                role_ping=role_ping,
            )
            await self._send_chunked_message(target_channel, msg, allowed_mentions=allowed_mentions)
            return

        for guild in self.bot.guilds:
            channel, ping = self._get_target_channel_and_ping(guild)
            if channel:
                try:
                    msg = build_afternoon_checkin_message(
                        enrolled_users=enrolled_users,
                        today_str=today_str,
                        quote=quote,
                        role_ping="",
                    )
                    await self._send_chunked_message(channel, msg, allowed_mentions=allowed_mentions)
                except Exception as e:
                    logger.warning(f"Could not send afternoon check-in to {channel.name} in {guild.name}: {e}")

    async def broadcast_evening_checkin(
        self,
        target_channel: discord.TextChannel = None,
        role_ping: str = "",
        user_context: Optional[Dict[str, Any]] = None,
        recent_history: Optional[List[Dict[str, Any]]] = None,
        override_quote: Optional[str] = None,
    ):
        """Sends evening streak alert showing completed & pending warriors with authentic callouts to dedicated channel."""
        now = get_now_ist()
        today_str = now.strftime("%Y-%m-%d")
        enrolled_users = db.get_enrolled_users(db_path=self.db_path)

        warriors_data = []
        for u in enrolled_users:
            prog = db.get_user_daily_progress(u["discord_id"], today_str, db_path=self.db_path)
            streak = db.calculate_streak(u["discord_id"], today_str, db_path=self.db_path)
            warriors_data.append({
                "discord_id": u["discord_id"],
                "username": u.get("username", "Warrior"),
                "points": prog["total_points"],
                "max_points": prog["max_possible_points"],
                "streak": streak,
                "perfect_day": prog["perfect_day"],
            })

        callouts, stoic_quote = await gemini_service.generate_evening_alert_data(
            warriors_data=warriors_data,
            override_quote=override_quote,
        )

        allowed_mentions = discord.AllowedMentions(users=True, roles=True, everyone=False)

        if target_channel:
            msg = build_evening_checkin_message(
                warriors_data=warriors_data,
                callouts=callouts,
                stoic_quote=stoic_quote,
                role_ping=role_ping,
            )
            await self._send_chunked_message(target_channel, msg, allowed_mentions=allowed_mentions)
            return

        for guild in self.bot.guilds:
            channel, ping = self._get_target_channel_and_ping(guild)
            if channel:
                try:
                    msg = build_evening_checkin_message(
                        warriors_data=warriors_data,
                        callouts=callouts,
                        stoic_quote=stoic_quote,
                        role_ping="",
                    )
                    await self._send_chunked_message(channel, msg, allowed_mentions=allowed_mentions)
                except Exception as e:
                    logger.warning(f"Could not send evening streak alert to {channel.name} in {guild.name}: {e}")

    async def broadcast_midnight_finalization(self, target_channel: discord.TextChannel = None, role_ping: str = "") -> discord.Embed:
        """Finalizes day's results, stores daily_summaries, and publishes podium with AI Toast & Roast."""
        now = get_now_ist()
        yesterday = (now - timedelta(days=1)).date().isoformat()

        leaderboard = db.finalize_daily_summaries(yesterday)
        embed = build_podium_embed(yesterday, leaderboard)

        # Notify users whose streak was preserved by an automated Streak Shield
        for entry in leaderboard:
            if entry.get("auto_shield_applied"):
                user_id = entry["discord_id"]
                try:
                    target_user = self.bot.get_user(user_id)
                    if not target_user:
                        target_user = await self.bot.fetch_user(user_id)
                    if target_user:
                        streak = entry.get("current_streak", 0)
                        shields_left = entry.get("shields_left", 0)
                        shield_dm_embed = discord.Embed(
                            title="🛡️ Streak Shield Automatically Deployed!",
                            description=(
                                f"**{target_user.display_name}**, you did not log your 30 points for **{yesterday}**.\n\n"
                                f"An available **Streak Shield** was automatically deployed during midnight checking to protect your streak!\n\n"
                                f"🔥 **Active Streak**: **{streak} days**\n"
                                f"🛡️ **Remaining Shields**: **{shields_left} / 2**\n\n"
                                f"{'⚠️ **0 shields left!** Log at least 30 points today to prevent your streak from breaking.' if shields_left == 0 else 'Keep grinding today to stay consistent and rebuild your shields at your next 7-day milestone.'}"
                            ),
                            color=0x00D2FF
                        )
                        shield_dm_embed.set_footer(text="Winter Arc • Automatic Midnight Streak Protection")
                        await target_user.send(embed=shield_dm_embed)
                except Exception as e:
                    logger.debug(f"Could not send auto-shield DM to user {user_id}: {e}")

        # AI Daily Toast & Roast
        ai_recap = ""
        try:
            grind_highlights = db.get_daily_grind_highlights(yesterday)
            enrolled_users = db.get_enrolled_users()
            active_yesterday = {e["discord_id"] for e in leaderboard if e["points"] > 0}
            slacker_count = len(enrolled_users) - len(active_yesterday)

            ai_recap = await gemini_service.generate_daily_toast_and_roast(
                podium_data=leaderboard,
                grind_highlights=grind_highlights,
                slacker_count=max(0, slacker_count),
                total_enrolled=len(enrolled_users)
            )
            if ai_recap:
                embed.description = f"> {ai_recap}\n\n" + embed.description
        except Exception as e:
            logger.debug(f"Could not append AI daily recap: {e}")

        # Update web dashboard statistics JSON
        try:
            from export_web_stats import export_stats_to_json
            export_stats_to_json()
        except Exception as e:
            logger.warning(f"Could not auto-export web stats: {e}")

        allowed_mentions = discord.AllowedMentions(users=True, roles=True, everyone=False)

        # Build individual channel alert messages for shields used and broken streaks
        individual_alerts = []
        for entry in leaderboard:
            u_id = entry.get("discord_id")
            if not u_id:
                continue

            if entry.get("auto_shield_applied"):
                streak = entry.get("current_streak", 0)
                shields_left = entry.get("shields_left", 0)
                if shields_left == 1:
                    alert = f"🛡️ <@{u_id}> Your Streak Shield just saved your **{streak}-day streak** at midnight! You have **1 shield left**. Lock in today!"
                else:
                    alert = f"🛡️ <@{u_id}> Your Streak Shield just saved your **{streak}-day streak** at midnight! That was your **last shield**! Make sure to log today or your streak breaks!"
                individual_alerts.append(alert)

            elif entry.get("streak_broken"):
                broken_streak = entry.get("broken_streak_count", 0)
                alert = f"💔 <@{u_id}> You missed yesterday and had no Streak Shields left. Your **{broken_streak}-day streak** has broken! Start fresh and rebuild today!"
                individual_alerts.append(alert)

        if target_channel:
            msg = build_midnight_finalization_message(
                date_str=yesterday,
                leaderboard=leaderboard,
                ai_recap=ai_recap,
                role_ping=role_ping,
            )
            await self._send_chunked_message(target_channel, msg, allowed_mentions=allowed_mentions)
            for alert in individual_alerts:
                try:
                    await target_channel.send(alert, allowed_mentions=allowed_mentions)
                except Exception as e:
                    logger.warning(f"Could not send streak alert to {target_channel.name}: {e}")
        else:
            for guild in self.bot.guilds:
                channel, ping = self._get_target_channel_and_ping(guild)
                if channel:
                    try:
                        msg = build_midnight_finalization_message(
                            date_str=yesterday,
                            leaderboard=leaderboard,
                            ai_recap=ai_recap,
                            role_ping="",
                        )
                        await self._send_chunked_message(channel, msg, allowed_mentions=allowed_mentions)
                        for alert in individual_alerts:
                            try:
                                await channel.send(alert, allowed_mentions=allowed_mentions)
                            except Exception as e:
                                logger.warning(f"Could not post streak alert to {channel.name} in {guild.name}: {e}")
                    except Exception as e:
                        logger.warning(f"Could not post midnight finalization to {channel.name} in {guild.name}: {e}")

        # Check if yesterday concluded a Winter Arc phase
        is_phase_end, concluded_phase = is_last_day_of_phase(yesterday)
        if is_phase_end and concluded_phase:
            logger.info(f"Yesterday ({yesterday}) marked the end of Phase {concluded_phase['id']}: {concluded_phase['name']}! Launching ceremony...")
            await asyncio.sleep(2)
            await self.broadcast_phase_conclusion(concluded_phase, target_channel=target_channel, role_ping=role_ping)

        return embed

    async def broadcast_phase_conclusion(self, phase_dict: Dict[str, Any], target_channel: discord.TextChannel = None, role_ping: str = "") -> Optional[discord.Embed]:
        """
        Runs the official End-of-Phase ceremony:
        1. Generates an automated standalone snapshot database for user cards.
        2. Dispatches Phase Podium Embed.
        3. Dispatches Gemini AI Phase Proclamation (Top 3 praise, bottom roasts, next phase unlock).
        """
        phase_id = phase_dict["id"]
        logger.info(f"Triggering Phase {phase_id} ({phase_dict['name']}) conclusion ceremony...")

        # 1. Create phase snapshot database
        try:
            snapshot_path = db.archive_phase_snapshot(phase_id, db_path=self.db_path)
            logger.info(f"Phase {phase_id} snapshot successfully archived to {snapshot_path}")
        except Exception as e:
            logger.error(f"Failed to create phase {phase_id} snapshot: {e}", exc_info=True)

        # 2. Compute phase leaderboard and next phase info
        phase_lb = db.get_phase_leaderboard(phase_id, db_path=self.db_path)
        next_phase = get_next_phase(phase_id)
        podium_embed = build_phase_podium_embed(phase_dict, phase_lb)

        # 3. Generate Gemini proclamation
        try:
            bottom_warriors = [w for w in phase_lb if w["total_points"] < 100]
            ceremony_speech = await gemini_service.generate_phase_ceremony(
                phase_info=phase_dict,
                top_warriors=phase_lb[:3],
                bottom_warriors=bottom_warriors,
                next_phase_info=next_phase
            )
        except Exception as e:
            logger.warning(f"Could not generate Gemini phase ceremony speech: {e}")
            ceremony_speech = ""

        allowed_mentions = discord.AllowedMentions(users=True, roles=True, everyone=False)
        msg = build_phase_conclusion_message(
            phase_dict=phase_dict,
            phase_lb=phase_lb,
            ceremony_speech=ceremony_speech,
            next_phase_dict=next_phase,
            role_ping=role_ping,
        )

        if target_channel:
            await self._send_chunked_message(target_channel, msg, allowed_mentions=allowed_mentions)
            return podium_embed

        for guild in self.bot.guilds:
            channel, ping = self._get_target_channel_and_ping(guild)
            if channel:
                try:
                    guild_msg = build_phase_conclusion_message(
                        phase_dict=phase_dict,
                        phase_lb=phase_lb,
                        ceremony_speech=ceremony_speech,
                        next_phase_dict=next_phase,
                        role_ping=ping,
                    )
                    await self._send_chunked_message(channel, guild_msg, allowed_mentions=allowed_mentions)
                except Exception as e:
                    logger.warning(f"Could not post phase conclusion to {channel.name} in {guild.name}: {e}")

        return podium_embed

    async def broadcast_sunday_state_of_the_pack(self, target_channel: discord.TextChannel = None, role_ping: str = "") -> discord.Embed:
        """Broadcasts the weekly Sunday State of the Pack address to dedicated channels."""
        now = get_now_ist()
        end_date = now.date().isoformat()
        start_date = (now.date() - timedelta(days=6)).isoformat()

        weekly_grinds = db.get_weekly_grind_highlights(start_date, end_date, db_path=self.db_path)
        weekly_lb = db.get_weekly_leaderboard(start_date, end_date, db_path=self.db_path)
        if not weekly_lb:
            weekly_lb = db.get_overall_leaderboard(db_path=self.db_path)
        top_warriors = weekly_lb[:5]
        enrolled_users = db.get_enrolled_users(db_path=self.db_path)

        # Compute weekly pack cumulative volume across all users
        weekly_volume = {"total_pushups": 0, "total_pullups": 0, "total_squats": 0, "total_situps": 0, "total_km": 0.0}
        try:
            with db.get_connection(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT t.name, COALESCE(SUM(l.amount), 0) as total_vol
                    FROM tasks t
                    LEFT JOIN daily_logs l ON t.id = l.task_id AND l.date >= ? AND l.date <= ?
                    GROUP BY t.id;
                """, (start_date, end_date))
                for r in cursor.fetchall():
                    name_l = r["name"].lower()
                    vol = float(r["total_vol"])
                    if "push" in name_l:
                        weekly_volume["total_pushups"] = int(vol)
                    elif "pull" in name_l:
                        weekly_volume["total_pullups"] = int(vol)
                    elif "squat" in name_l:
                        weekly_volume["total_squats"] = int(vol)
                    elif "sit" in name_l:
                        weekly_volume["total_situps"] = int(vol)
                    elif "run" in name_l:
                        weekly_volume["total_km"] = round(vol, 1)

                # Count ghost members (enrolled users who logged 0 points all week)
                cursor.execute("""
                    SELECT COUNT(DISTINCT user_id) as active_count
                    FROM daily_summaries
                    WHERE date >= ? AND date <= ? AND points > 0;
                """, (start_date, end_date))
                active_wk = cursor.fetchone()["active_count"]
                ghosts_count = max(0, len(enrolled_users) - active_wk)
        except Exception as e:
            logger.warning(f"Error aggregating weekly stats: {e}")
            ghosts_count = 0

        ai_speech = await gemini_service.generate_weekly_state_of_the_pack(
            weekly_stats=weekly_volume,
            top_warriors=top_warriors,
            weekly_grinds=weekly_grinds,
            ghosts_count=ghosts_count
        )
        if not ai_speech:
            ai_speech = "Week 1 is in the books. Execution continues tomorrow at 00:00 IST."

        embed = build_weekly_state_of_the_pack_embed(weekly_volume, top_warriors, ai_speech)
        allowed_mentions = discord.AllowedMentions(users=True, roles=True, everyone=False)

        if target_channel:
            msg = build_weekly_recap_message(
                weekly_stats=weekly_volume,
                top_warriors=top_warriors,
                ai_speech=ai_speech,
                role_ping=role_ping,
                date_dt=now,
            )
            await self._send_chunked_message(target_channel, msg, allowed_mentions=allowed_mentions)
            return embed

        for guild in self.bot.guilds:
            channel, ping = self._get_target_channel_and_ping(guild)
            if channel:
                try:
                    msg = build_weekly_recap_message(
                        weekly_stats=weekly_volume,
                        top_warriors=top_warriors,
                        ai_speech=ai_speech,
                        role_ping=ping,
                        date_dt=now,
                    )
                    await self._send_chunked_message(channel, msg, allowed_mentions=allowed_mentions)
                except Exception as e:
                    logger.warning(f"Could not post Weekly Recap to {channel.name} in {guild.name}: {e}")

        return embed

    # ==========================================
    # Private Direct Messaging Dispatchers (Concurrent Dispatch)
    # ==========================================

    async def _send_single_morning_dm(self, user_record: Dict[str, Any], active_tasks: List[Dict[str, Any]], today_str: str, date_display: str) -> bool:
        discord_id = user_record["discord_id"]
        try:
            discord_user = self.bot.get_user(discord_id)
            if not discord_user:
                discord_user = await self.bot.fetch_user(discord_id)
            if discord_user:
                streak = db.calculate_streak(discord_id, today_str, db_path=self.db_path)
                briefing_context = db.get_user_weekly_briefing_context(discord_id, db_path=self.db_path)
                curr_phase = get_current_phase()
                phase_progress = get_phase_progress(curr_phase) if curr_phase else None
                quote = ""
                try:
                    quote = await gemini_service.generate_personalized_morning_briefing(briefing_context)
                except Exception as e:
                    logger.debug(f"Could not generate AI DM quote: {e}")

                msg = build_dm_morning_message(
                    tasks=active_tasks,
                    streak=streak,
                    date_display=date_display,
                    quote=quote,
                    curr_phase=curr_phase,
                    phase_progress=phase_progress,
                )
                await discord_user.send(content=msg)
                return True
        except discord.Forbidden:
            logger.debug(f"Cannot send morning DM to user {discord_id} (DMs closed).")
        except Exception as e:
            logger.warning(f"Error sending morning DM to user {discord_id}: {e}")
        return False

    async def dispatch_morning_dms(self):
        """Dispatches personal morning briefing DMs concurrently to opted-in members."""
        users = db.get_opted_in_dm_users(category="morning", db_path=self.db_path)
        if not users:
            return

        active_tasks = db.get_active_tasks(db_path=self.db_path)
        now = get_now_ist()
        today_str = now.strftime("%Y-%m-%d")
        date_display = now.strftime("%A, %B %d, %Y")

        sem = asyncio.Semaphore(2)

        async def _bounded_morning_dm(u):
            async with sem:
                res = await self._send_single_morning_dm(u, active_tasks, today_str, date_display)
                await asyncio.sleep(0.1)
                return res

        tasks = [_bounded_morning_dm(u) for u in users]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        dispatched = sum(1 for r in results if r is True)
        logger.info(f"Morning briefing DMs dispatched to {dispatched}/{len(users)} member(s).")

    async def _send_single_afternoon_dm(self, user_record: Dict[str, Any], today_str: str) -> bool:
        discord_id = user_record["discord_id"]
        try:
            discord_user = self.bot.get_user(discord_id)
            if not discord_user:
                discord_user = await self.bot.fetch_user(discord_id)
            if discord_user:
                prog = db.get_user_daily_progress(discord_id, today_str, db_path=self.db_path)
                streak = db.calculate_streak(discord_id, today_str, db_path=self.db_path)
                msg = build_dm_afternoon_message(
                    user_name=discord_user.display_name,
                    points=prog.get("total_points", 0),
                    max_points=prog.get("max_possible_points", 500),
                    streak=streak,
                )
                await discord_user.send(content=msg)
                return True
        except discord.Forbidden:
            logger.debug(f"Cannot send afternoon DM to user {discord_id} (DMs closed).")
        except Exception as e:
            logger.warning(f"Error sending afternoon DM to user {discord_id}: {e}")
        return False

    async def dispatch_afternoon_dms(self):
        """Dispatches personal afternoon check-in DMs concurrently to opted-in members."""
        users = db.get_opted_in_dm_users(category="afternoon", db_path=self.db_path)
        if not users:
            return

        now = get_now_ist()
        today_str = now.strftime("%Y-%m-%d")

        sem = asyncio.Semaphore(2)

        async def _bounded_afternoon_dm(u):
            async with sem:
                res = await self._send_single_afternoon_dm(u, today_str)
                await asyncio.sleep(0.1)
                return res

        tasks = [_bounded_afternoon_dm(u) for u in users]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        dispatched = sum(1 for r in results if r is True)
        logger.info(f"Afternoon check-in DMs dispatched to {dispatched}/{len(users)} member(s).")

    async def _send_single_evening_dm(self, user_record: Dict[str, Any], today_str: str) -> bool:
        discord_id = user_record["discord_id"]
        try:
            discord_user = self.bot.get_user(discord_id)
            if not discord_user:
                discord_user = await self.bot.fetch_user(discord_id)
            if discord_user:
                progress = db.get_user_daily_progress(discord_id, today_str, db_path=self.db_path)
                streak = db.calculate_streak(discord_id, today_str, db_path=self.db_path)
                shield_status = db.get_user_shield_status(discord_id, db_path=self.db_path)
                quote = ""
                try:
                    quote = await gemini_service.generate_reminder_motivation(
                        reminder_type="evening",
                        user_context={
                            "username": discord_user.display_name,
                            "streak": streak,
                            "today_points": progress.get("total_points", 0),
                        },
                    )
                except Exception as e:
                    logger.debug(f"Could not generate AI DM quote: {e}")

                msg = build_dm_evening_message(
                    user_name=discord_user.display_name,
                    points=progress.get("total_points", 0),
                    max_points=progress.get("max_possible_points", 500),
                    streak=streak,
                    shields=shield_status.get("frost_shields", 0),
                    quote=quote,
                )
                await discord_user.send(content=msg)
                return True
        except discord.Forbidden:
            logger.debug(f"Cannot send evening DM to user {discord_id} (DMs closed).")
        except Exception as e:
            logger.warning(f"Error sending evening DM to user {discord_id}: {e}")
        return False

    async def dispatch_evening_dms(self):
        """Dispatches personal evening streak warning DMs concurrently to opted-in members."""
        users = db.get_opted_in_dm_users(category="evening", db_path=self.db_path)
        if not users:
            return

        now = get_now_ist()
        today_str = now.strftime("%Y-%m-%d")

        sem = asyncio.Semaphore(2)

        async def _bounded_evening_dm(u):
            async with sem:
                res = await self._send_single_evening_dm(u, today_str)
                await asyncio.sleep(0.1)
                return res

        tasks = [_bounded_evening_dm(u) for u in users]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        dispatched = sum(1 for r in results if r is True)
        logger.info(f"Evening streak alert DMs dispatched to {dispatched}/{len(users)} member(s).")

