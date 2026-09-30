"""
tests/test_ai_services.py - AI Parsing, Groq Nudges, and Gemini Grind Evaluation Tests
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import database as db
from ai import groq_service
from ai.groq_service import regex_fallback_parser, extract_disciplines_fallback
from ai.gemini_service import evaluate_grind, GeminiServiceError
from tests.base import WinterArcTestCase


class TestAIServices(WinterArcTestCase):
    def test_15_grind_log_db_lifecycle(self):
        user_id = 3001
        db.enroll_user(user_id, "GrindMaster", self.test_db)
        today_str = "2026-09-18"

        entry = db.record_grind_entry(
            discord_id=user_id,
            date_str=today_str,
            raw_input="Studied kernel memory and solved 2 Hard LeetCode",
            verdict="ACCEPTED",
            points=45,
            key_learning="OS Memory Virtualization",
            commentary="Real friction. Do not get complacent.",
            db_path=self.test_db
        )
        self.assertEqual(entry["points_awarded"], 45)
        self.assertEqual(entry["verdict"], "ACCEPTED")

        # Strict 1 submission per day
        with self.assertRaises(ValueError):
            db.record_grind_entry(
                discord_id=user_id,
                date_str=today_str,
                raw_input="Another submission on same day",
                verdict="ACCEPTED",
                points=30,
                key_learning="Algorithms",
                commentary="Extra",
                db_path=self.test_db
            )

        retrieved = db.get_user_daily_grind(user_id, today_str, self.test_db)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["points_awarded"], 45)

        prog = db.get_user_daily_progress(user_id, today_str, self.test_db)
        self.assertEqual(prog["grind_points"], 45)
        self.assertEqual(prog["physical_points"], 0)
        self.assertEqual(prog["total_points"], 45)

        daily_hl = db.get_daily_grind_highlights(today_str, self.test_db)
        self.assertEqual(len(daily_hl), 1)
        self.assertEqual(daily_hl[0]["username"], "GrindMaster")

        weekly_hl = db.get_weekly_grind_highlights("2026-09-15", "2026-09-20", self.test_db)
        self.assertEqual(len(weekly_hl), 1)

    def test_16_groq_workout_parser(self):
        active_tasks = db.get_active_tasks(self.test_db)

        res = regex_fallback_parser("did 45 pushups, 15 pullups and ran 5.5k", active_tasks)
        matches = {m["task_name"]: m["amount"] for m in res["matches"]}
        self.assertIn("Push-ups", matches)
        self.assertEqual(matches["Push-ups"], 45.0)
        self.assertIn("Pull-ups", matches)
        self.assertEqual(matches["Pull-ups"], 15.0)
        self.assertIn("Running", matches)
        self.assertEqual(matches["Running"], 5.5)

        res_foreign = regex_fallback_parser("did 50 bicep curls and 20 bench presses", active_tasks)
        self.assertEqual(len(res_foreign["matches"]), 0)

    def test_17_gemini_grind_evaluator(self):
        try:
            res = asyncio.run(evaluate_grind("Studied operating systems 4 hours and solved 2 Hard DP problems"))
            self.assertIn("verdict", res)
            self.assertIn(res["verdict"], ["ACCEPTED", "REJECTED", "ROASTED"])
            self.assertIn("points", res)
            self.assertTrue(0 <= res["points"] <= 60)
            self.assertIn("commentary", res)
        except GeminiServiceError as e:
            self.assertTrue(len(str(e)) > 0)

    def test_33_groq_reactive_nudges(self):
        progression = {
            "points": 250,
            "max_points": 500,
            "pct": 50,
            "streak": 5,
            "completed_tasks": ["Push-ups", "Sit-ups"],
            "pending_tasks": ["Running", "Squats", "Pull-ups"],
            "extra_info": "Logged 50 pushups",
        }
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Halfway there. 250 points remain."
        mock_res = MagicMock()
        mock_res.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_res)

        with patch.object(groq_service, "get_groq_client", return_value=mock_client):
            nudge = asyncio.run(groq_service.generate_reactive_nudge(
                user_name="Fenrir",
                command_name="today",
                progression=progression
            ))
            self.assertEqual(nudge, "Halfway there. 250 points remain.")

        test_uid = 999333
        self.assertTrue(groq_service.should_trigger_nudge(test_uid, force=True))
        groq_service.record_nudge_triggered(test_uid)
        self.assertFalse(groq_service.should_trigger_nudge(test_uid, force=False))

    def test_37_quicklog_fallback_parsing_robustness(self):
        active_tasks = db.get_active_tasks(self.test_db)

        # Case 1: Number before keyword
        res1 = extract_disciplines_fallback("did 25 pushups and ran 5.5 km", active_tasks)
        matches1 = {m["task_name"]: m["amount"] for m in res1["matches"]}
        self.assertEqual(matches1.get("Push-ups"), 25.0)
        self.assertEqual(matches1.get("Running"), 5.5)
        self.assertFalse(res1["suspicious"])

        # Case 2: Keyword before number with colons and equals
        res2 = extract_disciplines_fallback("pushups: 40, pullups: 15, squats = 50", active_tasks)
        matches2 = {m["task_name"]: m["amount"] for m in res2["matches"]}
        self.assertEqual(matches2.get("Push-ups"), 40.0)
        self.assertEqual(matches2.get("Pull-ups"), 15.0)
        self.assertEqual(matches2.get("Squats"), 50.0)
        self.assertFalse(res2["suspicious"])

        # Case 3: Aliases (chins, crunches, jog)
        res3 = extract_disciplines_fallback("12 chins, 45 crunches, 4km jog", active_tasks)
        matches3 = {m["task_name"]: m["amount"] for m in res3["matches"]}
        self.assertEqual(matches3.get("Pull-ups"), 12.0)
        self.assertEqual(matches3.get("Sit-ups"), 45.0)
        self.assertEqual(matches3.get("Running"), 4.0)

        # Case 4: Single-set suspicious rejection
        res4 = extract_disciplines_fallback("did 75 pushups in one go", active_tasks)
        self.assertTrue(res4["suspicious"], "Should flag >50 push-ups as suspicious single-set volume")

        res5 = extract_disciplines_fallback("ran 15 km this morning", active_tasks)
        self.assertTrue(res5["suspicious"], "Should flag >10 km run as suspicious single-set volume")

        # Case 5: Unrelated non-discipline text
        res6 = extract_disciplines_fallback("just had coffee and studied chemistry", active_tasks)
        self.assertEqual(len(res6["matches"]), 0)
