"""
tests/test_database_core.py - Core Database, Settings, and Auth Tests
"""
from datetime import date, datetime
import database as db
from config import BOT_TZ
from tests.base import WinterArcTestCase


class TestDatabaseCore(WinterArcTestCase):
    def test_01_tasks_seeded(self):
        tasks = db.get_active_tasks(self.test_db)
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
        settings = db.get_server_settings(guild_id, self.test_db)
        self.assertEqual(settings["channel_id"], 0)
        self.assertEqual(settings["role_id"], 0)

        # Set channel and role
        db.set_server_channel(guild_id, 888777, self.test_db)
        db.set_server_role(guild_id, 555444, self.test_db)

        updated = db.get_server_settings(guild_id, self.test_db)
        self.assertEqual(updated["channel_id"], 888777)
        self.assertEqual(updated["role_id"], 555444)

    def test_03_enrollment_gate(self):
        user_id = 1001
        self.assertFalse(db.is_user_enrolled(user_id, self.test_db))

        # Unenrolled user cannot log activity
        today = date.today().isoformat()
        with self.assertRaises(ValueError):
            db.log_activity(user_id, "Vishnu", "Push-ups", 30, today, self.test_db)

        # Enroll user
        user = db.enroll_user(user_id, "Vishnu", self.test_db)
        self.assertTrue(db.is_user_enrolled(user_id, self.test_db))
        self.assertEqual(user["username"], "Vishnu")

        # Now logging succeeds
        res = db.log_activity(user_id, "Vishnu", "Push-ups", 30, today, self.test_db)
        self.assertEqual(res["new_total"], 30.0)
        self.assertEqual(res["points_earned_delta"], 30)

        # Unenroll user
        db.unenroll_user(user_id, self.test_db)
        self.assertFalse(db.is_user_enrolled(user_id, self.test_db))

        # Re-enroll
        db.enroll_user(user_id, "Vishnu", self.test_db)
        self.assertTrue(db.is_user_enrolled(user_id, self.test_db))

    def test_14_user_dm_settings(self):
        user_id = 2003
        db.enroll_user(user_id, "DMWarrior", self.test_db)

        # Default settings: DMs off
        defaults = db.get_user_dm_settings(user_id, self.test_db)
        self.assertFalse(defaults["dm_reminders"])
        self.assertTrue(defaults["dm_morning"])
        self.assertTrue(defaults["dm_evening"])

        # Opt in
        updated = db.update_user_dm_settings(user_id, dm_reminders=True, dm_evening=False, db_path=self.test_db)
        self.assertTrue(updated["dm_reminders"])
        self.assertTrue(updated["dm_morning"])
        self.assertFalse(updated["dm_evening"])

        # Query opted in users
        morning_users = db.get_opted_in_dm_users("morning", self.test_db)
        self.assertTrue(any(u["discord_id"] == user_id for u in morning_users))

        evening_users = db.get_opted_in_dm_users("evening", self.test_db)
        self.assertFalse(any(u["discord_id"] == user_id for u in evening_users))

    def test_18_bot_state_persistence(self):
        # Initial missing state returns default
        val = db.get_bot_state("non_existent_key", default="fallback", db_path=self.test_db)
        self.assertEqual(val, "fallback")

        # Set and retrieve state
        db.set_bot_state("last_midnight_date", "2026-09-19", db_path=self.test_db)
        val = db.get_bot_state("last_midnight_date", db_path=self.test_db)
        self.assertEqual(val, "2026-09-19")

        # Update existing state
        db.set_bot_state("last_midnight_date", "2026-09-20", db_path=self.test_db)
        val = db.get_bot_state("last_midnight_date", db_path=self.test_db)
        self.assertEqual(val, "2026-09-20")

    def test_39_database_timezone_consistency(self):
        """Verifies that all database date helpers strictly return BOT_TZ dates."""
        expected_today = datetime.now(BOT_TZ).date().isoformat()

        self.assertEqual(db.get_today_str(), expected_today)
        self.assertEqual(db.get_today_date().isoformat(), expected_today)

        user_id = 991105
        db.enroll_user(user_id, "TzWarrior", self.test_db)

        # Calling calculate_streak without as_of_date must default cleanly to BOT_TZ
        streak = db.calculate_streak(user_id, db_path=self.test_db)
        self.assertEqual(streak, 0)

        # Calling get_user_stats without date must resolve without error
        stats = db.get_user_stats(user_id, self.test_db)
        self.assertIn("current_streak", stats)
        self.assertIn("lifetime_points", stats)
