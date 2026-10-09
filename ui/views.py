"""
ui/views.py - Interactive Discord UI Views and Components

Contains interactive views such as LeaderboardView with Daily / Overall tabs.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime
from typing import Any, Optional, Dict, List, Union
import discord
import database as db
from config import BOT_TZ, DEFAULT_ROLE_ID
from ui.embeds import (
    build_daily_leaderboard_embed,
    build_weekly_leaderboard_embed,
    build_monthly_leaderboard_embed,
    build_overall_leaderboard_embed,
    build_settings_embed,
    build_help_embed,
    build_recap_embed,
)

logger = logging.getLogger("winter_arc.ui.views")


class RobustView(discord.ui.View):
    """
    Base view that provides centralized error handling, interaction timeout handling,
    and structured logging across all interactive Discord components.
    """
    def __init__(self, timeout: Optional[float] = 180.0):
        super().__init__(timeout=timeout)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]) -> None:
        orig = getattr(error, "original", error)
        if (isinstance(orig, discord.errors.NotFound) and getattr(orig, "code", None) == 10062) or interaction.is_expired():
            logger.debug(
                f"Interaction for view '{self.__class__.__name__}' item '{getattr(item, 'custom_id', item.__class__.__name__)}' "
                f"expired or was cancelled by Discord (404 Unknown interaction). User: {interaction.user}"
            )
            return

        item_id = getattr(item, "custom_id", item.__class__.__name__)
        logger.error(
            f"Error in view '{self.__class__.__name__}' item '{item_id}' "
            f"invoked by {interaction.user} (ID: {interaction.user.id}) "
            f"in guild {getattr(interaction.guild, 'id', 'DM')}: {error}",
            exc_info=error
        )
        msg = "⚠️ An unexpected error occurred while processing this action. Please try again."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception as send_err:
            logger.debug(f"Could not deliver view error response: {send_err}")


class LeaderboardView(RobustView):
    """Interactive view allowing users to toggle between Weekly, Monthly, and All-Time leaderboards."""
    def __init__(self, current_tab: str = "weekly"):
        super().__init__(timeout=600)
        self.current_tab = current_tab
        self._update_buttons()

    def _update_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "tab_weekly":
                    child.disabled = (self.current_tab == "weekly")
                    child.style = discord.ButtonStyle.primary if self.current_tab == "weekly" else discord.ButtonStyle.secondary
                elif child.custom_id == "tab_monthly":
                    child.disabled = (self.current_tab == "monthly")
                    child.style = discord.ButtonStyle.primary if self.current_tab == "monthly" else discord.ButtonStyle.secondary
                elif child.custom_id == "tab_overall":
                    child.disabled = (self.current_tab == "overall")
                    child.style = discord.ButtonStyle.primary if self.current_tab == "overall" else discord.ButtonStyle.secondary

    @discord.ui.button(label="Weekly", emoji="📆", style=discord.ButtonStyle.primary, custom_id="tab_weekly")
    async def tab_weekly_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "weekly"
        self._update_buttons()
        logger.info(f"LeaderboardView switched to Weekly tab by {interaction.user}")
        embed = build_weekly_leaderboard_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Monthly", emoji="🗓️", style=discord.ButtonStyle.secondary, custom_id="tab_monthly")
    async def tab_monthly_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "monthly"
        self._update_buttons()
        logger.info(f"LeaderboardView switched to Monthly tab by {interaction.user}")
        embed = build_monthly_leaderboard_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="All-Time", emoji="🌐", style=discord.ButtonStyle.secondary, custom_id="tab_overall")
    async def tab_overall_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "overall"
        self._update_buttons()
        logger.info(f"LeaderboardView switched to All-Time tab by {interaction.user}")
        embed = build_overall_leaderboard_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class RemindersView(RobustView):
    """Interactive view for configuring personal DM notifications and reminders."""

    def __init__(self, user_id: int, settings: dict):
        super().__init__(timeout=180.0)
        self.user_id = user_id
        self.settings = settings
        self._sync_buttons()

    def _sync_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "toggle_morning":
                    on = bool(self.settings.get("dm_morning"))
                    child.label = "🌅 Morning: On" if on else "🌅 Morning: Off"
                    child.style = discord.ButtonStyle.success if on else discord.ButtonStyle.secondary
                elif child.custom_id == "toggle_afternoon":
                    on = bool(self.settings.get("dm_afternoon"))
                    child.label = "☀️ Afternoon: On" if on else "☀️ Afternoon: Off"
                    child.style = discord.ButtonStyle.success if on else discord.ButtonStyle.secondary
                elif child.custom_id == "toggle_evening":
                    on = bool(self.settings.get("dm_evening"))
                    child.label = "🌙 Evening: On" if on else "🌙 Evening: Off"
                    child.style = discord.ButtonStyle.success if on else discord.ButtonStyle.secondary

    async def _guard_user(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ These settings belong to another member. Run `/reminders` to manage yours.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🌅 Morning: On", style=discord.ButtonStyle.success, custom_id="toggle_morning", row=0)
    async def toggle_morning_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard_user(interaction):
            return
        new_state = not self.settings.get("dm_morning", True)
        self.settings = db.update_user_dm_settings(self.user_id, dm_morning=new_state)
        logger.info(f"User {interaction.user} ({self.user_id}) toggled morning reminders to {new_state}")
        self._sync_buttons()
        embed = build_settings_embed(interaction.user, self.settings)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="☀️ Afternoon: On", style=discord.ButtonStyle.success, custom_id="toggle_afternoon", row=0)
    async def toggle_afternoon_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard_user(interaction):
            return
        new_state = not self.settings.get("dm_afternoon", True)
        self.settings = db.update_user_dm_settings(self.user_id, dm_afternoon=new_state)
        logger.info(f"User {interaction.user} ({self.user_id}) toggled afternoon reminders to {new_state}")
        self._sync_buttons()
        embed = build_settings_embed(interaction.user, self.settings)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🌙 Evening: On", style=discord.ButtonStyle.success, custom_id="toggle_evening", row=0)
    async def toggle_evening_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard_user(interaction):
            return
        new_state = not self.settings.get("dm_evening", True)
        self.settings = db.update_user_dm_settings(self.user_id, dm_evening=new_state)
        logger.info(f"User {interaction.user} ({self.user_id}) toggled evening reminders to {new_state}")
        self._sync_buttons()
        embed = build_settings_embed(interaction.user, self.settings)
        await interaction.response.edit_message(embed=embed, view=self)


SettingsView = RemindersView


class HelpView(RobustView):
    """Interactive select menu allowing warriors to navigate the complete command manual."""
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.select(
        placeholder="📖 Select a category to explore...",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="Manual Overview", value="overview", description="Rules, 4 phases, 500 daily targets & schedule", emoji="📜"),
            discord.SelectOption(label="Workout & AI Logging", value="logging", description="/quick, /log, /set, /grind", emoji="⚡"),
            discord.SelectOption(label="Progress & Analytics", value="progress", description="/today, /streak, /profile, /leaderboard, /stats, /recap, /ranks", emoji="📊"),
            discord.SelectOption(label="Streak Shields & Recovery", value="shields", description="/shield status & /shield use mechanics", emoji="🛡️"),
            discord.SelectOption(label="Settings & Accountability", value="settings", description="/settings DMs, /enroll, /leave_arc", emoji="⚙️"),
            discord.SelectOption(label="Server Administration", value="admin", description="/admin controls, /test_reminder & health", emoji="👑"),
        ]
    )
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.Select):
        chosen = select.values[0]
        embed = build_help_embed(category=chosen)
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.NotFound:
            logger.debug(f"HelpView select interaction for '{chosen}' expired or was cancelled by Discord.")


class RecapView(RobustView):
    """
    Interactive view for /recap allowing warriors to switch between
    unlocked phases and the overall campaign recap.
    Only phases that have arrived/active are displayed as buttons.
    """
    def __init__(self, target_user: discord.Member, author_id: int, current_selection: str = "phase_1"):
        super().__init__(timeout=300)
        self.target_user = target_user
        self.author_id = author_id
        self.current_selection = current_selection
        self._build_buttons()

    def _build_buttons(self):
        self.clear_items()
        from phases import PHASES

        # Add button for Phase 1, Phase 2, Phase 3 (no emojis)
        phase_list = [p for p in PHASES if p["id"] <= 3]
        for p in phase_list:
            btn_id = f"phase_{p['id']}"
            is_active = (self.current_selection == btn_id)
            btn = discord.ui.Button(
                label=p['short_name'],
                style=discord.ButtonStyle.primary if is_active else discord.ButtonStyle.secondary,
                custom_id=f"recap_{btn_id}",
                disabled=is_active
            )
            btn.callback = self._make_phase_callback(p["id"], btn_id)
            self.add_item(btn)

        # Add Overall button (no emojis)
        is_overall = (self.current_selection == "overall")
        overall_btn = discord.ui.Button(
            label="Overall",
            style=discord.ButtonStyle.primary if is_overall else discord.ButtonStyle.secondary,
            custom_id="recap_overall",
            disabled=is_overall
        )
        overall_btn.callback = self._overall_callback
        self.add_item(overall_btn)

    def _make_phase_callback(self, phase_id: int, btn_id: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("Only the warrior who ran this command can navigate the recap.", ephemeral=True)
                return
            self.current_selection = btn_id
            self._build_buttons()
            stats = db.get_user_phase_stats(self.target_user.id, phase_id)
            embed = build_recap_embed(self.target_user, stats, is_overall=False)
            await interaction.response.edit_message(embed=embed, view=self)
        return callback

    async def _overall_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the warrior who ran this command can navigate the recap.", ephemeral=True)
            return
        self.current_selection = "overall"
        self._build_buttons()
        stats = db.get_user_overall_recap(self.target_user.id)
        embed = build_recap_embed(self.target_user, stats, is_overall=True)
        await interaction.response.edit_message(embed=embed, view=self)


class ServerRecordsView(RobustView):
    """
    Interactive view for /stats allowing members to switch between
    Overall (All-Time) and Phases 1, 2, 3 server benchmarks.
    Overall is the first button and default view.
    """
    def __init__(self, author_id: int, current_selection: str = "overall"):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.current_selection = current_selection
        self._build_buttons()

    def _build_buttons(self):
        self.clear_items()

        # 1. Overall button (FIRST button, default)
        is_overall = (self.current_selection == "overall")
        overall_btn = discord.ui.Button(
            label="Overall",
            style=discord.ButtonStyle.primary if is_overall else discord.ButtonStyle.secondary,
            custom_id="records_overall",
            disabled=is_overall
        )
        overall_btn.callback = self._overall_callback
        self.add_item(overall_btn)

        # 2. Phase 1, Phase 2, Phase 3 buttons
        from phases import PHASES
        phase_list = [p for p in PHASES if p["id"] <= 3]
        for p in phase_list:
            btn_id = f"phase_{p['id']}"
            is_active = (self.current_selection == btn_id)
            btn = discord.ui.Button(
                label=p['short_name'],
                style=discord.ButtonStyle.primary if is_active else discord.ButtonStyle.secondary,
                custom_id=f"records_{btn_id}",
                disabled=is_active
            )
            btn.callback = self._make_phase_callback(p["id"], btn_id)
            self.add_item(btn)

    def _make_phase_callback(self, phase_id: int, btn_id: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("Only the member who ran /stats can navigate these records.", ephemeral=True)
                return
            self.current_selection = btn_id
            self._build_buttons()
            import database as db
            from ui.embeds import build_server_records_embed
            data = db.get_server_records(phase_id)
            embed = build_server_records_embed(data, phase_id=phase_id)
            await interaction.response.edit_message(embed=embed, view=self)
        return callback

    async def _overall_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the member who ran /stats can navigate these records.", ephemeral=True)
            return
        self.current_selection = "overall"
        self._build_buttons()
        import database as db
        from ui.embeds import build_server_records_embed
        data = db.get_server_records(None)
        embed = build_server_records_embed(data, phase_id=None)
        await interaction.response.edit_message(embed=embed, view=self)


class StreakConsistencyView(RobustView):
    """
    Streamlined 2-button view for /streak and /calendar:
    - [Streak]: Shows our habit consistency dashboard & active streak status
    - [Calendar]: Opens the full 3-phase Winter Arc campaign calendar view
    """
    def __init__(
        self,
        target_user: Any,
        author_id: int,
        current_view: str = "streak"
    ):
        super().__init__(timeout=300)
        self.target_user = target_user
        self.author_id = author_id
        # Normalize "current" to "streak" for backwards compatibility
        self.current_view = "streak" if current_view in ("streak", "current") else "calendar"
        self._build_buttons()

    def _build_buttons(self):
        self.clear_items()

        is_streak = (self.current_view == "streak")
        streak_btn = discord.ui.Button(
            label="Streak",
            style=discord.ButtonStyle.primary if is_streak else discord.ButtonStyle.secondary,
            custom_id="streak_view_current",
            disabled=is_streak
        )
        streak_btn.callback = self._streak_callback
        self.add_item(streak_btn)

        is_calendar = (self.current_view == "calendar")
        calendar_btn = discord.ui.Button(
            label="Calendar",
            style=discord.ButtonStyle.primary if is_calendar else discord.ButtonStyle.secondary,
            custom_id="streak_view_calendar",
            disabled=is_calendar
        )
        calendar_btn.callback = self._calendar_callback
        self.add_item(calendar_btn)

    async def _streak_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the member who ran the command can navigate.", ephemeral=True)
            return
        self.current_view = "streak"
        self._build_buttons()
        import database as db
        from ui.embeds import build_streak_consistency_embed
        data = db.get_user_monthly_consistency(self.target_user.id)
        embed = build_streak_consistency_embed(self.target_user, data)
        await interaction.response.edit_message(content=None, embed=embed, view=self)

    # Alias for backwards compatibility
    _current_callback = _streak_callback

    async def _calendar_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the member who ran the command can navigate.", ephemeral=True)
            return
        self.current_view = "calendar"
        self._build_buttons()
        import database as db
        from ui.embeds import build_full_calendar_embed
        data = db.get_user_full_campaign_calendar(self.target_user.id)
        embed = build_full_calendar_embed(self.target_user, data)
        await interaction.response.edit_message(content=None, embed=embed, view=self)


POST_NUKE_GIFS = [
    "https://media.tenor.com/bxgD27sR5n0AAAAC/aot-goodbye-eren.gif",
    "https://media.tenor.com/rDdkpJVCV3UAAAAC/gord%C3%A3o-bomba-nuclear.gif",
    "https://media.tenor.com/s9YnGFQuqF8AAAAC/fnaf-2-movie-toy-chica.gif"
]
_nuke_gif_index = 0


def get_next_nuke_gif() -> str:
    """Rotates sequentially between the 3 post-nuke GIFs."""
    global _nuke_gif_index
    gif = POST_NUKE_GIFS[_nuke_gif_index % len(POST_NUKE_GIFS)]
    _nuke_gif_index += 1
    return gif


class Nuke2FAModal(discord.ui.Modal, title="🔐 Owner 2FA Verification"):
    """Secure pop-up modal asking for the owner's 2FA challenge answer."""

    answer_input = discord.ui.TextInput(
        label="Admin's pet dog name? (all small caps)",
        style=discord.TextStyle.short,
        placeholder="Enter security answer...",
        required=True,
        min_length=1,
        max_length=50
    )

    def __init__(self, channel: discord.TextChannel):
        super().__init__(timeout=120.0)
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        import hashlib
        from config import NUKE_SECURITY_HASH
        from helpers import auto_dismiss_ephemeral
        import asyncio

        submitted_answer = self.answer_input.value.strip().lower()
        submitted_hash = hashlib.sha256(submitted_answer.encode()).hexdigest()

        if not NUKE_SECURITY_HASH or submitted_hash != NUKE_SECURITY_HASH:
            await interaction.response.send_message(
                "❌ **2FA Verification Failed**: Incorrect answer. Nuke sequence aborted.",
                ephemeral=True
            )
            asyncio.create_task(auto_dismiss_ephemeral(interaction, delay=60))
            return

        await interaction.response.send_message("💥 **2FA Verified! Initiating channel purge...**", ephemeral=True)
        asyncio.create_task(auto_dismiss_ephemeral(interaction, delay=5))

        try:
            # Purge all messages in the channel
            await self.channel.purge(limit=None)

            # Post clean message with direct GIF in image-only embed (hides the URL completely)
            gif_url = get_next_nuke_gif()
            gif_embed = discord.Embed()
            gif_embed.set_image(url=gif_url)
            await self.channel.send(content="💥 **NUKED!**", embed=gif_embed)
        except discord.Forbidden:
            await self.channel.send(
                "❌ **Nuke Failed**: Missing Permissions. The bot requires the **Manage Messages** permission in this channel to delete messages.\n"
                "Please grant the bot's role the **Manage Messages** permission in Server Settings -> Roles or Channel Permissions."
            )
        except Exception as e:
            logger.error(f"Error executing channel nuke in {self.channel.id}: {e}", exc_info=True)
            await self.channel.send(f"❌ An error occurred during channel purge: `{e}`")


