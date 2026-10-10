"""
tests/test_todo_system.py - Comprehensive Unit & Integration Tests for Todo Addon

Tests:
- Database CRUD & dynamic relative numbering (#1..#N and T1..TN)
- Trash auto-retention & 7-day pruning
- DND quiet hours evaluation (cross-midnight and same-day)
- Schedule & reminder parser (intervals, smart 3x/5x daily frequencies, windowed)
- Background ticker & interactive views (pagination, alert buttons, assignment flow)
"""

import os
import time
import shutil
import tempfile
import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

import discord
import todo_db as db
import todo_parser as parser
from todo_reminders import TodoReminderService
from ui.todo_views import (
    TodoListView,
    ReminderAlertView,
    TaskAssignmentView,
    build_todo_list_embed,
)
from tests.base import WinterArcTestCase
from config import BOT_TZ


class TestTodoDatabaseAndNumbering(WinterArcTestCase):
    """Verifies isolated todo.db persistence, relative numbering, and trash retention."""

    def setUp(self):
        super().setUp()
        self.todo_test_db = os.path.join(self._temp_dir.name, "test_todo.db")
        db.init_todo_db(self.todo_test_db)
        self.user_id = 998877
        with db.get_todo_connection(self.todo_test_db) as conn:
            conn.execute("DELETE FROM todos;")
            conn.execute("DELETE FROM todo_user_settings;")
            conn.commit()

    def test_add_tasks_and_relative_sequential_numbering(self):
        """Verifies that active tasks receive clean, sequential 1-based numbers (#1, #2, #3)."""
        t1 = db.add_task(self.user_id, "Buy groceries", priority="normal", db_path=self.todo_test_db)
        t2 = db.add_task(self.user_id, "Critical server patch", priority="high", db_path=self.todo_test_db)
        t3 = db.add_task(self.user_id, "Call dentist", priority="low", db_path=self.todo_test_db)

        active = db.get_active_tasks(self.user_id, db_path=self.todo_test_db)
        self.assertEqual(len(active), 3)

        # High priority should sort first!
        self.assertEqual(active[0]["num"], 1)
        self.assertEqual(active[0]["task_text"], "Critical server patch")
        self.assertEqual(active[0]["priority"], "high")

        # Then normal, then low
        self.assertEqual(active[1]["num"], 2)
        self.assertEqual(active[1]["task_text"], "Buy groceries")

        self.assertEqual(active[2]["num"], 3)
        self.assertEqual(active[2]["task_text"], "Call dentist")

    def test_mark_done_reindexes_active_tasks_and_creates_trash(self):
        """Verifies that completing a task removes it from active list, moves to trash, and reindexes active tasks."""
        db.add_task(self.user_id, "Task A", priority="normal", db_path=self.todo_test_db)
        db.add_task(self.user_id, "Task B", priority="normal", db_path=self.todo_test_db)
        db.add_task(self.user_id, "Task C", priority="normal", db_path=self.todo_test_db)

        # Mark Task B (#2) as done
        done_task = db.mark_task_done(self.user_id, 2, db_path=self.todo_test_db)
        self.assertIsNotNone(done_task)
        self.assertEqual(done_task["task_text"], "Task B")
        self.assertEqual(done_task["status"], "completed")

        # Active tasks should now only be 2, renumbered #1 and #2!
        active = db.get_active_tasks(self.user_id, db_path=self.todo_test_db)
        self.assertEqual(len(active), 2)
        self.assertEqual(active[0]["num"], 1)
        self.assertEqual(active[0]["task_text"], "Task A")
        self.assertEqual(active[1]["num"], 2)
        self.assertEqual(active[1]["task_text"], "Task C")

        # Trash should have Task B with ID T1
        trash = db.get_trashed_tasks(self.user_id, db_path=self.todo_test_db)
        self.assertEqual(len(trash), 1)
        self.assertEqual(trash[0]["trash_id"], "T1")
        self.assertEqual(trash[0]["task_text"], "Task B")

    def test_restore_task_from_trash(self):
        """Verifies restoring a task from trash returns it to the active list."""
        db.add_task(self.user_id, "Test Item", db_path=self.todo_test_db)
        db.mark_task_done(self.user_id, 1, db_path=self.todo_test_db)

        self.assertEqual(len(db.get_active_tasks(self.user_id, db_path=self.todo_test_db)), 0)
        self.assertEqual(len(db.get_trashed_tasks(self.user_id, db_path=self.todo_test_db)), 1)

        # Restore T1
        restored = db.restore_task(self.user_id, 1, db_path=self.todo_test_db)
        self.assertIsNotNone(restored)
        self.assertEqual(restored["task_text"], "Test Item")

        # Active should be 1, trash should be 0
        self.assertEqual(len(db.get_active_tasks(self.user_id, db_path=self.todo_test_db)), 1)
        self.assertEqual(len(db.get_trashed_tasks(self.user_id, db_path=self.todo_test_db)), 0)

    def test_silence_and_edit_task(self):
        """Verifies silencing reminder leaves task active, and edit updates description/priority."""
        db.add_task(
            self.user_id,
            "Night Reading",
            remind_spec="every hour",
            next_reminder_at=int(time.time()) + 3600,
            db_path=self.todo_test_db
        )

        silenced = db.silence_task(self.user_id, 1, db_path=self.todo_test_db)
        self.assertEqual(silenced["status"], "silenced")
        self.assertIsNone(silenced["next_reminder_at"])

        # Edit task description and priority
        edited = db.edit_task(
            self.user_id,
            1,
            new_task_text="Night Reading - Chapter 5",
            new_priority="high",
            db_path=self.todo_test_db
        )
        self.assertEqual(edited["task_text"], "Night Reading - Chapter 5")
        self.assertEqual(edited["priority"], "high")

    def test_7_day_trash_pruning_and_manual_clear(self):
        """Verifies tasks older than 7 days are auto-purged, and clear_trash empties immediately."""
        now_ts = int(time.time())
        # Insert expired task in trash directly (8 days old)
        with db.get_todo_connection(self.todo_test_db) as conn:
            conn.execute("""
                INSERT INTO todos (user_id, task_text, status, trashed_at, created_at)
                VALUES (?, 'Old Trashed Item', 'completed', ?, ?)
            """, (self.user_id, now_ts - (8 * 86400), now_ts - (9 * 86400)))
            # Insert recent trashed item (1 day old)
            conn.execute("""
                INSERT INTO todos (user_id, task_text, status, trashed_at, created_at)
                VALUES (?, 'Recent Trashed Item', 'completed', ?, ?)
            """, (self.user_id, now_ts - 86400, now_ts - 86400))
            conn.commit()

        # Purging should delete the 8-day-old item and keep the 1-day-old item
        purged = db.purge_expired_trash(days=7, db_path=self.todo_test_db)
        self.assertEqual(purged, 1)

        trash = db.get_trashed_tasks(self.user_id, db_path=self.todo_test_db)
        self.assertEqual(len(trash), 1)
        self.assertEqual(trash[0]["task_text"], "Recent Trashed Item")

        # Manual clear
        cleared = db.clear_trash(self.user_id, db_path=self.todo_test_db)
        self.assertEqual(cleared, 1)
        self.assertEqual(len(db.get_trashed_tasks(self.user_id, db_path=self.todo_test_db)), 0)


