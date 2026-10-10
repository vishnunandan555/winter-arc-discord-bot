"""
tests/test_streaks_shields.py - Streak Calculation, Shields Lifecycle, Recovery, and Habit Calendar Tests
"""
from datetime import date, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
import discord
import database as db
from tests.base import WinterArcTestCase
from ui.embeds import (
    build_streak_consistency_embed,
    build_quick_streak_embed,
    build_full_calendar_embed,
    STREAK_LEGEND_SUBTEXT,
    STREAK_LEGEND_FOOTER,
)
from ui.views import StreakConsistencyView
from cogs.warrior import WarriorCog


class TestStreakCalculation(WinterArcTestCase):
    """Verifies streak logic: consecutive days, 30 pt threshold, and year rollovers."""

    def test_streak_consecutive_days_calculation_and_daily_summaries(self):
        """Verifies streak increments across consecutive daily summaries with 100% completion."""
        user_id = 2002
        db.enroll_user(user_id, "Arjun", self.test_db)

        today = date.today()
        d1 = (today - timedelta(days=2)).isoformat()
        d2 = (today - timedelta(days=1)).isoformat()

        # Day 1 100% completion (500 pts total)
        db.log_activity(user_id, "Arjun", "Push-ups", 100, d1, self.test_db)
        db.log_activity(user_id, "Arjun", "Pull-ups", 100, d1, self.test_db)
        db.log_activity(user_id, "Arjun", "Sit-ups", 100, d1, self.test_db)
        db.log_activity(user_id, "Arjun", "Squats", 100, d1, self.test_db)
        db.log_activity(user_id, "Arjun", "Running", 10, d1, self.test_db)

        # Day 2 100% completion (500 pts total)
        db.log_activity(user_id, "Arjun", "Push-ups", 100, d2, self.test_db)
        db.log_activity(user_id, "Arjun", "Pull-ups", 100, d2, self.test_db)
        db.log_activity(user_id, "Arjun", "Sit-ups", 100, d2, self.test_db)
        db.log_activity(user_id, "Arjun", "Squats", 100, d2, self.test_db)
        db.log_activity(user_id, "Arjun", "Running", 10, d2, self.test_db)

        db.finalize_daily_summaries(d1, self.test_db)
        db.finalize_daily_summaries(d2, self.test_db)

        streak = db.calculate_streak(user_id, as_of_date=today.isoformat(), db_path=self.test_db)
        self.assertEqual(streak, 2)

    def test_streak_minimum_thirty_points_daily_threshold(self):
        """Verifies that 30 points are strictly required to preserve or advance a streak."""
        user_id = 9001
        db.enroll_user(user_id, "ThirtyPtWarrior", self.test_db)
        today = date.today().isoformat()

        self.assertEqual(db.calculate_streak(user_id, today, self.test_db), 0)

        # Log exactly 5 reps of 4 exercises (20 pts) + 1 km run (10 pts) = 30 pts
        db.log_activity(user_id, "ThirtyPtWarrior", "Push-ups", 5, today, self.test_db)
        db.log_activity(user_id, "ThirtyPtWarrior", "Pull-ups", 5, today, self.test_db)
        db.log_activity(user_id, "ThirtyPtWarrior", "Squats", 5, today, self.test_db)
        db.log_activity(user_id, "ThirtyPtWarrior", "Sit-ups", 5, today, self.test_db)
        db.log_activity(user_id, "ThirtyPtWarrior", "Running", 1.0, today, self.test_db)

        prog = db.get_user_daily_progress(user_id, today, self.test_db)
        self.assertEqual(prog["total_points"], 30)

        streak = db.calculate_streak(user_id, today, self.test_db)
        self.assertEqual(streak, 1)

        with db.get_connection(self.test_db) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET frost_shields = 1 WHERE discord_id = ?;", (user_id,))
            conn.commit()

        summaries = db.finalize_daily_summaries(today, self.test_db)
        user_summary = next(s for s in summaries if s["discord_id"] == user_id)
        self.assertFalse(user_summary["is_shielded"])
        self.assertEqual(user_summary["points"], 30)

        shield_status = db.get_user_shield_status(user_id, self.test_db)
        self.assertEqual(shield_status["frost_shields"], 1)

    def test_streak_optimized_database_calculation_without_n_plus_one(self):
        """Verifies single-query historical streak calculation and live today addition."""
        streak_user = 3001
        db.enroll_user(streak_user, "StreakWarrior", self.test_db)
        today = date.today()

        # Seed 3 consecutive perfect days in daily_summaries
        with db.get_connection(self.test_db) as conn:
            cursor = conn.cursor()
            user_rec = db.get_user_by_discord_id(streak_user, self.test_db)
            for i in range(1, 4):
                d = (today - timedelta(days=i)).isoformat()
                cursor.execute("""
                    INSERT INTO daily_summaries (user_id, date, points, completion_rate, perfect_day, is_shielded)
                    VALUES (?, ?, 500, 1.0, 1, 0);
                """, (user_rec["id"], d))
            conn.commit()

        # Without today done, streak should be 3
        streak = db.calculate_streak(streak_user, today.isoformat(), self.test_db)
        self.assertEqual(streak, 3)

        # Log a perfect day for today: 100 for all 5 tasks
        active_tasks = db.get_active_tasks(self.test_db)
        for t in active_tasks:
            db.log_activity(streak_user, "StreakWarrior", t["name"], t["target"], today.isoformat(), self.test_db)

        # Streak should now be 4
        streak = db.calculate_streak(streak_user, today.isoformat(), self.test_db)
        self.assertEqual(streak, 4)

    def test_streak_year_rollover_and_month_boundaries(self):
        """Verifies streak calculation across Dec 31 -> Jan 1 year rollovers and month boundaries."""
        user_id = 991101
        db.enroll_user(user_id, "YearRolloverWarrior", self.test_db)

        dates = ["2025-12-30", "2025-12-31", "2026-01-01", "2026-01-02"]
        for d in dates:
            db.log_activity(user_id, "YearRolloverWarrior", "Push-ups", 100, log_date=d, db_path=self.test_db)
            db.log_activity(user_id, "YearRolloverWarrior", "Pull-ups", 100, log_date=d, db_path=self.test_db)
            db.log_activity(user_id, "YearRolloverWarrior", "Squats", 100, log_date=d, db_path=self.test_db)
            db.log_activity(user_id, "YearRolloverWarrior", "Sit-ups", 100, log_date=d, db_path=self.test_db)
            db.log_activity(user_id, "YearRolloverWarrior", "Running", 10.0, log_date=d, db_path=self.test_db)
            db.finalize_daily_summaries(d, self.test_db)

        streak = db.calculate_streak(user_id, as_of_date="2026-01-02", db_path=self.test_db)
        self.assertEqual(streak, 4)

        feb_dates = ["2026-02-27", "2026-02-28", "2026-03-01"]
        user_id_feb = 991102
        db.enroll_user(user_id_feb, "FebWarrior", self.test_db)
        for d in feb_dates:
            db.log_activity(user_id_feb, "FebWarrior", "Push-ups", 50, log_date=d, db_path=self.test_db)
            db.finalize_daily_summaries(d, self.test_db)

        streak_feb = db.calculate_streak(user_id_feb, as_of_date="2026-03-01", db_path=self.test_db)
        self.assertEqual(streak_feb, 3)

        db.log_activity(user_id_feb, "FebWarrior", "Push-ups", 50, log_date="2026-03-03", db_path=self.test_db)
        broken_streak = db.calculate_streak(user_id_feb, as_of_date="2026-03-03", db_path=self.test_db)
        self.assertEqual(broken_streak, 1)