class NukeConfirmView(RobustView):
    """Confirmation view with Yes (proceeds to 2FA Modal) and No buttons for /nuke."""

    def __init__(self, owner_id: int):
        super().__init__(timeout=60.0)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("🚫 Only the Server Owner can confirm this action.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⚠️ Yes, Proceed to 2FA", style=discord.ButtonStyle.danger, custom_id="btn_confirm_nuke")
    async def confirm_nuke(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("❌ This command can only be used in text channels.", ephemeral=True)
            return

        # Open the secure 2FA modal directly on the client
        await interaction.response.send_modal(Nuke2FAModal(channel=channel))

    @discord.ui.button(label="❌ No, Cancel", style=discord.ButtonStyle.secondary, custom_id="btn_cancel_nuke")
    async def cancel_nuke(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="🛡️ **Nuke operation cancelled.** The channel was not modified.", embed=None, view=None)
        from helpers import auto_dismiss_ephemeral
        import asyncio
        asyncio.create_task(auto_dismiss_ephemeral(interaction, delay=60))


# ==========================================
# Council & Accuse Governance Assets & Views
# ==========================================

# Council summon (AI roast or /accuse): objections, accusations, and council
# deciding-fate representations. One gif chosen at random per summon message.
COUNCIL_SUMMONED_GIFS: List[str] = [
    "https://media.tenor.com/nnujmeraF1QAAAAC/hmm-thinking.gif",
    "https://media.tenor.com/4i3rnwLdbwUAAAAC/objection-court.gif",
    "https://media.tenor.com/vRGRCmHizWYAAAAC/higoruma-objection-jujutsu-kaisen.gif",
    "https://media.tenor.com/JU42eKKaKYUAAAAC/ace-attorney-ace.gif",
    "https://media.tenor.com/6Sb0kwgyN3QAAAAC/caption-courtroom-anime.gif",
    "https://media.tenor.com/M6bB0cVDhoMAAAAC/no-reaction-my-honest-reaction.gif",
    "https://media.tenor.com/ZF_NNP-7O_AAAAAC/hmm.gif",
    "https://media.tenor.com/jz-K9VgBqPMAAAAC/buha-821-buha.gif",
    "https://media.tenor.com/-AQCD60blUMAAAAC/ramen-cat.gif",
    "https://media.tenor.com/YSSI38KUrIoAAAAd/cat-the-council.gif",
    "https://media.tenor.com/BYwBdEZ4oeAAAAAC/galactic-republic-court.gif",
    "https://media.tenor.com/Bv5BPqltOikAAAAC/the.gif",
    "https://media.tenor.com/DyOjHwbvzqYAAAAC/fate.gif",
    "https://media.tenor.com/y1kenLT3p3gAAAAC/hiromi-higuruma-higuruma.gif",
    "https://media.tenor.com/CUScSqoyNZAAAAAd/higuruma-jjk.gif",
    "https://media.tenor.com/u6gmNC6-UsYAAAAC/yuji-stare-yuji-itadori.gif",
    "https://media.tenor.com/Qwk0J63O4IwAAAAC/happy.gif",
]

# Verdict: cap confirmed (disapproval). One gif chosen at random per result message.
CAP_CONFIRMED_GIFS: List[str] = [
    "https://media.tenor.com/GCt_Jv5wD38AAAAC/patrick-s-patrick.gif",
    "https://media.tenor.com/aG80h12EqSIAAAAC/cat-court.gif",
    "https://media.tenor.com/ezJalkcOLcMAAAAC/phoenix-wright-ace-attorney.gif",
    "https://media.tenor.com/5SIG5XU_VcQAAAAC/crow-judging.gif",
    "https://media.tenor.com/-FOSoTZ8KWoAAAAC/son.gif",
    "https://media.tenor.com/FhI8aEMJxdUAAAAC/emoji-emoji-meme.gif",
    "https://media.tenor.com/89jKLhtbnmIAAAAC/really-sus.gif",
    "https://media.tenor.com/8BvIvPhOJDYAAAAC/doink.gif",
    "https://media.tenor.com/3Q0GX4tlKoEAAAAC/no.gif",
    "https://media.tenor.com/cMN5uVyHkysAAAAC/anderstand.gif",
    "https://media.tenor.com/n73fxApWd2QAAAAC/side-eye-sus.gif",
    "https://media.tenor.com/gZU3n_9Nv2EAAAAC/cat-cat-stare.gif",
    "https://media.tenor.com/TA12Xjm8PIwAAAAd/side-eye-dog.gif",
    "https://media.tenor.com/K-ami_tx12oAAAAC/funny-cat.gif",
    "https://media.tenor.com/Jww37x0z_L0AAAAd/anakin-star-wars.gif",
    "https://media.tenor.com/u6gmNC6-UsYAAAAC/yuji-stare-yuji-itadori.gif",
    "https://media.tenor.com/Qwk0J63O4IwAAAAC/happy.gif",
]

# Verdict: grind legit (approval). One gif chosen at random per result message.
LEGIT_VERIFIED_GIFS: List[str] = [
    "https://media.tenor.com/tLUcX-K4ILcAAAAC/cat.gif",
    "https://media.tenor.com/kPSe7B54P1EAAAAC/patrick-meme-patrick.gif",
    "https://media.tenor.com/STXhuZ7MFf0AAAAC/jujutsu-kaisen-jjk.gif",
    "https://media.tenor.com/qGPUKbS4t8EAAAAC/knuckles-knuckles-the-echidna.gif",
    "https://media.tenor.com/2roCm-zykAMAAAAC/seal-seal-of-approval.gif",
    "https://media.tenor.com/R8wS2yg_5ecAAAAC/thumps-up-glases-meme.gif",
    "https://media.tenor.com/4p8ils6cSY4AAAAC/vvh157309.gif",
    "https://media.tenor.com/T4Tq9zOHmdIAAAAC/joinha-sla.gif",
    "https://media.tenor.com/-HLjKV1b6YIAAAAC/yellow.gif",
    "https://media.tenor.com/aio2ikRC1GAAAAAC/ghost-xe.gif",
    "https://media.tenor.com/L8FEenhU_ucAAAAC/white-hamster-meme-hamster-meme.gif",
    "https://media.tenor.com/Jww37x0z_L0AAAAd/anakin-star-wars.gif",
]


class CouncilVotingView(RobustView):
    """
    Public voting view for Council verification when a member calls cap on a grind log.
    Allows enrolled members to vote 'He's Capping' or 'Legit'. Resolves at timer conclusion.
    """
    active_trials: set[int] = set()

    def __init__(
        self,
        accused: Union[discord.User, discord.Member],
        challenger: Union[discord.User, discord.Member],
        grind_entry: dict,
        timeout: float = 600.0
    ):
        super().__init__(timeout=timeout)
        self.accused = accused
        self.challenger = challenger
        self.grind_entry = grind_entry
        self.capping_votes: set[int] = set()
        self.legit_votes: set[int] = set()
        self.message: Optional[discord.Message] = None

    def _sync_labels(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "vote_cap":
                    child.label = f"🔨 Guilty ({len(self.capping_votes)})"
                elif child.custom_id == "vote_legit":
                    child.label = f"🛡️ Innocent ({len(self.legit_votes)})"

    async def _guard_voter(self, interaction: discord.Interaction) -> bool:
        if self.is_finished():
            await interaction.response.send_message("⚖️ Voting for this trial has already concluded.", ephemeral=True)
            return False

        if interaction.user.id == self.accused.id:
            await interaction.response.send_message(
                "Nice try, you can't vote on your own trial! Let the council decide.",
                ephemeral=True
            )
            return False

        if not db.is_user_enrolled(interaction.user.id):
            await interaction.response.send_message(
                "❌ Only enrolled Winter Arc members can vote on Council trials.",
                ephemeral=True
            )
            return False

        return True

    @discord.ui.button(label="🔨 Guilty (0)", style=discord.ButtonStyle.secondary, custom_id="vote_cap")
    async def vote_cap_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard_voter(interaction):
            return

        user_id = interaction.user.id
        if user_id in self.capping_votes:
            await interaction.response.send_message("🗳️ You have already cast your vote as **Guilty**.", ephemeral=True)
            return

        self.legit_votes.discard(user_id)
        self.capping_votes.add(user_id)
        self._sync_labels()
        logger.info(f"Council vote: {interaction.user} voted Guilty on {self.accused.display_name}")

        await interaction.response.edit_message(view=self)
        await interaction.followup.send("🗳️ Vote recorded: **Guilty** 🔨", ephemeral=True)

    @discord.ui.button(label="🛡️ Innocent (0)", style=discord.ButtonStyle.secondary, custom_id="vote_legit")
    async def vote_legit_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard_voter(interaction):
            return

        user_id = interaction.user.id
        if user_id in self.legit_votes:
            await interaction.response.send_message("🗳️ You have already cast your vote as **Innocent**.", ephemeral=True)
            return

        self.capping_votes.discard(user_id)
        self.legit_votes.add(user_id)
        self._sync_labels()
        logger.info(f"Council vote: {interaction.user} voted Innocent on {self.accused.display_name}")

        await interaction.response.edit_message(view=self)
        await interaction.followup.send("🗳️ Vote recorded: **Innocent** 🛡️", ephemeral=True)

    async def on_timeout(self) -> None:
        CouncilVotingView.active_trials.discard(self.accused.id)

        for child in self.children:
            child.disabled = True

        capping_count = len(self.capping_votes)
        legit_count = len(self.legit_votes)
        points = self.grind_entry.get("points", 0)

        # Disable buttons on the original message
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception as e:
                logger.warning(f"Could not disable council voting view buttons on timeout: {e}")

        channel = self.message.channel if self.message else None
        if not channel:
            return

        if capping_count > legit_count:
            # Accusation confirmed: zero out points for the challenged date
            target_date = self.grind_entry.get("date")
            db.cap_user_grind(self.accused.id, date_str=target_date)
            logger.info(f"Council trial resolved for {self.accused.display_name} ({self.accused.id}): {capping_count} Guilty vs {legit_count} Innocent -> Cap confirmed ({points} pts stripped)")
            gif = random.choice(CAP_CONFIRMED_GIFS)
            embed = discord.Embed(
                title="⚖️ Council Verdict: CAP CONFIRMED (GUILTY)",
                description=(
                    f"The Council has spoken: **{capping_count} Guilty** vs **{legit_count} Innocent**.\n\n"
                    f"{self.accused.mention}'s grind points for today (`{points} pts`) have been **stripped**.\n"
                    "Authenticity and sweat are the bedrock of the Winter Arc. No shortcuts."
                ),
                color=0xE74C3C
            )
            embed.set_image(url=gif)
            try:
                await channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Failed to post cap confirmed resolution: {e}")

        elif legit_count > capping_count:
            # Accusation dismissed: points stand
            logger.info(f"Council trial resolved for {self.accused.display_name} ({self.accused.id}): {legit_count} Innocent vs {capping_count} Guilty -> Legit verified ({points} pts stand)")
            gif = random.choice(LEGIT_VERIFIED_GIFS)
            embed = discord.Embed(
                title="⚖️ Council Verdict: GRIND LEGIT (NOT GUILTY)",
                description=(
                    f"The Council has spoken: **{legit_count} Innocent** vs **{capping_count} Guilty**.\n\n"
                    f"{self.accused.mention}'s daily grind has been verified by the brotherhood.\n"
                    f"Their **`{points} pts` stand**.\n\n"
                    "Stay disciplined and keep grinding."
                ),
                color=0x2ECC71
            )
            embed.set_image(url=gif)
            try:
                await channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Failed to post legit verified resolution: {e}")

        else:
            # Tie or 0:0 inconclusive
            logger.info(f"Council trial resolved for {self.accused.display_name} ({self.accused.id}): Tie ({capping_count} - {legit_count}) -> Trial dismissed ({points} pts stand)")
            gif = "https://media.tenor.com/nnujmeraF1QAAAAC/hmm-thinking.gif"
            embed = discord.Embed(
                title="⚖️ Council Review Dismissed: TIE / INCONCLUSIVE",
                description=(
                    f"The Council review concluded in a tie (`{capping_count}` - `{legit_count}`).\n\n"
                    f"Allegations were inconclusive. The trial is dismissed and {self.accused.mention} retains their `{points} pts`."
                ),
                color=0xF1C40F
            )
            embed.set_image(url=gif)
            try:
                await channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Failed to post council tie resolution: {e}")


class AccuseConfirmView(RobustView):
    """
    Ephemeral confirmation view presented to a challenger before summoning the Council.
    Enforces the Winter Arc Honor Code against petty rivalry.
    """
    def __init__(
        self,
        challenger: Union[discord.User, discord.Member],
        target: Union[discord.User, discord.Member],
        grind_entry: dict
    ):
        super().__init__(timeout=120.0)
        self.challenger = challenger
        self.target = target
        self.grind_entry = grind_entry

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.challenger.id:
            await interaction.response.send_message("❌ This confirmation prompt is private to the challenger.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⚔️ Yes, Summon Council", style=discord.ButtonStyle.danger, custom_id="btn_confirm_summon")
    async def confirm_summon(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True

        # Concurrency guard: check if trial already became active while ephemeral view was open
        if self.target.id in CouncilVotingView.active_trials:
            await interaction.response.edit_message(
                content=f"⚠️ A Council session is already actively underway for {self.target.mention}.",
                view=self
            )
            return

        # Stale state guard: check if target's points were already revoked
        today_str = datetime.now(BOT_TZ).strftime("%Y-%m-%d")
        fresh_grind = db.get_user_daily_grind(self.target.id, today_str)
        if not fresh_grind or fresh_grind.get("points", 0) <= 0:
            await interaction.response.edit_message(
                content=f"⚠️ {self.target.mention}'s grind log has already concluded or points have already been stripped.",
                view=self
            )
            return

        channel = interaction.channel
        settings = {}
        if interaction.guild:
            settings = db.get_server_settings(interaction.guild.id)
            ch_id = settings.get("channel_id")
            if ch_id:
                ch = interaction.guild.get_channel(ch_id)
                if ch:
                    channel = ch

        if not channel:
            await interaction.response.edit_message(content="❌ Could not locate channel to summon Council.", view=self)
            return

        await interaction.response.edit_message(content="⚔️ **The Council has been summoned.** Voting is now active in the channel.", view=self)
        logger.info(f"Accuse confirmation: {self.challenger} confirmed Council summon against {self.target.display_name} ({self.target.id})")

        log_text = self.grind_entry.get("raw_input", "")
        # Discord message content is capped at 4000 chars; keep the excerpt bounded.
        if len(log_text) > 800:
            log_text = log_text[:797] + "..."
        points = self.grind_entry.get("points", 0)

        role_id = (settings.get("role_id") if interaction.guild else None) or DEFAULT_ROLE_ID
        role_ping = f"<@&{role_id}> " if role_id else ""

        content = (
            f"{role_ping}🚨 **The Council Has Been Summoned** 🚨\n\n"
            f"*{self.challenger.mention} has formally accused {self.target.mention} of submitting an illegitimate grind log:*\n"
            f"```{log_text}```\n"
            f"*worth {points} points.*\n\n"
            f"⚔️ **Accuser**: {self.challenger.mention}\n"
            f"⚖️ **Accused**: {self.target.mention}\n"
            f"🎯 **Stake**: {points} Points\n\n"
            "⏳ Cast your vote below. Decision resolves when the timer concludes."
        )

        gif_url = random.choice(COUNCIL_SUMMONED_GIFS)
        gif_embed = discord.Embed(color=0xE74C3C)
        gif_embed.set_image(url=gif_url)

        voting_view = CouncilVotingView(
            accused=self.target,
            challenger=self.challenger,
            grind_entry=self.grind_entry,
            timeout=600.0
        )
        CouncilVotingView.active_trials.add(self.target.id)

        try:
            msg = await channel.send(
                content=content,
                embed=gif_embed,
                view=voting_view,
                allowed_mentions=discord.AllowedMentions(roles=True, users=True)
            )
            voting_view.message = msg
        except Exception as e:
            logger.error(f"Failed to post Council summon message in channel {channel.id}: {e}", exc_info=True)
            voting_view.stop()
            CouncilVotingView.active_trials.discard(self.target.id)

    @discord.ui.button(label="❌ No, Stand Down", style=discord.ButtonStyle.secondary, custom_id="btn_cancel_summon")
    async def cancel_summon(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        logger.info(f"Accuse confirmation: {self.challenger} canceled Council summon against {self.target.display_name}")
        await interaction.response.edit_message(content="🛡️ **Stand down confirmed.** The Council was not summoned.", view=self)


# Backwards compatibility alias
CallCapConfirmView = AccuseConfirmView