class TestTodoDNDMode(WinterArcTestCase):
    """Verifies Do Not Disturb quiet-hours math across midnight and same-day windows."""

    def setUp(self):
        super().setUp()
        self.todo_test_db = os.path.join(self._temp_dir.name, "test_todo_dnd.db")
        db.init_todo_db(self.todo_test_db)
        self.user_id = 112233
        with db.get_todo_connection(self.todo_test_db) as conn:
            conn.execute("DELETE FROM todos;")
            conn.execute("DELETE FROM todo_user_settings;")
            conn.commit()

    def test_dnd_disabled_by_default(self):
        """Verifies DND is off by default."""
        self.assertFalse(db.is_user_in_dnd(self.user_id, db_path=self.todo_test_db))

    def test_cross_midnight_dnd_window(self):
        """Verifies 22:00 to 06:00 quiet hours correctly flags night hours and permits daytime."""
        db.update_user_settings(
            self.user_id,
            dnd_enabled=True,
            dnd_start="22:00",
            dnd_end="06:00",
            timezone_name="Asia/Kolkata",
            db_path=self.todo_test_db
        )

        tz = BOT_TZ
        # 23:30 (11:30 PM) -> In DND
        dt_night = datetime(2026, 10, 10, 23, 30, tzinfo=tz)
        self.assertTrue(db.is_user_in_dnd(self.user_id, check_dt=dt_night, db_path=self.todo_test_db))

        # 03:15 (3:15 AM) -> In DND
        dt_early = datetime(2026, 10, 10, 3, 15, tzinfo=tz)
        self.assertTrue(db.is_user_in_dnd(self.user_id, check_dt=dt_early, db_path=self.todo_test_db))

        # 06:01 (6:01 AM) -> Outside DND
        dt_morning = datetime(2026, 10, 10, 6, 1, tzinfo=tz)
        self.assertFalse(db.is_user_in_dnd(self.user_id, check_dt=dt_morning, db_path=self.todo_test_db))

        # 14:00 (2:00 PM) -> Outside DND
        dt_afternoon = datetime(2026, 10, 10, 14, 0, tzinfo=tz)
        self.assertFalse(db.is_user_in_dnd(self.user_id, check_dt=dt_afternoon, db_path=self.todo_test_db))

    def test_same_day_dnd_window(self):
        """Verifies 13:00 to 17:00 daytime quiet window."""
        db.update_user_settings(
            self.user_id,
            dnd_enabled=True,
            dnd_start="13:00",
            dnd_end="17:00",
            timezone_name="Asia/Kolkata",
            db_path=self.todo_test_db
        )

        tz = BOT_TZ
        self.assertTrue(db.is_user_in_dnd(self.user_id, check_dt=datetime(2026, 10, 10, 14, 30, tzinfo=tz), db_path=self.todo_test_db))
        self.assertFalse(db.is_user_in_dnd(self.user_id, check_dt=datetime(2026, 10, 10, 18, 0, tzinfo=tz), db_path=self.todo_test_db))