class TestStreakShields(WinterArcTestCase):
    """Verifies Streak Shield inventory, manual activation, midnight rollover, and recovery."""

    def test_frost_shield_inventory_and_milestone_lifecycle(self):
        """Verifies earning shields at 7-day milestones, max 2 cap, and manual activation."""
        user_id = 2001
        db.enroll_user(user_id, "ShieldWarrior", self.test_db)

        status = db.get_user_shield_status(user_id, self.test_db)
        self.assertEqual(status["frost_shields"], 0)
        self.assertEqual(status["max_shields"], 2)
        self.assertFalse(status["is_today_shielded"])

        # Award shield at streak = 7
        awarded = db.check_and_award_shield(user_id, 7, self.test_db)
        self.assertTrue(awarded)
        status = db.get_user_shield_status(user_id, self.test_db)
        self.assertEqual(status["frost_shields"], 1)

        # No duplicate award for same milestone
        dup = db.check_and_award_shield(user_id, 7, self.test_db)
        self.assertFalse(dup)

        # Award at streak = 14
        awarded_14 = db.check_and_award_shield(user_id, 14, self.test_db)
        self.assertTrue(awarded_14)
        status = db.get_user_shield_status(user_id, self.test_db)
        self.assertEqual(status["frost_shields"], 2)

        # Capped at 2 max
        awarded_21 = db.check_and_award_shield(user_id, 21, self.test_db)
        self.assertFalse(awarded_21)
        status = db.get_user_shield_status(user_id, self.test_db)
        self.assertEqual(status["frost_shields"], 2)

        # Manual activation
        act = db.activate_frost_shield(user_id, reason="Testing recovery", db_path=self.test_db)
        self.assertTrue(act["success"])
        self.assertEqual(act["remaining_shields"], 1)

        # Today should now be shielded
        status_after = db.get_user_shield_status(user_id, self.test_db)
        self.assertEqual(status_after["frost_shields"], 1)
        self.assertTrue(status_after["is_today_shielded"])

        # Cannot double-activate for same day
        with self.assertRaises(ValueError):
            db.activate_frost_shield(user_id, reason="Duplicate attempt", db_path=self.test_db)

    def test_auto_shield_midnight_rollover_protection(self):
        """Verifies midnight rollover auto-activates an available shield if user missed target."""
        user_id = 2003
        db.enroll_user(user_id, "AutoShieldWarrior", self.test_db)

        # Award 1 shield
        db.check_and_award_shield(user_id, 7, self.test_db)

        day_1 = "2026-09-10"
        day_2 = "2026-09-11"

        # Log perfect day on day_1 to have active streak
        for t in ["Push-ups", "Pull-ups", "Squats", "Sit-ups", "Running"]:
            tgt = 10.0 if t == "Running" else 100.0
            db.log_activity(user_id, "AutoShieldWarrior", t, tgt, day_1, self.test_db)

        db.finalize_daily_summaries(day_1, self.test_db)
        streak_d1 = db.calculate_streak(user_id, day_1, self.test_db)
        self.assertEqual(streak_d1, 1)

        # Day 2: User logs nothing, but has 1 shield and streak > 0
        db.finalize_daily_summaries(day_2, self.test_db)

        # Shield should have been auto-consumed
        status = db.get_user_shield_status(user_id, self.test_db)
        self.assertEqual(status["frost_shields"], 0)

        # Streak should be preserved across Day 2!
        streak_d2 = db.calculate_streak(user_id, day_2, self.test_db)
        self.assertEqual(streak_d2, 2)

    def test_shield_activation_for_yesterday_retroactively(self):
        """Verifies retroactive shield activation for yesterday."""
        shield_user = 5001
        db.enroll_user(shield_user, "ShieldWarrior", self.test_db)
        user = db.get_user_by_discord_id(shield_user, self.test_db)

        with db.get_connection(self.test_db) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET frost_shields = 1 WHERE id = ?;", (user["id"],))
            conn.commit()

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        res = db.activate_frost_shield(shield_user, target_date=yesterday, reason="Travel", db_path=self.test_db)
        self.assertTrue(res["success"])
        self.assertEqual(res["target_date"], yesterday)
        self.assertEqual(res["remaining_shields"], 0)

    def test_finalize_daily_summaries_without_locking_shielded_days(self):
        """Verifies finalization auto-shields under-minimum days without transaction collision."""
        fin_user = 4001
        db.enroll_user(fin_user, "FinWarrior", self.test_db)
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        # Log under minimum workout for yesterday (15 pts < 30 pts)
        db.log_activity(fin_user, "FinWarrior", "Push-ups", 15, yesterday, self.test_db)

        # Give 1 frost shield and set active past streak
        user = db.get_user_by_discord_id(fin_user, self.test_db)
        day_before = (date.today() - timedelta(days=2)).isoformat()
        with db.get_connection(self.test_db) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET frost_shields = 1 WHERE id = ?;", (user["id"],))
            cursor.execute("""
                INSERT OR REPLACE INTO daily_summaries (user_id, date, points, completion_rate, perfect_day, is_shielded)
                VALUES (?, ?, 500, 1.0, 1, 0);
            """, (user["id"], day_before))
            conn.commit()

        # Finalization should auto-shield without throwing lock error
        summaries = db.finalize_daily_summaries(yesterday, self.test_db)
        self.assertTrue(len(summaries) >= 1)

        fin_summary = next((s for s in summaries if s["discord_id"] == fin_user), None)
        self.assertIsNotNone(fin_summary)
        self.assertTrue(fin_summary["is_shielded"])

    def test_shield_milestone_break_and_rebuild(self):
        """Verifies that when a streak is broken, last_shield_milestone resets so the warrior can earn shields again."""
        user_id = 991103
        db.enroll_user(user_id, "ShieldHero", self.test_db)

        self.assertTrue(db.check_and_award_shield(user_id, 7, self.test_db))
        status = db.get_user_shield_status(user_id, self.test_db)
        self.assertEqual(status["frost_shields"], 1)

        self.assertTrue(db.check_and_award_shield(user_id, 14, self.test_db))
        status = db.get_user_shield_status(user_id, self.test_db)
        self.assertEqual(status["frost_shields"], 2)

        self.assertFalse(db.check_and_award_shield(user_id, 21, self.test_db))
        status = db.get_user_shield_status(user_id, self.test_db)
        self.assertEqual(status["frost_shields"], 2)

        today_str = db.get_today_str()
        db.activate_frost_shield(user_id, target_date=today_str, reason="Active rest", db_path=self.test_db)
        status = db.get_user_shield_status(user_id, self.test_db)
        self.assertEqual(status["frost_shields"], 1)

        self.assertFalse(db.check_and_award_shield(user_id, 0, self.test_db))

        awarded_rebuild = db.check_and_award_shield(user_id, 7, self.test_db)
        self.assertTrue(awarded_rebuild, "Failed to re-award shield after rebuilding a broken streak")
        status = db.get_user_shield_status(user_id, self.test_db)
        self.assertEqual(status["frost_shields"], 2)

    def test_auto_shield_lifecycle_exhaustion_and_streak_break(self):
        """Verifies full lifecycle: 7-day streak earns shield, missed day auto-consumes it, exhaustion breaks streak, and rebuilding re-earns."""
        user_id = 771101
        db.enroll_user(user_id, "EnduranceHero", self.test_db)

        # Build initial 7-day streak
        base_date = date(2026, 9, 1)
        for i in range(7):
            d_str = (base_date + timedelta(days=i)).isoformat()
            db.log_activity(user_id, "EnduranceHero", "Push-ups", 100, d_str, self.test_db)
            db.finalize_daily_summaries(d_str, self.test_db)

        # Day 7 check: streak 7, 1 shield earned
        day_7_str = (base_date + timedelta(days=6)).isoformat()
        streak_7 = db.calculate_streak(user_id, day_7_str, self.test_db)
        self.assertEqual(streak_7, 7)
        status_7 = db.get_user_shield_status(user_id, self.test_db)
        self.assertEqual(status_7["frost_shields"], 1)

        # Day 8: User misses the day (< 30 pts)
        day_8_str = (base_date + timedelta(days=7)).isoformat()
        db.finalize_daily_summaries(day_8_str, self.test_db)

        # Shield was auto-consumed, streak was preserved to 8
        status_8 = db.get_user_shield_status(user_id, self.test_db)
        self.assertEqual(status_8["frost_shields"], 0)
        streak_8 = db.calculate_streak(user_id, day_8_str, self.test_db)
        self.assertEqual(streak_8, 8)

        # Day 9: User misses again, but has 0 shields left
        day_9_str = (base_date + timedelta(days=8)).isoformat()
        db.finalize_daily_summaries(day_9_str, self.test_db)

        # Streak is broken because 0 shields remained
        streak_9 = db.calculate_streak(user_id, day_9_str, self.test_db)
        self.assertEqual(streak_9, 0)

        # Rebuilding: Log 7 consecutive days (Day 10..16)
        for i in range(9, 16):
            d_str = (base_date + timedelta(days=i)).isoformat()
            db.log_activity(user_id, "EnduranceHero", "Push-ups", 100, d_str, self.test_db)
            db.finalize_daily_summaries(d_str, self.test_db)

        # At Day 16, streak is 7 again and new shield is earned
        day_16_str = (base_date + timedelta(days=15)).isoformat()
        streak_16 = db.calculate_streak(user_id, day_16_str, self.test_db)
        self.assertEqual(streak_16, 7)
        status_16 = db.get_user_shield_status(user_id, self.test_db)
        self.assertEqual(status_16["frost_shields"], 1)

    def test_shield_command_automated_ux(self):
        """Verifies /shield status and /shield use command outputs reflecting 100% automated system."""
        user_id = 771102
        db.enroll_user(user_id, "AutomatedHero", self.test_db)
        if not db.get_user_by_discord_id(user_id, db.DB_PATH):
            db.enroll_user(user_id, "AutomatedHero", db.DB_PATH)

        mock_member = self.create_mock_member(user_id, "AutomatedHero")
        mock_bot = MagicMock()
        cog = WarriorCog(mock_bot)

        async def run_shield_cmds():
            # Test /shield status
            status_inter = MagicMock(spec=discord.Interaction)
            status_inter.user = mock_member
            status_inter.response = MagicMock()
            status_inter.response.send_message = AsyncMock()

            with patch("helpers.require_enrolled", new_callable=AsyncMock, return_value=True), \
                 patch("cogs.warrior.require_enrolled", new_callable=AsyncMock, return_value=True), \
                 patch("cogs.warrior.dispatch_tip", new_callable=AsyncMock), \
                 patch("ai.groq_service.dispatch_interaction_nudge", new_callable=AsyncMock):
                await cog.shield_status_cmd.callback(cog, status_inter)
                status_inter.response.send_message.assert_called_once()
                call_kw = status_inter.response.send_message.call_args[1]
                embed = call_kw["embed"]
                self.assertIn("Streak Shield Status", embed.title)
                self.assertIn("Safety Status", embed.description)
                self.assertIn("Max 2 shields stored", embed.footer.text)

            # Test /shield use (0 shields)
            use_inter = MagicMock(spec=discord.Interaction)
            use_inter.user = mock_member
            use_inter.response = MagicMock()
            use_inter.response.send_message = AsyncMock()

            with patch("helpers.require_enrolled", new_callable=AsyncMock, return_value=True), \
                 patch("cogs.warrior.require_enrolled", new_callable=AsyncMock, return_value=True), \
                 patch("cogs.warrior.safe_react", new_callable=AsyncMock), \
                 patch("cogs.warrior.dispatch_tip", new_callable=AsyncMock), \
                 patch("ai.groq_service.dispatch_interaction_nudge", new_callable=AsyncMock):
                await cog.shield_use_cmd.callback(cog, use_inter)
                use_inter.response.send_message.assert_called_once()
                call_kw = use_inter.response.send_message.call_args[1]
                embed = call_kw["embed"]
                self.assertIn("100% Automated", embed.title)
                self.assertIn("only if you run out of Streak Shields", embed.description)

            # Test /shield use with 1 shield
            with db.get_connection(db.DB_PATH) as conn:
                conn.cursor().execute("UPDATE users SET frost_shields = 1 WHERE discord_id = ?;", (user_id,))
                conn.commit()
            use_inter_2 = MagicMock(spec=discord.Interaction)
            use_inter_2.user = mock_member
            use_inter_2.response = MagicMock()
            use_inter_2.response.send_message = AsyncMock()

            with patch("helpers.require_enrolled", new_callable=AsyncMock, return_value=True), \
                 patch("cogs.warrior.require_enrolled", new_callable=AsyncMock, return_value=True), \
                 patch("cogs.warrior.safe_react", new_callable=AsyncMock), \
                 patch("cogs.warrior.dispatch_tip", new_callable=AsyncMock), \
                 patch("ai.groq_service.dispatch_interaction_nudge", new_callable=AsyncMock):
                await cog.shield_use_cmd.callback(cog, use_inter_2)
                use_inter_2.response.send_message.assert_called_once()
                call_kw = use_inter_2.response.send_message.call_args[1]
                embed = call_kw["embed"]
                self.assertIn("100% Automated", embed.title)
                self.assertIn("automatically consumed at midnight", embed.description)

        asyncio.run(run_shield_cmds())

    def test_midnight_finalization_individual_channel_alerts(self):
        """Verifies individual separate messages are dispatched in channel for Case 1 (1 shield left), Case 2 (last shield), and Case 3 (streak broken)."""
        from scheduler import WinterArcScheduler

        user_a = 8801  # will have 1 shield left
        user_b = 8802  # will have 0 shields left (last shield)
        user_c = 8803  # will have streak broken (0 shields)

        db.enroll_user(user_a, "WarriorA", self.test_db)
        db.enroll_user(user_b, "WarriorB", self.test_db)
        db.enroll_user(user_c, "WarriorC", self.test_db)

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        day_before = (date.today() - timedelta(days=2)).isoformat()

        # Seed past streaks and shield inventories
        with db.get_connection(self.test_db) as conn:
            cursor = conn.cursor()
            # User A: past streak active, 2 frost shields
            cursor.execute("UPDATE users SET frost_shields = 2 WHERE discord_id = ?;", (user_a,))
            cursor.execute("INSERT OR REPLACE INTO daily_summaries (user_id, date, points, completion_rate, perfect_day, is_shielded) VALUES ((SELECT id FROM users WHERE discord_id = ?), ?, 500, 1.0, 1, 0);", (user_a, day_before))

            # User B: past streak active, 1 frost shield
            cursor.execute("UPDATE users SET frost_shields = 1 WHERE discord_id = ?;", (user_b,))
            cursor.execute("INSERT OR REPLACE INTO daily_summaries (user_id, date, points, completion_rate, perfect_day, is_shielded) VALUES ((SELECT id FROM users WHERE discord_id = ?), ?, 500, 1.0, 1, 0);", (user_b, day_before))

            # User C: past streak active, 0 frost shields
            cursor.execute("UPDATE users SET frost_shields = 0 WHERE discord_id = ?;", (user_c,))
            cursor.execute("INSERT OR REPLACE INTO daily_summaries (user_id, date, points, completion_rate, perfect_day, is_shielded) VALUES ((SELECT id FROM users WHERE discord_id = ?), ?, 500, 1.0, 1, 0);", (user_c, day_before))
            conn.commit()

        # Finalize yesterday
        leaderboard = db.finalize_daily_summaries(yesterday, self.test_db)

        entry_a = next(e for e in leaderboard if e["discord_id"] == user_a)
        entry_b = next(e for e in leaderboard if e["discord_id"] == user_b)
        entry_c = next(e for e in leaderboard if e["discord_id"] == user_c)

        self.assertTrue(entry_a["auto_shield_applied"])
        self.assertEqual(entry_a["shields_left"], 1)

        self.assertTrue(entry_b["auto_shield_applied"])
        self.assertEqual(entry_b["shields_left"], 0)

        self.assertFalse(entry_c["auto_shield_applied"])
        self.assertTrue(entry_c["streak_broken"])
        self.assertEqual(entry_c["broken_streak_count"], 1)

        # Now verify scheduler channel alerts
        mock_bot = MagicMock()
        mock_bot.get_user.return_value = None
        mock_bot.fetch_user = AsyncMock(return_value=None)
        scheduler = WinterArcScheduler(mock_bot, db_path=self.test_db)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.name = "winter-arc-general"
        mock_channel.send = AsyncMock()

        async def run_broadcast():
            with patch("database.finalize_daily_summaries", return_value=[entry_a, entry_b, entry_c]), \
                 patch("database.get_enrolled_users", return_value=[{"discord_id": user_a}, {"discord_id": user_b}, {"discord_id": user_c}]), \
                 patch("database.get_daily_grind_highlights", return_value=[]), \
                 patch("ai.gemini_service.generate_daily_toast_and_roast", new_callable=AsyncMock, return_value=""), \
                 patch("export_web_stats.export_stats_to_json"):
                await scheduler.broadcast_midnight_finalization(target_channel=mock_channel)

            # mock_channel.send should have been called individually for each alert
            send_calls = [call.kwargs.get("content") or (call.args[0] if call.args else "") for call in mock_channel.send.call_args_list]

            # Find Case 1 alert for User A (1 shield left)
            msg_a = next((m for m in send_calls if "**WarriorA**" in str(m) and "Streak Shield" in str(m)), None)
            self.assertIsNotNone(msg_a)
            self.assertNotIn(f"<@{user_a}>", msg_a)
            self.assertIn("Your Streak Shield just saved your", msg_a)
            self.assertIn("You have **1 shield left**. Lock in today!", msg_a)

            # Find Case 2 alert for User B (last shield)
            msg_b = next((m for m in send_calls if "**WarriorB**" in str(m) and "Streak Shield" in str(m)), None)
            self.assertIsNotNone(msg_b)
            self.assertNotIn(f"<@{user_b}>", msg_b)
            self.assertIn("Your Streak Shield just saved your", msg_b)
            self.assertIn("That was your **last shield**! Make sure to log today or your streak breaks!", msg_b)

            # Find Case 3 alert for User C (streak broken)
            msg_c = next((m for m in send_calls if "**WarriorC**" in str(m) and "broken" in str(m)), None)
            self.assertIsNotNone(msg_c)
            self.assertNotIn(f"<@{user_c}>", msg_c)
            self.assertIn("You missed yesterday and had no Streak Shields left.", msg_c)
            self.assertIn("has broken! Start fresh and rebuild today!", msg_c)

            # Verify that they were sent as distinct messages (not bundled together)
            self.assertEqual(len(send_calls), 4)  # 1 main message + 3 distinct individual alerts

        asyncio.run(run_broadcast())


