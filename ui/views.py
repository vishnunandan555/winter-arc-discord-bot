"""
ui/views.py - Interactive Discord UI Views and Components

Contains interactive views such as LeaderboardView with Daily / Overall tabs.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Dict, List, Union
import discord
import database as db
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

    @discord.ui.button(label="Daily", style=discord.ButtonStyle.primary, custom_id="tab_daily")
    async def tab_daily_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "daily"
        self._update_buttons()
        embed = build_daily_leaderboard_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Weekly", style=discord.ButtonStyle.secondary, custom_id="tab_weekly")
    async def tab_weekly_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "weekly"
        self._update_buttons()
        embed = build_weekly_leaderboard_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Monthly", style=discord.ButtonStyle.secondary, custom_id="tab_monthly")
    async def tab_monthly_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "monthly"
        self._update_buttons()
        embed = build_monthly_leaderboard_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="All-Time", style=discord.ButtonStyle.secondary, custom_id="tab_overall")
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
            discord.SelectOption(label="Workout & AI Logging", value="logging", description="/quick, /log, /set, /grind & #quick-log", emoji="⚡"),
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
        from ui.embeds import build_streak_consistency_embed, STREAK_LEGEND_SUBTEXT
        data = db.get_user_monthly_consistency(self.target_user.id)
        embed = build_streak_consistency_embed(self.target_user, data)
        await interaction.response.edit_message(content=STREAK_LEGEND_SUBTEXT, embed=embed, view=self)

    async def _calendar_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the member who ran the command can navigate.", ephemeral=True)
            return
        self.current_view = "calendar"
        self._build_buttons()
        import database as db
        from ui.embeds import build_full_calendar_embed, STREAK_LEGEND_SUBTEXT
        data = db.get_user_full_campaign_calendar(self.target_user.id)
        embed = build_full_calendar_embed(self.target_user, data)
        await interaction.response.edit_message(content=STREAK_LEGEND_SUBTEXT, embed=embed, view=self)



