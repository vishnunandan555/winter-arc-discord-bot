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

        # Level 1: Lone Stray
        l1 = get_level_info(0)
        self.assertEqual(l1["level"], 1)
        self.assertEqual(l1["title"], "Lone Stray")

        # Level 2: Stray
        l2 = get_level_info(500)
        self.assertEqual(l2["level"], 2)
        self.assertEqual(l2["title"], "Stray")

        # Level 7: Savage
        l7 = get_level_info(5500)
        self.assertEqual(l7["level"], 7)
        self.assertEqual(l7["title"], "Savage")

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
        self.assertEqual(lvl_up["title"], "Stray")

        # No level up within same tier (500 -> 600)
        no_lvl = check_level_up(500, 600)
        self.assertIsNone(no_lvl)

        # Big leap crossing multiple levels (0 -> 2500, Level 1 to Level 4)
        big_lvl = check_level_up(0, 2500)
        self.assertIsNotNone(big_lvl)
        self.assertEqual(big_lvl["level"], 4)
        self.assertEqual(big_lvl["title"], "Prowler")

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
        from ai.gemini_service import evaluate_grind

        # Test evaluation structure (works with or without API key via fallback)
        res = asyncio.run(evaluate_grind("Studied operating systems 4 hours and solved 2 Hard DP problems"))
        self.assertIn("verdict", res)
        self.assertIn(res["verdict"], ["ACCEPTED", "REJECTED", "ROASTED"])
        self.assertIn("points", res)
        self.assertTrue(0 <= res["points"] <= 60)
        self.assertIn("commentary", res)
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
            (0, 1, "Lone Stray"),
            (499, 1, "Lone Stray"),
            (500, 2, "Stray"),
            (1199, 2, "Stray"),
            (1200, 3, "Scout"),
            (1999, 3, "Scout"),
            (2000, 4, "Prowler"),
            (2999, 4, "Prowler"),
            (3000, 5, "Tracker"),
            (4199, 5, "Tracker"),
            (4200, 6, "Hunter"),
            (5499, 6, "Hunter"),
            (5500, 7, "Savage"),
            (6999, 7, "Savage"),
            (7000, 8, "Vanguard"),
            (8499, 8, "Vanguard"),
            (8500, 9, "Frostborn"),
            (9799, 9, "Frostborn"),
            (9800, 10, "Predator"),
            (10799, 10, "Predator"),
            (10800, 11, "Alpha"),
            (11999, 11, "Alpha"),
            (12000, 12, "Apex"),
            (15000, 12, "Apex"),
        ]

        for pts, exp_lvl, exp_title in expected_titles:
            info = get_level_info(pts)
            self.assertEqual(info["level"], exp_lvl, f"Failed level for {pts} pts")
            self.assertEqual(info["title"], exp_title, f"Failed title for {pts} pts")

        # Test next level progress calculations at 180 pts (Level 1: Lone Stray -> Level 2: Stray at 500)
        info180 = get_level_info(180)
        self.assertEqual(info180["pts_to_next"], 320)
        self.assertEqual(info180["points_in_tier"], 180)
        self.assertEqual(info180["next_title"], "Stray")
        self.assertEqual(info180["next_level"], 2)

        # Profile embed verification: focuses on next level and doesn't mention distant 12,000 pts arc bar
        mock_user = MagicMock()
        mock_user.display_name = "Vishnu"
        mock_user.avatar = None
        user_record = {"joined_at": "2026-09-18 10:00:00", "frost_shields": 1}
        stats_data = {"lifetime_points": 180}

        profile_embed = build_profile_embed(mock_user, user_record, streak=5, stats_data=stats_data)
        self.assertIn("Level Progression", profile_embed.description)
        self.assertIn("Level 2 (Stray)", profile_embed.description)
        self.assertIn("180 / 500 PTS", profile_embed.description)
        self.assertIn("320 pts remaining", profile_embed.description)
        self.assertIn("All-Time Rank", profile_embed.description)
        self.assertIn("Pack Level", profile_embed.description)
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
        field_texts = " ".join(f"{f.name} {f.value}" for f in overview_embed.fields)
        self.assertIn("500 pts max", field_texts)
        self.assertIn("05:00", field_texts)
        self.assertIn("/quick", field_texts)
        self.assertIn("/shield", field_texts)

        # 2. Logging
        logging_embed = build_help_embed("logging")
        self.assertIn("Workout & AI Logging", logging_embed.title)
        field_names = [f.name for f in logging_embed.fields]
        self.assertTrue(any("/quick" in name for name in field_names))
        self.assertTrue(any("#quick-log" in name for name in field_names))
        self.assertTrue(any("/grind" in name for name in field_names))

        # 3. Progress
        progress_embed = build_help_embed("progress")
        self.assertIn("Progression, Ranks", progress_embed.title)
        p_names = [f.name for f in progress_embed.fields]
        self.assertTrue(any("Accountability" in name for name in p_names))
        self.assertTrue(any("12-Tier" in name for name in p_names))

        # 4. Shields
        shields_embed = build_help_embed("shields")
        self.assertIn("Frost Shield", shields_embed.title)
        s_names = [f.name for f in shields_embed.fields]
        self.assertTrue(any("How Frost Shields Work" in name for name in s_names))
        self.assertTrue(any("Shield Commands" in name for name in s_names))

        # 5. Settings
        settings_embed = build_help_embed("settings")
        self.assertIn("Accountability, Settings", settings_embed.title)
        set_names = [f.name for f in settings_embed.fields]
        self.assertTrue(any("/settings" in name for name in set_names))
        self.assertTrue(any("Enrollment" in name for name in set_names))

        # 6. Admin
        admin_embed = build_help_embed("admin")
        self.assertIn("Server Administration", admin_embed.title)
        adm_names = [f.name for f in admin_embed.fields]
        self.assertTrue(any("Broadcast Configuration" in name for name in adm_names))
        self.assertTrue(any("Diagnostics" in name for name in adm_names))

        # 7. HelpView
        view = HelpView()
        self.assertEqual(view.timeout, 300)
        selects = [child for child in view.children if hasattr(child, "options")]
        self.assertEqual(len(selects), 1)
        options = selects[0].options
        self.assertEqual(len(options), 6)
        option_values = [opt.value for opt in options]
        self.assertEqual(option_values, ["overview", "logging", "progress", "shields", "settings", "admin"])

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


if __name__ == "__main__":
    unittest.main()