class TestTodoParserAndScheduleEngine(WinterArcTestCase):
    """Verifies natural schedule parsing, smart frequency spacing, and optional 'until' handling."""

    def test_smart_frequencies_3_times_and_5_times_a_day(self):
        """Verifies 3x daily (10:00, 15:00, 20:00) and 5x daily spacing."""
        now = datetime(2026, 10, 10, 8, 0, tzinfo=BOT_TZ)

        res3 = parser.parse_remind_spec("3 times a day", current_dt=now)
        self.assertEqual(res3["remind_type"], "smart_frequency")
        self.assertEqual(res3["remind_fixed_times"], ["10:00", "15:00", "20:00"])
        self.assertIn("10:00", res3["confirmation_msg"])
        self.assertIn("15:00", res3["confirmation_msg"])
        self.assertIn("20:00", res3["confirmation_msg"])

        res5 = parser.parse_remind_spec("5 times a day", current_dt=now)
        self.assertEqual(res5["remind_type"], "smart_frequency")
        self.assertEqual(len(res5["remind_fixed_times"]), 5)

    def test_windowed_interval_after_6pm(self):
        """Verifies 'every hour after 6 PM' parses interval=60 and window start 18:00."""
        now_morning = datetime(2026, 10, 10, 9, 0, tzinfo=BOT_TZ)
        res = parser.parse_remind_spec("every hour after 6 PM", current_dt=now_morning)
        self.assertEqual(res["remind_type"], "interval")
        self.assertEqual(res["remind_interval_mins"], 60)
        self.assertEqual(res["remind_window_start"], "18:00")
        self.assertIn("after 18:00", res["confirmation_msg"])

    def test_optional_until_and_recurrence_computation(self):
        """Verifies that 'until' is optional (repeats indefinitely) unless explicit cutoff is given."""
        # 1. No until given (default done)
        now = datetime(2026, 10, 10, 10, 0, tzinfo=BOT_TZ)
        task_indefinite = {
            "remind_type": "interval",
            "remind_interval_mins": 60,
            "until_timestamp": None,
        }
        next_ts = parser.compute_next_reminder(task_indefinite, from_dt=now)
        self.assertIsNotNone(next_ts)
        self.assertEqual(next_ts, int((now + timedelta(hours=1)).timestamp()))

        # 2. Until given and reached
        cutoff = now + timedelta(minutes=30)
        task_bounded = {
            "remind_type": "interval",
            "remind_interval_mins": 60,
            "until_timestamp": int(cutoff.timestamp()),
        }
        next_bounded = parser.compute_next_reminder(task_bounded, from_dt=now)
        # Next reminder would be +60m which exceeds cutoff +30m -> should return None!
        self.assertIsNone(next_bounded)


