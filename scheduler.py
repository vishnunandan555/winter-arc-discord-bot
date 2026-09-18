"""
scheduler.py - Dedicated Channel Scheduler for Winter Arc Bot (Asia/Kolkata)

Runs background checks every 30 seconds for:
- 05:00 IST: Morning challenge kickoff with role ping in dedicated channel
- 16:30 IST: Afternoon check-in with group progress and role ping in dedicated channel
- 00:00 IST: Midnight day finalization & podium broadcast in dedicated channel
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


DEFAULT_ROLE_ID = int(os.getenv("WINTER_ARC_ROLE_ID", "1550511682344845352"))


def get_now_ist() -> datetime:
    return datetime.now(BOT_TZ)


class WinterArcScheduler:
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
            logger.info(f"Executing 05:00 Morning Kickoff for {today_str}")
            await self.broadcast_morning_kickoff()

        # 2. 16:30 IST - Afternoon Check-in
        elif current_time_str == "16:30" and self._last_afternoon_date != today_str:
            self._last_afternoon_date = today_str
            logger.info(f"Executing 16:30 Afternoon Check-in for {today_str}")
            await self.broadcast_afternoon_checkin()

        # 3. 00:00 IST - Midnight Finalization
        elif current_time_str == "00:00" and self._last_midnight_date != today_str:
            self._last_midnight_date = today_str
            logger.info(f"Executing 00:00 Midnight Finalization for {today_str}")
            await self.broadcast_midnight_finalization()

    @ticker_loop.before_loop
    async def before_ticker(self):
        await self.bot.wait_until_ready()

    # ==========================================
    # Broadcast Routines (Dedicated Channel Only)
    # ==========================================

    def _get_target_channel_and_ping(self, guild: discord.Guild):
        settings = db.get_server_settings(guild.id)
        channel_id = settings.get("channel_id", 0)
        role_id = settings.get("role_id", 0) or DEFAULT_ROLE_ID

        channel = guild.get_channel(channel_id) if channel_id else None
        role_ping = ""
        if role_id:
            role = guild.get_role(role_id)
            if role:
                role_ping = f"{role.mention} "
            else:
                role_ping = f"<@&{role_id}> "
        if not role_ping:
            for r in guild.roles:
                if r.name.lower() in ["winter arc", "winterarc", "the winter arc"]:
                    role_ping = f"{r.mention} "
                    break
        return channel, role_ping

    async def broadcast_morning_kickoff(self, target_channel: discord.TextChannel = None, role_ping: str = ""):
        """Sends morning daily motivation and active challenge targets to dedicated channel."""
        active_tasks = db.get_active_tasks()
        now = get_now_ist()
        date_display = now.strftime("%B %d, %Y").upper()

        embed = discord.Embed(
            title=f"🌅 WINTER ARC — {date_display}",
            description=(
                "**Rise and conquer.** The grind doesn't care about feelings.\n"
                "Here are today's target disciplines:\n"
            ),
            color=0x3498DB
        )

        task_lines = []
        for t in active_tasks:
            target_display = int(t["target"]) if t["target"].is_integer() else t["target"]
            task_lines.append(f"• **{t['name']}**: `{target_display} {t['unit']}` *(Max {t['max_points']} pts)*")

        embed.add_field(name="📋 Today's Discipline Targets", value="\n".join(task_lines) if task_lines else "_No active tasks._", inline=False)
        embed.set_footer(text="Log sets with /log | View status with /today | Enrolled warriors only")

        if target_channel:
            await target_channel.send(content=f"{role_ping}🌅 **Morning Kickoff**", embed=embed)
            return

        # Broadcast to all guilds with configured dedicated channel
        for guild in self.bot.guilds:
            channel, ping = self._get_target_channel_and_ping(guild)
            if channel:
                try:
                    await channel.send(content=f"{ping}🌅 **Morning Kickoff**", embed=embed)
                except Exception as e:
                    logger.warning(f"Could not send morning kickoff to {channel.name} in {guild.name}: {e}")

    async def broadcast_afternoon_checkin(self, target_channel: discord.TextChannel = None, role_ping: str = ""):
        """Sends customized afternoon check-in showing enrolled group progress to dedicated channel."""
        now = get_now_ist()
        today_str = now.strftime("%Y-%m-%d")
        enrolled_users = db.get_enrolled_users()

        embed = discord.Embed(
            title="⏰ WINTER ARC — AFTERNOON CHECK-IN",
            description="You still have hours on the clock today. Check your standings and close the gap!\n",
            color=0xE67E22
        )

        if not enrolled_users:
            embed.description += "\n_No enrolled warriors yet. Use `/enroll` to join the Arc!_"
        else:
            warrior_lines = []
            for u in enrolled_users:
                prog = db.get_user_daily_progress(u["discord_id"], today_str)
                pct = int(prog["overall_completion_rate"] * 100)
                star = " ⭐" if prog["perfect_day"] else ""
                warrior_lines.append(
                    f"• **{u['username']}**: `{prog['total_points']} / {prog['max_possible_points']} pts` ({pct}%){star}"
                )
            embed.add_field(name="⚔️ Current Group Progress", value="\n".join(warrior_lines), inline=False)

        embed.set_footer(text="Use /log to record remaining sets.")

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
        embed = self.format_daily_podium_embed(yesterday, leaderboard)

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

    def format_daily_podium_embed(self, date_str: str, leaderboard: list) -> discord.Embed:
        try:
            d_obj = date.fromisoformat(date_str)
            title_date = d_obj.strftime("%B %d, %Y").upper()
        except Exception:
            title_date = date_str

        embed = discord.Embed(
            title=f"🌙 DAY COMPLETE — {title_date}",
            description="The day has ended and scores are locked in! Here is the daily podium:\n",
            color=0x9B59B6
        )

        podium_lines = []
        perfect_count = 0

        for idx, entry in enumerate(leaderboard):
            if idx == 0:
                rank = "`#1` 👑"
            elif idx == 1:
                rank = "`#2` ⚔️"
            elif idx == 2:
                rank = "`#3` 🛡️"
            else:
                rank = f"`#{idx+1:>2}` ▫️"

            perfect_star = " ⭐" if entry["perfect_day"] else ""
            if entry["perfect_day"]:
                perfect_count += 1
            pct = int(entry["completion_rate"] * 100)
            podium_lines.append(f"{rank} **{entry['username']}** — `{entry['points']} / 500 PTS` ({pct}%){perfect_star}")

        if not podium_lines:
            podium_lines.append("_No enrolled warriors logged activity for this day._")

        embed.add_field(name="🏆 Final Standings", value="\n".join(podium_lines), inline=False)
        embed.add_field(name="🔥 100% Perfect Days", value=f"**{perfect_count}** warriors completed all disciplines.", inline=False)
        embed.set_footer(text="A new day has begun. Run /today to view your fresh slate!")
        return embed
