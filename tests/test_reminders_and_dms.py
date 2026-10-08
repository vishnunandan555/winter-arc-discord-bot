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

    def test_reminders_view_and_interactive_toggles(self):
        """Verifies RemindersView button callbacks, UI states, and aliases."""
        self.assertIs(SettingsView, RemindersView)

        settings = db.get_user_dm_settings(self.user_id, db_path=self.test_db)
        view = RemindersView(user_id=self.user_id, settings=settings)

        # Verify initial buttons: Master, Morning, Afternoon, Evening
        btn_ids = [c.custom_id for c in view.children]
        self.assertIn("toggle_master", btn_ids)
        self.assertIn("toggle_morning", btn_ids)
        self.assertIn("toggle_afternoon", btn_ids)
        self.assertIn("toggle_evening", btn_ids)

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
