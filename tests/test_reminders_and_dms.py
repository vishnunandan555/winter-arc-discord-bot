"""
tests/test_reminders_and_dms.py - Comprehensive Unit and Integration Tests
for the Personal Reminders Subsystem, Personalized AI Morning Briefing,
Afternoon Progress Check, Evening Streak Alert, and Silent Daily Broadcasts.
"""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

import discord
import database as db
from config import BOT_TZ
from scheduler import WinterArcScheduler
from tests.base import WinterArcTestCase
from ui.embeds import (
    build_dm_morning_message,
    build_dm_afternoon_message,
    build_dm_evening_message,
    build_settings_embed,
)
from ui.views import RemindersView, SettingsView
from ai.gemini_service import generate_personalized_morning_briefing


class TestRemindersAndDMs(WinterArcTestCase):
    """Verifies personal reminder toggles, AI personalized briefings, and silent broadcasts."""

    def setUp(self):
        super().setUp()
        self.user_id = 770011
        db.enroll_user(self.user_id, "TestSpartan", db_path=self.test_db)
        db.enroll_user(self.user_id, "TestSpartan", db_path=db.DB_PATH)

    def test_user_dm_settings_database_crud(self):
        """Verifies dm_afternoon column migration, default states, updates, and category queries."""
        settings = db.get_user_dm_settings(self.user_id, db_path=self.test_db)
        # By default dm_reminders is False until opted in, but channels are True
        self.assertTrue(settings["dm_morning"])
        self.assertTrue(settings["dm_afternoon"])
        self.assertTrue(settings["dm_evening"])

        # Enable master switch and toggle afternoon off
        db.update_user_dm_settings(self.user_id, dm_reminders=True, dm_afternoon=False, db_path=self.test_db)
        updated = db.get_user_dm_settings(self.user_id, db_path=self.test_db)
        self.assertTrue(updated["dm_reminders"])
        self.assertFalse(updated["dm_afternoon"])
        self.assertTrue(updated["dm_morning"])
        self.assertTrue(updated["dm_evening"])

        # Opted-in lists
        afternoon_users = db.get_opted_in_dm_users("afternoon", db_path=self.test_db)
        self.assertNotIn(self.user_id, [u["discord_id"] for u in afternoon_users])

        morning_users = db.get_opted_in_dm_users("morning", db_path=self.test_db)
        self.assertIn(self.user_id, [u["discord_id"] for u in morning_users])

        # Disable master toggle
        db.update_user_dm_settings(self.user_id, dm_reminders=False, db_path=self.test_db)
        morning_users_after_master_off = db.get_opted_in_dm_users("morning", db_path=self.test_db)
        self.assertNotIn(self.user_id, [u["discord_id"] for u in morning_users_after_master_off])

    def test_dm_coalesce_null_handling(self):
        """Verifies that users with NULL dm_* values in SQLite default to opted-in (COALESCE(dm_*, 1) = 1)."""
        null_user_id = 880022
        import sqlite3
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        c.execute(
            """INSERT OR REPLACE INTO users (discord_id, username, enrolled, dm_reminders, dm_morning, dm_afternoon, dm_evening)
               VALUES (?, ?, 1, 1, NULL, NULL, NULL)""",
            (null_user_id, "NullWarrior")
        )
        conn.commit()
        conn.close()

        # All 3 categories should include this user because COALESCE(NULL, 1) = 1
        for cat in ["morning", "afternoon", "evening"]:
            users = db.get_opted_in_dm_users(cat, db_path=self.test_db)
            u_ids = [u["discord_id"] for u in users]
            self.assertIn(null_user_id, u_ids, f"User with NULL {cat} should be treated as opted-in via COALESCE")

        # In Python dict lookup, settings should also be True
        settings = db.get_user_dm_settings(null_user_id, db_path=self.test_db)
        self.assertTrue(settings["dm_morning"])
        self.assertTrue(settings["dm_afternoon"])
        self.assertTrue(settings["dm_evening"])

    def test_weekly_briefing_context_and_morning_briefing(self):
        """Verifies 7-day momentum aggregation and personalized morning briefing generator."""
        now = datetime.now(BOT_TZ)
        # Log tasks for past 3 days
        for i in range(1, 4):
            day_str = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            db.log_activity(self.user_id, "TestSpartan", "Push-ups", 60.0, log_date=day_str, db_path=self.test_db)

        # Record a grind entry
        yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        db.record_grind_entry(
            discord_id=self.user_id,
            date_str=yesterday_str,
            raw_input="45 min heavy deadlifts and clean diet",
            verdict="ACCEPTED",
            points=40,
            key_learning="Consistency under load",
            commentary="Iron will.",
            db_path=self.test_db
        )

        context = db.get_user_weekly_briefing_context(self.user_id, db_path=self.test_db)
        self.assertEqual(context["discord_id"], self.user_id)
        self.assertGreater(context["total_pts_7d"], 0)
        self.assertTrue(any("Push-ups" in d for d in context["top_disciplines"]))
        self.assertEqual(len(context["recent_grinds"]), 1)

        # Test briefing generation with mocked Gemini response
        mock_briefing = "You dominated heavy pulls yesterday. Keep this unbroken standard into day 4."
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = mock_briefing
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)
        with patch("ai.gemini_service.get_gemini_client", return_value=mock_client):
            briefing = asyncio.run(generate_personalized_morning_briefing(context))
            self.assertEqual(briefing, mock_briefing)

        # Test fallback when API client is not configured
        with patch("ai.gemini_service.get_gemini_client", return_value=None):
            fallback_briefing = asyncio.run(generate_personalized_morning_briefing(context))
            self.assertTrue(len(fallback_briefing) > 10)

        # Test build_dm_morning_message
        active_tasks = db.get_active_tasks(db_path=self.test_db)
        msg = build_dm_morning_message(
            tasks=active_tasks,
            streak=5,
            date_display=now.strftime("%A, %B %d, %Y"),
            quote=mock_briefing
        )
        self.assertIn("🌅 **Winter Arc — Morning Briefing", msg)
        self.assertIn(mock_briefing, msg)
        self.assertIn("5 days", msg)
        self.assertIn("/log", msg)

    def test_afternoon_and_evening_clean_dm_messages(self):
        """Verifies clean, non-embed message formatting for Afternoon and Evening DMs."""
        # Afternoon DM (10 points logged, needs 20 more for streak min)
        afternoon_msg = build_dm_afternoon_message(
            user_name="Spartan",
            points=10,
            max_points=500,
            streak=4
        )
        self.assertIn("☀️ **Winter Arc — Afternoon Check-in", afternoon_msg)
        self.assertIn("10 / 500 pts", afternoon_msg)
        self.assertIn("20 more points", afternoon_msg)
        self.assertIn("/log", afternoon_msg)

        # Afternoon DM (completed daily minimum)
        afternoon_done_msg = build_dm_afternoon_message(
            user_name="Spartan",
            points=45,
            max_points=500,
            streak=4
        )
        self.assertIn("Streak is already secured", afternoon_done_msg)
        self.assertIn("455 points", afternoon_done_msg)

        # Evening DM (warning when below minimum)
        evening_msg = build_dm_evening_message(
            user_name="Spartan",
            points=15,
            max_points=500,
            streak=7,
            shields=1
        )
        self.assertIn("🌙 **Winter Arc — 3 Hours Until Midnight Rollover!**", evening_msg)
        self.assertIn("15 pts missing", evening_msg)
        self.assertIn("1 / 2", evening_msg)

        # Evening DM (streak already defended)
        evening_safe_msg = build_dm_evening_message(
            user_name="Spartan",
            points=50,
            max_points=500,
            streak=7,
            shields=2
        )
        self.assertIn("safely secured", evening_safe_msg)

        # DMs with explicit user_mention pings
        ping_morning = build_dm_morning_message(
            tasks=db.get_active_tasks(db_path=self.test_db),
            streak=3,
            date_display="Today",
            quote="Rise",
            user_mention="<@770011>"
        )
        self.assertTrue(ping_morning.startswith("<@770011>\n"))

        ping_afternoon = build_dm_afternoon_message(
            user_name="Spartan",
            points=20,
            max_points=500,
            streak=3,
            user_mention="<@770011>"
        )
        self.assertIn("<@770011>, you have logged", ping_afternoon)

        ping_evening = build_dm_evening_message(
            user_name="Spartan",
            points=20,
            max_points=500,
            streak=3,
            shields=1,
            user_mention="<@770011>"
        )
        self.assertIn("<@770011>, scores finalize", ping_evening)

    def test_reminders_view_and_interactive_toggles(self):
        """Verifies RemindersView button callbacks, UI states, and aliases."""
        self.assertIs(SettingsView, RemindersView)

        settings = db.get_user_dm_settings(self.user_id, db_path=self.test_db)
        view = RemindersView(user_id=self.user_id, settings=settings)

        # Verify initial buttons: Morning, Afternoon, Evening
        btn_ids = [c.custom_id for c in view.children]
        self.assertNotIn("toggle_master", btn_ids)
        self.assertIn("toggle_morning", btn_ids)
        self.assertIn("toggle_afternoon", btn_ids)
        self.assertIn("toggle_evening", btn_ids)
        self.assertEqual(len(btn_ids), 3)

        # Toggle Afternoon off via button callback
        inter = self.create_mock_interaction(user_id=self.user_id)
        afternoon_btn = next(c for c in view.children if c.custom_id == "toggle_afternoon")

        with patch.object(db, "update_user_dm_settings") as mock_update:
            asyncio.run(afternoon_btn.callback(inter))
            mock_update.assert_called_once_with(self.user_id, dm_afternoon=False)
            inter.response.edit_message.assert_called_once()

        # Check unauthorized user attempting to click
        intruder_inter = self.create_mock_interaction(user_id=999999)
        asyncio.run(afternoon_btn.callback(intruder_inter))
        intruder_inter.response.send_message.assert_called_once()
        self.assertIn("another member", str(intruder_inter.response.send_message.call_args))

    def test_silent_daily_broadcasts_no_role_pings(self):
        """Verifies that none of the 4 routine daily channel broadcasts ping the @Winter Arc role."""
        mock_bot = MagicMock()
        mock_channel = self.create_mock_channel(8888)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 999111
        mock_bot.guilds = [mock_guild]

        scheduler = WinterArcScheduler(mock_bot, db_path=self.test_db)
        # Mock _get_target_channel_and_ping to return channel and a role ping
        with patch.object(scheduler, "_get_target_channel_and_ping", return_value=(mock_channel, "<@&999888>")):
            with patch("ai.gemini_service.generate_reminder_motivation", return_value="Keep the standard high."):
                with patch("ai.gemini_service.generate_evening_alert_data", return_value=([], "Endure.")):
                    with patch("ai.gemini_service.generate_daily_toast_and_roast", return_value="Great work today."):
                        # 1. Morning Kickoff
                        asyncio.run(scheduler.broadcast_morning_kickoff())
                        self.assertTrue(mock_channel.send.called)
                        sent_content = mock_channel.send.call_args.kwargs.get("content", "")
                        self.assertNotIn("<@&999888>", sent_content)
                        mock_channel.send.reset_mock()

                        # 2. Afternoon Checkin
                        asyncio.run(scheduler.broadcast_afternoon_checkin())
                        self.assertTrue(mock_channel.send.called)
                        sent_content = mock_channel.send.call_args.kwargs.get("content", "")
                        self.assertNotIn("<@&999888>", sent_content)
                        mock_channel.send.reset_mock()

                        # 3. Evening Checkin
                        asyncio.run(scheduler.broadcast_evening_checkin())
                        self.assertTrue(mock_channel.send.called)
                        sent_content = mock_channel.send.call_args.kwargs.get("content", "")
                        self.assertNotIn("<@&999888>", sent_content)
                        mock_channel.send.reset_mock()

                        # 4. Midnight Finalization
                        asyncio.run(scheduler.broadcast_midnight_finalization())
                        self.assertTrue(mock_channel.send.called)
                        sent_content = mock_channel.send.call_args.kwargs.get("content", "")
                        self.assertNotIn("<@&999888>", sent_content)

    def test_scheduler_dm_dispatch_edge_cases(self):
        """Verifies individual DM dispatch error resilience, closed DMs, and missing user handling."""
        mock_bot = MagicMock()
        mock_discord_user = MagicMock(spec=discord.User)
        mock_discord_user.send = AsyncMock()
        mock_discord_user.display_name = "TestSpartan"
        mock_bot.get_user.return_value = mock_discord_user

        scheduler = WinterArcScheduler(mock_bot, db_path=self.test_db)
        today_str = datetime.now(BOT_TZ).strftime("%Y-%m-%d")
        user_record = {"discord_id": self.user_id, "username": "TestSpartan"}
        active_tasks = db.get_active_tasks(db_path=self.test_db)

        # 1. Successful DM dispatches
        with patch("ai.gemini_service.generate_personalized_morning_briefing", return_value="Rise and grind."):
            res_m = asyncio.run(scheduler._send_single_morning_dm(user_record, active_tasks, today_str, "Today"))
            self.assertTrue(res_m)
            self.assertTrue(mock_discord_user.send.called)

        res_a = asyncio.run(scheduler._send_single_afternoon_dm(user_record, today_str))
        self.assertTrue(res_a)

        with patch("ai.gemini_service.generate_reminder_motivation", return_value="Defend the streak."):
            res_e = asyncio.run(scheduler._send_single_evening_dm(user_record, today_str))
            self.assertTrue(res_e)

        # 2. Closed DMs (discord.Forbidden)
        mock_discord_user.send.side_effect = discord.Forbidden(MagicMock(), "Cannot send messages to this user")
        with patch("ai.gemini_service.generate_personalized_morning_briefing", return_value="Rise and grind."):
            res_m_forbidden = asyncio.run(scheduler._send_single_morning_dm(user_record, active_tasks, today_str, "Today"))
        self.assertFalse(res_m_forbidden)

        res_a_forbidden = asyncio.run(scheduler._send_single_afternoon_dm(user_record, today_str))
        self.assertFalse(res_a_forbidden)

        with patch("ai.gemini_service.generate_reminder_motivation", return_value="Defend the streak."):
            res_e_forbidden = asyncio.run(scheduler._send_single_evening_dm(user_record, today_str))
            self.assertFalse(res_e_forbidden)

        # 3. Missing user (get_user and fetch_user return None)
        mock_bot.get_user.return_value = None
        mock_bot.fetch_user = AsyncMock(return_value=None)
        res_missing = asyncio.run(scheduler._send_single_afternoon_dm(user_record, today_str))
        self.assertFalse(res_missing)

    def test_reminders_slash_command_and_quick_parameter(self):
        """Verifies /reminders command invocation, quick dms toggle argument, and un-enrolled guard."""
        from cogs.warrior import WarriorCog
        mock_bot = MagicMock()
        cog = WarriorCog(mock_bot)

        # 1. Quick toggle dms=False
        inter = self.create_mock_interaction(user_id=self.user_id)
        asyncio.run(cog.reminders_cmd.callback(cog, inter, dms=False))
        inter.response.send_message.assert_called_once()
        s = db.get_user_dm_settings(self.user_id, db_path=db.DB_PATH)
        self.assertFalse(s["dm_reminders"])

        # 2. Quick toggle dms=True
        inter_on = self.create_mock_interaction(user_id=self.user_id)
        asyncio.run(cog.reminders_cmd.callback(cog, inter_on, dms=True))
        s_on = db.get_user_dm_settings(self.user_id, db_path=db.DB_PATH)
        self.assertTrue(s_on["dm_reminders"])

        # 3. Un-enrolled user rejected
        inter_stranger = self.create_mock_interaction(user_id=999888)
        asyncio.run(cog.reminders_cmd.callback(cog, inter_stranger))
        inter_stranger.response.send_message.assert_called_once()
        sent_embed = inter_stranger.response.send_message.call_args.kwargs.get("embed")
        self.assertIn("Not Enrolled", sent_embed.title)

    def test_test_reminder_admin_command_options(self):
        """Verifies /test_reminder admin command for morning_dm, afternoon_dm, and evening_dm previews."""
        from cogs.admin import AdminCog
        mock_bot = MagicMock()
        scheduler = WinterArcScheduler(mock_bot, db_path=self.test_db)
        mock_bot.scheduler = scheduler
        cog = AdminCog(mock_bot)

        inter = self.create_mock_interaction(user_id=self.user_id)
        inter.user.send = AsyncMock()

        # Morning DM preview
        with patch("ai.gemini_service.generate_personalized_morning_briefing", return_value="Test morning reflection."):
            asyncio.run(cog.test_reminder.callback(cog, inter, reminder_type="morning_dm"))
            self.assertTrue(inter.user.send.called)
            inter.followup.send.assert_called()

        # Afternoon DM preview
        inter.user.send.reset_mock()
        inter.followup.send.reset_mock()
        asyncio.run(cog.test_reminder.callback(cog, inter, reminder_type="afternoon_dm"))
        self.assertTrue(inter.user.send.called)
        inter.followup.send.assert_called()

        # Evening DM preview
        inter.user.send.reset_mock()
        inter.followup.send.reset_mock()
        with patch("ai.gemini_service.generate_reminder_motivation", return_value="Test evening alert."):
            asyncio.run(cog.test_reminder.callback(cog, inter, reminder_type="evening_dm"))
            self.assertTrue(inter.user.send.called)
            inter.followup.send.assert_called()

    def test_weekly_recap_and_phase_conclusion_broadcast_formatters(self):
        """Verifies exact formatting, headings, volume, streak metrics, and role ping placement."""
        from ui.embeds import build_weekly_recap_message, build_phase_conclusion_message

        # 1. Weekly Recap Message
        weekly_stats = {
            "total_pushups": 1420,
            "total_pullups": 350,
            "total_squats": 1200,
            "total_situps": 800,
            "total_km": 42.5
        }
        top_warriors = [
            {"discord_id": 111, "username": "Spartan", "points": 1500},
            {"discord_id": 222, "username": "Valkyrie", "points": 1350},
            {"discord_id": 333, "username": "Titan", "points": 1100},
            {"discord_id": 444, "username": "Ranger", "points": 950},
            {"discord_id": 555, "username": "Scout", "points": 800},
            {"discord_id": 666, "username": "Ghost", "points": 200},  # 6th should be excluded from top 5
        ]
        recap_msg = build_weekly_recap_message(
            weekly_stats=weekly_stats,
            top_warriors=top_warriors,
            ai_speech="Discipline is the only currency here. Strong week from the vanguard.",
            role_ping="<@&999111>",
            date_dt=datetime(2026, 10, 11, 10, 0, tzinfo=BOT_TZ)
        )
        self.assertIn("### Winter Arc | Weekly Recap", recap_msg)
        self.assertIn("> Discipline is the only currency here", recap_msg)
        self.assertIn("**Weekly Top 5**", recap_msg)
        self.assertIn("**Spartan** — **1,500 pts**", recap_msg)
        self.assertIn("**Scout** — **800 pts**", recap_msg)
        self.assertNotIn("<@111>", recap_msg)
        self.assertNotIn("<@666>", recap_msg)  # Only top 5
        self.assertIn("**Weekly Workout Volume**", recap_msg)
        self.assertIn("`1,420` reps", recap_msg)
        self.assertIn("`42.5` km", recap_msg)
        # Role ping at end before footer
        self.assertIn("<@&999111>", recap_msg)
        self.assertTrue(recap_msg.endswith("-# Sunday, 11th October 2026 | Winter Arc"))

        # 2. Phase Conclusion Message
        phase_dict = {"id": 1, "name": "First Frost", "short_name": "Phase 1"}
        next_phase = {"id": 2, "name": "THE HUNT", "short_name": "Phase 2"}
        phase_lb = [
            {"discord_id": 111, "username": "Spartan", "total_points": 15000, "streak": 31},
            {"discord_id": 222, "username": "Valkyrie", "total_points": 13500, "streak": 28},
            {"discord_id": 333, "username": "Titan", "total_points": 11000, "streak": 25},
            {"discord_id": 444, "username": "Ranger", "total_points": 9500, "streak": 21},
            {"discord_id": 555, "username": "Scout", "total_points": 8000, "streak": 18},
            {"discord_id": 666, "username": "Ghost", "total_points": 1000, "streak": 5},
        ]
        ceremony_speech = "First Frost has separated the committed from the curious."
        conclusion_msg = build_phase_conclusion_message(
            phase_dict=phase_dict,
            phase_lb=phase_lb,
            ceremony_speech=ceremony_speech,
            next_phase_dict=next_phase,
            role_ping="<@&999111>"
        )
        self.assertIn("### Winter Arc | Phase 1 Concluded • First Frost", conclusion_msg)
        self.assertIn("> First Frost has separated the committed", conclusion_msg)
        self.assertIn("**Phase 1 Top Standings**", conclusion_msg)
        self.assertIn("**Spartan** — **15,000 pts** *(31-day streak)*", conclusion_msg)
        self.assertNotIn("<@111>", conclusion_msg)
        self.assertNotIn("<@666>", conclusion_msg)  # Only top 5
        self.assertIn("**Winter Arc Phase 1 Stats:**", conclusion_msg)
        self.assertNotIn("Community", conclusion_msg)  # Word Community removed
        self.assertIn("Longest Active Streak: `31 days`", conclusion_msg)
        self.assertIn("⚔️ **Phase 2: THE HUNT** officially begins today.", conclusion_msg)
        self.assertIn("First Frost was about becoming the person capable of facing winter.", conclusion_msg)
        self.assertIn("<@&999111>", conclusion_msg)
        self.assertTrue(conclusion_msg.endswith("-# Phase 1 archived • Discipline compounds • Winter Arc"))

    def test_sunday_state_of_the_pack_date_window(self):
        """Verifies that Sunday broadcast recaps the completed Sun-Sat week and dispatches correctly."""
        bot = MagicMock()
        mock_guild = MagicMock()
        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()
        mock_guild.text_channels = [mock_channel]
        bot.guilds = [mock_guild]

        sched = WinterArcScheduler(bot, db_path=self.test_db)

        # Mock datetime on a Sunday: Oct 11, 2026 is Sunday
        sunday_dt = datetime(2026, 10, 11, 10, 0, tzinfo=BOT_TZ)

        async def run_sunday_test():
            with patch("scheduler.get_now_ist", return_value=sunday_dt):
                with patch("scheduler.gemini_service.generate_weekly_state_of_the_pack", new=AsyncMock(return_value="Solid week.")):
                    await sched.broadcast_sunday_state_of_the_pack(target_channel=mock_channel, role_ping="<@&999111>")

            mock_channel.send.assert_called()
            sent_content = mock_channel.send.call_args[1].get("content") or mock_channel.send.call_args[0][0]
            self.assertIn("### Winter Arc | Weekly Recap", sent_content)
            self.assertIn("<@&999111>", sent_content)

        asyncio.run(run_sunday_test())



