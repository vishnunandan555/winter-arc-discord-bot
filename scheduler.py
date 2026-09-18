"""
scheduler.py - Background Scheduler for Winter Arc Bot (Asia/Kolkata)

Runs background checks every 30 seconds to trigger:
- 05:00 IST: Morning challenge kickoff message
- 16:30 IST: Afternoon personalized progress check-in
- 00:00 IST: Midnight day finalization, daily summaries persistence, and podium broadcast
"""

import os
import asyncio
import logging
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import discord
from discord.ext import tasks

import database as db

logger = logging.getLogger("winter_arc.scheduler")
TIMEZONE_NAME = os.getenv("BOT_TIMEZONE", "Asia/Kolkata")
BOT_TZ = ZoneInfo(TIMEZONE_NAME)


def get_now_ist() -> datetime:
    return datetime.now(BOT_TZ)


class WinterArcScheduler:
    def __init__(self, bot: discord.Client, results_channel_id: int = 0):
        self.bot = bot
        self.results_channel_id = results_channel_id
        self._last_morning_date = None
        self._last_afternoon_date = None
        self._last_midnight_date = None

    def start(self):
        if not self.ticker_loop.is_running():
            self.ticker_loop.start()
            logger.info(f"Winter Arc Scheduler started in timezone {TIMEZONE_NAME}.")

    def stop(self):
        if self.ticker_loop.is_running():
            self.ticker_loop.cancel()

    @tasks.loop(seconds=30)
    async def ticker_loop(self):
        """Checks time every 30 seconds and triggers scheduled jobs."""
        await self.bot.wait_until_ready()
        now = get_now_ist()
        today_str = now.strftime("%Y-%m-%d")
        current_time_str = now.strftime("%H:%M")

        # 1. 05:00 IST - Morning Kickoff
        if current_time_str == "05:00" and self._last_morning_date != today_str:
            self._last_morning_date = today_str
            logger.info(f"Triggering morning kickoff for {today_str}")
            await self.send_morning_reminder()

        # 2. 16:30 IST - Afternoon Check-in
        elif current_time_str == "16:30" and self._last_afternoon_date != today_str:
            self._last_afternoon_date = today_str
            logger.info(f"Triggering afternoon check-in for {today_str}")
            await self.send_afternoon_reminder()

        # 3. 00:00 IST - Midnight Finalization
        elif current_time_str == "00:00" and self._last_midnight_date != today_str:
            self._last_midnight_date = today_str
            logger.info(f"Triggering midnight finalization for {today_str}")
            await self.run_midnight_job()

    @ticker_loop.before_loop
    async def before_ticker(self):
        await self.bot.wait_until_ready()

    # ==========================================
    # Reminder Actions
    # ==========================================

    async def send_morning_reminder(self, target_user: discord.User = None):
        """Sends morning daily motivation and active challenge targets."""
        active_tasks = db.get_active_tasks()
        if not active_tasks:
            return

        now = get_now_ist()
        date_display = now.strftime("%B %d").upper()

        embed = discord.Embed(
            title=f"🌅 WINTER ARC — {date_display}",
            description="Rise and conquer. Here are today's target disciplines:\n",
            color=0x3498DB
        )

        task_lines = []
        for t in active_tasks:
            unit_display = t["unit"]
            target_display = int(t["target"]) if t["target"].is_integer() else t["target"]
            task_lines.append(f"• **{t['name']}**: {target_display} {unit_display} ({t['max_points']} pts)")

        embed.add_field(name="📋 Target Goals", value="\n".join(task_lines), inline=False)
        embed.set_footer(text="Log your progress with /log | View your status with /today")

        if target_user:
            # Manual trigger for single user
            try:
                await target_user.send(embed=embed)
            except Exception as e:
                logger.warning(f"Could not DM user {target_user.id}: {e}")
            return

        # Broadcast to opted-in users
        opted_in = db.get_users_for_reminder("morning")
        for u in opted_in:
            try:
                discord_user = await self.bot.fetch_user(u["discord_id"])
                if discord_user:
                    await discord_user.send(embed=embed)
            except Exception as e:
                logger.warning(f"Failed to send morning reminder to {u['username']} ({u['discord_id']}): {e}")

        # If results channel configured, post announcement there as well
        channel = self._get_results_channel()
        if channel:
            try:
                await channel.send(embed=embed)
            except Exception as e:
                logger.warning(f"Could not send morning announcement to channel: {e}")

    async def send_afternoon_reminder(self, target_user: discord.User = None):
        """Sends customized afternoon check-in showing remaining amounts."""
        now = get_now_ist()
        today_str = now.strftime("%Y-%m-%d")

        users_to_check = [target_user.id] if target_user else [u["discord_id"] for u in db.get_users_for_reminder("afternoon")]

        for d_id in users_to_check:
            progress = db.get_user_daily_progress(d_id, today_str)
            if not progress or not progress["tasks"]:
                continue

            # Build progress lines
            lines = []
            for t in progress["tasks"]:
                cur = int(t["current_amount"]) if t["current_amount"].is_integer() else t["current_amount"]
                target = int(t["target"]) if t["target"].is_integer() else t["target"]
                icon = "✅" if t["completed"] else "⏳"
                lines.append(f"{icon} **{t['name']}**: {cur} / {target} {t['unit']} ({t['points_earned']}/{t['max_points']} pts)")

            pct = int(progress["overall_completion_rate"] * 100)
            embed = discord.Embed(
                title="⏰ WINTER ARC — AFTERNOON CHECK-IN",
                description="You still have time today. Finish strong!\n\n" + "\n".join(lines),
                color=0xE67E22
            )
            embed.add_field(
                name="Status",
                value=f"Points: **{progress['total_points']} / {progress['max_possible_points']}** ({pct}% complete)",
                inline=False
            )
            embed.set_footer(text="Use /log to record remaining sets.")

            try:
                discord_user = target_user if target_user else await self.bot.fetch_user(d_id)
                if discord_user:
                    await discord_user.send(embed=embed)
            except Exception as e:
                logger.warning(f"Failed to send afternoon reminder to {d_id}: {e}")

    async def run_midnight_job(self) -> discord.Embed:
        """
        Finalizes yesterday's results at 00:00 IST:
        - Writes daily_summaries
        - Formats podium leaderboard
        - Posts to results channel
        """
        now = get_now_ist()
        # The day just completed is yesterday
        yesterday = (now - timedelta(days=1)).date().isoformat()

        leaderboard = db.finalize_daily_summaries(yesterday)
        embed = self.format_daily_podium_embed(yesterday, leaderboard)

        channel = self._get_results_channel()
        if channel:
            try:
                await channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Failed to post midnight results to channel: {e}")

        return embed

    def format_daily_podium_embed(self, date_str: str, leaderboard: list) -> discord.Embed:
        try:
            d_obj = date.fromisoformat(date_str)
            title_date = d_obj.strftime("%B %d, %Y").upper()
        except Exception:
            title_date = date_str

        embed = discord.Embed(
            title=f"🌙 DAY COMPLETE — {title_date}",
            description="The day has concluded! Here is the finalized daily podium:\n",
            color=0x9B59B6
        )

        medals = ["🥇", "🥈", "🥉"]
        podium_lines = []
        perfect_count = 0

        for idx, entry in enumerate(leaderboard):
            medal = medals[idx] if idx < 3 else f"`#{idx+1}`"
            perfect_star = " ⭐" if entry["perfect_day"] else ""
            if entry["perfect_day"]:
                perfect_count += 1
            pct = int(entry["completion_rate"] * 100)
            podium_lines.append(f"{medal} **{entry['username']}** — **{entry['points']} pts** ({pct}%){perfect_star}")

        if not podium_lines:
            podium_lines.append("_No activity logged for this day._")

        embed.add_field(name="🏆 Daily Leaderboard", value="\n".join(podium_lines), inline=False)
        embed.add_field(name="🔥 Perfect Days", value=f"**{perfect_count}** warriors achieved 100% completion.", inline=False)
        embed.set_footer(text="A new day has begun. Use /today to view fresh targets!")
        return embed

    def _get_results_channel(self) -> discord.TextChannel | None:
        if self.results_channel_id:
            channel = self.bot.get_channel(int(self.results_channel_id))
            if channel:
                return channel

        # Fallback: search for a channel named 'daily-results' in any mutual guild
        for guild in self.bot.guilds:
            for ch in guild.text_channels:
                if ch.name in ("daily-results", "winter-arc", "general"):
                    return ch
        return None
