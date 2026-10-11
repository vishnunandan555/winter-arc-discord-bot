"""
tests/test_tips_feature.py - Comprehensive Unit & Integration Tests for Bot Usage Tips
"""

import time
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

import discord
from discord import app_commands

from tests.base import WinterArcTestCase
import database as db
import tips
from cogs.warrior import WarriorCog
from ui.views import TipsView
from ui.embeds import build_tips_embed


class TestTipsFeature(WinterArcTestCase):
    """Verifies tip dispatch guards, database preferences, slash commands, and interactive views."""

    def setUp(self):
        super().setUp()
        tips._last_tip_timestamps.clear()
        tips._user_seen_tips.clear()
        self.user_id = 998877
        self.guild_id = 112233
        db.enroll_user(self.user_id, "TipsWarrior", db_path=self.test_db)

    def test_database_user_and_server_tips_settings(self):
        """Verifies get/set user and server tips preferences in the database."""
        # 1. Defaults to True
        self.assertTrue(db.get_user_tips_enabled(self.user_id, db_path=self.test_db))
        self.assertTrue(db.get_server_tips_enabled(self.guild_id, db_path=self.test_db))

        # 2. Toggle user tips to False
        db.set_user_tips_enabled(self.user_id, False, db_path=self.test_db)
        self.assertFalse(db.get_user_tips_enabled(self.user_id, db_path=self.test_db))

        # 3. Toggle user tips back to True
        db.set_user_tips_enabled(self.user_id, True, db_path=self.test_db)
        self.assertTrue(db.get_user_tips_enabled(self.user_id, db_path=self.test_db))

        # 4. Toggle server tips to False
        db.set_server_tips_enabled(self.guild_id, False, db_path=self.test_db)
        self.assertFalse(db.get_server_tips_enabled(self.guild_id, db_path=self.test_db))

        # 5. Toggle server tips back to True
        db.set_server_tips_enabled(self.guild_id, True, db_path=self.test_db)
        self.assertTrue(db.get_server_tips_enabled(self.guild_id, db_path=self.test_db))

    def test_should_send_tip_respects_preferences(self):
        """Verifies should_send_tip suppresses tips when user or server disabled them."""
        # Setup mocks and db
        with patch("database.DB_PATH", self.test_db):
            # When tips enabled
            db.set_user_tips_enabled(self.user_id, True, db_path=self.test_db)
            db.set_server_tips_enabled(self.guild_id, True, db_path=self.test_db)
            self.assertTrue(tips.should_send_tip(self.user_id, roll_chance=1.0, guild_id=self.guild_id))

            # When user disabled tips
            db.set_user_tips_enabled(self.user_id, False, db_path=self.test_db)
            self.assertFalse(tips.should_send_tip(self.user_id, roll_chance=1.0, guild_id=self.guild_id))

            # force=True should bypass disabled status
            self.assertTrue(tips.should_send_tip(self.user_id, force=True, guild_id=self.guild_id))

            # Re-enable user, disable server
            db.set_user_tips_enabled(self.user_id, True, db_path=self.test_db)
            db.set_server_tips_enabled(self.guild_id, False, db_path=self.test_db)
            self.assertFalse(tips.should_send_tip(self.user_id, roll_chance=1.0, guild_id=self.guild_id))

    def test_tips_command_modes(self):
        """Verifies /tips command with mode: on, off, check, and default view."""
        bot = MagicMock()
        cog = WarriorCog(bot)

        # 1. Mode: OFF
        inter_off = MagicMock(spec=discord.Interaction)
        inter_off.user = MagicMock(spec=discord.Member)
        inter_off.user.id = self.user_id
        inter_off.user.name = "TipsWarrior"
        inter_off.user.mention = "<@998877>"
        inter_off.guild = None
        inter_off.response = MagicMock()
        inter_off.response.send_message = AsyncMock()

        choice_off = app_commands.Choice(name="Turn OFF", value="off")
        with patch("database.DB_PATH", self.test_db):
            asyncio.run(cog.tips_cmd.callback(cog, inter_off, mode=choice_off))
            self.assertFalse(db.get_user_tips_enabled(self.user_id, db_path=self.test_db))
            inter_off.response.send_message.assert_called_once()
            call_kwargs = inter_off.response.send_message.call_args.kwargs
            self.assertIn("Tips Disabled", call_kwargs["embed"].title)

        # 2. Mode: ON
        inter_on = MagicMock(spec=discord.Interaction)
        inter_on.user = inter_off.user
        inter_on.guild = None
        inter_on.response = MagicMock()
        inter_on.response.send_message = AsyncMock()

        choice_on = app_commands.Choice(name="Turn ON", value="on")
        with patch("database.DB_PATH", self.test_db):
            asyncio.run(cog.tips_cmd.callback(cog, inter_on, mode=choice_on))
            self.assertTrue(db.get_user_tips_enabled(self.user_id, db_path=self.test_db))
            inter_on.response.send_message.assert_called_once()
            call_kwargs = inter_on.response.send_message.call_args.kwargs
            self.assertIn("Tips Enabled", call_kwargs["embed"].title)

        # 3. Mode: CHECK
        inter_check = MagicMock(spec=discord.Interaction)
        inter_check.user = inter_off.user
        inter_check.guild = None
        inter_check.response = MagicMock()
        inter_check.response.send_message = AsyncMock()

        choice_check = app_commands.Choice(name="Check Status", value="check")
        with patch("database.DB_PATH", self.test_db):
            asyncio.run(cog.tips_cmd.callback(cog, inter_check, mode=choice_check))
            inter_check.response.send_message.assert_called_once()
            call_kwargs = inter_check.response.send_message.call_args.kwargs
            self.assertIn("Enabled", call_kwargs["embed"].description)

        # 4. Default Mode (Interactive Card)
        inter_default = MagicMock(spec=discord.Interaction)
        inter_default.user = inter_off.user
        inter_default.guild = None
        inter_default.response = MagicMock()
        inter_default.response.send_message = AsyncMock()

        with patch("database.DB_PATH", self.test_db):
            asyncio.run(cog.tips_cmd.callback(cog, inter_default, mode=None))
            inter_default.response.send_message.assert_called_once()
            call_kwargs = inter_default.response.send_message.call_args.kwargs
            self.assertIsInstance(call_kwargs["view"], TipsView)

    def test_tips_view_interactive_buttons(self):
        """Verifies TipsView button callbacks and user isolation checks."""
        view = TipsView(user_id=self.user_id, current_state=True, db_path=self.test_db)

        # 1. Turn Off button
        inter = MagicMock(spec=discord.Interaction)
        inter.user = MagicMock()
        inter.user.id = self.user_id
        inter.user.name = "TipsWarrior"
        inter.user.display_name = "TipsWarrior"
        inter.response = MagicMock()
        inter.response.edit_message = AsyncMock()

        asyncio.run(view.btn_off.callback(inter))
        self.assertFalse(view.current_state)
        self.assertFalse(db.get_user_tips_enabled(self.user_id, db_path=self.test_db))
        inter.response.edit_message.assert_called_once()

        # 2. Turn On button
        asyncio.run(view.btn_on.callback(inter))
        self.assertTrue(view.current_state)
        self.assertTrue(db.get_user_tips_enabled(self.user_id, db_path=self.test_db))

        # 3. User Guard
        other_inter = MagicMock(spec=discord.Interaction)
        other_inter.user = MagicMock()
        other_inter.user.id = 123456  # Different user
        other_inter.response = MagicMock()
        other_inter.response.send_message = AsyncMock()

        allowed = asyncio.run(view.interaction_check(other_inter))
        self.assertFalse(allowed)
        other_inter.response.send_message.assert_called_once()

    def test_static_tips_pool_content(self):
        """Verifies static tips pool covers /tips, /todo, incognito, rest days, and logic."""
        all_tips_text = " ".join(tips.BOT_USAGE_TIPS)

        # 1. Tips disabling & /tips
        self.assertIn("/tips off", all_tips_text)
        self.assertIn("/tips on", all_tips_text)
        self.assertTrue(any("annoying" in t.lower() or "distracting" in t.lower() for t in tips.BOT_USAGE_TIPS))

        # 2. Active Recovery Days & Rest Days
        self.assertTrue(any("Active Recovery Day" in t or "Rest Days" in t for t in tips.BOT_USAGE_TIPS))
        self.assertTrue(any("0 points required" in t for t in tips.BOT_USAGE_TIPS))

        # 3. /todo features
        self.assertIn("/todo add", all_tips_text)
        self.assertIn("/todo list", all_tips_text)
        self.assertIn("/todo done", all_tips_text)
        self.assertIn("/todo edit", all_tips_text)
        self.assertIn("/todo assign", all_tips_text)
        self.assertIn("/todo dnd", all_tips_text)

        # 4. Incognito mode
        self.assertIn("/todo incognito", all_tips_text)
        self.assertTrue(any("Incognito" in t for t in tips.BOT_USAGE_TIPS))

        # 5. System logic & rules
        self.assertTrue(any("500 points" in t for t in tips.BOT_USAGE_TIPS))
        self.assertTrue(any("30 points" in t for t in tips.BOT_USAGE_TIPS))
        self.assertTrue(any("Streak Shield" in t for t in tips.BOT_USAGE_TIPS))
        self.assertTrue(any("00:00 IST" in t for t in tips.BOT_USAGE_TIPS))
