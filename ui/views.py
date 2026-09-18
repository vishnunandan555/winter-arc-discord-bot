"""
ui/views.py - Interactive Discord UI Views and Components

Contains interactive views such as LeaderboardView with Daily / Overall tabs.
"""

import discord
from ui.embeds import build_daily_leaderboard_embed, build_overall_leaderboard_embed


class LeaderboardView(discord.ui.View):
    """Interactive view allowing users to toggle between Daily and Overall leaderboards."""
    def __init__(self, current_tab: str = "daily"):
        super().__init__(timeout=None)
        self.current_tab = current_tab
        self._update_buttons()

    def _update_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "tab_daily":
                    child.disabled = (self.current_tab == "daily")
                    child.style = discord.ButtonStyle.primary if self.current_tab == "daily" else discord.ButtonStyle.secondary
                elif child.custom_id == "tab_overall":
                    child.disabled = (self.current_tab == "overall")
                    child.style = discord.ButtonStyle.primary if self.current_tab == "overall" else discord.ButtonStyle.secondary

    @discord.ui.button(label="📅 Daily Standings", style=discord.ButtonStyle.primary, custom_id="tab_daily")
    async def tab_daily_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "daily"
        self._update_buttons()
        embed = build_daily_leaderboard_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🌐 All-Time Overall", style=discord.ButtonStyle.secondary, custom_id="tab_overall")
    async def tab_overall_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "overall"
        self._update_buttons()
        embed = build_overall_leaderboard_embed()
        await interaction.response.edit_message(embed=embed, view=self)
