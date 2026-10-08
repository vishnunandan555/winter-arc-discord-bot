"""
tests/test_call_cap_and_governance.py - Comprehensive Unit Tests for /accuse, Council Voting, Disciplinary Probation, and /admin grind
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from tests.base import WinterArcTestCase
import database as db
from config import BOT_TZ
from ui.views import (
    CallCapConfirmView,
    AccuseConfirmView,
    CouncilVotingView,
    COUNCIL_SUMMONED_GIFS,
    CAP_CONFIRMED_GIFS,
    LEGIT_VERIFIED_GIFS,
)
from cogs.warrior import WarriorCog
from cogs.admin import AdminCog


class TestCallCapAndGovernance(WinterArcTestCase):
    """Test suite covering database probation methods, /accuse flow, and /admin grind commands."""

    def setUp(self):
        super().setUp()
        self.user_a_id = 111001
        self.user_b_id = 111002
        self.user_c_id = 111003

        # Clean tables for sandbox isolation
        with db.get_connection(self.test_db) as conn:
            conn.execute("DELETE FROM grind_logs;")
            conn.execute("DELETE FROM daily_logs;")
            conn.execute("DELETE FROM daily_summaries;")
            conn.execute("DELETE FROM bot_state;")
            conn.execute("DELETE FROM users;")
            conn.commit()

        # Enroll users
        db.enroll_user(self.user_a_id, "WarriorA", db_path=self.test_db)
        db.enroll_user(self.user_b_id, "WarriorB", db_path=self.test_db)
        db.enroll_user(self.user_c_id, "WarriorC", db_path=self.test_db)

        self.today_str = datetime.now(BOT_TZ).strftime("%Y-%m-%d")

    def test_database_grind_probation_lifecycle(self):
        """Verifies setting, checking, and clearing grind probation in bot_state."""
        # Initial state: not blocked
        p0 = db.get_grind_probation(self.user_a_id, db_path=self.test_db)
        self.assertFalse(p0["is_blocked"])
        self.assertIsNone(p0["remaining_days"])

        # Block for 3 days
        db.set_grind_probation(self.user_a_id, days=3, db_path=self.test_db)
        p1 = db.get_grind_probation(self.user_a_id, db_path=self.test_db)
        self.assertTrue(p1["is_blocked"])
        self.assertEqual(p1["remaining_days"], 3)

        # Clear probation
        db.clear_grind_probation(self.user_a_id, db_path=self.test_db)
        p2 = db.get_grind_probation(self.user_a_id, db_path=self.test_db)
        self.assertFalse(p2["is_blocked"])
        self.assertIsNone(p2["remaining_days"])

        # Indefinite block (days=None)
        db.set_grind_probation(self.user_a_id, days=None, db_path=self.test_db)
        p3 = db.get_grind_probation(self.user_a_id, db_path=self.test_db)
        self.assertTrue(p3["is_blocked"])
        self.assertIsNone(p3["remaining_days"])

        # Expired probation test
        past_date = (datetime.now(BOT_TZ) - timedelta(days=2)).isoformat()
        db.set_bot_state(f"grind_ban_{self.user_a_id}", past_date, db_path=self.test_db)
        p_expired = db.get_grind_probation(self.user_a_id, db_path=self.test_db)
        self.assertFalse(p_expired["is_blocked"])

    def test_database_cap_user_grind(self):
        """Verifies capping zeroes out today's grind entry points and subtracts from user lifetime points."""
        db.record_grind_entry(
            discord_id=self.user_a_id,
            date_str=self.today_str,
            raw_input="Studied compiler optimization for 4 hours",
            verdict="ACCEPTED",
            points=45,
            key_learning="Compiler AST",
            commentary="Solid friction.",
            db_path=self.test_db
        )

        stats_before = db.get_user_stats(self.user_a_id, db_path=self.test_db)
        self.assertGreaterEqual(stats_before["lifetime_points"], 45)

        grind_entry = db.get_user_daily_grind(self.user_a_id, self.today_str, db_path=self.test_db)
        self.assertEqual(grind_entry["points"], 45)

        # Cap the user
        capped = db.cap_user_grind(self.user_a_id, date_str=self.today_str, db_path=self.test_db)
        self.assertIsNotNone(capped)

        grind_after = db.get_user_daily_grind(self.user_a_id, self.today_str, db_path=self.test_db)
        self.assertEqual(grind_after["points"], 0)
        self.assertEqual(grind_after["verdict"], "CAPPED")

        stats_after = db.get_user_stats(self.user_a_id, db_path=self.test_db)
        self.assertEqual(stats_after["lifetime_points"], stats_before["lifetime_points"] - 45)

    def test_accuse_confirm_view_honor_code(self):
        """Verifies AccuseConfirmView/CallCapConfirmView structure, honor code prompt, and Stand Down button."""
        mock_challenger = self.create_mock_member(self.user_b_id, "WarriorB")
        mock_accused = self.create_mock_member(self.user_a_id, "WarriorA")
        grind_entry = {
            "raw_input": "Studied distributed consensus algorithms",
            "points": 40
        }

        view = CallCapConfirmView(challenger=mock_challenger, target=mock_accused, grind_entry=grind_entry)
        self.assertEqual(len(view.children), 2)
        btn_labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        self.assertIn("⚔️ Yes, Summon Council", btn_labels)
        self.assertIn("❌ No, Stand Down", btn_labels)

        # Non-challenger cannot interact
        inter_stranger = self.create_mock_interaction(user_id=self.user_c_id, display_name="WarriorC")
        allowed = asyncio.run(view.interaction_check(inter_stranger))
        self.assertFalse(allowed)

        # Challenger allowed
        inter_challenger = self.create_mock_interaction(user_id=self.user_b_id, display_name="WarriorB")
        allowed_challenger = asyncio.run(view.interaction_check(inter_challenger))
        self.assertTrue(allowed_challenger)

    def test_council_voting_view_vote_mechanics_and_timeout(self):
        """Verifies Council voting buttons, self-voting prevention, and timeout verdicts."""
        mock_accused = self.create_mock_member(self.user_a_id, "WarriorA")
        mock_challenger = self.create_mock_member(self.user_b_id, "WarriorB")
        mock_juror = self.create_mock_member(self.user_c_id, "WarriorC")

        db.record_grind_entry(
            discord_id=self.user_a_id,
            date_str=self.today_str,
            raw_input="Deep quantum computing math and circuit design",
            verdict="ACCEPTED",
            points=35,
            key_learning="Quantum Circuits",
            commentary="High level.",
            db_path=self.test_db
        )
        grind_entry = db.get_user_daily_grind(self.user_a_id, self.today_str, db_path=self.test_db)

        view = CouncilVotingView(
            accused=mock_accused,
            challenger=mock_challenger,
            grind_entry=grind_entry,
            timeout=600.0
        )

        orig_enrolled = db.is_user_enrolled
        orig_cap = db.cap_user_grind
        with patch.object(db, "is_user_enrolled", side_effect=lambda uid, **kw: orig_enrolled(uid, db_path=self.test_db)):
            # Accused tries to vote -> rejected
            inter_accused = self.create_mock_interaction(user_id=self.user_a_id, display_name="WarriorA")
            guard_accused = asyncio.run(view._guard_voter(inter_accused))
            self.assertFalse(guard_accused)

            # Juror votes He's Capping
            inter_juror = self.create_mock_interaction(user_id=self.user_c_id, display_name="WarriorC")
            cap_button = [c for c in view.children if getattr(c, "custom_id", "") == "vote_cap"][0]
            asyncio.run(cap_button.callback(inter_juror))
            self.assertIn(mock_juror.id, view.capping_votes)
            self.assertEqual(len(view.legit_votes), 0)

            # Juror switches vote to Legit
            legit_button = [c for c in view.children if getattr(c, "custom_id", "") == "vote_legit"][0]
            asyncio.run(legit_button.callback(inter_juror))
            self.assertIn(mock_juror.id, view.legit_votes)
            self.assertNotIn(mock_juror.id, view.capping_votes)

            # Juror switches back to Capping
            asyncio.run(cap_button.callback(inter_juror))
            self.assertIn(mock_juror.id, view.capping_votes)

        # Mock channel and message for resolution
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.channel = mock_channel
        mock_msg.edit = AsyncMock()
        view.message = mock_msg

        # Patch db.cap_user_grind to use test_db
        with patch.object(db, "cap_user_grind", side_effect=lambda uid, **kw: orig_cap(uid, db_path=self.test_db)):
            asyncio.run(view.on_timeout())

        # Check that buttons were disabled
        for child in view.children:
            self.assertTrue(child.disabled)

        # Cap confirmed resolution sent
        self.assertTrue(mock_channel.send.called)
        sent_embed = mock_channel.send.call_args.kwargs.get("embed")
        self.assertIn("GUILTY", sent_embed.title)
        self.assertIn(sent_embed.image.url, CAP_CONFIRMED_GIFS)

        # Verify accused points were stripped
        grind_after = db.get_user_daily_grind(self.user_a_id, self.today_str, db_path=self.test_db)
        self.assertEqual(grind_after["points"], 0)

    def test_council_voting_legit_verdict_timeout(self):
        """Verifies that if legit votes > capping votes, points stand and legit GIF is sent."""
        mock_accused = self.create_mock_member(self.user_a_id, "WarriorA")
        mock_challenger = self.create_mock_member(self.user_b_id, "WarriorB")
        mock_juror = self.create_mock_member(self.user_c_id, "WarriorC")

        db.record_grind_entry(
            discord_id=self.user_a_id,
            date_str=self.today_str,
            raw_input="Solved 3 graph problems",
            verdict="ACCEPTED",
            points=30,
            key_learning="Graph Theory",
            commentary="Valid work.",
            db_path=self.test_db
        )
        grind_entry = db.get_user_daily_grind(self.user_a_id, self.today_str, db_path=self.test_db)

        view = CouncilVotingView(
            accused=mock_accused,
            challenger=mock_challenger,
            grind_entry=grind_entry,
            timeout=600.0
        )

        orig_enrolled = db.is_user_enrolled
        with patch.object(db, "is_user_enrolled", side_effect=lambda uid, **kw: orig_enrolled(uid, db_path=self.test_db)):
            # Juror votes Legit
            inter_juror = self.create_mock_interaction(user_id=self.user_c_id, display_name="WarriorC")
            legit_button = [c for c in view.children if getattr(c, "custom_id", "") == "vote_legit"][0]
            asyncio.run(legit_button.callback(inter_juror))

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.channel = mock_channel
        mock_msg.edit = AsyncMock()
        view.message = mock_msg

        asyncio.run(view.on_timeout())

        self.assertTrue(mock_channel.send.called)
        sent_embed = mock_channel.send.call_args.kwargs.get("embed")
        self.assertIn("NOT GUILTY", sent_embed.title)
        self.assertIn(sent_embed.image.url, LEGIT_VERIFIED_GIFS)

        # Points still 30
        grind_after = db.get_user_daily_grind(self.user_a_id, self.today_str, db_path=self.test_db)
        self.assertEqual(grind_after["points"], 30)

    def test_admin_grind_block_and_unlock_commands(self):
        """Verifies /admin grind block strips points and sets probation, and unlock clears probation."""
        bot = MagicMock()
        admin_cog = AdminCog(bot)

        # Give user_a an active grind entry
        db.record_grind_entry(
            discord_id=self.user_a_id,
            date_str=self.today_str,
            raw_input="Quantum math buzzwords",
            verdict="ACCEPTED",
            points=35,
            key_learning="Quantum",
            commentary="High level.",
            db_path=self.test_db
        )

        inter = self.create_mock_interaction(user_id=999999, display_name="ServerAdmin")
        inter.channel = self.create_mock_channel()
        inter.guild = MagicMock()
        inter.guild.id = 999111
        inter.guild.get_channel = MagicMock(return_value=self.create_mock_channel())

        mock_target = self.create_mock_member(self.user_a_id, "WarriorA")

        # Test block for 5 days with reason
        choice_block = MagicMock()
        choice_block.value = "block"

        orig_set = db.set_grind_probation
        orig_cap = db.cap_user_grind
        orig_clear = db.clear_grind_probation

        with patch.object(db, "set_grind_probation", side_effect=lambda uid, *a, **kw: orig_set(uid, kw.get("days", a[0] if a else None), db_path=self.test_db)), \
             patch.object(db, "cap_user_grind", side_effect=lambda uid, *a, **kw: orig_cap(uid, db_path=self.test_db)):
            asyncio.run(admin_cog.admin_grind.callback(
                admin_cog,
                inter,
                what=choice_block,
                member=mock_target,
                days=5,
                reason="Unsubstantiated quantum claims"
            ))

        prob = db.get_grind_probation(self.user_a_id, db_path=self.test_db)
        self.assertTrue(prob["is_blocked"])
        self.assertEqual(prob["remaining_days"], 5)

        grind_after = db.get_user_daily_grind(self.user_a_id, self.today_str, db_path=self.test_db)
        self.assertEqual(grind_after["points"], 0)

        # Test unlock
        choice_unlock = MagicMock()
        choice_unlock.value = "unlock"
        with patch.object(db, "clear_grind_probation", side_effect=lambda uid, *a, **kw: orig_clear(uid, db_path=self.test_db)):
            asyncio.run(admin_cog.admin_grind.callback(
                admin_cog,
                inter,
                what=choice_unlock,
                member=mock_target,
                days=None,
                reason="Appeal approved"
            ))

        prob_unlocked = db.get_grind_probation(self.user_a_id, db_path=self.test_db)
        self.assertFalse(prob_unlocked["is_blocked"])

    def test_gif_lists_contain_valid_media_urls(self):
        """Verifies that all GIF lists contain resolved direct media.tenor.com URLs."""
        for url in COUNCIL_SUMMONED_GIFS:
            self.assertTrue(url.startswith("https://media.tenor.com/"), f"Invalid GIF URL: {url}")
            self.assertTrue(url.endswith(".gif"))

        for url in CAP_CONFIRMED_GIFS:
            self.assertTrue(url.startswith("https://media.tenor.com/"), f"Invalid GIF URL: {url}")
            self.assertTrue(url.endswith(".gif"))

        for url in LEGIT_VERIFIED_GIFS:
            self.assertTrue(url.startswith("https://media.tenor.com/"), f"Invalid GIF URL: {url}")
            self.assertTrue(url.endswith(".gif"))

    def test_accuse_guards_and_concurrent_trial_prevention(self):
        """Verifies /accuse guards: self-challenge, non-enrolled target, no grind log, and concurrent trial."""
        bot = MagicMock()
        cog = WarriorCog(bot)

        # 1. Self challenge
        inter_self = self.create_mock_interaction(user_id=self.user_a_id, display_name="WarriorA")
        mock_a = self.create_mock_member(self.user_a_id, "WarriorA")
        with patch("cogs.warrior.require_enrolled", return_value=True):
            asyncio.run(cog.accuse_cmd.callback(cog, inter_self, target=mock_a))
        self.assertIn("cannot accuse yourself", inter_self.response.send_message.call_args[0][0])

        # 2. Target not enrolled
        inter = self.create_mock_interaction(user_id=self.user_b_id, display_name="WarriorB")
        mock_stranger = self.create_mock_member(999888, "Stranger")
        with patch("cogs.warrior.require_enrolled", return_value=True), \
             patch("cogs.warrior.db.is_user_enrolled", return_value=False):
            asyncio.run(cog.accuse_cmd.callback(cog, inter, target=mock_stranger))
        self.assertIn("not currently enrolled", inter.response.send_message.call_args[0][0])

        # 3. Target is a bot
        mock_bot_user = self.create_mock_member(999000, "BotUser")
        mock_bot_user.bot = True
        with patch("cogs.warrior.require_enrolled", return_value=True):
            asyncio.run(cog.accuse_cmd.callback(cog, inter, target=mock_bot_user))
        self.assertIn("cannot accuse a bot", inter.response.send_message.call_args[0][0])

        # 4. Concurrent active trial
        CouncilVotingView.active_trials.add(self.user_a_id)
        try:
            with patch("cogs.warrior.require_enrolled", return_value=True), \
                 patch("cogs.warrior.db.is_user_enrolled", return_value=True):
                asyncio.run(cog.accuse_cmd.callback(cog, inter, target=mock_a))
            self.assertIn("already active", inter.response.send_message.call_args[0][0])
        finally:
            CouncilVotingView.active_trials.discard(self.user_a_id)

    def test_accuse_confirm_view_concurrency_and_stale_guards(self):
        """Verifies that AccuseConfirmView/CallCapConfirmView rejects if a trial started or points were already stripped."""
        mock_challenger = self.create_mock_member(self.user_b_id, "WarriorB")
        mock_accused = self.create_mock_member(self.user_a_id, "WarriorA")
        grind_entry = {"raw_input": "Studied distributed systems", "points": 30}

        view = CallCapConfirmView(challenger=mock_challenger, target=mock_accused, grind_entry=grind_entry)
        inter = self.create_mock_interaction(user_id=self.user_b_id, display_name="WarriorB")
        inter.response.edit_message = AsyncMock()

        # 1. Guard against concurrent active trial
        CouncilVotingView.active_trials.add(self.user_a_id)
        try:
            asyncio.run(view.confirm_summon.callback(inter))
            self.assertIn("already actively underway", inter.response.edit_message.call_args.kwargs.get("content", ""))
        finally:
            CouncilVotingView.active_trials.discard(self.user_a_id)

        # 2. Guard against stale entry (no points or revoked)
        with patch("ui.views.db.get_user_daily_grind", return_value={"points": 0, "verdict": "CAPPED"}):
            asyncio.run(view.confirm_summon.callback(inter))
            self.assertIn("points have already been stripped", inter.response.edit_message.call_args.kwargs.get("content", ""))

    def test_council_voting_tie_outcome_with_thinking_gif(self):
        """Verifies that tied council voting preserves points and sends the thinking GIF."""
        mock_accused = self.create_mock_member(self.user_a_id, "WarriorA")
        mock_challenger = self.create_mock_member(self.user_b_id, "WarriorB")
        grind_entry = {"raw_input": "Advanced compiler optimization", "points": 35}

        view = CouncilVotingView(accused=mock_accused, challenger=mock_challenger, grind_entry=grind_entry, timeout=600.0)
        # Equal votes (1 cap, 1 legit)
        view.capping_votes.add(self.user_b_id)
        view.legit_votes.add(self.user_c_id)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.channel = mock_channel
        mock_msg.edit = AsyncMock()
        view.message = mock_msg

        asyncio.run(view.on_timeout())

        self.assertTrue(mock_channel.send.called)
        embed = mock_channel.send.call_args.kwargs.get("embed")
        self.assertIn("TIE / INCONCLUSIVE", embed.title)
        self.assertIn("hmm-thinking.gif", embed.image.url)

    def test_admin_grind_blocks_bots_and_cleans_active_trials(self):
        """Verifies that /admin grind block rejects bot targets and discards from active_trials."""
        bot = MagicMock()
        admin_cog = AdminCog(bot)

        inter = self.create_mock_interaction(user_id=999999, display_name="Admin")
        inter.guild = MagicMock()
        inter.guild.id = 999111
        inter.guild.get_channel = MagicMock(return_value=self.create_mock_channel())

        mock_bot_member = self.create_mock_member(888999, "TestBot")
        mock_bot_member.bot = True

        choice_block = MagicMock()
        choice_block.value = "block"

        asyncio.run(admin_cog.admin_grind.callback(admin_cog, inter, what=choice_block, member=mock_bot_member))
        self.assertIn("Bots cannot be placed on grind probation", inter.response.send_message.call_args.kwargs.get("content", inter.response.send_message.call_args[0][0]))

    def test_grind_blocked_by_probation(self):
        """Verifies that a user on grind probation is blocked from /grind."""
        bot = MagicMock()
        cog = WarriorCog(bot)

        # Place user on 4-day probation in test_db
        db.set_grind_probation(self.user_a_id, days=4, db_path=self.test_db)

        inter = self.create_mock_interaction(user_id=self.user_a_id, display_name="WarriorA")
        orig_prob = db.get_grind_probation
        with patch("cogs.warrior.require_enrolled", return_value=True), \
             patch.object(db, "get_grind_probation", side_effect=lambda uid, **kw: orig_prob(uid, db_path=self.test_db)), \
             patch("cogs.warrior.gemini_service.evaluate_grind") as mock_gemini:
            asyncio.run(cog.grind_cmd.callback(cog, inter, text="Studied theoretical physics and wrote simulations"))
            # AI should never be invoked when blocked
            self.assertFalse(mock_gemini.called)

        self.assertTrue(inter.response.send_message.called)
        sent_msg = inter.response.send_message.call_args[0][0]
        self.assertIn("Access Suspended", sent_msg)
        self.assertIn("4 more day(s)", sent_msg)

    def test_council_summon_pings_winter_arc_role(self):
        """Verifies that summoning the Council includes the Winter Arc role ping and allowed_mentions."""
        mock_challenger = self.create_mock_member(self.user_b_id, "WarriorB")
        mock_accused = self.create_mock_member(self.user_a_id, "WarriorA")
        grind_entry = {"raw_input": "Studied distributed systems", "points": 30}

        view = CallCapConfirmView(challenger=mock_challenger, target=mock_accused, grind_entry=grind_entry)
        inter = self.create_mock_interaction(user_id=self.user_b_id, display_name="WarriorB")
        inter.response.edit_message = AsyncMock()

        mock_channel = self.create_mock_channel()
        mock_channel.send = AsyncMock()
        inter.channel = mock_channel
        inter.guild = MagicMock()
        inter.guild.id = 123456
        inter.guild.get_channel = MagicMock(return_value=mock_channel)

        with patch("ui.views.db.get_user_daily_grind", return_value={"points": 30, "raw_input": "Studied distributed systems"}), \
             patch("ui.views.db.get_server_settings", return_value={"channel_id": mock_channel.id, "role_id": 999777}):
            asyncio.run(view.confirm_summon.callback(inter))

        self.assertTrue(mock_channel.send.called)
        call_kwargs = mock_channel.send.call_args.kwargs
        self.assertIn("<@&999777>", call_kwargs.get("content", ""))
        self.assertTrue(call_kwargs.get("allowed_mentions").roles)

    def test_accuse_confirm_view_stand_down_cancels(self):
        """Verifies that selecting Stand Down disables buttons and does not summon the Council."""
        mock_challenger = self.create_mock_member(self.user_b_id, "WarriorB")
        mock_accused = self.create_mock_member(self.user_a_id, "WarriorA")
        grind_entry = {"raw_input": "Studied distributed systems", "points": 30}

        view = AccuseConfirmView(challenger=mock_challenger, target=mock_accused, grind_entry=grind_entry)
        inter = self.create_mock_interaction(user_id=self.user_b_id, display_name="WarriorB")
        inter.response.edit_message = AsyncMock()

        asyncio.run(view.cancel_summon.callback(inter))
        self.assertTrue(all(child.disabled for child in view.children))
        call_kwargs = inter.response.edit_message.call_args.kwargs
        self.assertIn("Stand down confirmed", call_kwargs.get("content", ""))
        self.assertNotIn(self.user_a_id, CouncilVotingView.active_trials)

    def test_accuse_confirm_view_channel_send_failure_cleans_up(self):
        """Verifies that if channel.send raises an exception, the active trial is cleaned up and view stopped."""
        mock_challenger = self.create_mock_member(self.user_b_id, "WarriorB")
        mock_accused = self.create_mock_member(self.user_a_id, "WarriorA")
        grind_entry = {"raw_input": "Studied distributed systems", "points": 30}

        view = AccuseConfirmView(challenger=mock_challenger, target=mock_accused, grind_entry=grind_entry)
        inter = self.create_mock_interaction(user_id=self.user_b_id, display_name="WarriorB")
        inter.response.edit_message = AsyncMock()

        mock_channel = self.create_mock_channel()
        mock_channel.send = AsyncMock(side_effect=discord.DiscordException("Forbidden"))
        inter.channel = mock_channel
        inter.guild = MagicMock()
        inter.guild.id = 123456
        inter.guild.get_channel = MagicMock(return_value=mock_channel)

        with patch("ui.views.db.get_user_daily_grind", return_value={"points": 30, "raw_input": "Studied distributed systems"}), \
             patch("ui.views.db.get_server_settings", return_value={"channel_id": mock_channel.id}):
            asyncio.run(view.confirm_summon.callback(inter))

        # Must be removed from active trials so user is not permanently stuck
        self.assertNotIn(self.user_a_id, CouncilVotingView.active_trials)




