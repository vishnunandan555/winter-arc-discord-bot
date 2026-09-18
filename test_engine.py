"""
test_engine.py - Automated Unit & Integration Tests for Winter Arc Bot Engine
Tests database initialization, scoring capping, streaks, summaries, and anti-abuse checks.
"""

import os
import unittest
from datetime import date, timedelta
import database as db

TEST_DB = "test_winter_arc.db"


class TestWinterArcEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        db.init_db(TEST_DB)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)

    def test_01_tasks_seeded(self):
        tasks = db.get_active_tasks(TEST_DB)
        task_names = [t["name"] for t in tasks]
        self.assertIn("Push-ups", task_names)
        self.assertIn("Pull-ups", task_names)
        self.assertIn("Squats", task_names)
        self.assertIn("Running", task_names)
        self.assertEqual(len(tasks), 4)

    def test_02_user_creation_and_retrieval(self):
        user = db.get_or_create_user(1001, "Vishnu", TEST_DB)
        self.assertEqual(user["discord_id"], 1001)
        self.assertEqual(user["username"], "Vishnu")
        self.assertEqual(user["morning_reminder"], 1)
        self.assertEqual(user["afternoon_reminder"], 1)

        fetched = db.get_user_by_discord_id(1001, TEST_DB)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["username"], "Vishnu")

    def test_03_activity_logging_and_scoring(self):
        today = date.today().isoformat()
        
        # 1. Log 30 push-ups (target 100) -> 30 pts
        res1 = db.log_activity(1001, "Vishnu", "Push-ups", 30.0, today, TEST_DB)
        self.assertEqual(res1["amount_logged"], 30.0)
        self.assertEqual(res1["new_total"], 30.0)
        self.assertEqual(res1["points_earned_delta"], 30)
        self.assertEqual(res1["task_points_total"], 30)
        self.assertFalse(res1["is_target_reached"])

        # 2. Log another 35 push-ups -> total 65 -> +35 pts
        res2 = db.log_activity(1001, "Vishnu", "Push-ups", 35.0, today, TEST_DB)
        self.assertEqual(res2["new_total"], 65.0)
        self.assertEqual(res2["points_earned_delta"], 35)
        self.assertEqual(res2["task_points_total"], 65)

        # 3. Log 50 push-ups -> total 115 -> should cap at 100 points, delta is 35 points (not 50)
        res3 = db.log_activity(1001, "Vishnu", "Push-ups", 50.0, today, TEST_DB)
        self.assertEqual(res3["new_total"], 115.0)
        self.assertEqual(res3["points_earned_delta"], 35)
        self.assertEqual(res3["task_points_total"], 100)
        self.assertTrue(res3["is_target_reached"])

        # 4. Excess logging beyond target awards 0 additional points
        res4 = db.log_activity(1001, "Vishnu", "Push-ups", 50.0, today, TEST_DB)
        self.assertEqual(res4["new_total"], 165.0)
        self.assertEqual(res4["points_earned_delta"], 0)
        self.assertEqual(res4["task_points_total"], 100)

    def test_04_abuse_prevention(self):
        today = date.today().isoformat()
        # Negative amount rejected
        with self.assertRaises(ValueError):
            db.log_activity(1001, "Vishnu", "Push-ups", -10, today, TEST_DB)

        # Zero amount rejected
        with self.assertRaises(ValueError):
            db.log_activity(1001, "Vishnu", "Push-ups", 0, today, TEST_DB)

        # Unrealistic amount rejected
        with self.assertRaises(ValueError):
            db.log_activity(1001, "Vishnu", "Push-ups", 999999, today, TEST_DB)

        # Non-existent task rejected
        with self.assertRaises(ValueError):
            db.log_activity(1001, "Vishnu", "Flying", 10, today, TEST_DB)

    def test_05_daily_progress_structure(self):
        today = date.today().isoformat()
        progress = db.get_user_daily_progress(1001, today, TEST_DB)
        self.assertEqual(progress["username"], "Vishnu")
        self.assertEqual(len(progress["tasks"]), 4)
        # Pushups were completed above (165 reps >= 100 target)
        pushup_task = next(t for t in progress["tasks"] if t["name"] == "Push-ups")
        self.assertTrue(pushup_task["completed"])
        self.assertEqual(pushup_task["points_earned"], 100)

        # Running was not logged yet
        running_task = next(t for t in progress["tasks"] if t["name"] == "Running")
        self.assertFalse(running_task["completed"])
        self.assertEqual(running_task["current_amount"], 0.0)

    def test_06_streaks_and_summaries(self):
        user_id = 2002
        db.get_or_create_user(user_id, "Arjun", TEST_DB)

        today = date.today()
        day_1 = (today - timedelta(days=2)).isoformat()
        day_2 = (today - timedelta(days=1)).isoformat()

        # Complete all 4 tasks for Day 1
        db.log_activity(user_id, "Arjun", "Push-ups", 100, day_1, TEST_DB)
        db.log_activity(user_id, "Arjun", "Pull-ups", 20, day_1, TEST_DB)
        db.log_activity(user_id, "Arjun", "Squats", 100, day_1, TEST_DB)
        db.log_activity(user_id, "Arjun", "Running", 5, day_1, TEST_DB)

        # Complete all 4 tasks for Day 2
        db.log_activity(user_id, "Arjun", "Push-ups", 100, day_2, TEST_DB)
        db.log_activity(user_id, "Arjun", "Pull-ups", 20, day_2, TEST_DB)
        db.log_activity(user_id, "Arjun", "Squats", 100, day_2, TEST_DB)
        db.log_activity(user_id, "Arjun", "Running", 5, day_2, TEST_DB)

        # Finalize Day 1 and Day 2 summaries
        db.finalize_daily_summaries(day_1, TEST_DB)
        db.finalize_daily_summaries(day_2, TEST_DB)

        # Streak should be 2 days
        streak = db.calculate_streak(user_id, as_of_date=today.isoformat(), db_path=TEST_DB)
        self.assertEqual(streak, 2)

        # Complete today as well -> streak becomes 3
        today_str = today.isoformat()
        db.log_activity(user_id, "Arjun", "Push-ups", 100, today_str, TEST_DB)
        db.log_activity(user_id, "Arjun", "Pull-ups", 20, today_str, TEST_DB)
        db.log_activity(user_id, "Arjun", "Squats", 100, today_str, TEST_DB)
        db.log_activity(user_id, "Arjun", "Running", 5, today_str, TEST_DB)

        streak_today = db.calculate_streak(user_id, as_of_date=today.isoformat(), db_path=TEST_DB)
        self.assertEqual(streak_today, 3)

    def test_07_leaderboard_queries(self):
        today_str = date.today().isoformat()
        daily_lb = db.get_daily_leaderboard(today_str, TEST_DB)
        self.assertTrue(len(daily_lb) >= 2)
        # Arjun has 400 pts today, Vishnu has 100 pts -> Arjun should rank first
        self.assertEqual(daily_lb[0]["username"], "Arjun")
        self.assertEqual(daily_lb[0]["points"], 400)

        # Monthly leaderboard
        today = date.today()
        month_lb = db.get_monthly_leaderboard(today.year, today.month, TEST_DB)
        self.assertTrue(len(month_lb) >= 2)
        self.assertEqual(month_lb[0]["username"], "Arjun")
        self.assertGreaterEqual(month_lb[0]["total_points"], 1200)

    def test_08_reminder_preferences(self):
        user = db.get_user_by_discord_id(1001, TEST_DB)
        self.assertEqual(user["morning_reminder"], 1)

        # Toggle morning off
        updated = db.update_reminder_preferences(1001, morning=False, db_path=TEST_DB)
        self.assertEqual(updated["morning_reminder"], 0)
        self.assertEqual(updated["afternoon_reminder"], 1)

        opted_in_morning = db.get_users_for_reminder("morning", TEST_DB)
        morning_ids = [u["discord_id"] for u in opted_in_morning]
        self.assertNotIn(1001, morning_ids)
        self.assertIn(2002, morning_ids)


if __name__ == "__main__":
    unittest.main()
