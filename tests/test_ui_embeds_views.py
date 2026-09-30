"""
tests/test_ui_embeds_views.py - Test Suite for UI Embeds, Interactive Views, and Message Formatting
"""
import os
import time
import asyncio
from datetime import date, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
import discord

import database as db
from tests.base import WinterArcTestCase


class TestUIEmbedsViews(WinterArcTestCase):
    """Verifies all UI embeds, dropdown views, buttons, message formatters, and help screens."""

    def test_11_autocomplete_providers(self):
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

    def test_23_views_and_embeds(self):
        from ui.views import LeaderboardView
        from ui.embeds import build_monthly_leaderboard_embed, build_weekly_leaderboard_embed

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
        weekly_lb = db.get_weekly_leaderboard(db_path=self.test_db)
        self.assertIsInstance(weekly_lb, list)

        weekly_embed = build_weekly_leaderboard_embed()
        self.assertIn("Weekly Standings", weekly_embed.title)

        # Monthly embed builds successfully
        embed = build_monthly_leaderboard_embed()
        self.assertIn("Standings", embed.title)

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
        for cmd in ["/quick", "/log", "/set", "/grind", "/today", "/tasks", "/streak", "/profile", "/ranks",
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

    def test_30_tasks_embed_and_command(self):
        from ui.embeds import build_tasks_embed
        from cogs.warrior import WarriorCog

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
        from ai import gemini_service
        from ui.embeds import (
            build_morning_kickoff_embed,
            build_afternoon_checkin_embed,
            build_evening_checkin_embed,
            build_dm_morning_embed,
            build_dm_evening_embed,
        )

        # 1. Test generate_reminder_motivation
        quote = asyncio.run(gemini_service.generate_reminder_motivation(reminder_type="morning"))
        self.assertIsInstance(quote, str)
        self.assertTrue(len(quote) > 0)
        self.assertLessEqual(len(quote.split()), 35)

        # 2. Test embeds with quote
        test_quote = "The frost respects only discipline. Step into the cold."
        active_tasks = db.get_active_tasks(self.test_db)

        m_embed = build_morning_kickoff_embed(active_tasks, "Saturday, Sep 19", quote=test_quote)
        self.assertIn("**Daily Focus**:", m_embed.description)
        self.assertIn(test_quote, m_embed.description)

        enrolled = db.get_enrolled_users(self.test_db)
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

    def test_41_stats_and_grind_embed_crash_and_jargon_prevention(self):
        from ui.embeds import build_stats_embed, build_grind_embed, format_num, format_grind_reply
        from helpers import format_num as helper_format_num

        # 1. Test format_num robustness
        for fn in [format_num, helper_format_num]:
            self.assertEqual(fn(50), 50)
            self.assertEqual(fn(50.0), 50)
            self.assertEqual(fn(50.5), 50.5)
            self.assertEqual(fn("42"), 42)
            self.assertEqual(fn(None), 0)

        # 2. Test build_stats_embed with int total_volume
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

    def test_44_cleanup_fixes_and_robustness(self):
        """Verifies no-fallback Gemini error handling, formatted history with grind tags, and retroactive sync."""
        from ai.gemini_service import GeminiServiceError, evaluate_grind
        from ui.embeds import build_history_embed, build_stats_embed, build_profile_embed

        # 1. Verify GeminiServiceError is raised without fake fallback points when unconfigured or failing
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
        db.enroll_user(u_hist, "HistoryWarrior", db_path=self.test_db)
        past_d = db.get_today_date() - timedelta(days=2)
        past_date = past_d.isoformat()
        db.log_activity(u_hist, "HistoryWarrior", "Push-ups", 50, log_date=past_date, db_path=self.test_db)
        db.record_grind_entry(
            discord_id=u_hist,
            date_str=past_date,
            raw_input="Finished dynamic programming problem set",
            verdict="ACCEPTED",
            points=30,
            key_learning="Graph Dynamic Programming",
            commentary="Strong deep work",
            db_path=self.test_db
        )
        hist = db.get_user_history(u_hist, days=7, db_path=self.test_db)
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
        db.set_activity(u_hist, "HistoryWarrior", "Push-ups", 100, log_date=retro_date, db_path=self.test_db)
        with db.get_connection(self.test_db) as conn:
            row = conn.cursor().execute(
                "SELECT points, completion_rate FROM daily_summaries WHERE user_id = (SELECT id FROM users WHERE discord_id = ?) AND date = ?;",
                (u_hist, retro_date)
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["points"], 100)

        # 4. Check stats embed and profile embed footers
        s_embed = build_stats_embed(mock_user, db.get_user_stats(u_hist, self.test_db))
        self.assertNotIn("Winter Arc • Consistency Beats Motivation", s_embed.footer.text)
        p_embed = build_profile_embed(mock_user, db.get_user_by_discord_id(u_hist, self.test_db), 1, db.get_user_stats(u_hist, self.test_db))
        self.assertNotIn("Winter Arc • Consistency Beats Motivation", p_embed.footer.text)

    def test_45_evening_checkin_broadcast_message(self):
        from ui.embeds import build_evening_checkin_message
        from ai.gemini_service import generate_evening_alert_data, AUTHENTIC_STOIC_QUOTES

        warriors = [
            {"discord_id": 1001, "username": "STRANGER", "points": 0, "streak": 3},
            {"discord_id": 1002, "username": "Vikram", "points": 50, "streak": 5},
            {"discord_id": 1003, "username": "Alex", "points": 500, "streak": 12},
        ]

        quote = '"Waste no more time arguing what a good man should be. Be one." — Marcus Aurelius'
        msg = build_evening_checkin_message(
            warriors_data=warriors,
            callouts=None,  # uses default callouts
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
            build_phase_conclusion_message,
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

    def test_48_tips_system_and_command_output_grounding(self):
        import tips
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

    def test_49_help_command_execution_and_comprehensive_validation(self):
        """
        Validates the slash command /help execution lifecycle,
        HelpView interactive dropdown transitions across all 6 categories,
        tip dispatch scheduling, and strict absence of legacy 'Clean Day' text.
        """
        from cogs.warrior import WarriorCog
        from ui.views import HelpView

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
            with patch("cogs.warrior.dispatch_tip", new_callable=AsyncMock):
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


if __name__ == "__main__":
    import unittest
    unittest.main()
