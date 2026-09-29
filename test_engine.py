"""
test_engine.py - Automated Tests for Redesigned Winter Arc Engine
Covers: Enrollment gating, server settings, scoring math, capping, streaks, and leaderboards.
"""

import os
import unittest
from datetime import date, timedelta, datetime, timezone
import database as db

TEST_DB = "test_winter_arc.db"


class TestWinterArcRedesignEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        db.init_db(TEST_DB)
        cls._created_default_db = False
        if not os.path.exists(db.DB_PATH):
            db.init_db(db.DB_PATH)
            cls._created_default_db = True

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        if getattr(cls, "_created_default_db", False) and os.path.exists(db.DB_PATH):
            try:
                os.remove(db.DB_PATH)
            except Exception:
                pass

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

    def test_08_overall_leaderboard(self):
        overall = db.get_overall_leaderboard(TEST_DB)
        self.assertGreater(len(overall), 0)
        usernames = [u["username"] for u in overall]
        self.assertIn("Arjun", usernames)
        self.assertIn("Vishnu", usernames)
        # Top user should be Arjun who logged 500 on past days
        self.assertEqual(overall[0]["username"], "Arjun")
        self.assertGreaterEqual(overall[0]["total_points"], 1000)

    def test_09_leveling_hierarchy(self):
        from levels import get_level_info, get_all_ranks, RANKS

        self.assertEqual(len(RANKS), 12)
        all_r = get_all_ranks()
        self.assertEqual(len(all_r), 12)

        # Level 1: Initiate
        l1 = get_level_info(0)
        self.assertEqual(l1["level"], 1)
        self.assertEqual(l1["title"], "Initiate")

        # Level 2: Novice
        l2 = get_level_info(500)
        self.assertEqual(l2["level"], 2)
        self.assertEqual(l2["title"], "Novice")

        # Level 7: Iron
        l7 = get_level_info(5500)
        self.assertEqual(l7["level"], 7)
        self.assertEqual(l7["title"], "Iron")

        # Level 12: Apex
        l12 = get_level_info(12000)
        self.assertEqual(l12["level"], 12)
        self.assertEqual(l12["title"], "Apex")
        self.assertTrue(l12["is_apex"])
        self.assertEqual(l12["tier_pct"], 100)

    def test_10_level_up_triggers(self):
        from levels import check_level_up

        # Crossing 499 -> 500 (Level 1 to Level 2)
        lvl_up = check_level_up(499, 500)
        self.assertIsNotNone(lvl_up)
        self.assertEqual(lvl_up["level"], 2)
        self.assertEqual(lvl_up["title"], "Novice")

        # No level up within same tier (500 -> 600)
        no_lvl = check_level_up(500, 600)
        self.assertIsNone(no_lvl)

        # Big leap crossing multiple levels (0 -> 2500, Level 1 to Level 4)
        big_lvl = check_level_up(0, 2500)
        self.assertIsNotNone(big_lvl)
        self.assertEqual(big_lvl["level"], 4)
        self.assertEqual(big_lvl["title"], "Dedicated")

    def test_11_autocomplete_providers(self):
        import asyncio
        from unittest.mock import MagicMock
        from helpers import (
            task_autocomplete,
            all_tasks_autocomplete,
            unit_autocomplete,
            history_days_autocomplete,
            log_amount_autocomplete,
            set_amount_autocomplete,
            target_autocomplete,
            max_points_autocomplete,
        )

        mock_interaction = MagicMock()
        mock_interaction.namespace.task = "Running"

        # Task autocomplete
        res = asyncio.run(task_autocomplete(mock_interaction, "push"))
        self.assertTrue(any("Push-ups" in c.value for c in res))

        # Contextual running amounts (km)
        res_run = asyncio.run(log_amount_autocomplete(mock_interaction, "5"))
        self.assertTrue(any("km" in c.name for c in res_run))

        # Contextual calisthenics amounts (reps)
        mock_interaction.namespace.task = "Push-ups"
        res_push = asyncio.run(log_amount_autocomplete(mock_interaction, "25"))
        self.assertTrue(any("reps" in c.name for c in res_push))

        # Set reset option (0)
        res_set = asyncio.run(set_amount_autocomplete(mock_interaction, "0"))
        self.assertTrue(any(c.value == 0.0 for c in res_set))

        # Unit autocomplete
        res_units = asyncio.run(unit_autocomplete(mock_interaction, "min"))
        self.assertTrue(any(c.value == "minutes" for c in res_units))

        # History days autocomplete
        res_hist = asyncio.run(history_days_autocomplete(mock_interaction, "14"))
        self.assertTrue(any(c.value == 14 for c in res_hist))

        # Target & Max points autocomplete
        res_target = asyncio.run(target_autocomplete(mock_interaction, "50"))
        self.assertTrue(any(c.value == 50.0 for c in res_target))
        res_pts = asyncio.run(max_points_autocomplete(mock_interaction, "100"))
        self.assertTrue(any(c.value == 100 for c in res_pts))

    def test_12_frost_shield_lifecycle(self):
        user_id = 2001
        db.enroll_user(user_id, "ShieldWarrior", TEST_DB)

        status = db.get_user_shield_status(user_id, TEST_DB)
        self.assertEqual(status["frost_shields"], 0)
        self.assertEqual(status["max_shields"], 2)
        self.assertFalse(status["is_today_shielded"])

        # Award shield at streak = 7
        awarded = db.check_and_award_shield(user_id, 7, TEST_DB)
        self.assertTrue(awarded)
        status = db.get_user_shield_status(user_id, TEST_DB)
        self.assertEqual(status["frost_shields"], 1)

        # No duplicate award for same milestone
        dup = db.check_and_award_shield(user_id, 7, TEST_DB)
        self.assertFalse(dup)

        # Award at streak = 14
        awarded_14 = db.check_and_award_shield(user_id, 14, TEST_DB)
        self.assertTrue(awarded_14)
        status = db.get_user_shield_status(user_id, TEST_DB)
        self.assertEqual(status["frost_shields"], 2)

        # Capped at 2 max
        awarded_21 = db.check_and_award_shield(user_id, 21, TEST_DB)
        self.assertFalse(awarded_21)
        status = db.get_user_shield_status(user_id, TEST_DB)
        self.assertEqual(status["frost_shields"], 2)

        # Manual activation
        act = db.activate_frost_shield(user_id, reason="Testing recovery", db_path=TEST_DB)
        self.assertTrue(act["success"])
        self.assertEqual(act["remaining_shields"], 1)

        # Today should now be shielded
        status_after = db.get_user_shield_status(user_id, TEST_DB)
        self.assertEqual(status_after["frost_shields"], 1)
        self.assertTrue(status_after["is_today_shielded"])

        # Cannot double-activate for same day
        with self.assertRaises(ValueError):
            db.activate_frost_shield(user_id, reason="Duplicate attempt", db_path=TEST_DB)

    def test_13_auto_shield_midnight(self):
        user_id = 2002
        db.enroll_user(user_id, "AutoShieldWarrior", TEST_DB)

        # Award 1 shield
        db.check_and_award_shield(user_id, 7, TEST_DB)

        day_1 = "2026-09-10"
        day_2 = "2026-09-11"

        # Log perfect day on day_1 to have active streak
        for t in ["Push-ups", "Pull-ups", "Squats", "Sit-ups", "Running"]:
            tgt = 10.0 if t == "Running" else 100.0
            db.log_activity(user_id, "AutoShieldWarrior", t, tgt, day_1, TEST_DB)

        db.finalize_daily_summaries(day_1, TEST_DB)
        streak_d1 = db.calculate_streak(user_id, day_1, TEST_DB)
        self.assertEqual(streak_d1, 1)

        # Day 2: User logs nothing, but has 1 shield and streak > 0
        db.finalize_daily_summaries(day_2, TEST_DB)

        # Shield should have been auto-consumed
        status = db.get_user_shield_status(user_id, TEST_DB)
        self.assertEqual(status["frost_shields"], 0)

        # Streak should be preserved across Day 2!
        streak_d2 = db.calculate_streak(user_id, day_2, TEST_DB)
        self.assertEqual(streak_d2, 2)

    def test_14_user_dm_settings(self):
        user_id = 2003
        db.enroll_user(user_id, "DMWarrior", TEST_DB)

        # Default settings: DMs off
        defaults = db.get_user_dm_settings(user_id, TEST_DB)
        self.assertFalse(defaults["dm_reminders"])
        self.assertTrue(defaults["dm_morning"])
        self.assertTrue(defaults["dm_evening"])

        # Opt in
        updated = db.update_user_dm_settings(user_id, dm_reminders=True, dm_evening=False, db_path=TEST_DB)
        self.assertTrue(updated["dm_reminders"])
        self.assertTrue(updated["dm_morning"])
        self.assertFalse(updated["dm_evening"])

        # Query opted in users
        morning_users = db.get_opted_in_dm_users("morning", TEST_DB)
        self.assertTrue(any(u["discord_id"] == user_id for u in morning_users))

        evening_users = db.get_opted_in_dm_users("evening", TEST_DB)
        self.assertFalse(any(u["discord_id"] == user_id for u in evening_users))

    def test_15_grind_log_db_lifecycle(self):
        user_id = 3001
        db.enroll_user(user_id, "GrindMaster", TEST_DB)

        today_str = "2026-09-18"
        # 1. Record grind entry
        entry = db.record_grind_entry(
            discord_id=user_id,
            date_str=today_str,
            raw_input="Studied kernel memory and solved 2 Hard LeetCode",
            verdict="ACCEPTED",
            points=45,
            key_learning="OS Memory Virtualization",
            commentary="Real friction. Do not get complacent.",
            db_path=TEST_DB
        )
        self.assertEqual(entry["points_awarded"], 45)
        self.assertEqual(entry["verdict"], "ACCEPTED")

        # 2. Strict 1 submission per day: second attempt must fail
        with self.assertRaises(ValueError):
            db.record_grind_entry(
                discord_id=user_id,
                date_str=today_str,
                raw_input="Another submission on same day",
                verdict="ACCEPTED",
                points=30,
                key_learning="Algorithms",
                commentary="Extra",
                db_path=TEST_DB
            )

        # 3. Retrieve user's daily grind
        retrieved = db.get_user_daily_grind(user_id, today_str, TEST_DB)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["points_awarded"], 45)

        # 4. Daily progress includes grind points
        prog = db.get_user_daily_progress(user_id, today_str, TEST_DB)
        self.assertEqual(prog["grind_points"], 45)
        self.assertEqual(prog["physical_points"], 0)
        self.assertEqual(prog["total_points"], 45)

        # 5. Highlights queries
        daily_hl = db.get_daily_grind_highlights(today_str, TEST_DB)
        self.assertEqual(len(daily_hl), 1)
        self.assertEqual(daily_hl[0]["username"], "GrindMaster")

        weekly_hl = db.get_weekly_grind_highlights("2026-09-15", "2026-09-20", TEST_DB)
        self.assertEqual(len(weekly_hl), 1)

    def test_16_groq_workout_parser(self):
        from ai.groq_service import regex_fallback_parser
        active_tasks = db.get_active_tasks(TEST_DB)

        # Multi-task natural language workout
        res = regex_fallback_parser("did 45 pushups, 15 pullups and ran 5.5k", active_tasks)
        matches = {m["task_name"]: m["amount"] for m in res["matches"]}
        self.assertIn("Push-ups", matches)
        self.assertEqual(matches["Push-ups"], 45.0)
        self.assertIn("Pull-ups", matches)
        self.assertEqual(matches["Pull-ups"], 15.0)
        self.assertIn("Running", matches)
        self.assertEqual(matches["Running"], 5.5)

        # Foreign exercise should not match active tasks
        res_foreign = regex_fallback_parser("did 50 bicep curls and 20 bench presses", active_tasks)
        self.assertEqual(len(res_foreign["matches"]), 0)

    def test_17_gemini_grind_evaluator(self):
        import asyncio
        from ai.gemini_service import evaluate_grind, GeminiServiceError

        # Test evaluation structure (works with live API key or asserts GeminiServiceError if unconfigured/quota reached)
        try:
            res = asyncio.run(evaluate_grind("Studied operating systems 4 hours and solved 2 Hard DP problems"))
            self.assertIn("verdict", res)
            self.assertIn(res["verdict"], ["ACCEPTED", "REJECTED", "ROASTED"])
            self.assertIn("points", res)
            self.assertTrue(0 <= res["points"] <= 60)
            self.assertIn("commentary", res)
        except GeminiServiceError as e:
            self.assertTrue(len(str(e)) > 0)
    def test_18_bot_state_persistence(self):
        # Initial missing state returns default
        val = db.get_bot_state("non_existent_key", default="fallback", db_path=TEST_DB)
        self.assertEqual(val, "fallback")

        # Set and retrieve state
        db.set_bot_state("last_midnight_date", "2026-09-19", db_path=TEST_DB)
        val = db.get_bot_state("last_midnight_date", db_path=TEST_DB)
        self.assertEqual(val, "2026-09-19")

        # Update existing state
        db.set_bot_state("last_midnight_date", "2026-09-20", db_path=TEST_DB)
        val = db.get_bot_state("last_midnight_date", db_path=TEST_DB)
        self.assertEqual(val, "2026-09-20")

    def test_19_optimized_streak_calculation(self):
        streak_user = 3001
        db.enroll_user(streak_user, "StreakWarrior", TEST_DB)
        today = date.today()

        # Seed 3 consecutive perfect days in daily_summaries
        with db.get_connection(TEST_DB) as conn:
            cursor = conn.cursor()
            user_rec = db.get_user_by_discord_id(streak_user, TEST_DB)
            for i in range(1, 4):
                d = (today - timedelta(days=i)).isoformat()
                cursor.execute("""
                    INSERT INTO daily_summaries (user_id, date, points, completion_rate, perfect_day, is_shielded)
                    VALUES (?, ?, 500, 1.0, 1, 0);
                """, (user_rec["id"], d))
            conn.commit()

        # Without today done, streak should be 3
        streak = db.calculate_streak(streak_user, today.isoformat(), TEST_DB)
        self.assertEqual(streak, 3)

        # Log a perfect day for today: 100 for all 5 tasks
        active_tasks = db.get_active_tasks(TEST_DB)
        for t in active_tasks:
            db.log_activity(streak_user, "StreakWarrior", t["name"], t["target"], today.isoformat(), TEST_DB)

        # Streak should now be 4
        streak = db.calculate_streak(streak_user, today.isoformat(), TEST_DB)
        self.assertEqual(streak, 4)

    def test_20_finalize_without_lock(self):
        fin_user = 4001
        db.enroll_user(fin_user, "FinWarrior", TEST_DB)
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        # Log under minimum workout for yesterday (15 pts < 30 pts)
        db.log_activity(fin_user, "FinWarrior", "Push-ups", 15, yesterday, TEST_DB)

        # Give 1 frost shield and set active past streak
        user = db.get_user_by_discord_id(fin_user, TEST_DB)
        day_before = (date.today() - timedelta(days=2)).isoformat()
        with db.get_connection(TEST_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET frost_shields = 1 WHERE id = ?;", (user["id"],))
            cursor.execute("""
                INSERT INTO daily_summaries (user_id, date, points, completion_rate, perfect_day, is_shielded)
                VALUES (?, ?, 500, 1.0, 1, 0);
            """, (user["id"], day_before))
            conn.commit()

        # Finalization should auto-shield without throwing lock error
        summaries = db.finalize_daily_summaries(yesterday, TEST_DB)
        self.assertTrue(len(summaries) >= 1)

        fin_summary = next((s for s in summaries if s["discord_id"] == fin_user), None)
        self.assertIsNotNone(fin_summary)
        self.assertTrue(fin_summary["is_shielded"])

    def test_21_shield_yesterday(self):
        shield_user = 5001
        db.enroll_user(shield_user, "ShieldWarrior", TEST_DB)
        user = db.get_user_by_discord_id(shield_user, TEST_DB)

        # Give 1 shield
        with db.get_connection(TEST_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET frost_shields = 1 WHERE id = ?;", (user["id"],))
            conn.commit()

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        res = db.activate_frost_shield(shield_user, target_date=yesterday, reason="Travel", db_path=TEST_DB)
        self.assertTrue(res["success"])
        self.assertEqual(res["target_date"], yesterday)
        self.assertEqual(res["remaining_shields"], 0)

    def test_22_batched_leaderboards(self):
        today_str = date.today().isoformat()
        daily_lb = db.get_daily_leaderboard(today_str, TEST_DB)
        self.assertIsInstance(daily_lb, list)
        self.assertTrue(len(daily_lb) >= 1)

        overall_lb = db.get_overall_leaderboard(TEST_DB)
        self.assertIsInstance(overall_lb, list)
        self.assertTrue(len(overall_lb) >= 1)

        now = date.today()
        monthly_lb = db.get_monthly_leaderboard(now.year, now.month, TEST_DB)
        self.assertIsInstance(monthly_lb, list)
        self.assertTrue(len(monthly_lb) >= 1)

    def test_23_views_and_embeds(self):
        from ui.views import LeaderboardView
        from ui.embeds import build_monthly_leaderboard_embed, build_weekly_leaderboard_embed, build_quicklog_embed

        # LeaderboardView has 600s timeout and 4 tabs: Daily, Weekly, Monthly, All-Time
        view = LeaderboardView()
        self.assertEqual(view.timeout, 600)
        custom_ids = [child.custom_id for child in view.children if hasattr(child, "custom_id")]
        self.assertIn("tab_daily", custom_ids)
        self.assertIn("tab_weekly", custom_ids)
        self.assertIn("tab_monthly", custom_ids)
        self.assertIn("tab_overall", custom_ids)

        labels = [child.label for child in view.children if hasattr(child, "label")]
        self.assertEqual(labels, ["Daily", "Weekly", "Monthly", "All-Time"])

        # Weekly embed and database method test
        weekly_lb = db.get_weekly_leaderboard(db_path=TEST_DB)
        self.assertIsInstance(weekly_lb, list)

        weekly_embed = build_weekly_leaderboard_embed()
        self.assertIn("Weekly Standings", weekly_embed.title)

        # Monthly embed builds successfully
        embed = build_monthly_leaderboard_embed()
        self.assertIn("Standings", embed.title)

    def test_24_twelve_level_progression_details(self):
        from levels import get_level_info, RANKS
        from ui.embeds import build_profile_embed
        from unittest.mock import MagicMock

        expected_titles = [
            (0, 1, "Initiate"),
            (499, 1, "Initiate"),
            (500, 2, "Novice"),
            (1199, 2, "Novice"),
            (1200, 3, "Challenger"),
            (1999, 3, "Challenger"),
            (2000, 4, "Dedicated"),
            (2999, 4, "Dedicated"),
            (3000, 5, "Disciplined"),
            (4199, 5, "Disciplined"),
            (4200, 6, "Hardened"),
            (5499, 6, "Hardened"),
            (5500, 7, "Iron"),
            (6999, 7, "Iron"),
            (7000, 8, "Vanguard"),
            (8499, 8, "Vanguard"),
            (8500, 9, "Relentless"),
            (9799, 9, "Relentless"),
            (9800, 10, "Veteran"),
            (10799, 10, "Veteran"),
            (10800, 11, "Master"),
            (11999, 11, "Master"),
            (12000, 12, "Apex"),
            (15000, 12, "Apex"),
        ]

        for pts, exp_lvl, exp_title in expected_titles:
            info = get_level_info(pts)
            self.assertEqual(info["level"], exp_lvl, f"Failed level for {pts} pts")
            self.assertEqual(info["title"], exp_title, f"Failed title for {pts} pts")

        # Test next level progress calculations at 180 pts (Level 1: Initiate -> Level 2: Novice at 500)
        info180 = get_level_info(180)
        self.assertEqual(info180["pts_to_next"], 320)
        self.assertEqual(info180["points_in_tier"], 180)
        self.assertEqual(info180["next_title"], "Novice")
        self.assertEqual(info180["next_level"], 2)

        # Profile embed verification: focuses on next level and doesn't mention distant 12,000 pts arc bar
        mock_user = MagicMock()
        mock_user.display_name = "Vishnu"
        mock_user.avatar = None
        user_record = {"joined_at": "2026-09-18 10:00:00", "frost_shields": 1}
        stats_data = {"lifetime_points": 180}

        profile_embed = build_profile_embed(mock_user, user_record, streak=5, stats_data=stats_data)
        self.assertIn("Level Progression", profile_embed.description)
        self.assertIn("Level 2 (Novice)", profile_embed.description)
        self.assertIn("180 / 500 PTS", profile_embed.description)
        self.assertIn("320 pts remaining", profile_embed.description)
        self.assertIn("All-Time Rank", profile_embed.description)
        self.assertIn("Discipline Rank", profile_embed.description)
        self.assertIn("Today's Daily Progress", profile_embed.description)
        self.assertNotIn("90-Day Arc Progress", profile_embed.description)

    def test_25_memory_management_and_singletons(self):
        from unittest.mock import MagicMock
        from ai.gemini_service import get_gemini_client
        from ai.groq_service import get_groq_client
        from cogs.admin import get_system_health_metrics, build_health_embed

        # Singleton verification
        g1 = get_gemini_client()
        g2 = get_gemini_client()
        self.assertIs(g1, g2)

        q1 = get_groq_client()
        q2 = get_groq_client()
        self.assertIs(q1, q2)

        # Health metrics verification
        mock_bot = MagicMock()
        mock_bot.start_time = datetime.now(timezone.utc)
        mock_bot.latency = 0.042
        metrics = get_system_health_metrics(mock_bot)

        self.assertIn("ram_mb", metrics)
        self.assertIsInstance(metrics["ram_mb"], float)
        self.assertIn("db_size_kb", metrics)
        self.assertIn("uptime", metrics)
        self.assertIn("enrolled_count", metrics)

        # Health embed verification
        embed = build_health_embed(metrics)
        self.assertIn("Memory Health", embed.title)
        self.assertIn("Wispbyte Free Tier", embed.description)

    def test_26_help_command_and_view(self):
        from ui.embeds import build_help_embed
        from ui.views import HelpView

        # 1. Overview
        overview_embed = build_help_embed("overview")
        self.assertIn("Master Command Manual", overview_embed.title)
        self.assertIn("500 points (Perfect Day)", overview_embed.description)
        self.assertIn("30 pts/day minimum", overview_embed.description)
        self.assertNotIn("Clean Day", overview_embed.description)
        self.assertNotIn("Clean Days", overview_embed.description)

        field_map = {f.name: f.value for f in overview_embed.fields}
        self.assertTrue(any("Daily Disciplines (500 pts max)" in k for k in field_map))
        self.assertTrue(any("The 4 Official Arc Phases" in k for k in field_map))
        self.assertTrue(any("Automated Daily Schedule" in k for k in field_map))
        self.assertTrue(any("Command Directory Cheat Sheet" in k for k in field_map))

        # Check phase breakdown
        phases_text = [v for k, v in field_map.items() if "The 4 Official Arc Phases" in k][0]
        self.assertIn("Phase 1: FIRST FROST", phases_text)
        self.assertIn("Phase 2: THE HUNT", phases_text)
        self.assertIn("Phase 3: THE ENDGAME", phases_text)
        self.assertIn("Phase 4: AFTERMATH", phases_text)

        # Check cheat sheet roster
        cheat_sheet = [v for k, v in field_map.items() if "Command Directory Cheat Sheet" in k][0]
        for cmd in ["/quick", "/log", "/set", "/grind", "/today", "/tasks", "/streak", "/consistency", "/profile", "/ranks",
                    "/leaderboard", "/stats", "/history", "/recap", "/shield status", "/shield use",
                    "/settings", "/enroll", "/leave_arc", "/ping", "/admin"]:
            self.assertIn(cmd, cheat_sheet)

        # 2. Logging
        logging_embed = build_help_embed("logging")
        self.assertIn("Workout & AI Logging Engine", logging_embed.title)
        self.assertNotIn("Clean Day", logging_embed.description)
        log_field_map = {f.name: f.value for f in logging_embed.fields}
        self.assertTrue(any("/quick" in k for k in log_field_map))
        self.assertTrue(any("#quick-log" in k for k in log_field_map))
        self.assertTrue(any("/log" in k and "/set" in k for k in log_field_map))
        self.assertTrue(any("/grind" in k for k in log_field_map))
        self.assertTrue(any("Reactive AI Coach & Bot Tips" in k for k in log_field_map))

        ai_tips_text = [v for k, v in log_field_map.items() if "Reactive AI Coach" in k][0]
        self.assertIn("Amarok", ai_tips_text)
        self.assertIn("strictly excludes `/set`", ai_tips_text)
        self.assertIn("10-minute timer", ai_tips_text)
        self.assertIn("/stats", ai_tips_text)
        self.assertIn("/recap", ai_tips_text)

        # 3. Progress & Analytics
        progress_embed = build_help_embed("progress")
        self.assertIn("Progression, Ranks & Analytics", progress_embed.title)
        self.assertNotIn("Clean Day", progress_embed.description)
        self.assertIn("Daily goal: 500 points (Perfect Day)", progress_embed.footer.text)
        prog_field_map = {f.name: f.value for f in progress_embed.fields}
        self.assertTrue(any("Tracking" in k for k in prog_field_map))
        self.assertTrue(any("12-Tier Discipline Hierarchy" in k for k in prog_field_map))
        self.assertTrue(any("Standings, Benchmarks & Analytics" in k for k in prog_field_map))

        tracking_text = [v for k, v in prog_field_map.items() if "Tracking" in k][0]
        self.assertIn("Perfect Days (100%)", tracking_text)
        self.assertIn("/streak", tracking_text)
        self.assertIn("/consistency", tracking_text)
        self.assertNotIn("clean", tracking_text.lower())

        analytics_text = [v for k, v in prog_field_map.items() if "Standings, Benchmarks" in k][0]
        self.assertIn("/leaderboard", analytics_text)
        self.assertIn("/stats [phase]", analytics_text)
        self.assertIn("Server Records & Benchmarks", analytics_text)
        self.assertIn("peak maxers", analytics_text)
        self.assertIn("most Perfect Days", analytics_text)
        self.assertIn("/recap [member]", analytics_text)
        self.assertIn("Phase Explorer", analytics_text)
        self.assertIn("/history [days]", analytics_text)

        # 4. Shields
        shields_embed = build_help_embed("shields")
        self.assertIn("Streak Shield & Recovery System", shields_embed.title)
        self.assertNotIn("Clean Day", shields_embed.description)
        shield_field_map = {f.name: f.value for f in shields_embed.fields}
        self.assertTrue(any("How Streak Shields Work" in k for k in shield_field_map))
        self.assertTrue(any("Shield Commands" in k for k in shield_field_map))
        shield_work_text = [v for k, v in shield_field_map.items() if "How Streak Shields Work" in k][0]
        self.assertIn("30 points", shield_work_text)
        self.assertIn("7-day streak milestone", shield_work_text)
        self.assertIn("2 Streak Shields", shield_work_text)

        # 5. Settings
        settings_embed = build_help_embed("settings")
        self.assertIn("Accountability, Settings & Utilities", settings_embed.title)
        set_field_map = {f.name: f.value for f in settings_embed.fields}
        self.assertTrue(any("/settings" in k for k in set_field_map))
        self.assertTrue(any("Enrollment" in k for k in set_field_map))
        dm_text = [v for k, v in set_field_map.items() if "/settings" in k][0]
        self.assertIn("Morning Kickoff DM (05:00 IST)", dm_text)
        self.assertIn("Evening Streak Warning DM (21:00 IST)", dm_text)

        # 6. Admin
        admin_embed = build_help_embed("admin")
        self.assertIn("Server Administration & Maintenance", admin_embed.title)
        adm_field_map = {f.name: f.value for f in admin_embed.fields}
        self.assertTrue(any("Broadcast Configuration" in k for k in adm_field_map))
        self.assertTrue(any("Discipline Management" in k for k in adm_field_map))
        self.assertTrue(any("System Diagnostics" in k for k in adm_field_map))
        diag_text = [v for k, v in adm_field_map.items() if "Diagnostics" in k][0]
        self.assertIn("Collect GC & Free RAM", diag_text)
        self.assertIn("/test_reminder", diag_text)

        # 7. HelpView
        view = HelpView()
        self.assertEqual(view.timeout, 300)
        selects = [child for child in view.children if hasattr(child, "options")]
        self.assertEqual(len(selects), 1)
        options = selects[0].options
        self.assertEqual(len(options), 6)
        option_values = [opt.value for opt in options]
        self.assertEqual(option_values, ["overview", "logging", "progress", "shields", "settings", "admin"])

        # Validate dropdown labels & descriptions
        progress_opt = next(o for o in options if o.value == "progress")
        self.assertEqual(progress_opt.label, "Progress & Analytics")
        self.assertIn("/stats", progress_opt.description)
        self.assertIn("/recap", progress_opt.description)

    def test_27_today_embed_per_task_bars(self):
        from ui.embeds import build_today_embed
        from unittest.mock import MagicMock

        mock_user = MagicMock()
        mock_user.display_name = "WarriorX"
        progress = {
            "total_points": 75,
            "max_possible_points": 500,
            "overall_completion_rate": 0.15,
            "perfect_day": False,
            "tasks": [
                {"name": "Push-ups", "current_amount": 50, "target": 100, "unit": "reps", "points_earned": 50, "completed": False},
                {"name": "Pull-ups", "current_amount": 25, "target": 100, "unit": "reps", "points_earned": 25, "completed": False},
            ],
            "grind_points": 0,
        }

        embed = build_today_embed(mock_user, progress, streak=4, date_display="Saturday, Sep 19")
        self.assertIn("WarriorX", embed.description)
        self.assertIn("🔥 Current Streak: **4 days** *(Streak Secured ✅)*", embed.description)
        self.assertIn("🟩🟩🟩🟩⬜⬜⬜⬜ `50%`", embed.description)
        self.assertIn("🟩🟩⬜⬜⬜⬜⬜⬜ `25%`", embed.description)
        self.assertIn("📊 **Total Daily Progress**: **75 / 500 pts** (**15%**)", embed.description)

    def test_28_evening_checkin_broadcast_embed(self):
        from ui.embeds import build_evening_checkin_embed

        enrolled = [
            {"discord_id": 101, "username": "AlphaWolf"},
            {"discord_id": 102, "username": "BetaPup"},
        ]
        today_str = "2026-09-19"
        embed = build_evening_checkin_embed(enrolled, today_str)

        self.assertIn("Evening Streak Alert", embed.title)
        self.assertIn("3 Hours Remaining", embed.description)
        self.assertIn("AlphaWolf", embed.description)
        self.assertIn("BetaPup", embed.description)

    def test_29_streak_thirty_points_minimum(self):
        user_id = 9001
        db.enroll_user(user_id, "ThirtyPtWarrior", TEST_DB)
        today = date.today().isoformat()

        # Streak should initially be 0
        self.assertEqual(db.calculate_streak(user_id, today, TEST_DB), 0)

        # Log exactly 5 reps of 4 exercises (20 pts) + 1 km run (10 pts) = 30 pts
        db.log_activity(user_id, "ThirtyPtWarrior", "Push-ups", 5, today, TEST_DB)
        db.log_activity(user_id, "ThirtyPtWarrior", "Pull-ups", 5, today, TEST_DB)
        db.log_activity(user_id, "ThirtyPtWarrior", "Squats", 5, today, TEST_DB)
        db.log_activity(user_id, "ThirtyPtWarrior", "Sit-ups", 5, today, TEST_DB)
        db.log_activity(user_id, "ThirtyPtWarrior", "Running", 1.0, today, TEST_DB)

        prog = db.get_user_daily_progress(user_id, today, TEST_DB)
        self.assertEqual(prog["total_points"], 30)

        # 30 pts should now qualify for live streak!
        streak = db.calculate_streak(user_id, today, TEST_DB)
        self.assertEqual(streak, 1)

        # Give 1 frost shield to ensure auto-shield is NOT consumed
        with db.get_connection(TEST_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET frost_shields = 1 WHERE discord_id = ?;", (user_id,))
            conn.commit()

        # Finalize day
        summaries = db.finalize_daily_summaries(today, TEST_DB)
        user_summary = next(s for s in summaries if s["discord_id"] == user_id)
        self.assertFalse(user_summary["is_shielded"])
        self.assertEqual(user_summary["points"], 30)

        # Shield should still be 1
        shield_status = db.get_user_shield_status(user_id, TEST_DB)
        self.assertEqual(shield_status["frost_shields"], 1)

    def test_30_tasks_embed_and_command(self):
        from ui.embeds import build_tasks_embed
        from cogs.warrior import WarriorCog
        from unittest.mock import MagicMock

        mock_user = MagicMock()
        mock_user.display_name = "Fenrir"
        progress = {
            "total_points": 50,
            "max_possible_points": 500,
            "overall_completion_rate": 0.10,
            "perfect_day": False,
            "tasks": [
                {
                    "name": "Push-ups",
                    "description": "Works chest, shoulders, and triceps",
                    "current_amount": 50,
                    "target": 100,
                    "unit": "reps",
                    "points_earned": 50,
                    "max_points": 100,
                    "completed": False,
                }
            ],
            "grind_points": 0,
        }

        embed = build_tasks_embed(mock_user, progress, streak=2, date_display="Saturday, Sep 19")
        self.assertIn("Fenrir", embed.description)
        self.assertIn("Disciplines & Task Guide", embed.description)
        self.assertIn("Works chest, shoulders, and triceps", embed.description)
        self.assertIn("🟩🟩🟩🟩⬜⬜⬜⬜ `50%`", embed.description)
        self.assertIn("50 / 100 reps", embed.description)

        # Verify command registration in WarriorCog
        commands = [cmd.name for cmd in WarriorCog.get_app_commands(WarriorCog(MagicMock()))]
        self.assertIn("tasks", commands)
        self.assertIn("today", commands)

    def test_31_reminder_motivation_quotes_and_embeds(self):
        import asyncio
        from ai import gemini_service
        from ui.embeds import (
            build_morning_kickoff_embed,
            build_afternoon_checkin_embed,
            build_evening_checkin_embed,
            build_dm_morning_embed,
            build_dm_evening_embed,
        )
        from unittest.mock import MagicMock

        # 1. Test generate_reminder_motivation
        quote = asyncio.run(gemini_service.generate_reminder_motivation(reminder_type="morning"))
        self.assertIsInstance(quote, str)
        self.assertTrue(len(quote) > 0)
        self.assertLessEqual(len(quote.split()), 35)

        # 2. Test embeds with quote
        test_quote = "The frost respects only discipline. Step into the cold."
        active_tasks = db.get_active_tasks(TEST_DB)
        
        m_embed = build_morning_kickoff_embed(active_tasks, "Saturday, Sep 19", quote=test_quote)
        self.assertIn("**Daily Focus**:", m_embed.description)
        self.assertIn(test_quote, m_embed.description)

        enrolled = db.get_enrolled_users(TEST_DB)
        a_embed = build_afternoon_checkin_embed(enrolled, "2026-09-19", quote=test_quote)
        self.assertIn("**Midday Note**:", a_embed.description)
        self.assertIn(test_quote, a_embed.description)

        e_embed = build_evening_checkin_embed(enrolled, "2026-09-19", quote=test_quote)
        self.assertIn("**Evening Note**:", e_embed.description)
        self.assertIn(test_quote, e_embed.description)

        mock_user = MagicMock()
        mock_user.display_name = "Fenrir"
        dm_m_embed = build_dm_morning_embed(active_tasks, streak=5, date_display="Saturday, Sep 19", quote=test_quote)
        self.assertIn("**Focus**:", dm_m_embed.description)
        self.assertIn(test_quote, dm_m_embed.description)

        prog = {"total_points": 50, "max_possible_points": 500, "overall_completion_rate": 0.1, "perfect_day": False}
        shield_status = {"frost_shields": 1}
        dm_e_embed = build_dm_evening_embed(mock_user, prog, streak=5, shield_status=shield_status, quote=test_quote)
        self.assertIn("**Evening Note**:", dm_e_embed.description)
        self.assertIn(test_quote, dm_e_embed.description)

    def test_32_user_recent_logs_and_grinds(self):
        user_id = 999222
        db.enroll_user(user_id, "Berserker", TEST_DB)
        today = date.today().isoformat()

        # Log physical tasks
        db.log_activity(user_id, "Berserker", "Push-ups", 50, today, TEST_DB)
        db.log_activity(user_id, "Berserker", "Running", 5, today, TEST_DB)

        recent_logs = db.get_user_recent_logs(user_id, limit=3, db_path=TEST_DB)
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
            db_path=TEST_DB
        )

        recent_grinds = db.get_user_recent_grinds(user_id, limit=2, db_path=TEST_DB)
        self.assertEqual(len(recent_grinds), 1)
        self.assertEqual(recent_grinds[0]["key_learning"], "Compiler Registers")

    def test_33_groq_reactive_nudges(self):
        import asyncio
        from ai import groq_service

        # 1. Test generate_reactive_nudge
        progression = {
            "points": 250,
            "max_points": 500,
            "pct": 50,
            "streak": 5,
            "completed_tasks": ["Push-ups", "Sit-ups"],
            "pending_tasks": ["Running", "Squats", "Pull-ups"],
            "extra_info": "Logged 50 pushups",
        }
        from unittest.mock import AsyncMock, MagicMock, patch
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

        # 2. Test Cooldown and force logic
        test_uid = 999333
        # Should trigger when forced
        self.assertTrue(groq_service.should_trigger_nudge(test_uid, force=True))
        
        # Record trigger
        groq_service.record_nudge_triggered(test_uid)
        
        # Normal check right after should return False due to 1-hour cooldown
        self.assertFalse(groq_service.should_trigger_nudge(test_uid, force=False))

    def test_34_task_name_resolution(self):
        """Verifies that get_task_by_name correctly resolves autocomplete labels, emojis, parens, and aliases."""
        user_id = 998877
        db.enroll_user(user_id, "FuzzyWarrior", TEST_DB)
        today = date.today().isoformat()

        # Autocomplete labels
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
            task = db.get_task_by_name(input_label, TEST_DB)
            self.assertIsNotNone(task, f"Failed to resolve task for '{input_label}'")
            self.assertEqual(task["name"], expected_canonical, f"Mismatch for '{input_label}'")

        # Test set_activity directly with autocomplete string
        res = db.set_activity(
            discord_id=user_id,
            username="FuzzyWarrior",
            task_name="💪 Push-ups (100 reps)",
            target_amount=40.0,
            log_date=today,
            db_path=TEST_DB
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
            db_path=TEST_DB
        )
        self.assertEqual(res_log["new_total"], 55.0)
        self.assertEqual(res_log["task_name"], "Push-ups")

    def test_35_streak_year_rollover_and_month_boundaries(self):
        """Verifies streak calculation across Dec 31 -> Jan 1 year rollovers and month boundaries."""
        user_id = 991101
        db.enroll_user(user_id, "YearRolloverWarrior", TEST_DB)

        # 4 consecutive days crossing year boundary: 2025-12-30, 2025-12-31, 2026-01-01, 2026-01-02
        dates = ["2025-12-30", "2025-12-31", "2026-01-01", "2026-01-02"]
        for d in dates:
            db.log_activity(user_id, "YearRolloverWarrior", "Push-ups", 100, log_date=d, db_path=TEST_DB)
            db.log_activity(user_id, "YearRolloverWarrior", "Pull-ups", 100, log_date=d, db_path=TEST_DB)
            db.log_activity(user_id, "YearRolloverWarrior", "Squats", 100, log_date=d, db_path=TEST_DB)
            db.log_activity(user_id, "YearRolloverWarrior", "Sit-ups", 100, log_date=d, db_path=TEST_DB)
            db.log_activity(user_id, "YearRolloverWarrior", "Running", 10.0, log_date=d, db_path=TEST_DB)
            db.finalize_daily_summaries(d, TEST_DB)

        # As of Jan 2, streak must be 4
        streak = db.calculate_streak(user_id, as_of_date="2026-01-02", db_path=TEST_DB)
        self.assertEqual(streak, 4)

        # Now test Feb 28 to Mar 1 boundary
        feb_dates = ["2026-02-27", "2026-02-28", "2026-03-01"]
        user_id_feb = 991102
        db.enroll_user(user_id_feb, "FebWarrior", TEST_DB)
        for d in feb_dates:
            db.log_activity(user_id_feb, "FebWarrior", "Push-ups", 50, log_date=d, db_path=TEST_DB)
            db.finalize_daily_summaries(d, TEST_DB)

        streak_feb = db.calculate_streak(user_id_feb, as_of_date="2026-03-01", db_path=TEST_DB)
        self.assertEqual(streak_feb, 3)

        # Miss a day (2026-03-02 not logged), then log on 2026-03-03
        db.log_activity(user_id_feb, "FebWarrior", "Push-ups", 50, log_date="2026-03-03", db_path=TEST_DB)
        # As of March 3, streak should reset to 1 because March 2 was missed
        broken_streak = db.calculate_streak(user_id_feb, as_of_date="2026-03-03", db_path=TEST_DB)
        self.assertEqual(broken_streak, 1)

    def test_36_shield_milestone_break_and_rebuild(self):
        """Verifies that when a streak is broken, last_shield_milestone resets so the warrior can earn shields again."""
        user_id = 991103
        db.enroll_user(user_id, "ShieldHero", TEST_DB)

        # 1. Earn milestone at 7 days
        self.assertTrue(db.check_and_award_shield(user_id, 7, TEST_DB))
        status = db.get_user_shield_status(user_id, TEST_DB)
        self.assertEqual(status["frost_shields"], 1)

        # 2. Earn milestone at 14 days
        self.assertTrue(db.check_and_award_shield(user_id, 14, TEST_DB))
        status = db.get_user_shield_status(user_id, TEST_DB)
        self.assertEqual(status["frost_shields"], 2)

        # 3. Cannot exceed max capacity of 2
        self.assertFalse(db.check_and_award_shield(user_id, 21, TEST_DB))
        status = db.get_user_shield_status(user_id, TEST_DB)
        self.assertEqual(status["frost_shields"], 2)

        # 4. Use 1 shield
        today_str = db.get_today_str()
        db.activate_frost_shield(user_id, target_date=today_str, reason="Active rest", db_path=TEST_DB)
        status = db.get_user_shield_status(user_id, TEST_DB)
        self.assertEqual(status["frost_shields"], 1)

        # 5. Streak breaks (drops to 0)
        # check_and_award_shield should recognize streak broke below last_milestone (14) and reset tracked milestone
        self.assertFalse(db.check_and_award_shield(user_id, 0, TEST_DB))

        # 6. Warrior starts over and hits 7-day streak again!
        # With our fix, this MUST award a shield instead of permanently blocking them!
        awarded_rebuild = db.check_and_award_shield(user_id, 7, TEST_DB)
        self.assertTrue(awarded_rebuild, "Failed to re-award shield after rebuilding a broken streak")
        status = db.get_user_shield_status(user_id, TEST_DB)
        self.assertEqual(status["frost_shields"], 2)

    def test_37_quicklog_fallback_parsing_robustness(self):
        """Tests pure-Python fallback NLP extraction against varied grammar, aliases, formats, and limits."""
        from ai.groq_service import extract_disciplines_fallback
        active_tasks = db.get_active_tasks(TEST_DB)

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

    def test_38_set_and_log_return_schema_and_zero_division(self):
        """Verifies schema consistency between log and set return dictionaries and zero-division protection."""
        user_id = 991104
        db.enroll_user(user_id, "SchemaWarrior", TEST_DB)
        today = db.get_today_str()

        # Test log_activity return keys
        log_res = db.log_activity(user_id, "SchemaWarrior", "Push-ups", 30, today, TEST_DB)
        required_keys = [
            "points_added", "new_points", "points_earned_delta",
            "previous_total", "new_total", "task_points_total",
            "task_max_points", "is_target_reached", "daily_points_total",
            "daily_points_max", "daily_completion_rate", "shield_awarded"
        ]
        for key in required_keys:
            self.assertIn(key, log_res, f"log_activity missing key: {key}")

        # Test set_activity return keys
        set_res = db.set_activity(user_id, "SchemaWarrior", "Push-ups", 50, today, TEST_DB)
        set_required_keys = [
            "old_points", "new_points", "points_added", "points_earned_delta",
            "previous_total", "new_total", "task_points_total",
            "task_max_points", "is_target_reached", "daily_points_total"
        ]
        for key in set_required_keys:
            self.assertIn(key, set_res, f"set_activity missing key: {key}")

        # Test validation guards
        with self.assertRaises(ValueError):
            db.log_activity(user_id, "SchemaWarrior", "Push-ups", -10, today, TEST_DB)

        with self.assertRaises(ValueError):
            db.set_activity(user_id, "SchemaWarrior", "Push-ups", -5, today, TEST_DB)

        with self.assertRaises(ValueError):
            db.log_activity(user_id, "SchemaWarrior", "Push-ups", 6000, today, TEST_DB)

        with self.assertRaises(ValueError):
            db.add_task(name="InvalidZero", target=0, unit="reps", max_points=100, db_path=TEST_DB)

        with self.assertRaises(ValueError):
            db.add_task(name="InvalidNegPts", target=10, unit="reps", max_points=-50, db_path=TEST_DB)

    def test_39_database_timezone_consistency(self):
        """Verifies that all database date helpers strictly return BOT_TZ dates."""
        from config import BOT_TZ
        from datetime import datetime
        expected_today = datetime.now(BOT_TZ).date().isoformat()

        self.assertEqual(db.get_today_str(), expected_today)
        self.assertEqual(db.get_today_date().isoformat(), expected_today)

        user_id = 991105
        db.enroll_user(user_id, "TzWarrior", TEST_DB)

        # Calling calculate_streak without as_of_date must default cleanly to BOT_TZ
        streak = db.calculate_streak(user_id, db_path=TEST_DB)
        self.assertEqual(streak, 0)

        # Calling get_user_stats without date must resolve without error
        stats = db.get_user_stats(user_id, TEST_DB)
        self.assertIn("current_streak", stats)
        self.assertIn("lifetime_points", stats)

    def test_40_weekly_and_monthly_leaderboard_standings(self):
        """Verifies that weekly and monthly leaderboards aggregate past finalized summaries and today's live activity correctly."""
        u1 = 991106
        u2 = 991107
        db.enroll_user(u1, "LeaderOne", TEST_DB)
        db.enroll_user(u2, "LeaderTwo", TEST_DB)

        today = db.get_today_date()
        yesterday = (today - timedelta(days=1)).isoformat()
        today_str = today.isoformat()

        # Finalized day yesterday: u1 got 500 pts, u2 got 200 pts
        db.log_activity(u1, "LeaderOne", "Push-ups", 100, yesterday, TEST_DB)
        db.log_activity(u1, "LeaderOne", "Pull-ups", 100, yesterday, TEST_DB)
        db.log_activity(u1, "LeaderOne", "Squats", 100, yesterday, TEST_DB)
        db.log_activity(u1, "LeaderOne", "Sit-ups", 100, yesterday, TEST_DB)
        db.log_activity(u1, "LeaderOne", "Running", 10.0, yesterday, TEST_DB)

        db.log_activity(u2, "LeaderTwo", "Push-ups", 100, yesterday, TEST_DB)
        db.log_activity(u2, "LeaderTwo", "Pull-ups", 100, yesterday, TEST_DB)
        db.finalize_daily_summaries(yesterday, TEST_DB)

        # Live day today: u1 got 100 pts, u2 got 300 pts
        db.log_activity(u1, "LeaderOne", "Push-ups", 100, today_str, TEST_DB)
        db.log_activity(u2, "LeaderTwo", "Push-ups", 100, today_str, TEST_DB)
        db.log_activity(u2, "LeaderTwo", "Squats", 100, today_str, TEST_DB)
        db.log_activity(u2, "LeaderTwo", "Sit-ups", 100, today_str, TEST_DB)

        # Overall leaderboard: u1 (500 + 100 = 600) vs u2 (200 + 300 = 500)
        overall = db.get_overall_leaderboard(TEST_DB)
        u1_entry = next((entry for entry in overall if entry["discord_id"] == u1), None)
        u2_entry = next((entry for entry in overall if entry["discord_id"] == u2), None)
        self.assertIsNotNone(u1_entry)
        self.assertIsNotNone(u2_entry)
        self.assertEqual(u1_entry["total_points"], 600)
        self.assertEqual(u2_entry["total_points"], 500)

    def test_41_stats_and_grind_embed_crash_and_jargon_prevention(self):
        from unittest.mock import MagicMock
        from ui.embeds import build_stats_embed, build_grind_embed, format_num
        from helpers import format_num as helper_format_num

        # 1. Test format_num robustness
        for fn in [format_num, helper_format_num]:
            self.assertEqual(fn(50), 50)
            self.assertEqual(fn(50.0), 50)
            self.assertEqual(fn(50.5), 50.5)
            self.assertEqual(fn("42"), 42)
            self.assertEqual(fn(None), 0)

        # 2. Test build_stats_embed with int total_volume (previously crashed with AttributeError: 'int' object has no attribute 'is_integer')
        mock_user = MagicMock()
        mock_user.display_name = "TestWarrior"
        stats_data = {
            "current_streak": 5,
            "perfect_days": 2,
            "active_days": 10,
            "lifetime_points": 850,
            "task_totals": [
                {"name": "Push-ups", "total_volume": 150, "unit": "reps"},
                {"name": "Running", "total_volume": 12.5, "unit": "km"},
                {"name": "Squats", "total_volume": 200, "unit": "reps"},
            ]
        }
        embed = build_stats_embed(mock_user, stats_data)
        self.assertIn("TestWarrior", embed.description)
        self.assertIn("150 reps", embed.description)
        self.assertIn("12.5 km", embed.description)
        self.assertIn("⭐ **Perfect Days**: 2", embed.description)
        self.assertNotIn("Clean Days", embed.description)

        # 3. Test build_grind_embed: strictly NO "Verdict:", "Assessment:", "Submission Roasted:", or "Daily Intellectual Friction"
        grind_roasted = {
            "verdict": "ROASTED",
            "points": 0,
            "key_learning": "None",
            "commentary": "Watching TV isn't deep work. Turn off the screen and write code."
        }
        embed_roasted = build_grind_embed(mock_user, grind_roasted, 45)
        self.assertNotIn("Verdict", embed_roasted.description)
        self.assertNotIn("Assessment", embed_roasted.description)
        self.assertNotIn("Submission Roasted", embed_roasted.title)
        self.assertNotIn("Daily Intellectual Friction", embed_roasted.description)
        self.assertIn("0 pts earned", embed_roasted.description)
        self.assertIn("Watching TV isn't deep work", embed_roasted.description)

        grind_accepted = {
            "verdict": "ACCEPTED",
            "points": 35,
            "key_learning": "Dynamic Programming",
            "commentary": "Good work tackling graph DP problems."
        }
        embed_accepted = build_grind_embed(mock_user, grind_accepted, 80)
        self.assertNotIn("Verdict", embed_accepted.description)
        self.assertNotIn("Assessment", embed_accepted.description)
        self.assertNotIn("Grind Accepted", embed_accepted.title)
        self.assertIn("+35 pts earned", embed_accepted.description)
        self.assertIn("Dynamic Programming", embed_accepted.description)

        # 4. Test format_grind_reply (casual human reply format)
        from ui.embeds import format_grind_reply
        roasted_reply = format_grind_reply(grind_roasted)
        self.assertEqual(roasted_reply, "Watching TV isn't deep work. Turn off the screen and write code.")
        self.assertNotIn("Points Earned", roasted_reply)
        self.assertNotIn("Logged:", roasted_reply)

        accepted_reply = format_grind_reply(grind_accepted)
        self.assertIn("Good work tackling graph DP problems.", accepted_reply)
        self.assertIn("**Points Earned**: 35 pts", accepted_reply)
        self.assertIn("**Logged**: Dynamic Programming", accepted_reply)

    def test_42_humanized_replies_and_broadcast_embeds(self):
        from ui.embeds import build_weekly_state_of_the_pack_embed
        from ai.gemini_service import CURATED_STOIC_FALLBACKS
        from ai.groq_service import REACTIVE_STOIC_FALLBACKS

        # 1. Test weekly broadcast embed title and format
        stats = {
            "total_pushups": 4200,
            "total_pullups": 900,
            "total_squats": 3500,
            "total_situps": 2100,
            "total_km": 150.5
        }
        top = [
            {"username": "ApexOne", "points": 1450},
            {"username": "WarriorTwo", "points": 1200}
        ]
        embed = build_weekly_state_of_the_pack_embed(stats, top, "Solid weekly execution across the board.")
        self.assertEqual(embed.title, "📊 Winter Arc — Weekly Community Recap")
        self.assertNotIn("Weekly Reflection", embed.description)
        self.assertNotIn("State of the Pack", embed.title)
        self.assertIn("Solid weekly execution across the board.", embed.description)
        self.assertIn("4,200", embed.description)
        self.assertIn("150.5 km", embed.description)

        # 2. Verify all fallback pools contain zero fantasy melodrama or gothic tropes
        banned_tropes = ["shadow", "crucible", "howling", "pack respects", "blizzard", "frost take"]
        for quote in CURATED_STOIC_FALLBACKS + REACTIVE_STOIC_FALLBACKS:
            for trope in banned_tropes:
                self.assertNotIn(trope, quote.lower())

    def test_43_winter_arc_phases_and_recap_system(self):
        """Verifies phase definitions, calendar bounding, recap queries, snapshot isolation, and UI views."""
        import phases
        from unittest.mock import MagicMock
        from ui.embeds import (
            build_recap_embed,
            build_phase_podium_embed,
            build_monthly_leaderboard_embed,
            build_profile_embed,
        )
        from ui.views import RecapView

        # 1. Verify Phase Metadata & Names
        self.assertEqual(len(phases.PHASES), 4)
        p1 = phases.get_phase_by_id(1)
        p2 = phases.get_phase_by_id(2)
        p3 = phases.get_phase_by_id(3)
        p4 = phases.get_phase_by_id(4)

        self.assertEqual(p1["name"], "FIRST FROST")
        self.assertEqual(p1["total_days"], 31)
        self.assertEqual(p2["name"], "THE HUNT")
        self.assertEqual(p2["total_days"], 30)
        self.assertEqual(p3["name"], "THE ENDGAME")
        self.assertEqual(p3["total_days"], 31)
        self.assertEqual(p4["name"], "AFTERMATH")
        self.assertEqual(p4["total_days"], 31)

        # 2. Verify Calendar Discovery & Unlocking
        self.assertEqual(phases.get_current_phase("2026-10-15")["id"], 1)
        self.assertEqual(phases.get_current_phase("2026-11-20")["id"], 2)
        self.assertEqual(phases.get_current_phase("2026-12-25")["id"], 3)
        self.assertEqual(phases.get_current_phase("2027-01-10")["id"], 4)

        # Unlocked phases: strictly omits future phases
        self.assertEqual(len(phases.get_unlocked_phases("2026-10-10")), 1)
        self.assertEqual(len(phases.get_unlocked_phases("2026-11-05")), 2)
        self.assertEqual(len(phases.get_unlocked_phases("2026-12-01")), 3)
        self.assertEqual(len(phases.get_unlocked_phases("2027-01-01")), 4)

        # Last day detection
        is_last, ph = phases.is_last_day_of_phase("2026-10-31")
        self.assertTrue(is_last)
        self.assertEqual(ph["name"], "FIRST FROST")

        is_last_mid, _ = phases.is_last_day_of_phase("2026-10-15")
        self.assertFalse(is_last_mid)

        # 3. Test Phase Leaderboard, User Phase Stats, and Overall Recap
        u_phase = 777111
        db.enroll_user(u_phase, "PhaseWarrior", TEST_DB)

        # Seed activity in October (Phase 1)
        d_oct1 = "2026-10-05"
        d_oct2 = "2026-10-06"
        db.log_activity(u_phase, "PhaseWarrior", "Push-ups", 100, d_oct1, TEST_DB)
        db.log_activity(u_phase, "PhaseWarrior", "Running", 10, d_oct1, TEST_DB) # 200 pts
        db.finalize_daily_summaries(d_oct1, TEST_DB)

        db.log_activity(u_phase, "PhaseWarrior", "Squats", 100, d_oct2, TEST_DB) # 100 pts
        db.finalize_daily_summaries(d_oct2, TEST_DB)

        # Seed activity in November (Phase 2)
        d_nov = "2026-11-05"
        db.log_activity(u_phase, "PhaseWarrior", "Sit-ups", 100, d_nov, TEST_DB) # 100 pts
        db.finalize_daily_summaries(d_nov, TEST_DB)

        # Check Phase 1 Leaderboard (should only contain October 300 pts)
        p1_lb = db.get_phase_leaderboard(1, TEST_DB)
        p1_entry = next((e for e in p1_lb if e["discord_id"] == u_phase), None)
        self.assertIsNotNone(p1_entry)
        self.assertEqual(p1_entry["total_points"], 300)

        # Check Phase 1 User Stats
        p1_stats = db.get_user_phase_stats(u_phase, 1, TEST_DB)
        self.assertEqual(p1_stats["total_points"], 300)
        self.assertEqual(p1_stats["active_days"], 2)
        push_vol = next((t["total_volume"] for t in p1_stats["task_totals"] if t["name"] == "Push-ups"), 0)
        self.assertEqual(push_vol, 100)

        # Check Overall Recap (includes Oct 300 + Nov 100 = 400 pts)
        overall_recap = db.get_user_overall_recap(u_phase, TEST_DB)
        self.assertGreaterEqual(overall_recap["lifetime_points"], 400)

        # 4. Test Snapshot Archival
        import os
        import sqlite3
        backup_dir = os.path.join(os.path.dirname(TEST_DB), "test_backups")
        snapshot_file = db.archive_phase_snapshot(1, TEST_DB, backup_dir=backup_dir)
        self.assertTrue(os.path.exists(snapshot_file))

        with sqlite3.connect(snapshot_file) as s_conn:
            s_cur = s_conn.cursor()
            s_cur.execute("SELECT total_points FROM phase_standings WHERE discord_id = ?;", (u_phase,))
            row = s_cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], 300)

            # Ensure November records are NOT in October snapshot
            s_cur.execute("SELECT COUNT(*) FROM daily_summaries WHERE date >= '2026-11-01';")
            self.assertEqual(s_cur.fetchone()[0], 0)

        # Clean up test snapshot
        try:
            import shutil
            shutil.rmtree(backup_dir, ignore_errors=True)
        except Exception:
            pass

        # 5. Test UI Embeds & RecapView
        mock_user = MagicMock()
        mock_user.id = u_phase
        mock_user.display_name = "PhaseWarrior"
        mock_user.avatar = None

        embed_p1 = build_recap_embed(mock_user, p1_stats, is_overall=False)
        self.assertIn("FIRST FROST", embed_p1.title)
        self.assertIn("300 pts", embed_p1.description)

        embed_all = build_recap_embed(mock_user, overall_recap, is_overall=True)
        self.assertIn("Overall Campaign Recap", embed_all.title)

        podium_embed = build_phase_podium_embed(p1, p1_lb)
        self.assertIn("FIRST FROST Concluded", podium_embed.title)

        # Monthly leaderboard mentions Phase
        m_embed = build_monthly_leaderboard_embed(year=2026, month=10)
        self.assertIn("FIRST FROST", m_embed.title)

        # Profile embed mentions Phase
        user_record = db.get_user_by_discord_id(u_phase, TEST_DB)
        stats_data = db.get_user_stats(u_phase, TEST_DB)
        prof_embed = build_profile_embed(mock_user, user_record, 2, stats_data)
        self.assertIn("Active Phase", prof_embed.description)

        # RecapView initialization
        view = RecapView(target_user=mock_user, author_id=mock_user.id, current_selection="phase_1")
        self.assertTrue(len(view.children) >= 2)

    def test_44_cleanup_fixes_and_robustness(self):
        """Verifies no-fallback Gemini error handling, formatted history with grind tags, and retroactive sync."""
        from ai.gemini_service import GeminiServiceError, evaluate_grind
        from ui.embeds import build_history_embed, build_stats_embed, build_profile_embed

        # 1. Verify GeminiServiceError is raised without fake fallback points when unconfigured or failing
        import asyncio
        from unittest.mock import patch, AsyncMock, MagicMock
        with patch("ai.gemini_service.get_gemini_client", return_value=None):
            with self.assertRaises(GeminiServiceError):
                asyncio.run(evaluate_grind("Studied algorithms for 3 hours"))

        mock_failing_client = MagicMock()
        mock_failing_client.aio.models.generate_content = AsyncMock(side_effect=RuntimeError("API quota exhausted"))
        with patch("ai.gemini_service.get_gemini_client", return_value=mock_failing_client):
            with self.assertRaises(GeminiServiceError):
                asyncio.run(evaluate_grind("Studied algorithms for 3 hours"))

        # 2. Formatted history with grind log attachment
        u_hist = 999777
        db.enroll_user(u_hist, "HistoryWarrior", db_path=TEST_DB)
        past_d = db.get_today_date() - timedelta(days=2)
        past_date = past_d.isoformat()
        db.log_activity(u_hist, "HistoryWarrior", "Push-ups", 50, log_date=past_date, db_path=TEST_DB)
        db.record_grind_entry(
            discord_id=u_hist,
            date_str=past_date,
            raw_input="Finished dynamic programming problem set",
            verdict="ACCEPTED",
            points=30,
            key_learning="Graph Dynamic Programming",
            commentary="Strong deep work",
            db_path=TEST_DB
        )
        hist = db.get_user_history(u_hist, days=7, db_path=TEST_DB)
        matching = [h for h in hist if h["date"] == past_date]
        self.assertEqual(len(matching), 1)
        self.assertIsNotNone(matching[0].get("grind_entry"))
        self.assertEqual(matching[0]["grind_entry"]["points_awarded"], 30)

        # History embed format
        mock_user = MagicMock()
        mock_user.id = u_hist
        mock_user.display_name = "HistoryWarrior"
        mock_user.avatar = None
        h_embed = build_history_embed(mock_user, hist)
        expected_date_str = past_d.strftime("%a, %b %d")
        self.assertIn(expected_date_str, h_embed.description)
        self.assertIn("↳ 🧠 *+30 pts grind (Graph Dynamic Programming)*", h_embed.description)
        self.assertNotIn("Winter Arc • Consistency Beats Motivation", h_embed.footer.text)

        # 3. Retroactive set_activity re-finalizes daily_summaries
        retro_date = (db.get_today_date() - timedelta(days=3)).isoformat()
        db.set_activity(u_hist, "HistoryWarrior", "Push-ups", 100, log_date=retro_date, db_path=TEST_DB)
        with db.get_connection(TEST_DB) as conn:
            row = conn.cursor().execute(
                "SELECT points, completion_rate FROM daily_summaries WHERE user_id = (SELECT id FROM users WHERE discord_id = ?) AND date = ?;",
                (u_hist, retro_date)
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["points"], 100)

        # 4. Check stats embed and profile embed footers
        s_embed = build_stats_embed(mock_user, db.get_user_stats(u_hist, TEST_DB))
        self.assertNotIn("Winter Arc • Consistency Beats Motivation", s_embed.footer.text)
        p_embed = build_profile_embed(mock_user, db.get_user_by_discord_id(u_hist, TEST_DB), 1, db.get_user_stats(u_hist, TEST_DB))
        self.assertNotIn("Winter Arc • Consistency Beats Motivation", p_embed.footer.text)

    def test_45_evening_checkin_broadcast_message(self):
        import asyncio
        from ui.embeds import build_evening_checkin_message
        from ai.gemini_service import generate_evening_alert_data, AUTHENTIC_STOIC_QUOTES, get_default_callout

        warriors = [
            {"discord_id": 1001, "username": "STRANGER", "points": 0, "streak": 3},
            {"discord_id": 1002, "username": "Vikram", "points": 50, "streak": 5},
            {"discord_id": 1003, "username": "Alex", "points": 500, "streak": 12},
        ]

        quote = '"Waste no more time arguing what a good man should be. Be one." — Marcus Aurelius'
        msg = build_evening_checkin_message(
            warriors_data=warriors,
            callouts=None, # uses default callouts
            stoic_quote=quote,
            role_ping="@Coldfornt"
        )

        expected_msg = (
            "@Coldfornt [WinterArc] 3 hours left until midnight rollover. ⏳\n"
            "If you haven't hit your 30 points yet, get your reps or run logged before midnight to keep your streak alive.\n\n"
            "- <@1001> — 0 pts on the board. Stop scrolling, drop and get your 30 push-ups in before your streak breaks tonight.\n"
            "- <@1002> — 50 pts, streak is safe! Solid execution, but see if you can squeeze in another set before midnight.\n"
            "- <@1003> — 500 pts, completely maxed out the board early. Rest up for tomorrow.\n\n"
            "> \"Waste no more time arguing what a good man should be. Be one.\" — Marcus Aurelius\n\n"
            "-# Log with /log • 30 pts/day minimum for streak • Rollover at midnight"
        )

        self.assertEqual(msg, expected_msg)

        # Test generate_evening_alert_data
        callouts, stoic_quote = asyncio.run(
            generate_evening_alert_data(warriors, override_quote=quote)
        )
        self.assertEqual(stoic_quote, quote)
        self.assertIn(1001, callouts)
        self.assertIn(1002, callouts)
        self.assertIn(1003, callouts)
        self.assertIn("0 pts on the board", callouts[1001])
        self.assertIn("50 pts", callouts[1002])
        self.assertIn("500 pts", callouts[1003])

        # Test random stoic quote pool
        self.assertTrue(len(AUTHENTIC_STOIC_QUOTES) >= 10)
        for q in AUTHENTIC_STOIC_QUOTES:
            self.assertIn("—", q)

    def test_46_clean_replies_and_native_broadcasts(self):
        from ui.embeds import (
            format_log_reply,
            format_set_reply,
            build_morning_kickoff_message,
            build_afternoon_checkin_message,
            build_midnight_finalization_message,
            build_weekly_recap_message,
        )

        # 1. format_log_reply
        log_res = {
            "new_total": 30,
            "target": 50,
            "previous_total": 0,
            "is_target_reached": False,
            "daily_points_total": 60,
            "daily_points_max": 500,
            "unit": "reps",
            "task_name": "Push-ups",
            "shield_awarded": False,
        }
        res_str = format_log_reply(log_res, 30)
        self.assertIn("Logged **+30 reps** to **Push-ups** (30/50 reps)", res_str)
        self.assertIn("Today: **60/500 pts**", res_str)

        # Target completed + Level up + Shield
        log_res_up = {
            "new_total": 50,
            "target": 50,
            "previous_total": 30,
            "is_target_reached": True,
            "daily_points_total": 100,
            "daily_points_max": 500,
            "unit": "reps",
            "task_name": "Push-ups",
            "shield_awarded": True,
        }
        lvl_up = {"level": 2, "title": "Novice", "badge": "🥉"}
        res_up_str = format_log_reply(log_res_up, 20, level_up_info=lvl_up)
        self.assertIn("⭐ Target completed!", res_up_str)
        self.assertIn("Rank Promotion!", res_up_str)
        self.assertIn("Level 2 — 🥉 Novice", res_up_str)
        self.assertIn("Streak Shield Earned!", res_up_str)

        # 2. format_set_reply
        set_res = {
            "new_total": 40,
            "target": 50,
            "previous_total": 20,
            "is_target_reached": False,
            "daily_points_total": 80,
            "daily_points_max": 500,
            "unit": "reps",
            "task_name": "Push-ups",
        }
        set_str = format_set_reply(set_res, 40)
        self.assertIn("Adjusted **Push-ups**: **20** ➔ **40 reps**", set_str)

        # Reset set_reply
        reset_res = {
            "new_total": 0,
            "target": 50,
            "previous_total": 40,
            "is_target_reached": False,
            "daily_points_total": 0,
            "daily_points_max": 500,
            "unit": "reps",
            "task_name": "Push-ups",
        }
        reset_str = format_set_reply(reset_res, 0)
        self.assertIn("Reset **Push-ups** to **0 reps** (was 40 reps)", reset_str)

        # 3. build_morning_kickoff_message
        active_tasks = [
            {"name": "Push-ups", "target": 50, "unit": "reps", "max_points": 100},
            {"name": "Running", "target": 5, "unit": "km", "max_points": 100},
        ]
        morning_msg = build_morning_kickoff_message(
            active_tasks=active_tasks,
            date_display="Mon, Sep 29",
            quote="Focus on the work.",
            role_ping="@Coldfornt"
        )
        self.assertIn("@Coldfornt [WinterArc] Mon, Sep 29 🌅", morning_msg)
        self.assertIn("• **Push-ups**: `50 reps` *(100 pts)*", morning_msg)
        self.assertIn("• **Running**: `5 km` *(100 pts)*", morning_msg)
        self.assertIn("> Focus on the work.", morning_msg)
        self.assertIn("-# Log with /log", morning_msg)

        # 4. build_afternoon_checkin_message
        enrolled_users = [
            {"discord_id": 1001, "username": "Vikram"},
        ]
        afternoon_msg = build_afternoon_checkin_message(
            enrolled_users=enrolled_users,
            today_str="2026-09-29",
            quote="Stay disciplined.",
            role_ping="@Coldfornt"
        )
        self.assertIn("@Coldfornt [WinterArc] Afternoon Check-in ⏳", afternoon_msg)
        self.assertIn("- <@1001> —", afternoon_msg)
        self.assertIn("> Stay disciplined.", afternoon_msg)
        self.assertIn("-# Log with /log", afternoon_msg)

        # 5. build_midnight_finalization_message
        lb = [
            {"discord_id": 1001, "username": "Vikram", "points": 120, "completion_rate": 0.24, "perfect_day": False},
            {"discord_id": 1002, "username": "Alex", "points": 500, "completion_rate": 1.0, "perfect_day": True},
        ]
        midnight_msg = build_midnight_finalization_message(
            date_str="2026-09-29",
            leaderboard=lb,
            ai_recap="Great daily effort from the group.",
            role_ping="@Coldfornt"
        )
        self.assertIn("@Coldfornt [WinterArc] Day Finalized", midnight_msg)
        self.assertIn("🥇 <@1001> — **120 pts** (24%)", midnight_msg)
        self.assertIn("🥈 <@1002> — **500 pts** (100%) ⭐", midnight_msg)
        self.assertIn("Great daily effort from the group.", midnight_msg)
        self.assertIn("🔥 **Perfect Days**: **1** member(s) hit 100%.", midnight_msg)

        # 6. build_weekly_recap_message
        weekly_stats = {
            "total_pushups": 1500,
            "total_pullups": 800,
            "total_squats": 2000,
            "total_situps": 1200,
            "total_km": 42.5,
        }
        weekly_top = [
            {"discord_id": 1001, "username": "Vikram", "points": 3200},
            {"discord_id": 1002, "username": "Alex", "points": 2800},
            {"discord_id": 1003, "username": "Sam", "points": 2100},
        ]
        recap_msg = build_weekly_recap_message(
            weekly_stats=weekly_stats,
            top_warriors=weekly_top,
            ai_speech="Unstoppable consistency.",
            role_ping="@Coldfornt"
        )
        self.assertIn("@Coldfornt [WinterArc] Weekly Community Recap 📊", recap_msg)
        self.assertIn("🥇 <@1001> — **3200 pts**", recap_msg)
        self.assertIn("🥈 <@1002> — **2800 pts**", recap_msg)
        self.assertIn("🥉 <@1003> — **2100 pts**", recap_msg)
        self.assertIn("• 💪 Push-ups: `1,500`", recap_msg)
        self.assertIn("• 🏃 Running: `42.5 km`", recap_msg)
        self.assertIn("> Unstoppable consistency.", recap_msg)

        # 7. build_phase_conclusion_message
        from ui.embeds import build_phase_conclusion_message
        phase_dict = {"id": 1, "name": "FIRST FROST", "short_name": "Phase 1", "total_days": 31}
        phase_lb = [
            {"discord_id": 1001, "username": "Vikram", "total_points": 14200, "perfect_days": 28},
            {"discord_id": 1002, "username": "Alex", "total_points": 12850, "perfect_days": 25},
            {"discord_id": 1003, "username": "Devin", "total_points": 9400, "perfect_days": 19},
            {"discord_id": 1004, "username": "Sam", "total_points": 8100},
            {"discord_id": 1005, "username": "Arjun", "total_points": 7500},
        ]
        next_phase = {"id": 2, "name": "THE HUNT", "short_name": "Phase 2"}
        phase_msg = build_phase_conclusion_message(
            phase_dict=phase_dict,
            phase_lb=phase_lb,
            ceremony_speech="Month 1 filtered out the talkers.",
            next_phase_dict=next_phase,
            role_ping="@Coldfornt"
        )
        self.assertIn("@Coldfornt [WinterArc] Phase 1 Concluded • FIRST FROST 🏆", phase_msg)
        self.assertIn("🥇 <@1001> — **14,200 pts** *(28 perfect days)*", phase_msg)
        self.assertIn("🥈 <@1002> — **12,850 pts** *(25 perfect days)*", phase_msg)
        self.assertIn("🥉 <@1003> — **9,400 pts** *(19 perfect days)*", phase_msg)
        self.assertIn("4th: <@1004> — **8,100 pts**", phase_msg)
        self.assertIn("5th: <@1005> — **7,500 pts**", phase_msg)
        self.assertIn("• Active Participants: `5`", phase_msg)
        self.assertIn("• Perfect Days Logged: `72`", phase_msg)
        self.assertIn("• Total Volume: `52,050 pts`", phase_msg)
        self.assertIn("⚡ **Phase 2 (THE HUNT)** begins tomorrow at 00:00 IST.", phase_msg)
        self.assertIn("-# Phase snapshot archived • Streaks carry over uninterrupted", phase_msg)

    def test_47_comprehensive_suite_and_edge_cases(self):
        """Validates all edge cases: volume limits, autocomplete fallbacks, zero overrides, and tier leaps."""
        from levels import check_level_up, get_level_info, APEX_THRESHOLD
        from ui.embeds import format_log_reply, format_set_reply, build_shield_status_embed

        # 1. Multi-tier leap crossing (0 -> 7500 pts = Level 1 Initiate -> Level 8 Vanguard)
        leap = check_level_up(0, 7500)
        self.assertIsNotNone(leap)
        self.assertEqual(leap["level"], 8)
        self.assertEqual(leap["title"], "Vanguard")
        self.assertEqual(leap["badge"], "🛡️")

        # 2. Apex threshold verification
        apex_info = get_level_info(APEX_THRESHOLD)
        self.assertEqual(apex_info["level"], 12)
        self.assertEqual(apex_info["title"], "Apex")
        self.assertTrue(apex_info["is_apex"])
        self.assertEqual(apex_info["tier_pct"], 100)

        # Beyond Apex threshold (15,000 pts)
        beyond_apex = get_level_info(15000)
        self.assertEqual(beyond_apex["level"], 12)
        self.assertTrue(beyond_apex["is_apex"])
        self.assertEqual(beyond_apex["tier_pct"], 100)

        # 3. Log reply edge cases: target over-completion
        over_log = {
            "new_total": 75,
            "target": 50,
            "previous_total": 45,
            "is_target_reached": True,
            "daily_points_total": 120,
            "daily_points_max": 500,
            "unit": "reps",
            "task_name": "Squats",
            "shield_awarded": False,
        }
        res_over = format_log_reply(over_log, 30)
        self.assertIn("Logged **+30 reps** to **Squats** (75/50 reps) ⭐ Target completed!", res_over)

        # 4. Set reply edge cases: downward correction
        down_set = {
            "new_total": 20,
            "target": 50,
            "previous_total": 40,
            "is_target_reached": False,
            "daily_points_total": 40,
            "daily_points_max": 500,
            "unit": "reps",
            "task_name": "Pull-ups",
        }
        res_down = format_set_reply(down_set, 20)
        self.assertIn("Adjusted **Pull-ups**: **40** ➔ **20 reps** (20/50 reps)", res_down)

        # 5. Shield Status embed shows Streak Shield
        from unittest.mock import MagicMock
        mock_u = MagicMock()
        mock_u.display_name = "IronWarrior"
        status_data = {
            "frost_shields": 2,
            "max_shields": 2,
            "is_today_shielded": False,
            "days_until_next_shield": 0,
            "current_streak": 14,
            "recent_uses": [{"date": "2026-09-20", "reason": "Rest day"}],
        }
        shield_embed = build_shield_status_embed(mock_u, status_data)
        self.assertIn("Streak Shield Status", shield_embed.title)
        self.assertIn("Streak Shields Work", shield_embed.description)
        self.assertIn("MAX SHIELDS STORED (2/2)", shield_embed.description)

        # 6. build_ranks_embed verification
        from ui.embeds import build_ranks_embed
        ranks_embed = build_ranks_embed(50)
        self.assertIn("12-Tier Progression Hierarchy", ranks_embed.title)
        self.assertNotIn("Pack", ranks_embed.title)
        self.assertIn("🥉 **Lvl 1: Initiate**", ranks_embed.description)
        self.assertIn("🥉 **Lvl 2: Novice**", ranks_embed.description)
        self.assertIn("💎 **Lvl 12: Apex**", ranks_embed.description)
        self.assertNotIn("Lone Stray", ranks_embed.description)
        self.assertIn("Your Current Standing: 🥉 **Level 1: Initiate** (50 pts)", ranks_embed.description)

        # 7. Server records & ServerRecordsView verification
        from ui.views import ServerRecordsView
        from ui.embeds import build_server_records_embed
        records_data = db.get_server_records(None, db_path=TEST_DB)
        records_embed = build_server_records_embed(records_data, phase_id=None)
        self.assertIn("All-Time Server Records", records_embed.title)
        self.assertIn("Achievements & Records", records_embed.description)
        self.assertIn("Server Totals", records_embed.description)
        self.assertIn("Total Volume", records_embed.description)
        self.assertIn("Total Perfect Days", records_embed.description)
        self.assertNotIn("Clean Days", records_embed.description)
        self.assertNotIn("Combined Volume", records_embed.description)

        records_view = ServerRecordsView(author_id=123, current_selection="overall")
        self.assertEqual(len(records_view.children), 4)  # Overall, Phase 1, Phase 2, Phase 3
        self.assertEqual(records_view.children[0].label, "Overall")

    def test_51_tips_system_and_command_output_grounding(self):
        import time
        import asyncio
        import tips
        import discord
        from unittest.mock import MagicMock, AsyncMock, patch
        from ui.embeds import format_embed_as_text
        from ai import groq_service

        # 1. Test format_embed_as_text
        test_embed = discord.Embed(
            title="🏆 Daily Leaderboard",
            description="Phase 1: FIRST FROST\n🥇 1. Alice - 500 pts\n🥈 2. Bob - 350 pts"
        )
        test_embed.add_field(name="Active Phase", value="Phase 1")
        test_embed.set_footer(text="Updated live")
        formatted = format_embed_as_text(test_embed)
        self.assertIn("🏆 Daily Leaderboard", formatted)
        self.assertIn("🥇 1. Alice - 500 pts", formatted)
        self.assertIn("Active Phase:\nPhase 1", formatted)
        self.assertIn("Footer: Updated live", formatted)

        # 2. Test tips timer & probability
        u1 = 888111
        u2 = 888222
        # Initial call: timer not active yet
        self.assertTrue(tips.should_send_tip(u1, roll_chance=1.0))
        tip_text = tips.get_tip_for_user(u1)
        self.assertIn(tip_text, tips.BOT_USAGE_TIPS)

        # 10-minute timer is now active: must skip probability check
        self.assertFalse(tips.should_send_tip(u1, roll_chance=1.0))

        # Other user is unaffected
        self.assertTrue(tips.should_send_tip(u2, roll_chance=1.0))

        # Simulate 10 minutes passing (601 seconds)
        tips._last_tip_timestamps[u1] = time.time() - 601.0
        self.assertTrue(tips.should_send_tip(u1, roll_chance=1.0))
        self.assertFalse(tips.should_send_tip(u1, roll_chance=0.0))

        # 3. Test generate_reactive_nudge command_output grounding
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content="Number one on the board. Don't slack off."))]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        async def run_nudge_test():
            with patch("ai.groq_service.get_groq_client", return_value=mock_client):
                res = await groq_service.generate_reactive_nudge(
                    user_name="Fenrir",
                    command_name="leaderboard",
                    progression={"points": 500, "max_points": 500, "streak": 10},
                    command_output=formatted
                )
                self.assertEqual(res, "Number one on the board. Don't slack off.")
                call_args = mock_client.chat.completions.create.call_args[1]
                user_msg = [m["content"] for m in call_args["messages"] if m["role"] == "user"][0]
                self.assertIn("Command Output / Result:", user_msg)
                self.assertIn("🥇 1. Alice - 500 pts", user_msg)
                sys_msg = [m["content"] for m in call_args["messages"] if m["role"] == "system"][0]
                self.assertIn("USE THE COMMAND OUTPUT FOR REPLYING", sys_msg)

        asyncio.run(run_nudge_test())

    def test_52_help_command_execution_and_comprehensive_validation(self):
        """
        Validates the slash command /help execution lifecycle,
        HelpView interactive dropdown transitions across all 6 categories,
        tip dispatch scheduling, and strict absence of legacy 'Clean Day' text.
        """
        import asyncio
        import discord
        from unittest.mock import MagicMock, AsyncMock, patch
        from cogs.warrior import WarriorCog
        from ui.views import HelpView
        from ui.embeds import build_help_embed

        mock_bot = MagicMock()
        cog = WarriorCog(mock_bot)

        # 1. Slash command invocation
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.user = MagicMock()
        mock_interaction.user.id = 999555
        mock_interaction.user.display_name = "DisciplineSeeker"
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        async def run_help_cmd_test():
            with patch("cogs.warrior.dispatch_tip", new_callable=AsyncMock) as mock_dispatch:
                await cog.help_cmd.callback(cog, mock_interaction)
                mock_interaction.response.send_message.assert_called_once()
                call_kwargs = mock_interaction.response.send_message.call_args[1]
                embed = call_kwargs["embed"]
                view = call_kwargs["view"]

                self.assertIsInstance(view, HelpView)
                self.assertIn("Master Command Manual", embed.title)
                self.assertIn("500 points (Perfect Day)", embed.description)
                self.assertNotIn("Clean Day", embed.description)

        asyncio.run(run_help_cmd_test())

        # 2. Interactive dropdown switching across all 6 categories
        view = HelpView()
        categories = ["overview", "logging", "progress", "shields", "settings", "admin"]

        async def test_view_categories():
            for cat in categories:
                select_interaction = MagicMock(spec=discord.Interaction)
                select_interaction.response = MagicMock()
                select_interaction.response.edit_message = AsyncMock()

                view.select_category._values = [cat]

                await view.select_category.callback(select_interaction)
                select_interaction.response.edit_message.assert_called_once()
                edited_embed = select_interaction.response.edit_message.call_args[1]["embed"]

                # Ensure strict absence of legacy 'Clean Day' terminology across every category
                all_text = f"{edited_embed.title} {edited_embed.description} " + " ".join(
                    f"{f.name} {f.value}" for f in edited_embed.fields
                )
                if edited_embed.footer and edited_embed.footer.text:
                    all_text += f" {edited_embed.footer.text}"

                self.assertNotIn("clean day", all_text.lower(), f"Found legacy 'clean day' in category '{cat}'")
                self.assertNotIn("clean sweep", all_text.lower(), f"Found legacy 'clean sweep' in category '{cat}'")

                if cat == "logging":
                    self.assertIn("Amarok", all_text)
                    self.assertIn("strictly excludes `/set`", all_text)
                    self.assertIn("10-minute timer", all_text)
                    self.assertIn("/quick", all_text)
                    self.assertIn("/grind", all_text)
                elif cat == "progress":
                    self.assertIn("/stats [phase]", all_text)
                    self.assertIn("Server Records & Benchmarks", all_text)
                    self.assertIn("peak maxers", all_text)
                    self.assertIn("most Perfect Days", all_text)
                    self.assertIn("/recap [member]", all_text)
                    self.assertIn("Phase Explorer", all_text)
                    self.assertIn("Perfect Days (100%)", all_text)
                elif cat == "shields":
                    self.assertIn("30 points", all_text)
                    self.assertIn("7-day streak milestone", all_text)
                    self.assertIn("/shield use", all_text)
                elif cat == "settings":
                    self.assertIn("/settings", all_text)
                    self.assertIn("05:00 IST", all_text)
                    self.assertIn("21:00 IST", all_text)
                elif cat == "admin":
                    self.assertIn("Collect GC & Free RAM", all_text)
                    self.assertIn("/test_reminder", all_text)

        asyncio.run(test_view_categories())

    def test_53_monthly_streak_and_consistency(self):
        """
        Validates the monthly streak and calendar consistency system:
        - get_user_longest_streak calculation
        - get_user_monthly_consistency grid generation with Monday start
        - Other-month padding (▪️) and future month days (▫️)
        - Highlights calculation (streak, consistency %, perfect days, shields)
        - build_streak_consistency_embed and build_quick_streak_embed formatting
        - StreakConsistencyView interactive navigation (calendar, quick, shield, month pagination)
        - /streak and /consistency slash commands
        """
        import asyncio
        import discord
        from datetime import date
        from unittest.mock import MagicMock, AsyncMock, patch
        import database as db
        from ui.embeds import (
            build_streak_consistency_embed,
            build_quick_streak_embed,
            STREAK_LEGEND_SUBTEXT,
        )
        from ui.views import StreakConsistencyView
        from cogs.warrior import WarriorCog

        # 1. Setup user in test database
        user_id = 999777
        user = db.get_user_by_discord_id(user_id, TEST_DB)
        if not user:
            db.enroll_user(user_id, "ConsistencyWarrior", TEST_DB)
            user = db.get_user_by_discord_id(user_id, TEST_DB)
        if not db.get_user_by_discord_id(user_id, db.DB_PATH):
            db.enroll_user(user_id, "ConsistencyWarrior", db.DB_PATH)

        # Seed test data for October 2026
        # Oct 01 (Thu) - 50 pts (kept)
        # Oct 02 (Fri) - 100 pts (kept)
        # Oct 03 (Sat) - 500 pts (perfect day)
        # Oct 04 (Sun) - 50 pts (kept)
        # Oct 05 (Mon) - 500 pts (perfect day)
        # Oct 06 (Tue) - shielded day
        db.log_activity(user_id, "ConsistencyWarrior", "pushups", 50, log_date="2026-10-01", db_path=TEST_DB)
        db.finalize_daily_summaries("2026-10-01", TEST_DB)

        db.log_activity(user_id, "ConsistencyWarrior", "pushups", 100, log_date="2026-10-02", db_path=TEST_DB)
        db.finalize_daily_summaries("2026-10-02", TEST_DB)

        with db.get_connection(TEST_DB) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO daily_summaries (user_id, date, points, completion_rate, perfect_day, is_shielded)
                VALUES (?, '2026-10-03', 500, 1.0, 1, 0);
            """, (user["id"],))
            cur.execute("""
                INSERT OR REPLACE INTO daily_summaries (user_id, date, points, completion_rate, perfect_day, is_shielded)
                VALUES (?, '2026-10-04', 50, 0.1, 0, 0);
            """, (user["id"],))
            cur.execute("""
                INSERT OR REPLACE INTO daily_summaries (user_id, date, points, completion_rate, perfect_day, is_shielded)
                VALUES (?, '2026-10-05', 500, 1.0, 1, 0);
            """, (user["id"],))
            cur.execute("""
                INSERT OR REPLACE INTO daily_summaries (user_id, date, points, completion_rate, perfect_day, is_shielded)
                VALUES (?, '2026-10-06', 0, 0.0, 0, 1);
            """, (user["id"],))
            cur.execute("""
                INSERT OR REPLACE INTO shield_logs (user_id, date, reason)
                VALUES (?, '2026-10-06', 'Muscle Recovery');
            """, (user["id"],))
            conn.commit()

        # 2. Test get_user_longest_streak
        longest_streak = db.get_user_longest_streak(user_id, TEST_DB)
        self.assertGreaterEqual(longest_streak, 6)

        # 3. Test get_user_monthly_consistency for October 2026
        data = db.get_user_monthly_consistency(user_id, year=2026, month=10, db_path=TEST_DB)
        self.assertEqual(data["year"], 2026)
        self.assertEqual(data["month"], 10)
        self.assertEqual(data["month_name"], "October")

        grid = data["calendar_grid"]
        self.assertIn("Mo  Tu  We  Th  Fr  Sa  Su", grid)
        self.assertIn("W1", grid)
        self.assertIn("W2", grid)
        self.assertIn("W3", grid)
        self.assertIn("W4", grid)
        self.assertIn("W5", grid)
        # Check padding from previous month (Sep 28, 29, 30 are ▪️)
        self.assertIn("▪️", grid)
        # Check day completion formatting
        self.assertIn("days", grid)
        self.assertIn("pts)", grid)

        h = data["highlights"]
        self.assertGreaterEqual(h["highest_streak"], 6)
        self.assertGreaterEqual(h["perfect_days"], 2)  # Oct 03 and Oct 05
        self.assertGreaterEqual(h["shields_used"], 1)  # Oct 06

        # 4. Test build_streak_consistency_embed
        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "ConsistencyWarrior"
        mock_member.id = user_id

        embed = build_streak_consistency_embed(mock_member, data)
        self.assertEqual(embed.title, "📅 Winter Arc — Streak and Consistency")
        self.assertIn("CONSISTENCYWARRIOR", embed.description)
        self.assertIn("OCTOBER 2026", embed.description)
        self.assertIn("🏆 **Month Highlights:**", embed.description)
        self.assertIn("• Highest Streak: 🏔️", embed.description)
        self.assertIn("• Current Streak: 🔥", embed.description)
        self.assertIn("• Consistency: 📅", embed.description)
        self.assertIn("• Volume: ⚡", embed.description)
        self.assertIn("• Perfect Days: ⭐", embed.description)
        self.assertIn("• Streak Shields Used: 🛡️", embed.description)

        # 5. Test STREAK_LEGEND_SUBTEXT
        self.assertIn("-#", STREAK_LEGEND_SUBTEXT)
        self.assertIn("🟩 Streak Preserved (30+ pts)", STREAK_LEGEND_SUBTEXT)
        self.assertIn("⭐ Perfect Day (100%)", STREAK_LEGEND_SUBTEXT)
        self.assertIn("🛡️ Streak Shield", STREAK_LEGEND_SUBTEXT)
        self.assertIn("▫️ Upcoming", STREAK_LEGEND_SUBTEXT)

        # 6. Test build_full_calendar_embed and get_user_full_campaign_calendar
        from ui.embeds import build_full_calendar_embed
        full_data = db.get_user_full_campaign_calendar(user_id, TEST_DB)
        self.assertIn("PHASE 1: OCTOBER", full_data["calendar_text"])
        self.assertIn("PHASE 2: NOVEMBER", full_data["calendar_text"])
        self.assertIn("PHASE 3: DECEMBER", full_data["calendar_text"])

        full_embed = build_full_calendar_embed(mock_member, full_data)
        self.assertEqual(full_embed.title, "📅 Winter Arc — Full Calendar")
        self.assertIn("CONSISTENCYWARRIOR", full_embed.description)
        self.assertIn("OCT 1 – DEC 31", full_embed.description)
        self.assertIn("🏆 **Overall Highlights:**", full_embed.description)
        self.assertIn("• Overall Consistency: 📅", full_embed.description)
        self.assertIn("• All-Time Longest Streak: 🏔️", full_embed.description)
        self.assertIn("• Campaign Volume: ⚡", full_embed.description)
        self.assertIn("• Total Perfect Days: ⭐", full_embed.description)
        self.assertIn("• Total Shields Used: 🛡️", full_embed.description)

        # 7. Test Streamlined 2-button StreakConsistencyView
        view = StreakConsistencyView(
            target_user=mock_member,
            author_id=user_id,
            current_view="current"
        )
        self.assertEqual(len(view.children), 2)
        btn_labels = [c.label for c in view.children]
        self.assertEqual(btn_labels, ["Current", "Calendar"])
        self.assertTrue(view.children[0].disabled)  # Current is active & disabled
        self.assertFalse(view.children[1].disabled) # Calendar is clickable

        # Test view interactions
        async def test_view_interactions():
            inter = MagicMock(spec=discord.Interaction)
            inter.user.id = user_id
            inter.response.edit_message = AsyncMock()

            # Switch to Calendar view
            await view._calendar_callback(inter)
            self.assertEqual(view.current_view, "calendar")
            self.assertFalse(view.children[0].disabled) # Current now enabled
            self.assertTrue(view.children[1].disabled)  # Calendar now disabled
            inter.response.edit_message.assert_called_once()
            cal_call = inter.response.edit_message.call_args[1]
            self.assertEqual(cal_call["embed"].title, "📅 Winter Arc — Full Calendar")

            # Switch back to Current view
            inter.response.edit_message.reset_mock()
            await view._current_callback(inter)
            self.assertEqual(view.current_view, "current")
            self.assertTrue(view.children[0].disabled)  # Current now disabled
            self.assertFalse(view.children[1].disabled) # Calendar now enabled
            inter.response.edit_message.assert_called_once()
            curr_call = inter.response.edit_message.call_args[1]
            self.assertEqual(curr_call["embed"].title, "📅 Winter Arc — Streak and Consistency")

        asyncio.run(test_view_interactions())

        # 8. Test /streak and /consistency command callbacks
        mock_bot = MagicMock()
        cog = WarriorCog(mock_bot)

        async def test_streak_commands():
            cmd_inter = MagicMock(spec=discord.Interaction)
            cmd_inter.user = mock_member
            cmd_inter.response = MagicMock()
            cmd_inter.response.defer = AsyncMock()
            cmd_inter.followup = MagicMock()
            cmd_inter.followup.send = AsyncMock()

            with patch("cogs.warrior.require_enrolled", new_callable=AsyncMock, return_value=True), \
                 patch("cogs.warrior.safe_react", new_callable=AsyncMock), \
                 patch("cogs.warrior.dispatch_tip", new_callable=AsyncMock), \
                 patch("ai.groq_service.dispatch_interaction_nudge", new_callable=AsyncMock):
                # /streak execution
                await cog.streak_cmd.callback(cog, cmd_inter)
                cmd_inter.followup.send.assert_called_once()
                call_kw = cmd_inter.followup.send.call_args[1]
                self.assertIn(STREAK_LEGEND_SUBTEXT, call_kw["content"])
                self.assertEqual(call_kw["embed"].title, "📅 Winter Arc — Streak and Consistency")
                self.assertIsInstance(call_kw["view"], StreakConsistencyView)

                # /consistency execution
                cmd_inter.followup.send.reset_mock()
                await cog.consistency_cmd.callback(cog, cmd_inter)
                cmd_inter.followup.send.assert_called_once()
                call_kw2 = cmd_inter.followup.send.call_args[1]
                self.assertIn(STREAK_LEGEND_SUBTEXT, call_kw2["content"])
                self.assertEqual(call_kw2["embed"].title, "📅 Winter Arc — Streak and Consistency")

        asyncio.run(test_streak_commands())

    def test_51_all_extensions_and_slash_commands_load(self):
        """Verify cogs.admin and cogs.warrior load cleanly and register all 22 slash commands."""
        import asyncio
        from bot import WinterArcBot

        async def verify_bot_cogs():
            bot = WinterArcBot()
            await bot.load_extension("cogs.admin")
            await bot.load_extension("cogs.warrior")
            commands = bot.tree.get_commands()
            cmd_names = {c.name for c in commands}

            expected_cmds = {
                "admin", "consistency", "enroll", "grind", "help", "history",
                "leaderboard", "leave_arc", "log", "ping", "profile", "quick",
                "ranks", "recap", "set", "settings", "shield", "stats", "streak",
                "tasks", "test_reminder", "today"
            }
            self.assertTrue(expected_cmds.issubset(cmd_names), f"Missing commands: {expected_cmds - cmd_names}")
            self.assertEqual(len(commands), 22)

            admin_cmd = next(c for c in commands if c.name == "admin")
            subcmd_names = {sc.name for sc in admin_cmd.commands}
            self.assertIn("sync", subcmd_names)

        asyncio.run(verify_bot_cogs())

    def test_52_robust_logging_and_error_handling(self):
        """Verify logging mechanism, RobustView error handling, and cog error responses."""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock
        import discord
        from discord import app_commands
        from config import LOG_FILE_PATH, LOG_LEVEL_NAME, logger
        from ui.views import RobustView
        from cogs.warrior import WarriorCog
        from cogs.admin import AdminCog, get_system_health_metrics

        self.assertTrue(bool(LOG_FILE_PATH))
        self.assertTrue(bool(LOG_LEVEL_NAME))

        # Test RobustView on_error
        async def test_view_error():
            view = RobustView()
            inter = MagicMock(spec=discord.Interaction)
            inter.user = MagicMock(id=12345, name="TestUser")
            inter.guild = MagicMock(id=67890)
            inter.is_expired.return_value = False
            inter.response = MagicMock()
            inter.response.is_done.return_value = False
            inter.response.send_message = AsyncMock()

            button = discord.ui.Button(label="Test", custom_id="btn_test")
            await view.on_error(inter, ValueError("Simulated view error"), button)
            inter.response.send_message.assert_called_once()
            self.assertIn("unexpected error occurred", inter.response.send_message.call_args[0][0])

        asyncio.run(test_view_error())

        # Test WarriorCog cog_app_command_error with cooldown
        async def test_warrior_cog_error():
            bot = MagicMock()
            cog = WarriorCog(bot)
            inter = MagicMock(spec=discord.Interaction)
            inter.command = MagicMock()
            inter.command.name = "today"
            inter.user = MagicMock(id=12345)
            inter.is_expired.return_value = False
            inter.response = MagicMock()
            inter.response.is_done.return_value = False
            inter.response.send_message = AsyncMock()

            cooldown_err = app_commands.CommandOnCooldown(None, 4.5)
            await cog.cog_app_command_error(inter, cooldown_err)
            inter.response.send_message.assert_called_once()
            self.assertIn("4.5s", inter.response.send_message.call_args[0][0])

        asyncio.run(test_warrior_cog_error())

        # Test AdminCog cog_app_command_error with missing permissions
        async def test_admin_cog_error():
            bot = MagicMock()
            cog = AdminCog(bot)
            inter = MagicMock(spec=discord.Interaction)
            inter.command = MagicMock()
            inter.command.name = "sync"
            inter.user = MagicMock(id=12345)
            inter.is_expired.return_value = False
            inter.response = MagicMock()
            inter.response.is_done.return_value = False
            inter.response.send_message = AsyncMock()

            perm_err = app_commands.MissingPermissions(missing_permissions=["administrator"])
            await cog.cog_app_command_error(inter, perm_err)
            inter.response.send_message.assert_called_once()
            self.assertIn("Administrator", inter.response.send_message.call_args[0][0])

        asyncio.run(test_admin_cog_error())

        # Test system health metrics include log footprint
        mock_bot = MagicMock()
        mock_bot.latency = 0.045
        mock_bot.start_time = None
        metrics = get_system_health_metrics(mock_bot)
        self.assertIn("log_size_kb", metrics)
        self.assertIn("log_level", metrics)


if __name__ == "__main__":
    unittest.main()
