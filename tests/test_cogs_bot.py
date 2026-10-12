"""
tests/test_cogs_bot.py - Test Suite for Bot Lifecycle, Cogs Loading, Singletons, and Error Handling
"""
import os
import asyncio
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import MagicMock, AsyncMock
import discord
from discord import app_commands

import database as db
from tests.base import WinterArcTestCase


class TestBotLifecycleAndSlashCommands(WinterArcTestCase):
    """Verifies bot lifecycle, extension loading, 25 slash commands tree registration, and system health metrics."""

    def test_all_extensions_and_slash_commands_load(self):
        """Verify cogs.admin and cogs.warrior load cleanly and register all 25 slash commands."""
        from bot import WinterArcBot

        async def verify_bot_cogs():
            bot = WinterArcBot()
            await bot.load_extension("cogs.admin")
            await bot.load_extension("cogs.warrior")
            commands = bot.tree.get_commands()
            cmd_names = {c.name for c in commands}

            expected_cmds = {
                "admin", "accuse", "calendar", "enroll", "grind", "help", "history",
                "leaderboard", "leave_arc", "log", "nuke", "nuke_day", "ping", "profile", "quick",
                "ranks", "recap", "reminders", "set", "settings", "shield", "stats", "streak",
                "tasks", "test_reminder", "today", "tips"
            }
            self.assertTrue(expected_cmds.issubset(cmd_names), f"Missing commands: {expected_cmds - cmd_names}")
            self.assertEqual(len(commands), len(expected_cmds))

            admin_cmd = next(c for c in commands if c.name == "admin")
            subcmd_names = {sc.name for sc in admin_cmd.commands}
            self.assertIn("sync", subcmd_names)
            self.assertIn("grind", subcmd_names)
            self.assertIn("backup", subcmd_names)
            self.assertIn("tips", subcmd_names)
            self.assertIn("nuke_day", subcmd_names)

        asyncio.run(verify_bot_cogs())

    def test_memory_management_singletons_and_health_metrics(self):
        """Verifies AI client singleton reuse and Wispbyte free tier health metrics."""
        from ai.groq_service import get_groq_client
        from ai.reasoning_service import get_openrouter_candidate_models
        from cogs.admin import get_system_health_metrics, build_health_embed

        # OpenRouter fallback list verification
        cands = get_openrouter_candidate_models()
        self.assertTrue(len(cands) >= 1)

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
        self.assertIn("VisiHost", embed.description)


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

    def test_admin_dm_command_and_templates(self):
        """Verifies dm_target_autocomplete, dm_template_autocomplete, and /admin dm command execution."""
        from helpers import dm_target_autocomplete, dm_template_autocomplete
        from dm_templates import DM_TEMPLATES, build_message_from_template
        from cogs.admin import AdminCog

        # 1. Autocompletes
        mock_inter = self.create_mock_interaction(user_id=99999)
        mock_guild = MagicMock()
        mock_guild.id = 123456789
        mock_m1 = MagicMock(id=111, display_name="Spartan", name="spartan", bot=False)
        mock_m2 = MagicMock(id=222, display_name="Valkyrie", name="valkyrie", bot=False)
        mock_bot_user = MagicMock(id=333, display_name="SomeBot", name="somebot", bot=True)
        mock_guild.members = [mock_m1, mock_m2, mock_bot_user]
        mock_guild.get_member.side_effect = lambda uid: mock_m1 if uid == 111 else (mock_m2 if uid == 222 else None)
        mock_inter.guild = mock_guild

        # Target autocomplete returns "all" and non-bot members
        choices_all = asyncio.run(dm_target_autocomplete(mock_inter, ""))
        choice_values = [c.value for c in choices_all]
        self.assertIn("all", choice_values)
        self.assertIn("111", choice_values)
        self.assertIn("222", choice_values)
        self.assertNotIn("333", choice_values)

        # Template autocomplete
        tmpl_choices = asyncio.run(dm_template_autocomplete(mock_inter, ""))
        tmpl_keys = [c.value for c in tmpl_choices]
        self.assertIn("launch_invite", tmpl_keys)
        self.assertIn("custom_message_1", tmpl_keys)

        # 2. Template builder
        embed = build_message_from_template("launch_invite", "Spartan", 1554843200814845952)
        self.assertIn("Winter Arc 2026 // Kicking Off Tomorrow (Oct 1)", embed.title)
        self.assertIn("Hi **Spartan**", embed.description)

        embed_c1 = build_message_from_template("custom_message_1", "Spartan", 1554843200814845952, extra_text="Be on time!")
        self.assertIn("Be on time!", embed_c1.description)

        # 3. Test /admin dm command for single and multiple members
        async def run_admin_dm_test():
            bot = MagicMock()
            cog = AdminCog(bot)
            mock_m1.send = AsyncMock()
            mock_m2.send = AsyncMock()

            # Target by single user ID
            await cast(Any, cog.admin_dm.callback)(cog, mock_inter, target="111", message="launch_invite")
            mock_m1.send.assert_called_once()
            call_embed = mock_m1.send.call_args[1]["embed"]
            self.assertIn("Hi **Spartan**", call_embed.description)
            self.assertEqual(mock_m1.send.call_args[1].get("content"), mock_m1.mention)
            self.assertTrue(mock_m1.send.call_args[1].get("allowed_mentions").users)
            mock_inter.followup.send.assert_called()

            # Target multiple members at once
            mock_m1.send.reset_mock()
            mock_m2.send.reset_mock()
            await cast(Any, cog.admin_dm.callback)(cog, mock_inter, target="111, 222", message="custom_message_1")
            mock_m1.send.assert_called_once()
            mock_m2.send.assert_called_once()

        asyncio.run(run_admin_dm_test())

        # 4. Test multi-select comma autocomplete
        multi_choices = asyncio.run(dm_target_autocomplete(mock_inter, "111, "))
        multi_vals = [c.value for c in multi_choices]
        self.assertTrue(any("111, 222" in v for v in multi_vals))

    def test_nuke_command_and_confirmation_view(self):
        """Verifies owner-only permission guard, confirmation view, and channel purge on /nuke."""
        from cogs.admin import AdminCog
        from ui.views import NukeConfirmView

        bot = MagicMock()
        cog = AdminCog(bot)

        # 1. Non-owner invocation rejected
        inter_non_owner = self.create_mock_interaction(user_id=12345)
        mock_guild = MagicMock()
        mock_guild.owner_id = 99999
        inter_non_owner.guild = mock_guild

        async def run_non_owner_test():
            await cog.nuke.callback(cog, inter_non_owner)
            inter_non_owner.response.send_message.assert_called_once()
            self.assertIn("Only the **Server Owner**", inter_non_owner.response.send_message.call_args[0][0])

        asyncio.run(run_non_owner_test())

        # 2. Owner invocation prompts confirmation
        inter_owner = self.create_mock_interaction(user_id=99999)
        inter_owner.guild = mock_guild
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.mention = "#test-channel"
        mock_channel.purge = AsyncMock()
        mock_channel.send = AsyncMock()
        mock_channel.permissions_for.return_value.manage_messages = True
        inter_owner.channel = mock_channel

        async def run_owner_prompt_test():
            await cog.nuke.callback(cog, inter_owner)
            inter_owner.response.send_message.assert_called_once()
            call_kwargs = inter_owner.response.send_message.call_args[1]
            self.assertIn("view", call_kwargs)
            self.assertIsInstance(call_kwargs["view"], NukeConfirmView)

        asyncio.run(run_owner_prompt_test())

        # 3. Confirm button opens 2FA Modal
        from ui.views import Nuke2FAModal
        view = NukeConfirmView(owner_id=99999)
        button_confirm = [b for b in view.children if getattr(b, "custom_id", "") == "btn_confirm_nuke"][0]

        async def run_modal_open_test():
            inter_btn = self.create_mock_interaction(user_id=99999)
            inter_btn.channel = mock_channel
            inter_btn.response.send_modal = AsyncMock()
            await button_confirm.callback(inter_btn)
            inter_btn.response.send_modal.assert_called_once()
            modal = inter_btn.response.send_modal.call_args[0][0]
            self.assertIsInstance(modal, Nuke2FAModal)

        asyncio.run(run_modal_open_test())

        # 4. Wrong 2FA answer rejects
        modal = Nuke2FAModal(channel=mock_channel)
        modal.answer_input._value = "wrong_dog_name"

        async def run_wrong_2fa_test():
            inter_modal = self.create_mock_interaction(user_id=99999)
            await modal.on_submit(inter_modal)
            inter_modal.response.send_message.assert_called_once()
            self.assertIn("2FA Verification Failed", inter_modal.response.send_message.call_args[0][0])
            mock_channel.purge.assert_not_called()

        asyncio.run(run_wrong_2fa_test())

        # 5. Correct 2FA answer ("jackie") purges channel and sends nuke gif
        modal_correct = Nuke2FAModal(channel=mock_channel)
        modal_correct.answer_input._value = "jackie"

        async def run_correct_2fa_test():
            inter_modal_ok = self.create_mock_interaction(user_id=99999)
            await modal_correct.on_submit(inter_modal_ok)
            mock_channel.purge.assert_called_once_with(limit=None)
            mock_channel.send.assert_called_once()
            send_kwargs = mock_channel.send.call_args[1]
            sent_content = send_kwargs.get("content", "")
            self.assertIn("NUKED!", sent_content)
            self.assertNotIn("http", sent_content)
            self.assertIn("embed", send_kwargs)
            self.assertIn("media.tenor.com", send_kwargs["embed"].image.url)

        asyncio.run(run_correct_2fa_test())

        # 6. Verify post-nuke rotation between the 3 GIFs
        from ui.views import get_next_nuke_gif, POST_NUKE_GIFS
        self.assertEqual(len(POST_NUKE_GIFS), 3)
        g1 = get_next_nuke_gif()
        g2 = get_next_nuke_gif()
        g3 = get_next_nuke_gif()
        self.assertEqual(len({g1, g2, g3}), 3)

    def test_admin_backup_command(self):
        """Verifies /admin backup creates a consistent database snapshot and delivers discord.File attachment."""
        from cogs.admin import AdminCog

        cog = AdminCog(bot=MagicMock())
        inter = self.create_mock_interaction(user_id=123456)
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        async def run_backup():
            await cog.admin_backup.callback(cog, inter)
            inter.response.defer.assert_called_once_with(ephemeral=True)
            inter.followup.send.assert_called_once()
            call_kwargs = inter.followup.send.call_args[1]
            self.assertIn("embed", call_kwargs)
            self.assertIn("file", call_kwargs)
            file_obj = call_kwargs["file"]
            self.assertIsInstance(file_obj, discord.File)
            self.assertTrue(file_obj.filename.startswith("winter_arc_backup_"))
            self.assertTrue(file_obj.filename.endswith(".db"))

        asyncio.run(run_backup())

    def test_nuke_day_command_and_2fa_workflow(self):
        """Verifies owner/admin permission guards, confirmation view, and 2FA modal workflow for /nuke_day."""
        from cogs.admin import AdminCog
        from ui.views import NukeDayConfirmView, NukeDay2FAModal

        bot = MagicMock()
        cog = AdminCog(bot)
        target_date = "2026-10-11"

        # 1. Non-admin and non-owner invocation rejected
        inter_unauth = self.create_mock_interaction(user_id=12345)
        mock_guild = MagicMock()
        mock_guild.owner_id = 99999
        inter_unauth.guild = mock_guild
        inter_unauth.user.guild_permissions.administrator = False

        async def run_unauth_test():
            await cog.nuke_day.callback(cog, inter_unauth, target_date)
            inter_unauth.response.send_message.assert_called_once()
            self.assertIn("Permission Denied", inter_unauth.response.send_message.call_args[0][0])

        asyncio.run(run_unauth_test())

        # 2. Owner invocation prompts confirmation view
        inter_owner = self.create_mock_interaction(user_id=99999)
        inter_owner.guild = mock_guild
        inter_owner.user.guild_permissions.administrator = True

        async def run_owner_prompt_test():
            await cog.nuke_day.callback(cog, inter_owner, target_date)
            inter_owner.response.send_message.assert_called_once()
            call_kwargs = inter_owner.response.send_message.call_args[1]
            self.assertIn("view", call_kwargs)
            self.assertIsInstance(call_kwargs["view"], NukeDayConfirmView)

        asyncio.run(run_owner_prompt_test())

        # 3. Confirm button opens NukeDay2FAModal
        view = NukeDayConfirmView(owner_id=99999, target_date=target_date)
        btn_confirm = [b for b in view.children if getattr(b, "custom_id", "") == "btn_confirm_nuke_day"][0]

        async def run_modal_open_test():
            inter_btn = self.create_mock_interaction(user_id=99999)
            inter_btn.response.send_modal = AsyncMock()
            await btn_confirm.callback(inter_btn)
            inter_btn.response.send_modal.assert_called_once()
            modal = inter_btn.response.send_modal.call_args[0][0]
            self.assertIsInstance(modal, NukeDay2FAModal)
            self.assertEqual(modal.target_date, target_date)

        asyncio.run(run_modal_open_test())

        # 4. Incorrect 2FA answer rejected
        modal_bad = NukeDay2FAModal(target_date=target_date)
        modal_bad.answer_input._value = "wrong_pass"
        inter_modal_bad = self.create_mock_interaction(user_id=99999)

        async def run_wrong_2fa_test():
            await modal_bad.on_submit(inter_modal_bad)
            inter_modal_bad.response.send_message.assert_called_once()
            self.assertIn("2FA Verification Failed", inter_modal_bad.response.send_message.call_args[0][0])

        asyncio.run(run_wrong_2fa_test())

        # 5. Correct 2FA answer purges day and delivers success embed
        modal_ok = NukeDay2FAModal(target_date=target_date)
        modal_ok.answer_input._value = "jackie"
        inter_modal_ok = self.create_mock_interaction(user_id=99999)
        inter_modal_ok.response.defer = AsyncMock()
        inter_modal_ok.followup = MagicMock()
        inter_modal_ok.followup.send = AsyncMock()

        async def run_correct_2fa_test():
            await modal_ok.on_submit(inter_modal_ok)
            inter_modal_ok.response.defer.assert_called_once_with(ephemeral=True)
            inter_modal_ok.followup.send.assert_called_once()
            call_kwargs = inter_modal_ok.followup.send.call_args[1]
            self.assertIn("embed", call_kwargs)
            embed = call_kwargs["embed"]
            self.assertIn("DAY NUKED", embed.title)

        asyncio.run(run_correct_2fa_test())

    def test_today_and_tasks_commands_embed_generation(self):
        """Verifies /today and /tasks commands successfully construct embeds and send followups without NameError."""
        from unittest.mock import patch
        from cogs.warrior import WarriorCog
        import database as db

        bot = MagicMock()
        cog = WarriorCog(bot)

        uid = 555666
        db.enroll_user(uid, "TestWarrior", db_path=self.test_db)

        # 1. Test /today
        inter_today = self.create_mock_interaction(user_id=uid, display_name="TestWarrior")
        inter_today.guild = None

        with patch("database.DB_PATH", self.test_db), \
             patch("cogs.warrior.safe_react", new_callable=AsyncMock), \
             patch("cogs.warrior.dispatch_tip", new_callable=AsyncMock), \
             patch("ai.groq_service.dispatch_interaction_nudge", new_callable=AsyncMock):
            asyncio.run(cog.today.callback(cog, inter_today))
            inter_today.followup.send.assert_called_once()
            kwargs = inter_today.followup.send.call_args.kwargs
            self.assertIn("embed", kwargs)
            self.assertIsInstance(kwargs["embed"], discord.Embed)

        # 2. Test /tasks
        inter_tasks = self.create_mock_interaction(user_id=uid, display_name="TestWarrior")
        inter_tasks.guild = None

        with patch("database.DB_PATH", self.test_db), \
             patch("cogs.warrior.safe_react", new_callable=AsyncMock), \
             patch("cogs.warrior.dispatch_tip", new_callable=AsyncMock), \
             patch("ai.groq_service.dispatch_interaction_nudge", new_callable=AsyncMock):
            asyncio.run(cog.tasks_cmd.callback(cog, inter_tasks))
            inter_tasks.followup.send.assert_called_once()
            kwargs = inter_tasks.followup.send.call_args.kwargs
            self.assertIn("embed", kwargs)
            self.assertIsInstance(kwargs["embed"], discord.Embed)



