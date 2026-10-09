"""
tests/base.py - Enterprise Base Test Fixture and Mock Factories for Winter Arc Test Suite
"""
import os
import unittest
import tempfile
from typing import Optional, List
from unittest.mock import MagicMock, AsyncMock
import discord

import database as db


class WinterArcTestCase(unittest.TestCase):
    """
    Base test case providing isolated temporary SQLite sandboxes,
    Discord mock factories, and custom embed assertion helpers.
    """

    test_db: str = "test_winter_arc.db"
    _temp_dir: Optional[tempfile.TemporaryDirectory] = None
    _orig_db_path: str = "winter_arc.db"

    @classmethod
    def setUpClass(cls):
        # Create an isolated temporary sandbox for each test case class
        cls._temp_dir = tempfile.TemporaryDirectory()
        cls.test_db = os.path.join(cls._temp_dir.name, f"{cls.__name__.lower()}.db")
        cls._orig_db_path = db.DB_PATH

        # Redirect default DB_PATH to sandbox so fallback queries never pollute root workspace
        temp_default_db = os.path.join(cls._temp_dir.name, "fallback_default.db")
        db.DB_PATH = temp_default_db

        db.init_db(cls.test_db)
        db.init_db(db.DB_PATH)

    @classmethod
    def tearDownClass(cls):
        db.DB_PATH = getattr(cls, "_orig_db_path", "winter_arc.db")
        if cls._temp_dir is not None:
            try:
                cls._temp_dir.cleanup()
            except Exception:
                pass

    def setUp(self):
        # Guarantee default DB tables exist for functions querying db.DB_PATH
        if not os.path.exists(db.DB_PATH):
            db.init_db(db.DB_PATH)

    # -------------------------------------------------------------------------
    # Discord Mock Factory Helpers
    # -------------------------------------------------------------------------

    def create_mock_member(
        self,
        user_id: int = 1001,
        display_name: str = "TestWarrior",
        roles: Optional[List[MagicMock]] = None
    ) -> MagicMock:
        """Creates a mock discord.Member with standard attributes."""
        member = MagicMock(spec=discord.Member)
        member.id = user_id
        member.display_name = display_name
        member.name = display_name.lower()
        member.mention = f"<@{user_id}>"
        member.roles = roles or []
        member.bot = False
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 999111
        return member

    def create_mock_interaction(
        self,
        user_id: int = 1001,
        display_name: str = "TestWarrior",
        guild_id: int = 999111,
        command_name: Optional[str] = None
    ) -> MagicMock:
        """Creates a fully mocked discord.Interaction with async response methods."""
        inter = MagicMock(spec=discord.Interaction)
        user = self.create_mock_member(user_id, display_name)
        inter.user = user
        inter.guild_id = guild_id
        inter.guild = user.guild
        inter.is_expired = MagicMock(return_value=False)

        if command_name:
            inter.command = MagicMock()
            inter.command.name = command_name
        else:
            inter.command = None

        inter.response = MagicMock()
        inter.response.is_done = MagicMock(return_value=False)

        async def _mock_defer(*args, **kwargs):
            inter.response.is_done.return_value = True

        async def _mock_send_message(*args, **kwargs):
            inter.response.is_done.return_value = True

        inter.response.defer = AsyncMock(side_effect=_mock_defer)
        inter.response.send_message = AsyncMock(side_effect=_mock_send_message)
        inter.response.edit_message = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()
        return inter

    def create_mock_channel(
        self,
        channel_id: int = 8888,
        name: str = "winter-arc-general"
    ) -> MagicMock:
        """Creates a mock discord.TextChannel with async send method."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = channel_id
        channel.name = name
        channel.send = AsyncMock()
        return channel

    def create_mock_message(
        self,
        author: Optional[MagicMock] = None,
        content: str = "",
        attachments: Optional[List[MagicMock]] = None
    ) -> MagicMock:
        """Creates a mock discord.Message with attachments and reactions."""
        msg = MagicMock(spec=discord.Message)
        msg.author = author or self.create_mock_member()
        msg.content = content
        msg.attachments = attachments or []
        msg.add_reaction = AsyncMock()
        msg.reply = AsyncMock()
        return msg

    # -------------------------------------------------------------------------
    # Custom Discord Embed Assertion Helpers
    # -------------------------------------------------------------------------

    def assertEmbedTitle(self, embed: discord.Embed, expected_title: str):
        """Asserts that an embed title matches expected string."""
        self.assertEqual(embed.title, expected_title)

    def assertEmbedTitleContains(self, embed: discord.Embed, *snippets: str):
        """Asserts that all specified substrings are present in embed.title."""
        title = embed.title or ""
        for snippet in snippets:
            self.assertIn(snippet, title, f"Snippet '{snippet}' not found in embed title: {title}")

    def assertEmbedDescriptionContains(self, embed: discord.Embed, *snippets: str):
        """Asserts that all specified substrings are present in embed.description."""
        desc = embed.description or ""
        for snippet in snippets:
            self.assertIn(snippet, desc, f"Snippet '{snippet}' not found in embed description: {desc}")

    def assertEmbedFooter(self, embed: discord.Embed, expected_footer: str):
        """Asserts that embed.footer.text matches expected footer string."""
        footer_text = embed.footer.text if (embed.footer and embed.footer.text) else ""
        self.assertEqual(footer_text, expected_footer)

    def assertEmbedFooterContains(self, embed: discord.Embed, *snippets: str):
        """Asserts that embed.footer.text contains all specified substrings."""
        footer_text = embed.footer.text if (embed.footer and embed.footer.text) else ""
        for snippet in snippets:
            self.assertIn(snippet, footer_text, f"Snippet '{snippet}' not found in footer: {footer_text}")

    def assertEmbedField(
        self,
        embed: discord.Embed,
        name_substr: str,
        value_substr: Optional[str] = None
    ):
        """Asserts that an embed field exists with name containing name_substr (and optionally value_substr)."""
        matching_fields = [f for f in embed.fields if name_substr in f.name]
        self.assertTrue(
            len(matching_fields) > 0,
            f"No field found containing '{name_substr}' in name. Available fields: {[f.name for f in embed.fields]}"
        )
        if value_substr:
            matching_values = [f for f in matching_fields if value_substr in f.value]
            self.assertTrue(
                len(matching_values) > 0,
                f"Field '{name_substr}' found, but does not contain value snippet '{value_substr}'"
            )