class TestTodoViewsAndInteractionFlow(WinterArcTestCase):
    """Verifies 15-item pagination, interactive alert card buttons, and assignment workflow."""

    def setUp(self):
        super().setUp()
        self.todo_test_db = os.path.join(self._temp_dir.name, "test_todo_ui.db")
        db.init_todo_db(self.todo_test_db)
        self.user_id = 554433
        with db.get_todo_connection(self.todo_test_db) as conn:
            conn.execute("DELETE FROM todos;")
            conn.execute("DELETE FROM todo_user_settings;")
            conn.commit()

    def test_pagination_15_items_per_page(self):
        """Verifies that 20 tasks span 2 pages (15 on page 1, 5 on page 2)."""
        mock_user = self.create_mock_member(user_id=self.user_id, display_name="TaskMaster")
        for i in range(1, 21):
            db.add_task(self.user_id, f"Work Task {i}", db_path=self.todo_test_db)

        view = TodoListView(user_id=self.user_id, user=mock_user, page=1, db_path=self.todo_test_db)
        items_p1, total_pages, total_items = view._get_current_items()
        self.assertEqual(total_items, 20)
        self.assertEqual(total_pages, 2)
        self.assertEqual(len(items_p1), 15)

        # Move to page 2
        view.page = 2
        items_p2, _, _ = view._get_current_items()
        self.assertEqual(len(items_p2), 5)
        self.assertEqual(items_p2[0]["task_text"], "Work Task 16")

    def test_reminder_alert_view_callbacks(self):
        """Verifies interactive [ ✅ Done ], [ 🔕 Silence ], [ ⏰ Snooze 30m ] callbacks on alert card."""
        task = db.add_task(
            self.user_id,
            "Important Submission",
            remind_spec="every 30 mins",
            next_reminder_at=int(time.time()),
            db_path=self.todo_test_db
        )
        task_id = task["id"]

        view = ReminderAlertView(task_id=task_id, user_id=self.user_id, db_path=self.todo_test_db)
        inter = self.create_mock_interaction(user_id=self.user_id)

        # Test Snooze 30m callback
        asyncio.run(view.btn_alert_snooze.callback(inter))
        inter.followup.send.assert_called()
        snoozed_text = inter.followup.send.call_args[0][0]
        self.assertIn("30 minutes", snoozed_text)

        # Test Done callback
        inter.followup.send.reset_mock()
        asyncio.run(view.btn_alert_done.callback(inter))
        inter.followup.send.assert_called()
        done_text = inter.followup.send.call_args[0][0]
        self.assertIn("completed", done_text)

        # Task should now be in trash
        self.assertEqual(len(db.get_active_tasks(self.user_id, db_path=self.todo_test_db)), 0)
        self.assertEqual(len(db.get_trashed_tasks(self.user_id, db_path=self.todo_test_db)), 1)

    def test_task_assignment_accept_flow(self):
        """Verifies friend assignment invitation and Accept button callback."""
        assigner_id = 111
        assignee_id = 222
        task_data = {
            "task_text": "Shared Engineering Review",
            "priority": "high",
            "remind_spec": "tomorrow 14:00",
            "remind_type": "once",
            "next_reminder_at": int(time.time()) + 3600,
            "dm_only": True,
        }

        view = TaskAssignmentView(
            assignee_id=assignee_id,
            assigner_id=assigner_id,
            task_data=task_data,
            db_path=self.todo_test_db
        )

        inter = self.create_mock_interaction(user_id=assignee_id)
        asyncio.run(view.btn_accept.callback(inter))

        inter.response.edit_message.assert_called()
        edit_content = inter.response.edit_message.call_args[1].get("content")
        self.assertIn("Task Accepted", edit_content)

        # Assignee should now have the task active with #1
        assignee_tasks = db.get_active_tasks(assignee_id, db_path=self.todo_test_db)
        self.assertEqual(len(assignee_tasks), 1)
        self.assertEqual(assignee_tasks[0]["task_text"], "Shared Engineering Review")
        self.assertEqual(assignee_tasks[0]["priority"], "high")
