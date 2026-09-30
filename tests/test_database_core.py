"""
tests/test_database_core.py - Core Database Schema, Settings, Auth, and Timezone Tests
"""
from datetime import date, datetime
import database as db
from config import BOT_TZ
from tests.base import WinterArcTestCase


class TestDatabaseSchemaAndSeeding(WinterArcTestCase):
    """Verifies schema initialization, core tasks catalog, and bot state storage."""

    def test_default_tasks_seeded_and_points_sum_to_500(self):
        """Verifies that all 5 default disciplines are seeded with exact target points."""
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

    def test_bot_state_key_value_persistence(self):
        """Verifies persistent key-value storage for bot scheduler state."""
        val = db.get_bot_state("non_existent_key", default="fallback", db_path=self.test_db)
        self.assertEqual(val, "fallback")

        db.set_bot_state("last_midnight_date", "2026-09-19", db_path=self.test_db)
        val = db.get_bot_state("last_midnight_date", db_path=self.test_db)
        self.assertEqual(val, "2026-09-19")

        db.set_bot_state("last_midnight_date", "2026-09-20", db_path=self.test_db)
        val = db.get_bot_state("last_midnight_date", db_path=self.test_db)
        self.assertEqual(val, "2026-09-20")


class TestUserEnrollmentAndSettings(WinterArcTestCase):
    """Verifies user enrollment gating, guild settings, and DM preferences."""

    def test_enrollment_gate_blocks_logging_until_enrolled(self):
        """Verifies that unenrolled users cannot log and re-enrollment preserves integrity."""
        user_id = 1001
        self.assertFalse(db.is_user_enrolled(user_id, self.test_db))

        today = date.today().isoformat()
        with self.assertRaises(ValueError):
            db.log_activity(user_id, "Vishnu", "Push-ups", 30, today, self.test_db)

        user = db.enroll_user(user_id, "Vishnu", self.test_db)
        self.assertTrue(db.is_user_enrolled(user_id, self.test_db))
        self.assertEqual(user["username"], "Vishnu")

        res = db.log_activity(user_id, "Vishnu", "Push-ups", 30, today, self.test_db)
        self.assertEqual(res["new_total"], 30.0)
        self.assertEqual(res["points_earned_delta"], 30)

        db.unenroll_user(user_id, self.test_db)
        self.assertFalse(db.is_user_enrolled(user_id, self.test_db))

        db.enroll_user(user_id, "Vishnu", self.test_db)
        self.assertTrue(db.is_user_enrolled(user_id, self.test_db))

    def test_server_settings_channel_and_role_persistence(self):
        """Verifies server channel and role configuration storage per guild."""
        guild_id = 999111
        settings = db.get_server_settings(guild_id, self.test_db)
        self.assertEqual(settings["channel_id"], 0)
        self.assertEqual(settings["role_id"], 0)

        db.set_server_channel(guild_id, 888777, self.test_db)
        db.set_server_role(guild_id, 555444, self.test_db)

        updated = db.get_server_settings(guild_id, self.test_db)
        self.assertEqual(updated["channel_id"], 888777)
        self.assertEqual(updated["role_id"], 555444)

    def test_user_dm_settings_preferences_and_opt_in_filtering(self):
        """Verifies DM opt-in toggles and dispatch filtering."""
        user_id = 2003
        db.enroll_user(user_id, "DMWarrior", self.test_db)

        defaults = db.get_user_dm_settings(user_id, self.test_db)
        self.assertFalse(defaults["dm_reminders"])
        self.assertTrue(defaults["dm_morning"])
        self.assertTrue(defaults["dm_evening"])

        updated = db.update_user_dm_settings(user_id, dm_reminders=True, dm_evening=False, db_path=self.test_db)
        self.assertTrue(updated["dm_reminders"])
        self.assertTrue(updated["dm_morning"])
        self.assertFalse(updated["dm_evening"])

        morning_users = db.get_opted_in_dm_users("morning", self.test_db)
        self.assertTrue(any(u["discord_id"] == user_id for u in morning_users))

        evening_users = db.get_opted_in_dm_users("evening", self.test_db)
        self.assertFalse(any(u["discord_id"] == user_id for u in evening_users))


class TestDatabaseTimezoneConsistency(WinterArcTestCase):
    """Verifies that all database date helpers strictly return BOT_TZ dates."""

    def test_database_date_helpers_match_bot_timezone(self):
        expected_today = datetime.now(BOT_TZ).date().isoformat()

        self.assertEqual(db.get_today_str(), expected_today)
        self.assertEqual(db.get_today_date().isoformat(), expected_today)

        user_id = 991105
        db.enroll_user(user_id, "TzWarrior", self.test_db)

        streak = db.calculate_streak(user_id, db_path=self.test_db)
        self.assertEqual(streak, 0)

        stats = db.get_user_stats(user_id, self.test_db)
        self.assertIn("current_streak", stats)
        self.assertIn("lifetime_points", stats)
