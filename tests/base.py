"""
tests/base.py - Base Test Fixture and Mock Factories for Winter Arc Test Suite
"""
import os
import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from typing import Optional

import database as db


class WinterArcTestCase(unittest.TestCase):
    """Base test case providing isolated SQLite databases and mock Discord helpers."""

    test_db: str = "test_winter_arc.db"

    @classmethod
    def setUpClass(cls):
        cls.test_db = f"test_{cls.__name__.lower()}.db"
        for ext in ["", "-wal", "-shm"]:
            f = f"{cls.test_db}{ext}"
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass

        db.init_db(cls.test_db)
        cls._created_default_db = False
        if not os.path.exists(db.DB_PATH):
            db.init_db(db.DB_PATH)
            cls._created_default_db = True

    @classmethod
    def tearDownClass(cls):
        for ext in ["", "-wal", "-shm"]:
            f = f"{cls.test_db}{ext}"
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass
        if getattr(cls, "_created_default_db", False) and os.path.exists(db.DB_PATH):
            try:
                os.remove(db.DB_PATH)
            except OSError:
                pass

    def create_mock_member(self, user_id: int = 1001, display_name: str = "TestWarrior") -> MagicMock:
        import discord
        member = MagicMock(spec=discord.Member)
        member.id = user_id
        member.display_name = display_name
        member.mention = f"<@{user_id}>"
        return member

    def create_mock_interaction(
        self,
        user_id: int = 1001,
        display_name: str = "TestWarrior",
        guild_id: int = 999111
    ) -> MagicMock:
        import discord
        inter = MagicMock(spec=discord.Interaction)
        user = self.create_mock_member(user_id, display_name)
        inter.user = user
        inter.guild_id = guild_id
        inter.response = MagicMock()
        inter.response.defer = AsyncMock()
        inter.response.send_message = AsyncMock()
        inter.response.edit_message = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()
        return inter
