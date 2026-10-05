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
from config import BOT_TZ
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
    """Interactive view allowing users to toggle between Daily, Weekly, Monthly, and All-Time leaderboards."""
    def __init__(self, current_tab: str = "daily"):
        super().__init__(timeout=600)
        self.current_tab = current_tab
        self._update_buttons()

    def _update_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "tab_daily":
                    child.disabled = (self.current_tab == "daily")
                    child.style = discord.ButtonStyle.primary if self.current_tab == "daily" else discord.ButtonStyle.secondary
                elif child.custom_id == "tab_weekly":
                    child.disabled = (self.current_tab == "weekly")
                    child.style = discord.ButtonStyle.primary if self.current_tab == "weekly" else discord.ButtonStyle.secondary
                elif child.custom_id == "tab_monthly":
                    child.disabled = (self.current_tab == "monthly")
                    child.style = discord.ButtonStyle.primary if self.current_tab == "monthly" else discord.ButtonStyle.secondary
                elif child.custom_id == "tab_overall":
                    child.disabled = (self.current_tab == "overall")
                    child.style = discord.ButtonStyle.primary if self.current_tab == "overall" else discord.ButtonStyle.secondary

    @discord.ui.button(label="Daily", emoji="📅", style=discord.ButtonStyle.primary, custom_id="tab_daily")
    async def tab_daily_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "daily"
        self._update_buttons()
        embed = build_daily_leaderboard_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Weekly", emoji="📆", style=discord.ButtonStyle.secondary, custom_id="tab_weekly")
    async def tab_weekly_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "weekly"
        self._update_buttons()
        embed = build_weekly_leaderboard_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Monthly", emoji="🗓️", style=discord.ButtonStyle.secondary, custom_id="tab_monthly")
    async def tab_monthly_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "monthly"
        self._update_buttons()
        embed = build_monthly_leaderboard_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="All-Time", emoji="🌐", style=discord.ButtonStyle.secondary, custom_id="tab_overall")
    async def tab_overall_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "overall"
        self._update_buttons()
        embed = build_overall_leaderboard_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class SettingsView(RobustView):
    """Interactive view for configuring personal DM notifications."""

    def __init__(self, user_id: int, settings: dict):
        super().__init__(timeout=180.0)
        self.user_id = user_id
        self.settings = settings
        self._sync_buttons()

    def _sync_buttons(self):
        master = self.settings["dm_reminders"]
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "toggle_master":
                    child.label = "🔔 Master DMs: Enabled" if master else "🔕 Master DMs: Disabled"
                    child.style = discord.ButtonStyle.success if master else discord.ButtonStyle.secondary
                elif child.custom_id == "toggle_morning":
                    child.disabled = not master
                    child.label = "🌅 Morning: On" if self.settings["dm_morning"] else "🌅 Morning: Off"
                    child.style = discord.ButtonStyle.primary if self.settings["dm_morning"] and master else discord.ButtonStyle.secondary
                elif child.custom_id == "toggle_evening":
                    child.disabled = not master
                    child.label = "🌙 Evening: On" if self.settings["dm_evening"] else "🌙 Evening: Off"
                    child.style = discord.ButtonStyle.primary if self.settings["dm_evening"] and master else discord.ButtonStyle.secondary

    async def _guard_user(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ These settings belong to another member. Run `/settings` to manage yours.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🔔 Master DMs", style=discord.ButtonStyle.secondary, custom_id="toggle_master")
    async def toggle_master_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard_user(interaction):
            return
        new_state = not self.settings["dm_reminders"]
        self.settings = db.update_user_dm_settings(self.user_id, dm_reminders=new_state)
        self._sync_buttons()
        embed = build_settings_embed(interaction.user, self.settings)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🌅 Morning: On", style=discord.ButtonStyle.secondary, custom_id="toggle_morning")
    async def toggle_morning_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard_user(interaction):
            return
        new_state = not self.settings["dm_morning"]
        self.settings = db.update_user_dm_settings(self.user_id, dm_morning=new_state)
        self._sync_buttons()
        embed = build_settings_embed(interaction.user, self.settings)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🌙 Evening: On", style=discord.ButtonStyle.secondary, custom_id="toggle_evening")
    async def toggle_evening_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard_user(interaction):
            return
        new_state = not self.settings["dm_evening"]
        self.settings = db.update_user_dm_settings(self.user_id, dm_evening=new_state)
        self._sync_buttons()
        embed = build_settings_embed(interaction.user, self.settings)
        await interaction.response.edit_message(embed=embed, view=self)


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
        await interaction.response.edit_message(embed=embed, view=self)


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
    Streamlined 2-button view for /streak and /consistency:
    - [Current]: Shows our current month habit consistency only (no month changes)
    - [Calendar]: Opens the full 3-phase Winter Arc campaign calendar view
    """
    def __init__(
        self,
        target_user: Any,
        author_id: int,
        current_view: str = "current"
    ):
        super().__init__(timeout=300)
        self.target_user = target_user
        self.author_id = author_id
        self.current_view = current_view
        self._build_buttons()

    def _build_buttons(self):
        self.clear_items()

        is_current = (self.current_view == "current")
        current_btn = discord.ui.Button(
            label="Current",
            style=discord.ButtonStyle.primary if is_current else discord.ButtonStyle.secondary,
            custom_id="streak_view_current",
            disabled=is_current
        )
        current_btn.callback = self._current_callback
        self.add_item(current_btn)

        is_calendar = (self.current_view == "calendar")
        calendar_btn = discord.ui.Button(
            label="Calendar",
            style=discord.ButtonStyle.primary if is_calendar else discord.ButtonStyle.secondary,
            custom_id="streak_view_calendar",
            disabled=is_calendar
        )
        calendar_btn.callback = self._calendar_callback
        self.add_item(calendar_btn)

    async def _current_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the member who ran the command can navigate.", ephemeral=True)
            return
        self.current_view = "current"
        self._build_buttons()
        import database as db
        from ui.embeds import build_streak_consistency_embed
        data = db.get_user_monthly_consistency(self.target_user.id)
        embed = build_streak_consistency_embed(self.target_user, data)
        await interaction.response.edit_message(content=None, embed=embed, view=self)

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
# Council & Call-Cap Governance Assets & Views
# ==========================================

COUNCIL_SUMMONED_GIFS: List[str] = [
    "https://media.tenor.com/DP615vqUzeAAAAAM/ace-attorney-phoenix-wright.gif",
    "https://media.tenor.com/9aSgH93prb8AAAAM/higuruma-meme-jjk.gif",
    "https://media.tenor.com/W_FsaAqZ2YkAAAAM/phoenix-wright-ace-attorney.gif",
    "https://media.tenor.com/bm3kkN80t90AAAAM/caption-courtroom-anime.gif",
    "https://media.tenor.com/JiStbOAbFwIAAAAM/side-eye-hmm.gif",
    "https://media.tenor.com/1lxTZHxvQUsAAAAM/anakin-skywalker-star-wars-revenge-of-the-sith.gif",
    "https://media.tenor.com/aGj-frNYMFEAAAAM/cat-cat-dance.gif",
    "https://media.tenor.com/UAHUJ7LSK2AAAAAM/galactic-republic-flag.gif",
    "https://media.tenor.com/znGPVdu2GR8AAAAM/eating-ramen-noodles.gif",
    "https://media.tenor.com/YhGD-tzR3KAAAAAM/tea-spill-the-tea.gif",
    "https://media.tenor.com/aLGLTuVa5wAAAAAM/tenor.gif",
    "https://media.tenor.com/XHiHKmWWf9gAAAAM/boring-unimpressed.gif",
    "https://media.tenor.com/ZF_NNP-7O_AAAAAj/hmm.gif",
    "https://media.tenor.com/jz-K9VgBqPMAAAAj/buha-821-buha.gif",
]

CAP_CONFIRMED_GIFS: List[str] = [
    "https://media.tenor.com/NeubPwLVK94AAAAM/ace-attorney-phoenix-wright.gif",
    "https://media.tenor.com/XfxU1QnRpWcAAAAM/oh-my-god-bruh-jjk.gif",
    "https://media.tenor.com/B0piVWUiKaUAAAAM/patrick-drooling-patrick-star.gif",
    "https://media.tenor.com/FsNeRoz6apcAAAAM/st-paddys-day-2023.gif",
    "https://media.tenor.com/I50TI2DmFXIAAAAM/yuji-stare-yuji-itadori.gif",
    "https://media.tenor.com/Czj7xHpjdQwAAAAM/raven-walk.gif",
    "https://media.tenor.com/-FOSoTZ8KWoAAAAj/son.gif",
    "https://media.tenor.com/FhI8aEMJxdUAAAAj/emoji-emoji-meme.gif",
    "https://media.tenor.com/89jKLhtbnmIAAAAj/really-sus.gif",
    "https://media.tenor.com/8BvIvPhOJDYAAAAj/doink.gif",
    "https://media.tenor.com/3Q0GX4tlKoEAAAAj/no.gif",
    "https://media.tenor.com/cMN5uVyHkysAAAAj/anderstand.gif",
    "https://media.tenor.com/lY7VOhEjpTEAAAAM/angry.gif",
    "https://media.tenor.com/HXHCV0LpqNAAAAAM/hilarious-so-funny.gif",
]

LEGIT_VERIFIED_GIFS: List[str] = [
    "https://media.tenor.com/DcdpcwgX8nMAAAAM/lacucu.gif",
    "https://media.tenor.com/93mTZ4pPjI0AAAAM/crazy-seal-seal.gif",
    "https://media.tenor.com/CV8ObVxsVvQAAAAM/hello-jjk.gif",
    "https://media.tenor.com/peucjgy5sEoAAAAM/euphonium-anime-thumbs-up.gif",
    "https://media.tenor.com/4p8ils6cSY4AAAAj/vvh157309.gif",
    "https://media.tenor.com/gotOLnyvy4YAAAAM/bubu-dancing-dance.gif",
    "https://media.tenor.com/T4Tq9zOHmdIAAAAj/joinha-sla.gif",
    "https://media.tenor.com/-HLjKV1b6YIAAAAj/yellow.gif",
    "https://media.tenor.com/ZA03JtK4SwoAAAAM/ghost-ghost-game.gif",
    "https://media.tenor.com/-ighVtBUFCAAAAAM/hampter-my-honest-reaction.gif",
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
                    child.label = f"🧢 He's Capping ({len(self.capping_votes)})"
                elif child.custom_id == "vote_legit":
                    child.label = f"✅ Legit ({len(self.legit_votes)})"

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

    @discord.ui.button(label="🧢 He's Capping (0)", style=discord.ButtonStyle.secondary, custom_id="vote_cap")
    async def vote_cap_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard_voter(interaction):
            return

        user_id = interaction.user.id
        if user_id in self.capping_votes:
            await interaction.response.send_message("🗳️ You have already cast your vote as **He's Capping**.", ephemeral=True)
            return

        self.legit_votes.discard(user_id)
        self.capping_votes.add(user_id)
        self._sync_labels()

        await interaction.response.edit_message(view=self)
        await interaction.followup.send("🗳️ Vote recorded: **He's Capping** 🧢", ephemeral=True)

    @discord.ui.button(label="✅ Legit (0)", style=discord.ButtonStyle.secondary, custom_id="vote_legit")
    async def vote_legit_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard_voter(interaction):
            return

        user_id = interaction.user.id
        if user_id in self.legit_votes:
            await interaction.response.send_message("🗳️ You have already cast your vote as **Legit**.", ephemeral=True)
            return

        self.capping_votes.discard(user_id)
        self.legit_votes.add(user_id)
        self._sync_labels()

        await interaction.response.edit_message(view=self)
        await interaction.followup.send("🗳️ Vote recorded: **Legit** ✅", ephemeral=True)

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
            # Cap confirmed: zero out points for the challenged date
            target_date = self.grind_entry.get("date")
            db.cap_user_grind(self.accused.id, date_str=target_date)
            gif = random.choice(CAP_CONFIRMED_GIFS)
            embed = discord.Embed(
                title="⚖️ Council Verdict: CAP CONFIRMED",
                description=(
                    f"The Council has spoken: **{capping_count} Capping** vs **{legit_count} Legit**.\n\n"
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
            # Legit verified: points stand
            gif = random.choice(LEGIT_VERIFIED_GIFS)
            embed = discord.Embed(
                title="⚖️ Council Verdict: GRIND LEGIT",
                description=(
                    f"The Council has spoken: **{legit_count} Legit** vs **{capping_count} Capping**.\n\n"
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
            gif = "https://media.tenor.com/ZF_NNP-7O_AAAAAj/hmm.gif"
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


class CallCapConfirmView(RobustView):
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

        log_text = self.grind_entry.get("raw_input", "")
        points = self.grind_entry.get("points", 0)

        role_id = settings.get("role_id") if interaction.guild else None
        role_ping = f"<@&{role_id}> " if role_id else ""

        content = (
            f"{role_ping}🚨 **The Council Has Been Summoned** 🚨\n\n"
            f"*{self.challenger.mention} has called cap on {self.target.mention}'s grind log of*\n"
            f"```{log_text}```\n"
            f"*worth {points} points.*\n\n"
            f"⚔️ **Summoner**: {self.challenger.mention}\n"
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
            msg = await channel.send(content=content, embed=gif_embed, view=voting_view)
            voting_view.message = msg
        except Exception as e:
            logger.error(f"Failed to post Council summon message in channel {channel.id}: {e}", exc_info=True)
            CouncilVotingView.active_trials.discard(self.target.id)

    @discord.ui.button(label="❌ No, Stand Down", style=discord.ButtonStyle.secondary, custom_id="btn_cancel_summon")
    async def cancel_summon(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="🛡️ **Stand down confirmed.** The Council was not summoned.", view=self)




