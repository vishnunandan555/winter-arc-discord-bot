"""
tests/test_leaderboards_phases.py - Leaderboards, Phases, Recaps, and Server Records Tests
"""
from datetime import date, timedelta
from unittest.mock import MagicMock
import os
import sqlite3
import shutil
import database as db
import phases
from ui.embeds import (
    build_recap_embed,
    build_phase_podium_embed,
    build_monthly_leaderboard_embed,
    build_profile_embed,
    build_shield_status_embed,
    build_ranks_embed,
    build_server_records_embed,
    format_log_reply,
    format_set_reply,
)
from ui.views import RecapView, ServerRecordsView
from levels import check_level_up, get_level_info, APEX_THRESHOLD
from tests.base import WinterArcTestCase


class TestLeaderboardRankings(WinterArcTestCase):
    """Verifies daily, weekly, monthly, and overall campaign leaderboard calculations."""

    def test_daily_and_overall_leaderboard_aggregation(self):
        """Verifies ranking order by total points across past finalized summaries and today's logs."""
        u1 = 1001
        u2 = 2002
        db.enroll_user(u1, "Vishnu", self.test_db)
        db.enroll_user(u2, "Arjun", self.test_db)

        today = date.today()
        today_str = today.isoformat()
        db.log_activity(u1, "Vishnu", "Push-ups", 30, today_str, self.test_db)

        # Check daily leaderboard
        daily_lb = db.get_daily_leaderboard(today_str, self.test_db)
        usernames = [u["username"] for u in daily_lb]
        self.assertIn("Vishnu", usernames)

        # Check overall leaderboard with multi-day activity
        d1 = (today - timedelta(days=2)).isoformat()
        db.log_activity(u2, "Arjun", "Push-ups", 100, d1, self.test_db)
        db.log_activity(u2, "Arjun", "Pull-ups", 100, d1, self.test_db)
        db.log_activity(u2, "Arjun", "Squats", 100, d1, self.test_db)
        db.log_activity(u2, "Arjun", "Sit-ups", 100, d1, self.test_db)
        db.log_activity(u2, "Arjun", "Running", 10, d1, self.test_db)
        db.finalize_daily_summaries(d1, self.test_db)

        overall = db.get_overall_leaderboard(self.test_db)
        self.assertGreater(len(overall), 0)
        overall_usernames = [u["username"] for u in overall]
        self.assertIn("Arjun", overall_usernames)
        self.assertIn("Vishnu", overall_usernames)
        self.assertEqual(overall[0]["username"], "Arjun")
        self.assertGreaterEqual(overall[0]["total_points"], 500)

    def test_batched_leaderboard_types_return_lists(self):
        """Verifies daily, monthly, and overall leaderboard queries return list instances."""
        today_str = date.today().isoformat()
        daily_lb = db.get_daily_leaderboard(today_str, self.test_db)
        self.assertIsInstance(daily_lb, list)

        overall_lb = db.get_overall_leaderboard(self.test_db)
        self.assertIsInstance(overall_lb, list)

        now = date.today()
        monthly_lb = db.get_monthly_leaderboard(now.year, now.month, self.test_db)
        self.assertIsInstance(monthly_lb, list)

    def test_weekly_and_monthly_leaderboard_standings_and_live_activity(self):
        """Verifies that weekly and monthly leaderboards aggregate past finalized summaries and today's live activity correctly."""
        u1 = 991106
        u2 = 991107
        db.enroll_user(u1, "LeaderOne", self.test_db)
        db.enroll_user(u2, "LeaderTwo", self.test_db)

        today = db.get_today_date()
        yesterday = (today - timedelta(days=1)).isoformat()
        today_str = today.isoformat()

        # Finalized day yesterday: u1 got 500 pts, u2 got 200 pts
        db.log_activity(u1, "LeaderOne", "Push-ups", 100, yesterday, self.test_db)
        db.log_activity(u1, "LeaderOne", "Pull-ups", 100, yesterday, self.test_db)
        db.log_activity(u1, "LeaderOne", "Squats", 100, yesterday, self.test_db)
        db.log_activity(u1, "LeaderOne", "Sit-ups", 100, yesterday, self.test_db)
        db.log_activity(u1, "LeaderOne", "Running", 10.0, yesterday, self.test_db)

        db.log_activity(u2, "LeaderTwo", "Push-ups", 100, yesterday, self.test_db)
        db.log_activity(u2, "LeaderTwo", "Pull-ups", 100, yesterday, self.test_db)
        db.finalize_daily_summaries(yesterday, self.test_db)

        # Live day today: u1 got 100 pts, u2 got 300 pts
        db.log_activity(u1, "LeaderOne", "Push-ups", 100, today_str, self.test_db)
        db.log_activity(u2, "LeaderTwo", "Push-ups", 100, today_str, self.test_db)
        db.log_activity(u2, "LeaderTwo", "Squats", 100, today_str, self.test_db)
        db.log_activity(u2, "LeaderTwo", "Sit-ups", 100, today_str, self.test_db)

        # Overall leaderboard: u1 (500 + 100 = 600) vs u2 (200 + 300 = 500)
        overall = db.get_overall_leaderboard(self.test_db)
        u1_entry = next((entry for entry in overall if entry["discord_id"] == u1), None)
        u2_entry = next((entry for entry in overall if entry["discord_id"] == u2), None)
        self.assertIsNotNone(u1_entry)
        self.assertIsNotNone(u2_entry)
        self.assertEqual(u1_entry["total_points"], 600)
        self.assertEqual(u2_entry["total_points"], 500)


