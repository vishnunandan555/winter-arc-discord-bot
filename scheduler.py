"""
scheduler.py - Dedicated Channel Scheduler for Winter Arc Bot (Asia/Kolkata)

Runs background checks every 30 seconds for:
- 05:00 IST: Morning challenge kickoff with role ping in dedicated channel
- 16:30 IST: Afternoon check-in with group progress and role ping in dedicated channel
- 00:00 IST: Midnight day finalization & podium broadcast in dedicated channel
"""

import logging
from datetime import datetime, date, timedelta
import discord
from discord.ext import tasks

import database as db
from config import BOT_TZ, DEFAULT_ROLE_ID
from ui.embeds import (
    build_morning_kickoff_embed,
    build_afternoon_checkin_embed,
    build_podium_embed,
)

logger = logging.getLogger("winter_arc.scheduler")


def get_now_ist() -> datetime:
    return datetime.now(BOT_TZ)


class WinterArcScheduler:
    """Automated daily broadcast scheduler for dedicated server channels."""

    def __init__(self, bot: discord.Client):
        self.bot = bot
        self._last_morning_date = None
        self._last_afternoon_date = None
        self._last_midnight_date = None

    def start(self):
        if not self.ticker_loop.is_running():
            self.ticker_loop.start()
            logger.info("Scheduler ticker loop started (evaluating every 30s in Asia/Kolkata).")

    def stop(self):
        if self.ticker_loop.is_running():
            self.ticker_loop.stop()
            logger.info("Scheduler ticker loop stopped.")

    # ==========================================
    # Main Ticker Loop (Every 30 seconds)
    # ==========================================

    @tasks.loop(seconds=30.0)
    async def ticker_loop(self):
        now = get_now_ist()
        current_time_str = now.strftime("%H:%M")
        today_str = now.date().isoformat()

        # 1. 05:00 IST - Morning Kickoff
        if current_time_str == "05:00" and self._last_morning_date != today_str:
            self._last_morning_date = today_str
            logger.info(f"Triggering Morning Kickoff for {today_str}...")
            await self.broadcast_morning_kickoff()

        # 2. 16:30 IST - Afternoon Check-in
        if current_time_str == "16:30" and self._last_afternoon_date != today_str:
            self._last_afternoon_date = today_str
            logger.info(f"Triggering Afternoon Check-in for {today_str}...")
            await self.broadcast_afternoon_checkin()

        # 3. 00:00 IST - Midnight Finalization & Podium
        if current_time_str == "00:00" and self._last_midnight_date != today_str:
            self._last_midnight_date = today_str
            logger.info(f"Triggering Midnight Finalization at {today_str}...")
            await self.broadcast_midnight_finalization()

    @ticker_loop.before_loop
    async def before_ticker(self):
        await self.bot.wait_until_ready()
        logger.info("Scheduler ticker loop synchronized with Discord Gateway.")

    # ==========================================
    # Channel & Ping Resolution
    # ==========================================

    def _get_target_channel_and_ping(self, guild: discord.Guild):
        """Returns the configured dedicated TextChannel and role ping string for a guild."""
        settings = db.get_server_settings(guild.id)
        channel_id = settings.get("channel_id")
        if not channel_id:
            return None, ""

        channel = guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
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
        return channel, role_ping

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

    async def broadcast_midnight_finalization(self, target_channel: discord.TextChannel = None, role_ping: str = "") -> discord.Embed:
        """Finalizes day's results, stores daily_summaries, and publishes podium to dedicated channel."""
        now = get_now_ist()
        yesterday = (now - timedelta(days=1)).date().isoformat()

        leaderboard = db.finalize_daily_summaries(yesterday)
        embed = build_podium_embed(yesterday, leaderboard)

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
