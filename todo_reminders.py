"""
todo_reminders.py - Background Reminder Ticker & Auto-Prune Engine for Todo Addon

Runs a lightweight asyncio loop every 30 seconds to:
1. Scan todo.db for due reminders.
2. Check user's Do Not Disturb (DND) quiet hours before delivering alerts.
3. Deliver notification cards with interactive action buttons [ ✅ Done ], [ 🔕 Silence ], [ ⏰ Snooze 30m ].
4. Advance recurring reminders or retire completed ones.
5. Auto-purge trashed tasks older than 7 days.
"""

import time
import asyncio
import logging
from typing import Optional
import discord
from discord.ext import tasks, commands

import todo_db as db
import todo_parser as parser
from ui.todo_views import ReminderAlertView, format_priority_badge

logger = logging.getLogger("winter_arc.todo.reminders")


class TodoReminderService:
    """Background service managing reminder evaluation, DND checks, and delivery."""

    def __init__(self, bot: commands.Bot, db_path: Optional[str] = None):
        self.bot = bot
        self.db_path = db_path
        self._last_purge_date = None

    def start(self):
        """Starts the reminder ticker loop."""
        if not self.reminder_loop.is_running():
            self.reminder_loop.start()
            logger.info("Todo reminder service loop started.")

    def stop(self):
        """Stops the reminder ticker loop."""
        if self.reminder_loop.is_running():
            self.reminder_loop.cancel()
            logger.info("Todo reminder service loop stopped.")

    @tasks.loop(seconds=30.0)
    async def reminder_loop(self):
        """Ticks every 30 seconds to evaluate due reminders and clean 7-day trash."""
        try:
            now_ts = int(time.time())
            due_tasks = db.get_due_reminders(now_ts, db_path=self.db_path)

            for task in due_tasks:
                await self._process_single_reminder(task, now_ts)

            # Auto-purge expired trash (> 7 days) once a day
            today_date = time.strftime("%Y-%m-%d")
            if self._last_purge_date != today_date:
                self._last_purge_date = today_date
                purged = db.purge_expired_trash(days=7, db_path=self.db_path)
                if purged > 0:
                    logger.info(f"Cleaned {purged} expired tasks from todo trash (> 7 days).")

        except Exception as e:
            logger.error(f"Error in todo reminder_loop: {e}", exc_info=True)

    @reminder_loop.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()

    async def _process_single_reminder(self, task: dict, now_ts: int):
        """Evaluates DND, delivers reminder, and computes next occurrence."""
        user_id = task["user_id"]
        task_id = task["id"]

        # 1. DND Quiet Hours Check
        if db.is_user_in_dnd(user_id, db_path=self.db_path):
            logger.debug(f"User {user_id} is in DND window. Postponing reminder for task #{task_id} by 30m.")
            # Delay next check by 30 minutes to avoid waking user
            db.advance_reminder(task_id, now_ts + 1800, db_path=self.db_path)
            return

        # 2. Build and deliver the alert message
        delivered = await self._deliver_alert(task)

        # 3. Compute and advance next reminder
        next_ts = parser.compute_next_reminder(task)
        db.advance_reminder(task_id, next_ts, db_path=self.db_path)

        if next_ts:
            logger.debug(f"Advanced recurring task #{task_id} next alert to {next_ts}.")
        else:
            logger.debug(f"Task #{task_id} reminder completed (no further recurrences).")

    async def _deliver_alert(self, task: dict) -> bool:
        """Sends the reminder card to DM or origin channel."""
        user_id = task["user_id"]
        task_id = task["id"]
        task_text = task["task_text"]
        priority = task.get("priority", "normal")
        p_badge = format_priority_badge(priority)
        p_str = f" • {p_badge}" if p_badge else ""

        user = self.bot.get_user(user_id)
        if not user:
            try:
                user = await self.bot.fetch_user(user_id)
            except Exception:
                user = None

        if not user:
            logger.warning(f"Could not resolve user {user_id} for todo reminder #{task_id}.")
            return False

        view = ReminderAlertView(task_id=task_id, user_id=user_id, db_path=self.db_path)

        embed = discord.Embed(
            title="🔔 To-Do Reminder",
            description=f"**{task_text}**{p_str}",
            color=0x3498DB # Clean neutral blue
        )

        schedule_info = []
        if task.get("remind_spec"):
            schedule_info.append(f"🔁 **Schedule**: {task['remind_spec']}")
        if task.get("until_spec") and task["until_spec"] != "done":
            schedule_info.append(f"⏳ **Until**: {task['until_spec']}")
        
        if schedule_info:
            embed.set_footer(text=" • ".join(schedule_info))

        # Check delivery mode: DM only vs Channel
        dm_only = bool(task.get("dm_only", 1))

        if dm_only:
            try:
                await user.send(embed=embed, view=view)
                logger.info(f"Delivered private todo DM reminder to {user.display_name} for task #{task_id}.")
                return True
            except discord.Forbidden:
                logger.debug(f"Cannot send todo DM to {user.display_name} (DMs closed).")
                # Fallback to origin channel if configured
                channel_id = task.get("origin_channel_id")
                if channel_id:
                    ch = self.bot.get_channel(channel_id)
                    if ch:
                        try:
                            await ch.send(content=f"<@{user_id}>", embed=embed, view=view)
                            return True
                        except Exception:
                            pass
                return False
            except Exception as e:
                logger.warning(f"Error sending todo DM to {user.display_name}: {e}")
                return False
        else:
            # Channel delivery
            channel_id = task.get("origin_channel_id")
            ch = self.bot.get_channel(channel_id) if channel_id else None
            if ch:
                try:
                    await ch.send(content=f"<@{user_id}>", embed=embed, view=view)
                    logger.info(f"Delivered todo channel reminder to #{ch.name} for {user.display_name}.")
                    return True
                except Exception as e:
                    logger.warning(f"Could not send reminder to channel {channel_id}: {e}")

            # Fallback to DM if channel failed
            try:
                await user.send(embed=embed, view=view)
                return True
            except Exception:
                return False
