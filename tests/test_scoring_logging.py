"""
tests/test_scoring_logging.py - Workout Logging, Capped Scoring, /set Overrides, and Validation Tests
"""
from datetime import date
import database as db
from tests.base import WinterArcTestCase


class TestScoringLogging(WinterArcTestCase):
    def test_04_capped_scoring_and_abuse_rejection(self):
        today = date.today().isoformat()
        user_id = 1001
        db.enroll_user(user_id, "Vishnu", self.test_db)

        # Push-ups target is 100. Previous was 0.
        # Log 70 -> total 70 -> +70 pts (task pts: 70)
        res1 = db.log_activity(user_id, "Vishnu", "Push-ups", 70, today, self.test_db)
        self.assertEqual(res1["new_total"], 70.0)
        self.assertEqual(res1["points_earned_delta"], 70)
        self.assertEqual(res1["task_points_total"], 70)

        # Log 30 more -> total 100 -> +30 pts (task pts: 100)
        res2 = db.log_activity(user_id, "Vishnu", "Push-ups", 30, today, self.test_db)
        self.assertEqual(res2["new_total"], 100.0)
        self.assertEqual(res2["points_earned_delta"], 30)
        self.assertEqual(res2["task_points_total"], 100)

        # Log 50 more beyond target -> total 150 -> capped at 100 pts (+0 pts delta)
        res3 = db.log_activity(user_id, "Vishnu", "Push-ups", 50, today, self.test_db)
        self.assertEqual(res3["new_total"], 150.0)
        self.assertEqual(res3["points_earned_delta"], 0)
        self.assertEqual(res3["task_points_total"], 100)

        # Negative and zero rejected
        with self.assertRaises(ValueError):
            db.log_activity(user_id, "Vishnu", "Push-ups", -10, today, self.test_db)
        with self.assertRaises(ValueError):
            db.log_activity(user_id, "Vishnu", "Push-ups", 0, today, self.test_db)

    def test_07_set_activity_override(self):
        user_id = 1001
        db.enroll_user(user_id, "Vishnu", self.test_db)
        today = date.today().isoformat()

        # Force set total to 45
        res1 = db.set_activity(user_id, "Vishnu", "Push-ups", 45, today, self.test_db)
        self.assertEqual(res1["new_total"], 45.0)
        self.assertEqual(res1["task_points_total"], 45)

        # Reset to 0
        res2 = db.set_activity(user_id, "Vishnu", "Push-ups", 0, today, self.test_db)
        self.assertEqual(res2["new_total"], 0.0)
        self.assertEqual(res2["task_points_total"], 0)

    def test_32_user_recent_logs_and_grinds(self):
        user_id = 999222
        db.enroll_user(user_id, "Berserker", self.test_db)
        today = date.today().isoformat()

        # Log physical tasks
        db.log_activity(user_id, "Berserker", "Push-ups", 50, today, self.test_db)
        db.log_activity(user_id, "Berserker", "Running", 5, today, self.test_db)

        recent_logs = db.get_user_recent_logs(user_id, limit=3, db_path=self.test_db)
        self.assertGreaterEqual(len(recent_logs), 2)
        task_names = [l["task_name"] for l in recent_logs]
        self.assertIn("Push-ups", task_names)
        self.assertIn("Running", task_names)

        # Log grind
        db.record_grind_entry(
            discord_id=user_id,
            date_str=today,
            raw_input="Studied compiler memory layouts and registers",
            verdict="ACCEPTED",
            points=50,
            key_learning="Compiler Registers",
            commentary="Cold stoic discipline.",
            db_path=self.test_db
        )

        recent_grinds = db.get_user_recent_grinds(user_id, limit=2, db_path=self.test_db)
        self.assertEqual(len(recent_grinds), 1)
        self.assertEqual(recent_grinds[0]["key_learning"], "Compiler Registers")

    def test_34_task_name_resolution(self):
        """Verifies that get_task_by_name correctly resolves autocomplete labels, emojis, parens, and aliases."""
        user_id = 998877
        db.enroll_user(user_id, "FuzzyWarrior", self.test_db)
        today = date.today().isoformat()

        labels = [
            ("💪 Push-ups (100 reps)", "Push-ups"),
            ("🧗 Pull-ups (100 reps)", "Pull-ups"),
            ("🦵 Squats (100 reps)", "Squats"),
            ("🧘 Sit-ups (100 reps)", "Sit-ups"),
            ("🏃 Running (10 km)", "Running"),
            ("🟢 Push-ups (Active)", "Push-ups"),
            ("🔴 Running (Disabled)", "Running"),
            ("pushups", "Push-ups"),
            ("pushup", "Push-ups"),
            ("chins", "Pull-ups"),
            ("chinups", "Pull-ups"),
            ("squat", "Squats"),
            ("situps", "Sit-ups"),
            ("crunches", "Sit-ups"),
            ("abs", "Sit-ups"),
            ("run", "Running"),
            ("jog", "Running"),
        ]

        for input_label, expected_canonical in labels:
            task = db.get_task_by_name(input_label, self.test_db)
            self.assertIsNotNone(task, f"Failed to resolve task for '{input_label}'")
            self.assertEqual(task["name"], expected_canonical, f"Mismatch for '{input_label}'")

        # Test set_activity directly with autocomplete string
        res = db.set_activity(
            discord_id=user_id,
            username="FuzzyWarrior",
            task_name="💪 Push-ups (100 reps)",
            target_amount=40.0,
            log_date=today,
            db_path=self.test_db
        )
        self.assertEqual(res["new_total"], 40.0)
        self.assertEqual(res["task_name"], "Push-ups")

        # Test log_activity directly with alias string
        res_log = db.log_activity(
            discord_id=user_id,
            username="FuzzyWarrior",
            task_name="pushups",
            amount=15.0,
            log_date=today,
            db_path=self.test_db
        )
        self.assertEqual(res_log["new_total"], 55.0)
        self.assertEqual(res_log["task_name"], "Push-ups")

    def test_38_set_and_log_return_schema_and_zero_division(self):
        """Verifies schema consistency between log and set return dictionaries and zero-division protection."""
        user_id = 991104
        db.enroll_user(user_id, "SchemaWarrior", self.test_db)
        today = db.get_today_str()

        # Test log_activity return keys
        log_res = db.log_activity(user_id, "SchemaWarrior", "Push-ups", 30, today, self.test_db)
        required_keys = [
            "points_added", "new_points", "points_earned_delta",
            "previous_total", "new_total", "task_points_total",
            "task_max_points", "is_target_reached", "daily_points_total",
            "daily_points_max", "daily_completion_rate", "shield_awarded"
        ]
        for key in required_keys:
            self.assertIn(key, log_res, f"log_activity missing key: {key}")

        # Test set_activity return keys
        set_res = db.set_activity(user_id, "SchemaWarrior", "Push-ups", 50, today, self.test_db)
        set_required_keys = [
            "old_points", "new_points", "points_added", "points_earned_delta",
            "previous_total", "new_total", "task_points_total",
            "task_max_points", "is_target_reached", "daily_points_total"
        ]
        for key in set_required_keys:
            self.assertIn(key, set_res, f"set_activity missing key: {key}")

        # Test validation guards
        with self.assertRaises(ValueError):
            db.log_activity(user_id, "SchemaWarrior", "Push-ups", -10, today, self.test_db)

        with self.assertRaises(ValueError):
            db.set_activity(user_id, "SchemaWarrior", "Push-ups", -5, today, self.test_db)

        with self.assertRaises(ValueError):
            db.log_activity(user_id, "SchemaWarrior", "Push-ups", 6000, today, self.test_db)

        with self.assertRaises(ValueError):
            db.add_task(name="InvalidZero", target=0, unit="reps", max_points=100, db_path=self.test_db)

        with self.assertRaises(ValueError):
            db.add_task(name="InvalidNegPts", target=10, unit="reps", max_points=-50, db_path=self.test_db)