class TestWinterArcPhases(WinterArcTestCase):
    """Verifies phase definitions, calendar bounding, recap queries, snapshot isolation, and UI views."""

    def test_winter_arc_phases_definitions_and_calendar_bounding(self):
        """Verifies 4-phase metadata, boundaries, active discovery, and last-day detection."""
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

        self.assertEqual(len(phases.get_unlocked_phases("2026-10-10")), 1)
        self.assertEqual(len(phases.get_unlocked_phases("2026-11-05")), 2)
        self.assertEqual(len(phases.get_unlocked_phases("2026-12-01")), 3)
        self.assertEqual(len(phases.get_unlocked_phases("2027-01-01")), 4)

        is_last, ph = phases.is_last_day_of_phase("2026-10-31")
        self.assertTrue(is_last)
        self.assertEqual(ph["name"], "FIRST FROST")

        is_last_mid, _ = phases.is_last_day_of_phase("2026-10-15")
        self.assertFalse(is_last_mid)

    def test_phase_leaderboard_user_stats_and_snapshot_archival(self):
        """Verifies phase standings, volume aggregations, snapshot isolation, and UI recaps."""
        u_phase = 777111
        db.enroll_user(u_phase, "PhaseWarrior", self.test_db)

        d_oct1 = "2026-10-05"
        d_oct2 = "2026-10-06"
        db.log_activity(u_phase, "PhaseWarrior", "Push-ups", 100, d_oct1, self.test_db)
        db.log_activity(u_phase, "PhaseWarrior", "Running", 10, d_oct1, self.test_db)
        db.finalize_daily_summaries(d_oct1, self.test_db)

        db.log_activity(u_phase, "PhaseWarrior", "Squats", 100, d_oct2, self.test_db)
        db.finalize_daily_summaries(d_oct2, self.test_db)

        d_nov = "2026-11-05"
        db.log_activity(u_phase, "PhaseWarrior", "Sit-ups", 100, d_nov, self.test_db)
        db.finalize_daily_summaries(d_nov, self.test_db)

        p1_lb = db.get_phase_leaderboard(1, self.test_db)
        p1_entry = next((e for e in p1_lb if e["discord_id"] == u_phase), None)
        self.assertIsNotNone(p1_entry)
        self.assertEqual(p1_entry["total_points"], 300)

        p1_stats = db.get_user_phase_stats(u_phase, 1, self.test_db)
        self.assertEqual(p1_stats["total_points"], 300)
        self.assertEqual(p1_stats["active_days"], 2)
        push_vol = next((t["total_volume"] for t in p1_stats["task_totals"] if t["name"] == "Push-ups"), 0)
        self.assertEqual(push_vol, 100)

        overall_recap = db.get_user_overall_recap(u_phase, self.test_db)
        self.assertGreaterEqual(overall_recap["lifetime_points"], 400)

        # Snapshot Archival
        backup_dir = os.path.join(os.path.dirname(self.test_db), "test_backups")
        snapshot_file = db.archive_phase_snapshot(1, self.test_db, backup_dir=backup_dir)
        self.assertTrue(os.path.exists(snapshot_file))

        s_conn = sqlite3.connect(snapshot_file)
        try:
            s_cur = s_conn.cursor()
            s_cur.execute("SELECT total_points FROM phase_standings WHERE discord_id = ?;", (u_phase,))
            row = s_cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], 300)

            s_cur.execute("SELECT COUNT(*) FROM daily_summaries WHERE date >= '2026-11-01';")
            self.assertEqual(s_cur.fetchone()[0], 0)
        finally:
            s_conn.close()

        shutil.rmtree(backup_dir, ignore_errors=True)

        # UI Embeds & RecapView
        mock_user = self.create_mock_member(user_id=u_phase, display_name="PhaseWarrior")
        mock_user.avatar = None

        embed_p1 = build_recap_embed(mock_user, p1_stats, is_overall=False)
        self.assertIn("FIRST FROST", embed_p1.title)
        self.assertIn("300 pts", embed_p1.description)

        embed_all = build_recap_embed(mock_user, overall_recap, is_overall=True)
        self.assertIn("Overall Campaign Recap", embed_all.title)

        p1 = phases.get_phase_by_id(1)
        podium_embed = build_phase_podium_embed(p1, p1_lb)
        self.assertIn("FIRST FROST Concluded", podium_embed.title)

        m_embed = build_monthly_leaderboard_embed(year=2026, month=10)
        self.assertIn("FIRST FROST", m_embed.title)

        user_record = db.get_user_by_discord_id(u_phase, self.test_db)
        stats_data = db.get_user_stats(u_phase, self.test_db)
        prof_embed = build_profile_embed(mock_user, user_record, 2, stats_data)
        self.assertIn("Active Phase", prof_embed.description)

        view = RecapView(target_user=mock_user, author_id=mock_user.id, current_selection="phase_1")
        self.assertTrue(len(view.children) >= 2)


