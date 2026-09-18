"""
bot.py - Winter Arc Discord Bot Main Entry Point

A high-performance, modular fitness and accountability bot built with discord.py 2.x.
Tracks daily disciplines (pushups, pullups, squats, situps, running), 12-level pack progression,
and automated daily check-ins.
"""

import sys
import logging
import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import DISCORD_TOKEN, logger
from scheduler import WinterArcScheduler

EXTENSIONS = [
    "cogs.warrior",
    "cogs.admin",
]


class WinterArcBot(commands.Bot):
    """Core bot client with automatic cog discovery and scheduler management."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )
        self.scheduler: WinterArcScheduler = None
        self._synced = False

    async def setup_hook(self):
        """Initializes database, loads cogs, and initializes scheduler."""
        # 1. Initialize SQLite database schemas
        db.init_db()

        # 2. Load modular cogs
        for ext in EXTENSIONS:
            try:
                await self.load_extension(ext)
                logger.info(f"Loaded extension: {ext}")
            except Exception as e:
                logger.error(f"Failed to load extension {ext}: {e}", exc_info=True)

        # 3. Initialize background scheduler
        self.scheduler = WinterArcScheduler(self)

        # 4. Global slash command tree synchronization if application_id is available
        if self.application_id:
            try:
                synced = await self.tree.sync()
                self._synced = True
                logger.info(f"Slash command tree synchronized ({len(synced)} commands registered).")
            except Exception as e:
                logger.error(f"Failed to sync slash commands in setup_hook: {e}")

    async def on_ready(self):
        """Called when gateway connection is established."""
        logger.info(f"Winter Arc Bot is online as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} Discord server(s):")
        for g in self.guilds:
            logger.info(f"  • {g.name} (ID: {g.id}) - {g.member_count} members")

        # Sync slash commands once connected to Discord Gateway if not synced yet
        if not self._synced:
            try:
                synced = await self.tree.sync()
                self._synced = True
                logger.info(f"Slash command tree synchronized ({len(synced)} commands registered).")
            except Exception as e:
                logger.error(f"Failed to sync slash commands in on_ready: {e}")

        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.competing,
                name="Winter Arc (500 pts daily)"
            ),
            status=discord.Status.online
        )

        if self.scheduler:
            self.scheduler.start()

    async def on_message(self, message: discord.Message):
        """Subtle mascot reactions when replied to or mentioned."""
        if message.author.bot:
            return

        is_reply_to_bot = (
            message.reference
            and message.reference.resolved
            and isinstance(message.reference.resolved, discord.Message)
            and message.reference.resolved.author.id == self.user.id
        )
        is_bot_mentioned = self.user in message.mentions
        is_mascot_named = "amarok" in (message.content.lower() if message.content else "")

        if is_reply_to_bot or is_bot_mentioned or is_mascot_named:
            try:
                await message.add_reaction("🐺")
            except discord.Forbidden:
                pass
            except Exception as e:
                logger.debug(f"Could not react to message: {e}")

        await self.process_commands(message)

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Global error handler for slash commands."""
        logger.error(f"AppCommand error on '{interaction.command.name if interaction.command else 'unknown'}': {error}")

        if isinstance(error, app_commands.MissingPermissions):
            msg = "🚫 You need **Administrator** permissions to execute this command."
        elif isinstance(error, app_commands.CommandOnCooldown):
            msg = f"⏳ Command on cooldown. Try again in {error.retry_after:.1f}s."
        elif isinstance(error, app_commands.CheckFailure):
            return
        else:
            msg = "❌ An unexpected error occurred while processing your request."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to deliver error response: {e}")


bot = WinterArcBot()


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.error("❌ DISCORD_TOKEN is not set in your .env file!")
        sys.exit(1)

    bot.run(DISCORD_TOKEN)
