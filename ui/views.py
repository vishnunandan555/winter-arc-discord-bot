"""
ui/views.py - Interactive Discord UI Views and Components

Contains interactive views such as LeaderboardView with Daily / Overall tabs.
"""

import discord
import database as db
from ui.embeds import (
    build_daily_leaderboard_embed,
    build_monthly_leaderboard_embed,
    build_overall_leaderboard_embed,
    build_settings_embed,
)


class LeaderboardView(discord.ui.View):
    """Interactive view allowing users to toggle between Daily, Overall, and Monthly leaderboards."""
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
                elif child.custom_id == "tab_monthly":
                    child.disabled = (self.current_tab == "monthly")
                    child.style = discord.ButtonStyle.primary if self.current_tab == "monthly" else discord.ButtonStyle.secondary
                elif child.custom_id == "tab_overall":
                    child.disabled = (self.current_tab == "overall")
                    child.style = discord.ButtonStyle.primary if self.current_tab == "overall" else discord.ButtonStyle.secondary

    @discord.ui.button(label="📅 Daily Standings", style=discord.ButtonStyle.primary, custom_id="tab_daily")
    async def tab_daily_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "daily"
        self._update_buttons()
        embed = build_daily_leaderboard_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="📆 Monthly", style=discord.ButtonStyle.secondary, custom_id="tab_monthly")
    async def tab_monthly_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "monthly"
        self._update_buttons()
        embed = build_monthly_leaderboard_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🌐 All-Time Overall", style=discord.ButtonStyle.secondary, custom_id="tab_overall")
    async def tab_overall_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "overall"
        self._update_buttons()
        embed = build_overall_leaderboard_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class SettingsView(discord.ui.View):
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
            await interaction.response.send_message("❌ These settings belong to another warrior. Run `/settings` to manage yours.", ephemeral=True)
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