class TestStreakCalendar(WinterArcTestCase):
    """Verifies monthly consistency calendar, 3-phase full view, and exact legend footers."""

    def test_monthly_habit_calendar_and_exact_legend_footer(self):
        """Validates monthly habit calendar grid, streak highlights, /streak command, and exact footer."""
        user_id = 999777
        user = db.get_user_by_discord_id(user_id, self.test_db)
        if not user:
            db.enroll_user(user_id, "ConsistencyWarrior", self.test_db)
            user = db.get_user_by_discord_id(user_id, self.test_db)
        if not db.get_user_by_discord_id(user_id, db.DB_PATH):
            db.enroll_user(user_id, "ConsistencyWarrior", db.DB_PATH)

        db.log_activity(user_id, "ConsistencyWarrior", "pushups", 50, log_date="2026-10-01", db_path=self.test_db)
        db.finalize_daily_summaries("2026-10-01", self.test_db)

        db.log_activity(user_id, "ConsistencyWarrior", "pushups", 100, log_date="2026-10-02", db_path=self.test_db)
        db.finalize_daily_summaries("2026-10-02", self.test_db)

        with db.get_connection(self.test_db) as conn:
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

        longest_streak = db.get_user_longest_streak(user_id, self.test_db)
        self.assertGreaterEqual(longest_streak, 6)

        data = db.get_user_monthly_consistency(user_id, year=2026, month=10, db_path=self.test_db)
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
        self.assertIn("▪️", grid)
        self.assertIn("days", grid)
        self.assertIn("pts)", grid)

        h = data["highlights"]
        self.assertGreaterEqual(h["highest_streak"], 6)
        self.assertGreaterEqual(h["perfect_days"], 2)
        self.assertGreaterEqual(h["shields_used"], 1)

        mock_member = self.create_mock_member(user_id, "ConsistencyWarrior")
        embed = build_streak_consistency_embed(mock_member, data)
        self.assertEmbedTitle(embed, "📅 Winter Arc — Streak and Consistency")
        self.assertEmbedDescriptionContains(
            embed,
            "CONSISTENCYWARRIOR",
            "OCTOBER 2026",
            "🏆 **Month Highlights:**",
            "• Highest Streak: 🏔️",
            "• Current Streak: 🔥",
            "• Consistency: 📅",
            "• Volume: ⚡",
            "• Perfect Days: ⭐",
            "• Streak Shields Used: 🛡️",
        )

        self.assertEmbedFooter(embed, STREAK_LEGEND_FOOTER)
        self.assertIn("🟩 Streaked", embed.footer.text)
        self.assertIn("⭐ Perfect Day (100%)", embed.footer.text)
        self.assertIn("🛡️ Shield Used", embed.footer.text)
        self.assertIn("🟥 Missed", embed.footer.text)
        self.assertIn("▫️ Upcoming", embed.footer.text)

        full_data = db.get_user_full_campaign_calendar(user_id, self.test_db)
        self.assertIn("PHASE 1: OCTOBER", full_data["calendar_text"])
        self.assertIn("PHASE 2: NOVEMBER", full_data["calendar_text"])
        self.assertIn("PHASE 3: DECEMBER", full_data["calendar_text"])

        full_embed = build_full_calendar_embed(mock_member, full_data)
        self.assertEmbedTitle(full_embed, "📅 Winter Arc — Full Calendar")
        self.assertEmbedDescriptionContains(
            full_embed,
            "CONSISTENCYWARRIOR",
            "OCT 1 – DEC 31",
            "🏆 **Overall Highlights:**",
            "• Overall Consistency: 📅",
            "• All-Time Longest Streak: 🏔️",
            "• Campaign Volume: ⚡",
            "• Total Perfect Days: ⭐",
            "• Total Shields Used: 🛡️",
        )
        self.assertEmbedFooter(full_embed, STREAK_LEGEND_FOOTER)

        view = StreakConsistencyView(
            target_user=mock_member,
            author_id=user_id,
            current_view="current"
        )
        self.assertEqual(len(view.children), 2)
        btn_labels = [c.label for c in view.children]
        self.assertEqual(btn_labels, ["Streak", "Calendar"])
        self.assertTrue(view.children[0].disabled)
        self.assertFalse(view.children[1].disabled)

        async def test_view_interactions():
            inter = MagicMock(spec=discord.Interaction)
            inter.user.id = user_id
            inter.response.edit_message = AsyncMock()

            await view._calendar_callback(inter)
            self.assertEqual(view.current_view, "calendar")
            self.assertFalse(view.children[0].disabled)
            self.assertTrue(view.children[1].disabled)
            inter.response.edit_message.assert_called_once()
            cal_call = inter.response.edit_message.call_args[1]
            self.assertEqual(cal_call["embed"].title, "📅 Winter Arc — Full Calendar")

            inter.response.edit_message.reset_mock()
            await view._current_callback(inter)
            self.assertEqual(view.current_view, "streak")
            self.assertTrue(view.children[0].disabled)
            self.assertFalse(view.children[1].disabled)
            inter.response.edit_message.assert_called_once()
            curr_call = inter.response.edit_message.call_args[1]
            self.assertEqual(curr_call["embed"].title, "📅 Winter Arc — Streak and Consistency")

        asyncio.run(test_view_interactions())

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
                await cog.streak_cmd.callback(cog, cmd_inter)
                cmd_inter.followup.send.assert_called_once()
                call_kw = cmd_inter.followup.send.call_args[1]
                self.assertEqual(call_kw["embed"].footer.text, STREAK_LEGEND_FOOTER)
                self.assertEqual(call_kw["embed"].title, "📅 Winter Arc — Streak and Consistency")
                self.assertIsInstance(call_kw["view"], StreakConsistencyView)
                self.assertEqual(call_kw["view"].current_view, "streak")

                # Test /calendar command
                cmd_inter.followup.send.reset_mock()
                await cog.calendar_cmd.callback(cog, cmd_inter)
                cmd_inter.followup.send.assert_called_once()
                cal_kw = cmd_inter.followup.send.call_args[1]
                self.assertEqual(cal_kw["embed"].footer.text, STREAK_LEGEND_FOOTER)
                self.assertEqual(cal_kw["embed"].title, "📅 Winter Arc — Full Calendar")
                self.assertIsInstance(cal_kw["view"], StreakConsistencyView)
                self.assertEqual(cal_kw["view"].current_view, "calendar")

        asyncio.run(test_streak_commands())
