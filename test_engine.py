"""
test_engine.py - Automated Tests for Redesigned Winter Arc Engine
Covers: Enrollment gating, server settings, scoring math, capping, streaks, and leaderboards.
"""

import os
import unittest
from datetime import date, timedelta
import database as db

TEST_DB = "test_winter_arc.db"


class TestWinterArcRedesignEngine(unittest.TestCase):
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
        names = [t["name"] for t in tasks]
        self.assertIn("Push-ups", names)
        self.assertIn("Pull-ups", names)
        self.assertIn("Squats", names)
        self.assertIn("Sit-ups", names)
        self.assertIn("Running", names)
        self.assertEqual(len(tasks), 5)
        total_max_pts = sum(t["max_points"] for t in tasks)
        self.assertEqual(total_max_pts, 500)

    def test_02_server_settings_persistence(self):
        guild_id = 999111
        settings = db.get_server_settings(guild_id, TEST_DB)
        self.assertEqual(settings["channel_id"], 0)
        self.assertEqual(settings["role_id"], 0)

        # Set channel and role
        db.set_server_channel(guild_id, 888777, TEST_DB)
        db.set_server_role(guild_id, 555444, TEST_DB)

        updated = db.get_server_settings(guild_id, TEST_DB)
        self.assertEqual(updated["channel_id"], 888777)
        self.assertEqual(updated["role_id"], 555444)

    def test_03_enrollment_gate(self):
        user_id = 1001
        self.assertFalse(db.is_user_enrolled(user_id, TEST_DB))

        # Unenrolled user cannot log activity
        today = date.today().isoformat()
        with self.assertRaises(ValueError):
            db.log_activity(user_id, "Vishnu", "Push-ups", 30, today, TEST_DB)

        # Enroll user
        user = db.enroll_user(user_id, "Vishnu", TEST_DB)
        self.assertTrue(db.is_user_enrolled(user_id, TEST_DB))
        self.assertEqual(user["username"], "Vishnu")

        # Now logging succeeds
        res = db.log_activity(user_id, "Vishnu", "Push-ups", 30, today, TEST_DB)
        self.assertEqual(res["new_total"], 30.0)
        self.assertEqual(res["points_earned_delta"], 30)

        # Unenroll user
        db.unenroll_user(user_id, TEST_DB)
        self.assertFalse(db.is_user_enrolled(user_id, TEST_DB))

        # Re-enroll
        db.enroll_user(user_id, "Vishnu", TEST_DB)
        self.assertTrue(db.is_user_enrolled(user_id, TEST_DB))

    def test_04_capped_scoring_and_abuse_rejection(self):
        today = date.today().isoformat()
        user_id = 1001

        # Push-ups target is 100. Previous was 30.
        # Log 70 more -> total 100 -> +70 pts (task pts: 100)
        res1 = db.log_activity(user_id, "Vishnu", "Push-ups", 70, today, TEST_DB)
        self.assertEqual(res1["new_total"], 100.0)
        self.assertEqual(res1["points_earned_delta"], 70)
        self.assertEqual(res1["task_points_total"], 100)

        # Log 50 more beyond target -> total 150 -> capped at 100 pts (+0 pts delta)
        res2 = db.log_activity(user_id, "Vishnu", "Push-ups", 50, today, TEST_DB)
        self.assertEqual(res2["new_total"], 150.0)
        self.assertEqual(res2["points_earned_delta"], 0)
        self.assertEqual(res2["task_points_total"], 100)

        # Negative and zero rejected
        with self.assertRaises(ValueError):
            db.log_activity(user_id, "Vishnu", "Push-ups", -10, today, TEST_DB)
        with self.assertRaises(ValueError):
            db.log_activity(user_id, "Vishnu", "Push-ups", 0, today, TEST_DB)

    def test_05_streaks_and_summaries(self):
        user_id = 2002
        db.enroll_user(user_id, "Arjun", TEST_DB)

        today = date.today()
        d1 = (today - timedelta(days=2)).isoformat()
        d2 = (today - timedelta(days=1)).isoformat()

        # Day 1 100% completion (500 pts total)
        db.log_activity(user_id, "Arjun", "Push-ups", 100, d1, TEST_DB)
        db.log_activity(user_id, "Arjun", "Pull-ups", 100, d1, TEST_DB)
        db.log_activity(user_id, "Arjun", "Sit-ups", 100, d1, TEST_DB)
        db.log_activity(user_id, "Arjun", "Squats", 100, d1, TEST_DB)
        db.log_activity(user_id, "Arjun", "Running", 10, d1, TEST_DB)

        # Day 2 100% completion (500 pts total)
        db.log_activity(user_id, "Arjun", "Push-ups", 100, d2, TEST_DB)
        db.log_activity(user_id, "Arjun", "Pull-ups", 100, d2, TEST_DB)
        db.log_activity(user_id, "Arjun", "Sit-ups", 100, d2, TEST_DB)
        db.log_activity(user_id, "Arjun", "Squats", 100, d2, TEST_DB)
        db.log_activity(user_id, "Arjun", "Running", 10, d2, TEST_DB)

        db.finalize_daily_summaries(d1, TEST_DB)
        db.finalize_daily_summaries(d2, TEST_DB)

        streak = db.calculate_streak(user_id, as_of_date=today.isoformat(), db_path=TEST_DB)
        self.assertEqual(streak, 2)

    def test_06_enrolled_leaderboard(self):
        today_str = date.today().isoformat()
        lb = db.get_daily_leaderboard(today_str, TEST_DB)
        usernames = [u["username"] for u in lb]
        self.assertIn("Vishnu", usernames)
        self.assertIn("Arjun", usernames)

    def test_07_set_activity_override(self):
        user_id = 1001
        today = date.today().isoformat()

        # Force set total to 45
        res1 = db.set_activity(user_id, "Vishnu", "Push-ups", 45, today, TEST_DB)
        self.assertEqual(res1["new_total"], 45.0)
        self.assertEqual(res1["task_points_total"], 45)

        # Reset to 0
        res2 = db.set_activity(user_id, "Vishnu", "Push-ups", 0, today, TEST_DB)
        self.assertEqual(res2["new_total"], 0.0)
        self.assertEqual(res2["task_points_total"], 0)


if __name__ == "__main__":
    unittest.main()
