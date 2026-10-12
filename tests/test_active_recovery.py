"""
tests/test_active_recovery.py - Comprehensive Unit Tests for Active Recovery Day (ARD)

Verifies:
1. Schedule accuracy (Oct 7 days, Nov 8 days, Dec 4 days).
2. Streak preservation across ARD days (zero point logging preserves streak).
3. Monospace calendar rendering with '❤️' emoji on ARD days.
4. Midnight finalization safety (zero shield deduction, zero broken streak).
5. Progress embed status ('ARD ❤️ Streak Protected' vs 'Streak Secured ✅').
6. Reactive AI nudge tone adaptation on recovery days.
"""

import os
import asyncio
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

import discord
from tests.base import WinterArcTestCase
import phases
import database as db
from ui.embeds import (
    build_today_embed,
    build_evening_checkin_embed,
    build_evening_checkin_message,
    build_morning_kickoff_message,
    build_morning_kickoff_embed,
    build_afternoon_checkin_embed,
    build_afternoon_checkin_message,
    build_dm_morning_message,
    build_dm_evening_message,
    build_streak_consistency_embed,
    build_daily_leaderboard_embed,
)
from ai import groq_service
from scheduler import WinterArcScheduler


class TestActiveRecoverySystem(WinterArcTestCase):
    """Test suite covering the end-to-end active recovery day engine."""

    def test_recovery_schedule_dates_and_helpers(self):
        """Verifies locked recovery dates for Oct, Nov, and Dec 2026."""
        # October: 7 dates (Every 3rd day starting Oct 11)
        oct_dates = phases.get_phase_recovery_days(1)
        self.assertEqual(len(oct_dates), 7)
        self.assertIn(f"{phases.BASE_YEAR}-10-11", oct_dates)
        self.assertIn(f"{phases.BASE_YEAR}-10-14", oct_dates)
        self.assertIn(f"{phases.BASE_YEAR}-10-29", oct_dates)

        # November: 8 dates (Every 4th day starting Nov 1)
        nov_dates = phases.get_phase_recovery_days(2)
        self.assertEqual(len(nov_dates), 8)
        self.assertIn(f"{phases.BASE_YEAR}-11-01", nov_dates)
        self.assertIn(f"{phases.BASE_YEAR}-11-05", nov_dates)
        self.assertIn(f"{phases.BASE_YEAR}-11-29", nov_dates)

        # December: 4 dates (Sundays)
        dec_dates = phases.get_phase_recovery_days(3)
        self.assertEqual(len(dec_dates), 4)
        self.assertIn(f"{phases.BASE_YEAR}-12-06", dec_dates)
        self.assertIn(f"{phases.BASE_YEAR}-12-13", dec_dates)
        self.assertIn(f"{phases.BASE_YEAR}-12-20", dec_dates)
        self.assertIn(f"{phases.BASE_YEAR}-12-27", dec_dates)

        # Helpers
        self.assertTrue(phases.is_recovery_day(f"{phases.BASE_YEAR}-10-11"))
        self.assertFalse(phases.is_recovery_day(f"{phases.BASE_YEAR}-10-12"))
        self.assertEqual(
            phases.get_next_recovery_day(f"{phases.BASE_YEAR}-10-12"),
            f"{phases.BASE_YEAR}-10-14"
        )

    def test_streak_preservation_across_ard_days(self):
        """Verifies that a user's streak bridges across ARD days with 0 points without breaking."""
        user_id = 991100
        u = db.enroll_user(user_id, "ZenWarrior", db_path=self.test_db)
        self.assertIsNotNone(u)

        # Train on Oct 9 and Oct 10 (30 pts each)
        d_oct9 = f"{phases.BASE_YEAR}-10-09"
        d_oct10 = f"{phases.BASE_YEAR}-10-10"
        d_oct11 = f"{phases.BASE_YEAR}-10-11"  # ARD
        d_oct12 = f"{phases.BASE_YEAR}-10-12"  # Training Day

        # Add completed days directly to daily_summaries
        with db.get_connection(self.test_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO daily_summaries (user_id, date, points, completion_rate, perfect_day, is_shielded)
                VALUES (?, ?, 30, 0.3, 0, 0), (?, ?, 30, 0.3, 0, 0);
            """, (u["id"], d_oct9, u["id"], d_oct10))
            conn.commit()

        # On Oct 10: streak should be 2
        streak_oct10 = db.calculate_streak(user_id, as_of_date=d_oct10, db_path=self.test_db)
        self.assertEqual(streak_oct10, 2)

        # On Oct 11 (ARD, 0 points logged): streak should remain preserved at 2!
        streak_oct11 = db.calculate_streak(user_id, as_of_date=d_oct11, db_path=self.test_db)
        self.assertEqual(streak_oct11, 2)

        # On Oct 11 at midnight: finalization should NOT break streak and NOT use shields
        leaderboard = db.finalize_daily_summaries(target_date_str=d_oct11, db_path=self.test_db)
        user_entry = next(e for e in leaderboard if e["discord_id"] == user_id)
        self.assertFalse(user_entry["streak_broken"])
        self.assertFalse(user_entry["auto_shield_applied"])
        self.assertEqual(user_entry["shields_left"], 0)

        # On Oct 12: user logs 30 points -> streak becomes 3!
        with db.get_connection(self.test_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO daily_summaries (user_id, date, points, completion_rate, perfect_day, is_shielded)
                VALUES (?, ?, 30, 0.3, 0, 0);
            """, (u["id"], d_oct12))
            conn.commit()

        streak_oct12 = db.calculate_streak(user_id, as_of_date=d_oct12, db_path=self.test_db)
        self.assertEqual(streak_oct12, 3)

    def test_calendar_matrix_renders_heart_emoji(self):
        """Verifies habit calendar renders '❤️' on scheduled ARD days."""
        user_id = 991101
        db.enroll_user(user_id, "RestTracker", db_path=self.test_db)

        # Check October calendar matrix
        matrix = db.get_user_monthly_consistency(user_id, year=phases.BASE_YEAR, month=10, db_path=self.test_db)
        grid = matrix["calendar_grid"]

        # The '❤️' emoji must be present in the grid for Oct 11, 14, 17, etc.
        self.assertIn("❤️", grid)

    def test_today_embed_recovery_day_status(self):
        """Verifies /today embed displays protected ARD status when under 30 points."""
        member = self.create_mock_member(user_id=991102, display_name="RestTester")
        prog = {
            "total_points": 0,
            "max_possible_points": 500,
            "overall_completion_rate": 0.0,
            "perfect_day": False,
            "tasks": [],
        }

        # Mock today as an ARD day (e.g. Oct 11)
        with patch("ui.embeds.is_recovery_day", return_value=True):
            embed = build_today_embed(
                target_user=member,
                progress=prog,
                streak=5,
                date_display="Sunday, Oct 11",
            )
            self.assertIn("*(ARD ❤️ Streak Protected)*", embed.description)
            self.assertIn("Active Recovery Day (ARD) ❤️", embed.footer.text)

        # When user hits 30 points on recovery day: shows Secured ✅
        prog["total_points"] = 35
        with patch("ui.embeds.is_recovery_day", return_value=True):
            embed_secured = build_today_embed(
                target_user=member,
                progress=prog,
                streak=5,
                date_display="Sunday, Oct 11",
            )
            self.assertIn("*(Streak Secured ✅)*", embed_secured.description)

    def test_evening_checkin_peaceful_wind_down(self):
        """Verifies evening check-in switches to peaceful wind-down without panic warnings."""
        warriors_data = [{
            "discord_id": 991103,
            "username": "ChillWarrior",
            "points": 0,
            "max_points": 500,
            "streak": 7,
            "perfect_day": False,
        }]

        # Normal day -> Urgent warning
        normal_msg = build_evening_checkin_message(warriors_data, is_recovery=False)
        self.assertIn("3 hours left until midnight rollover. ⏳", normal_msg)
        self.assertIn("Stop scrolling", normal_msg)

        # Recovery day -> Peaceful wind-down
        recovery_msg = build_evening_checkin_message(warriors_data, is_recovery=True)
        self.assertIn("Winter Arc — Evening Wind-Down 🌙", recovery_msg)
        self.assertIn("Active Recovery Day is winding down", recovery_msg)
        self.assertNotIn("Stop scrolling", recovery_msg)

    def test_calendar_matrix_hides_upcoming_ard(self):
        """Verifies future ARDs remain hidden as '▫️' until the date actually arrives."""
        user_id = 991104
        db.enroll_user(user_id, "SecretAgent", db_path=self.test_db)

        # On Oct 11 (ARD), Oct 11 shows ❤️, but future ARD Oct 14 shows ▫️
        matrix = db.get_user_monthly_consistency(user_id, year=phases.BASE_YEAR, month=10, db_path=self.test_db)
        day_details = matrix["day_details"]
        self.assertEqual(day_details[11]["status"], "❤️")
        # Oct 14 is in the future relative to Oct 11 -> hidden as ▫️
        self.assertEqual(day_details[14]["status"], "▫️")
        self.assertEqual(day_details[29]["status"], "▫️")

    def test_morning_kickoff_pings_role_on_ard(self):
        """Verifies morning kickoff pings the role on ARD days as an explicit exception."""
        mock_bot = MagicMock()
        mock_channel = self.create_mock_channel(7777)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 999222
        mock_bot.guilds = [mock_guild]

        scheduler = WinterArcScheduler(mock_bot, db_path=self.test_db)
        with patch.object(scheduler, "_get_target_channel_and_ping", return_value=(mock_channel, "<@&999888>")):
            with patch("scheduler.is_recovery_day", return_value=True):
                with patch("ai.reasoning_service.generate_personalized_morning_briefing", return_value="Active recovery pack advice."):
                    with patch("ai.reasoning_service.generate_reminder_motivation", return_value="Take a light walk."):
                        asyncio.run(scheduler.broadcast_morning_kickoff())
                        self.assertTrue(mock_channel.send.called)
                        sent_content = mock_channel.send.call_args.kwargs.get("content", "")
                        # Role ping must be present on ARD
                        self.assertIn("<@&999888>", sent_content)
                        allowed_mentions = mock_channel.send.call_args.kwargs.get("allowed_mentions")
                        self.assertIsNotNone(allowed_mentions)
                        self.assertTrue(allowed_mentions.roles)

    def test_afternoon_checkin_ard_format(self):
        """Verifies afternoon check-in on ARD has no role ping, simple AI reminder, and no roster."""
        mock_bot = MagicMock()
        mock_channel = self.create_mock_channel(7778)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 999222
        mock_bot.guilds = [mock_guild]

        scheduler = WinterArcScheduler(mock_bot, db_path=self.test_db)
        with patch.object(scheduler, "_get_target_channel_and_ping", return_value=(mock_channel, "<@&999888>")):
            with patch("scheduler.is_recovery_day", return_value=True), \
                 patch("ui.embed_builders.broadcasts.is_recovery_day", return_value=True), \
                 patch("ai.reasoning_service.generate_reminder_motivation", return_value="Hydrate and stretch lightly."):
                asyncio.run(scheduler.broadcast_afternoon_checkin())
                self.assertTrue(mock_channel.send.called)
                sent_content = mock_channel.send.call_args.kwargs.get("content", "")
                # No role ping on ARD afternoon
                self.assertNotIn("<@&999888>", sent_content)
                embed = mock_channel.send.call_args.kwargs.get("embed")
                self.assertIn("Winter Arc — Midday Pulse 🌿", embed.title)
                self.assertIn("Hydrate and stretch lightly.", embed.description)

    def test_midnight_finalization_silent_on_ard(self):
        """Verifies midnight finalization silently executes without channel dispatch on ARD."""
        mock_bot = MagicMock()
        mock_channel = self.create_mock_channel(7779)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 999222
        mock_bot.guilds = [mock_guild]

        scheduler = WinterArcScheduler(mock_bot, db_path=self.test_db)
        with patch.object(scheduler, "_get_target_channel_and_ping", return_value=(mock_channel, "<@&999888>")):
            # Yesterday was an ARD
            with patch("scheduler.is_recovery_day", return_value=True):
                asyncio.run(scheduler.broadcast_midnight_finalization())
                # Channel send must NOT be called on ARD!
                self.assertFalse(mock_channel.send.called)

    def test_ard_dm_messaging_and_skip_afternoon(self):
        """Verifies short DM messages and skipping afternoon DMs on ARD."""
        # Morning DM
        msg_m = build_dm_morning_message([], streak=5, date_display="Sunday, Oct 11", quote="Focus on joint mobility and water.", is_recovery=True)
        self.assertIn("Today is Rest Day!", msg_m)
        self.assertIn("Focus on joint mobility and water.", msg_m)

        # Evening DM
        msg_e = build_dm_evening_message("Warrior", points=0, max_points=500, streak=5, shields=0, is_recovery=True)
        self.assertIn("Active Recovery Day Complete! 🌙", msg_e)
        self.assertNotIn("3 hours left", msg_e)

        # Scheduler dispatch_afternoon_dms skips on ARD
        mock_bot = MagicMock()
        scheduler = WinterArcScheduler(mock_bot, db_path=self.test_db)
        with patch("scheduler.is_recovery_day", return_value=True):
            with patch.object(scheduler, "_send_single_afternoon_dm") as mock_dm:
                asyncio.run(scheduler.dispatch_afternoon_dms())
                self.assertFalse(mock_dm.called)

    def test_daily_leaderboard_paused_on_ard(self):
        """Verifies daily leaderboard reflects paused competition on recovery days."""
        with patch("ui.embeds.is_recovery_day", return_value=True):
            embed = build_daily_leaderboard_embed()
            self.assertIn("Active Recovery Day 🌿", embed.title)
            self.assertIn("The scoreboard is paused today.", embed.description)
            self.assertIn("Daily scoring and competition are closed", embed.description)

    def test_ard_blocks_logging_commands(self):
        """Verifies /log, /set, /grind, and /quick reject submissions on recovery days."""
        from cogs.warrior import WarriorCog
        from unittest.mock import AsyncMock

        mock_bot = MagicMock()
        cog = WarriorCog(mock_bot)
        mock_user = self.create_mock_member(user_id=12345, display_name="TiredWarrior")

        async def run_checks():
            # 1. /log
            inter_log = MagicMock(spec=discord.Interaction)
            inter_log.user = mock_user
            inter_log.response = MagicMock()
            inter_log.response.defer = AsyncMock()
            inter_log.followup = MagicMock()
            inter_log.followup.send = AsyncMock()

            with patch("cogs.warrior.require_enrolled", new_callable=AsyncMock, return_value=True), \
                 patch("cogs.warrior.is_recovery_day", return_value=True), \
                 patch("cogs.warrior.safe_react", new_callable=AsyncMock):
                await cog.log_activity_cmd.callback(cog, inter_log, "Push-ups", 25)
                inter_log.followup.send.assert_called_once()
                args, _ = inter_log.followup.send.call_args
                self.assertIn("Active Recovery Day (ARD)", args[0])

            # 2. /set
            inter_set = MagicMock(spec=discord.Interaction)
            inter_set.user = mock_user
            inter_set.response = MagicMock()
            inter_set.response.defer = AsyncMock()
            inter_set.followup = MagicMock()
            inter_set.followup.send = AsyncMock()

            with patch("cogs.warrior.require_enrolled", new_callable=AsyncMock, return_value=True), \
                 patch("cogs.warrior.is_recovery_day", return_value=True), \
                 patch("cogs.warrior.safe_react", new_callable=AsyncMock):
                await cog.set_activity_cmd.callback(cog, inter_set, "Push-ups", 0)
                inter_set.followup.send.assert_called_once()
                args, _ = inter_set.followup.send.call_args
                self.assertIn("Active Recovery Day (ARD)", args[0])

            # 3. /grind
            inter_grind = MagicMock(spec=discord.Interaction)
            inter_grind.user = mock_user
            inter_grind.response = MagicMock()
            inter_grind.response.send_message = AsyncMock()

            with patch("cogs.warrior.require_enrolled", new_callable=AsyncMock, return_value=True), \
                 patch("cogs.warrior.is_recovery_day", return_value=True):
                await cog.grind_cmd.callback(cog, inter_grind, "Light morning yoga and breathing")
                inter_grind.response.send_message.assert_called_once()
                args, _ = inter_grind.response.send_message.call_args
                self.assertIn("Active Recovery Day (ARD)", args[0])

            # 4. /quick
            inter_quick = MagicMock(spec=discord.Interaction)
            inter_quick.user = mock_user
            inter_quick.response = MagicMock()
            inter_quick.response.send_message = AsyncMock()

            with patch("cogs.warrior.require_enrolled", new_callable=AsyncMock, return_value=True), \
                 patch("cogs.warrior.is_recovery_day", return_value=True):
                await cog.quick_cmd.callback(cog, inter_quick, "did 30 pushups")
                inter_quick.response.send_message.assert_called_once()
                args, _ = inter_quick.response.send_message.call_args
                self.assertIn("Active Recovery Day (ARD)", args[0])

        asyncio.run(run_checks())

    def test_purge_recovery_day_logs(self):
        """Verifies safe database purge of accidental activity, grind, and summaries on recovery days."""
        test_uid = 887766
        ard_date = f"{phases.BASE_YEAR}-10-11"

        db.enroll_user(test_uid, "AccidentalLogger", self.test_db)
        db.log_activity(test_uid, "AccidentalLogger", "Push-ups", 40, ard_date, db_path=self.test_db)
        db.record_grind_entry(test_uid, ard_date, "Heavy bag session", "PASS", 30, "Stamina", "Solid work", db_path=self.test_db)

        # Confirm logs exist prior to purge
        prog_before = db.get_user_daily_progress(test_uid, ard_date, db_path=self.test_db)
        self.assertGreater(prog_before["total_points"], 0)

        # Perform safe purge
        res = db.purge_recovery_day_logs(ard_date, db_path=self.test_db)
        self.assertEqual(res["date"], ard_date)
        self.assertGreaterEqual(res["deleted_daily_logs"], 1)
        self.assertGreaterEqual(res["deleted_grind_logs"], 1)
        self.assertTrue(os.path.exists(res["backup_path"]))

        # Confirm logs are wiped clean for that target day
        prog_after = db.get_user_daily_progress(test_uid, ard_date, db_path=self.test_db)
        self.assertEqual(prog_after["total_points"], 0)
        self.assertIsNone(db.get_user_daily_grind(test_uid, ard_date, db_path=self.test_db))

    def test_history_and_calculations_ignore_rest_day_points_and_tasks(self):
        """Verifies that rest day points/tasks are strictly ignored in calculations and /history."""
        test_uid = 998877
        ard_date = f"{phases.BASE_YEAR}-10-11"
        workout_date = f"{phases.BASE_YEAR}-10-10"

        db.enroll_user(test_uid, "RestDayWarrior", self.test_db)

        # Log real workout on workout_date
        db.log_activity(test_uid, "RestDayWarrior", "Push-ups", 100, workout_date, db_path=self.test_db)
        db.finalize_daily_summaries(workout_date, db_path=self.test_db)

        # Even if logs existed on recovery day:
        db.log_activity(test_uid, "RestDayWarrior", "Pull-ups", 50, ard_date, db_path=self.test_db)
        db.record_grind_entry(test_uid, ard_date, "Leetcode study", "ACCEPTED", 35, "Algorithms", "Nice", db_path=self.test_db)

        # 1. /history DAO check
        hist = db.get_user_history(test_uid, days=3, db_path=self.test_db)
        ard_entry = next((h for h in hist if h["date"] == ard_date), None)
        self.assertIsNotNone(ard_entry)
        self.assertTrue(ard_entry["is_rest_day"])
        self.assertEqual(ard_entry["points"], 0)

        # 2. /history Embed UI check
        from ui.embeds import build_history_embed
        mock_member = self.create_mock_member(test_uid, "RestDayWarrior")
        embed = build_history_embed(mock_member, hist)
        self.assertIn("Active Recovery Day", embed.description)
        self.assertIn("Streak Protected ❤️", embed.description)
        # Should not display points or grind for ARD
        self.assertNotIn("+35 pts grind", embed.description)

        # 3. get_user_stats check: lifetime points and task volume must ignore recovery day
        stats = db.get_user_stats(test_uid, db_path=self.test_db)
        self.assertEqual(stats["lifetime_points"], 100)  # Only 100 pts from Oct 10
        pullup_vol = next((t["total_volume"] for t in stats["task_totals"] if t["name"] == "Pull-ups"), 0.0)
        self.assertEqual(pullup_vol, 0.0)  # Oct 11 pull-ups ignored

        # 4. Overall leaderboard check
        overall = db.get_overall_leaderboard(db_path=self.test_db)
        user_row = next((r for r in overall if r["discord_id"] == test_uid), None)
        self.assertIsNotNone(user_row)
        self.assertEqual(user_row["total_points"], 100)

        # 5. Phase leaderboard check
        p1_lb = db.get_phase_leaderboard(1, db_path=self.test_db)
        p1_row = next((r for r in p1_lb if r["discord_id"] == test_uid), None)
        self.assertIsNotNone(p1_row)
        self.assertEqual(p1_row["total_points"], 100)

    def test_ard_presence_rotation(self):
        """Verifies that maintenance_and_presence_loop cycles ARD-specific statuses on recovery days."""
        mock_bot = MagicMock()
        mock_bot.change_presence = AsyncMock()
        scheduler = WinterArcScheduler(mock_bot, db_path=self.test_db)

        # 1. On an Active Recovery Day:
        with patch("scheduler.is_recovery_day", return_value=True):
            scheduler._presence_index = 0
            # Cycle 4 times to check all 4 ARD statuses
            for expected_name in [
                "/help • Winter Arc",
                "Enrolled Warriors",
                "Recovery Mode 🧘",
                "Active Recovery ❤️"
            ]:
                asyncio.run(scheduler.maintenance_and_presence_loop.coro(scheduler))
                call_args = mock_bot.change_presence.call_args
                self.assertIsNotNone(call_args)
                activity = call_args.kwargs.get("activity")
                self.assertIn(expected_name, activity.name)

        # 2. On a Standard Training Day:
        with patch("scheduler.is_recovery_day", return_value=False):
            scheduler._presence_index = 0
            for expected_name in [
                "/help • Winter Arc",
                "Enrolled Warriors",
                "Winter Arc (500 pts daily)",
                "Defend the Flame | /streak"
            ]:
                asyncio.run(scheduler.maintenance_and_presence_loop.coro(scheduler))
                call_args = mock_bot.change_presence.call_args
                self.assertIsNotNone(call_args)
                activity = call_args.kwargs.get("activity")
                self.assertIn(expected_name, activity.name)




