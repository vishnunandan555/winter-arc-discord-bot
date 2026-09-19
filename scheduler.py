"""
scheduler.py - Dedicated Channel Scheduler for Winter Arc Bot (Asia/Kolkata)

Runs background checks every 30 seconds for:
- 05:00 IST: Morning challenge kickoff with role ping in dedicated channel
- 16:30 IST: Afternoon check-in with group progress and role ping in dedicated channel
- 00:00 IST: Midnight day finalization & podium broadcast in dedicated channel
"""

import os
import logging
import asyncio
import gc
from datetime import datetime, date, timedelta
import discord
from discord.ext import tasks

import database as db
from config import BOT_TZ, DEFAULT_ROLE_ID
from ui.embeds import (
    build_morning_kickoff_embed,
    build_afternoon_checkin_embed,
    build_evening_checkin_embed,
    build_podium_embed,
    build_dm_morning_embed,
    build_dm_evening_embed,
    build_weekly_state_of_the_pack_embed,
)
from ai import gemini_service

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

        # 3. 21:00 - 21:05 IST - Evening Streak Warning Channel Broadcast & Personal DMs (3h before midnight)
        if now.hour == 21 and now.minute < 5 and self._last_evening_date != today_str:
            self._last_evening_date = today_str
            db.set_bot_state("last_evening_date", today_str, db_path=self.db_path)
            logger.info(f"Triggering Evening Streak Warning for {today_str}...")
            await self.broadcast_evening_checkin()
            await self.dispatch_evening_dms()

        # 3.5 Sunday 20:00 - 20:05 IST - Weekly State of the Pack
        if now.weekday() == 6 and now.hour == 20 and now.minute < 5 and self._last_sunday_date != today_str:
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

    @ticker_loop.before_loop
    async def before_ticker(self):
        await self.bot.wait_until_ready()
        logger.info("Scheduler ticker loop synchronized with Discord Gateway.")

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
                discord.Activity(type=discord.ActivityType.listening, name="Amarok | /help"),
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

        # Fallback 1: check DAILY_RESULTS_CHANNEL_ID or LOG_CHANNEL_ID env vars
        if not target_channel:
            env_id = os.getenv("DAILY_RESULTS_CHANNEL_ID") or os.getenv("LOG_CHANNEL_ID")
            if env_id and env_id.strip().isdigit():
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

    async def broadcast_morning_kickoff(self, target_channel: discord.TextChannel = None, role_ping: str = ""):
        """Sends morning daily motivation and active challenge targets to dedicated channel."""
        active_tasks = db.get_active_tasks()
        now = get_now_ist()
        date_display = now.strftime("%A, %B %d, %Y")

        embed = build_morning_kickoff_embed(active_tasks, date_display)

        if target_channel:
            await target_channel.send(content=f"{role_ping}🌅 **Morning Kickoff**", embed=embed)
            return

        for guild in self.bot.guilds:
            channel, ping = self._get_target_channel_and_ping(guild)
            if channel:
                try:
                    await channel.send(content=f"{ping}🌅 **Morning Kickoff**", embed=embed)
                except Exception as e:
                    logger.warning(f"Could not send morning kickoff to {channel.name} in {guild.name}: {e}")

    async def broadcast_afternoon_checkin(self, target_channel: discord.TextChannel = None, role_ping: str = ""):
        """Sends afternoon check-in showing enrolled group progress to dedicated channel."""
        now = get_now_ist()
        today_str = now.strftime("%Y-%m-%d")
        enrolled_users = db.get_enrolled_users()

        embed = build_afternoon_checkin_embed(enrolled_users, today_str)

        if target_channel:
            await target_channel.send(content=f"{role_ping}⏰ **Afternoon Check-in**", embed=embed)
            return

        for guild in self.bot.guilds:
            channel, ping = self._get_target_channel_and_ping(guild)
            if channel:
                try:
                    await channel.send(content=f"{ping}⏰ **Afternoon Check-in**", embed=embed)
                except Exception as e:
                    logger.warning(f"Could not send afternoon check-in to {channel.name} in {guild.name}: {e}")

    async def broadcast_evening_checkin(self, target_channel: discord.TextChannel = None, role_ping: str = ""):
        """Sends evening streak alert showing completed & pending warriors to dedicated channel."""
        now = get_now_ist()
        today_str = now.strftime("%Y-%m-%d")
        enrolled_users = db.get_enrolled_users(db_path=self.db_path)

        embed = build_evening_checkin_embed(enrolled_users, today_str)

        if target_channel:
            await target_channel.send(content=f"{role_ping}🌙 **Evening Streak Alert — Final Call (3h Left)**", embed=embed)
            return

        for guild in self.bot.guilds:
            channel, ping = self._get_target_channel_and_ping(guild)
            if channel:
                try:
                    await channel.send(content=f"{ping}🌙 **Evening Streak Alert — Final Call (3h Left)**", embed=embed)
                except Exception as e:
                    logger.warning(f"Could not send evening streak alert to {channel.name} in {guild.name}: {e}")

    async def broadcast_midnight_finalization(self, target_channel: discord.TextChannel = None, role_ping: str = "") -> discord.Embed:
        """Finalizes day's results, stores daily_summaries, and publishes podium with AI Toast & Roast."""
        now = get_now_ist()
        yesterday = (now - timedelta(days=1)).date().isoformat()

        leaderboard = db.finalize_daily_summaries(yesterday)
        embed = build_podium_embed(yesterday, leaderboard)

        # AI Daily Toast & Roast
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
                embed.description = f"🐺 **Amarok's Daily Toast & Roast**:\n> *\"{ai_recap}\"*\n\n" + embed.description
        except Exception as e:
            logger.debug(f"Could not append AI daily recap: {e}")

        # Update web dashboard statistics JSON
        try:
            from export_web_stats import export_stats_to_json
            export_stats_to_json()
        except Exception as e:
            logger.warning(f"Could not auto-export web stats: {e}")

        if target_channel:
            await target_channel.send(content=f"{role_ping}🌙 **Day Finalized!**", embed=embed)
            return embed

        for guild in self.bot.guilds:
            channel, ping = self._get_target_channel_and_ping(guild)
            if channel:
                try:
                    await channel.send(content=f"{ping}🌙 **Day Finalized!**", embed=embed)
                except Exception as e:
                    logger.warning(f"Could not post midnight finalization to {channel.name} in {guild.name}: {e}")

        return embed

    async def broadcast_sunday_state_of_the_pack(self, target_channel: discord.TextChannel = None, role_ping: str = "") -> discord.Embed:
        """Broadcasts the weekly Sunday State of the Pack address to dedicated channels."""
        now = get_now_ist()
        end_date = now.date().isoformat()
        start_date = (now.date() - timedelta(days=6)).isoformat()

        weekly_grinds = db.get_weekly_grind_highlights(start_date, end_date, db_path=self.db_path)
        overall_data = db.get_overall_leaderboard(db_path=self.db_path)
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
            top_warriors=overall_data[:3],
            weekly_grinds=weekly_grinds,
            ghosts_count=ghosts_count
        )
        if not ai_speech:
            ai_speech = "The pack moves forward. Honor to the consistent, cold comfort to the idle. Monday 05:00 awaits."

        embed = build_weekly_state_of_the_pack_embed(weekly_volume, overall_data[:3], ai_speech)

        if target_channel:
            await target_channel.send(content=f"{role_ping}🐺 **State of the Pack**", embed=embed)
            return embed

        for guild in self.bot.guilds:
            channel, ping = self._get_target_channel_and_ping(guild)
            if channel:
                try:
                    await channel.send(content=f"{ping}🐺 **State of the Pack**", embed=embed)
                except Exception as e:
                    logger.warning(f"Could not post State of the Pack to {channel.name} in {guild.name}: {e}")

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
                embed = build_dm_morning_embed(active_tasks, streak, date_display)
                await discord_user.send(embed=embed)
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

        tasks = [self._send_single_morning_dm(u, active_tasks, today_str, date_display) for u in users]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        dispatched = sum(1 for r in results if r is True)
        logger.info(f"Morning briefing DMs dispatched to {dispatched}/{len(users)} member(s).")

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
                embed = build_dm_evening_embed(discord_user, progress, streak, shield_status)
                await discord_user.send(embed=embed)
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

        tasks = [self._send_single_evening_dm(u, today_str) for u in users]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        dispatched = sum(1 for r in results if r is True)
        logger.info(f"Evening streak alert DMs dispatched to {dispatched}/{len(users)} member(s).")