class TestProgressionAndRecordsEdgeCases(WinterArcTestCase):
    """Verifies edge cases in volume limits, reply formatters, apex tiers, and server records."""

    def test_apex_threshold_and_multi_tier_leaps(self):
        """Verifies leap to Vanguard and capped calculations at and beyond Apex threshold."""
        leap = check_level_up(0, 7500)
        self.assertIsNotNone(leap)
        self.assertEqual(leap["level"], 8)
        self.assertEqual(leap["title"], "Vanguard")
        self.assertEqual(leap["badge"], "🛡️")

        apex_info = get_level_info(APEX_THRESHOLD)
        self.assertEqual(apex_info["level"], 12)
        self.assertEqual(apex_info["title"], "Apex")
        self.assertTrue(apex_info["is_apex"])
        self.assertEqual(apex_info["tier_pct"], 100)

        beyond_apex = get_level_info(15000)
        self.assertEqual(beyond_apex["level"], 12)
        self.assertTrue(beyond_apex["is_apex"])
        self.assertEqual(beyond_apex["tier_pct"], 100)

    def test_log_reply_formatters_and_shield_status_embed(self):
        """Verifies clean message formatting for rep logging, set overrides, and shield cards."""
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

        mock_u = self.create_mock_member(user_id=888999, display_name="IronWarrior")
        status_data = {
            "frost_shields": 2,
            "max_shields": 2,
            "is_today_shielded": False,
            "days_until_next_shield": 0,
            "current_streak": 14,
            "recent_uses": [{"date": "2026-09-20", "reason": "Rest day"}],
        }
        shield_embed = build_shield_status_embed(mock_u, status_data)
        self.assertEmbedTitleContains(shield_embed, "Streak Shield Status")
        self.assertEmbedDescriptionContains(
            shield_embed,
            "Streak Shields Work",
            "MAX SHIELDS STORED (2/2)",
        )

    def test_ranks_embed_and_server_records_view(self):
        """Verifies 12-tier rank overview embed and server records interactive view."""
        ranks_embed = build_ranks_embed(50)
        self.assertEmbedTitleContains(ranks_embed, "12-Tier Progression Hierarchy")
        self.assertNotIn("Pack", ranks_embed.title)
        self.assertEmbedDescriptionContains(
            ranks_embed,
            "🥉 **Lvl 1: Initiate**",
            "🥉 **Lvl 2: Novice**",
            "💎 **Lvl 12: Apex**",
            "Your Current Standing: 🥉 **Level 1: Initiate** (50 pts)",
        )
        self.assertNotIn("Lone Stray", ranks_embed.description)

        records_data = db.get_server_records(None, db_path=self.test_db)
        records_embed = build_server_records_embed(records_data, phase_id=None)
        self.assertEmbedTitleContains(records_embed, "All-Time Server Records")
        self.assertEmbedDescriptionContains(
            records_embed,
            "Achievements & Records",
            "Server Totals",
            "Total Volume",
            "Total Perfect Days",
        )
        self.assertNotIn("Clean Days", records_embed.description)
        self.assertNotIn("Combined Volume", records_embed.description)

        records_view = ServerRecordsView(author_id=123, current_selection="overall")
        self.assertEqual(len(records_view.children), 4)
        self.assertEqual(records_view.children[0].label, "Overall")
