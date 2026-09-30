"""
tests/test_cogs_bot.py - Test Suite for Bot Lifecycle, Cogs Loading, Singletons, and Error Handling
"""
import os
import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock
import discord
from discord import app_commands

import database as db
from tests.base import WinterArcTestCase


class TestBotLifecycleAndSlashCommands(WinterArcTestCase):
    """Verifies bot lifecycle, extension loading, 21 slash commands tree registration, and system health metrics."""

    def test_all_extensions_and_slash_commands_load(self):
        """Verify cogs.admin and cogs.warrior load cleanly and register all 21 slash commands."""
        from bot import WinterArcBot

        async def verify_bot_cogs():
            bot = WinterArcBot()
            await bot.load_extension("cogs.admin")
            await bot.load_extension("cogs.warrior")
            commands = bot.tree.get_commands()
            cmd_names = {c.name for c in commands}

            expected_cmds = {
                "admin", "enroll", "grind", "help", "history",
                "leaderboard", "leave_arc", "log", "ping", "profile", "quick",
                "ranks", "recap", "set", "settings", "shield", "stats", "streak",
                "tasks", "test_reminder", "today"
            }
            self.assertTrue(expected_cmds.issubset(cmd_names), f"Missing commands: {expected_cmds - cmd_names}")
            self.assertEqual(len(commands), 21)

            admin_cmd = next(c for c in commands if c.name == "admin")
            subcmd_names = {sc.name for sc in admin_cmd.commands}
            self.assertIn("sync", subcmd_names)

        asyncio.run(verify_bot_cogs())

    def test_memory_management_singletons_and_health_metrics(self):
        """Verifies AI client singleton reuse and Wispbyte free tier health metrics."""
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


class TestErrorHandlingAndRobustLogging(WinterArcTestCase):
    """Verifies logging mechanism, RobustView error handling, and cog error responses."""

    def test_robust_view_error_handling(self):
        """Verifies that unhandled view exceptions invoke user-facing error replies."""
        from ui.views import RobustView

        async def test_view_error():
            view = RobustView()
            inter = self.create_mock_interaction(user_id=12345, display_name="TestUser")
            inter.response.is_done.return_value = False

            button = discord.ui.Button(label="Test", custom_id="btn_test")
            await view.on_error(inter, ValueError("Simulated view error"), button)
            inter.response.send_message.assert_called_once()
            self.assertIn("unexpected error occurred", inter.response.send_message.call_args[0][0])

        asyncio.run(test_view_error())

    def test_cog_app_command_cooldown_and_permission_errors(self):
        """Verifies cooldown messages and missing permission notices across cogs."""
        from config import LOG_FILE_PATH, LOG_LEVEL_NAME
        from cogs.warrior import WarriorCog
        from cogs.admin import AdminCog, get_system_health_metrics

        self.assertTrue(bool(LOG_FILE_PATH))
        self.assertTrue(bool(LOG_LEVEL_NAME))

        # Test WarriorCog cog_app_command_error with cooldown
        async def test_warrior_cog_error():
            bot = MagicMock()
            cog = WarriorCog(bot)
            inter = self.create_mock_interaction(user_id=12345, command_name="today")
            inter.response.is_done.return_value = False

            cooldown_err = app_commands.CommandOnCooldown(None, 4.5)
            await cog.cog_app_command_error(inter, cooldown_err)
            inter.response.send_message.assert_called_once()
            self.assertIn("4.5s", inter.response.send_message.call_args[0][0])

        asyncio.run(test_warrior_cog_error())

        # Test AdminCog cog_app_command_error with missing permissions
        async def test_admin_cog_error():
            bot = MagicMock()
            cog = AdminCog(bot)
            inter = self.create_mock_interaction(user_id=12345, command_name="sync")
            inter.response.is_done.return_value = False

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
