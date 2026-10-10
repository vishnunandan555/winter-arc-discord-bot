"""
bot.py - Winter Arc Discord Bot Main Entry Point

A high-performance, modular fitness and accountability bot built with discord.py 2.x.
Tracks daily disciplines (pushups, pullups, squats, situps, running), 12-level pack progression,
and automated daily check-ins.
"""

import os
import sys
import signal
import asyncio
import logging
import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import DISCORD_TOKEN, logger, setup_global_exception_handlers
from scheduler import WinterArcScheduler

EXTENSIONS = [
    "cogs.warrior",
    "cogs.admin",
]


class AutocompleteNotFoundFilter(logging.Filter):
    """Suppresses benign Discord 10062 Unknown interaction errors caused by superseded keystrokes during rapid autocomplete typing."""
    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info and len(record.exc_info) > 1 and record.exc_info[1]:
            exc = record.exc_info[1]
            if isinstance(exc, discord.errors.NotFound) and getattr(exc, "code", None) == 10062:
                return False
        msg = record.getMessage()
        if "Ignoring exception in autocomplete" in msg and "10062" in msg:
            return False
        return True


logging.getLogger("discord.app_commands.tree").addFilter(AutocompleteNotFoundFilter())


class WinterArcBot(commands.Bot):
    """Core bot client with automatic cog discovery and scheduler management."""

    def __init__(self):
        intents = discord.Intents.default()
        # Enable members intent for server roster DMs, invitations, and role assignment
        intents.members = True
        if os.getenv("ENABLE_MESSAGE_CONTENT_INTENT", "false").lower() in ("true", "1", "yes"):
            intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            max_messages=100,
            chunk_guilds_at_startup=True,
        )
        self.scheduler: WinterArcScheduler = None
        self._synced = False
        self._has_started = False
        from datetime import datetime, timezone
        self.start_time = datetime.now(timezone.utc)
        setup_global_exception_handlers(logger)

    async def on_error(self, event_method: str, *args, **kwargs):
        """Global gateway event exception listener."""
        logger.error(f"Unhandled exception in Discord gateway event '{event_method}'", exc_info=True)

    async def setup_hook(self):
        """Initializes database, loads cogs, and initializes scheduler."""
        # 0. Global asyncio background task exception handler
        try:
            loop = asyncio.get_running_loop()
            def handle_async_exception(loop, context):
                msg = context.get("message", "Unhandled exception in background asyncio task")
                exc = context.get("exception")
                logger.error(f"{msg}: {exc}", exc_info=exc)
            loop.set_exception_handler(handle_async_exception)
        except Exception as e:
            logger.debug(f"Could not attach asyncio loop exception handler: {e}")

        # 1. Initialize SQLite database schemas
        db.init_db()

        # Pre-warm AI client singletons at startup so heavy imports occur BEFORE connecting to gateway
        try:
            from ai.gemini_service import get_gemini_client
            get_gemini_client()
        except Exception as e:
            logger.debug(f"Gemini client startup warmup: {e}")

        try:
            from ai.groq_service import get_groq_client
            get_groq_client()
        except Exception as e:
            logger.debug(f"Groq client startup warmup: {e}")

        # 2. Load modular cogs
        for ext in EXTENSIONS:
            try:
                await self.load_extension(ext)
                logger.info(f"Loaded extension: {ext}")
            except Exception as e:
                logger.error(f"Failed to load extension {ext}: {e}", exc_info=True)

        # 3. Initialize background scheduler
        self.scheduler = WinterArcScheduler(self)

        # 4. Global slash command tree error handler
        async def on_tree_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
            cmd_name = interaction.command.name if interaction.command else "unknown"
            user_info = f"{interaction.user} (ID: {interaction.user.id})"
            guild_name = getattr(interaction.guild, "name", "DM")
            channel_name = getattr(interaction.channel, "name", "unknown")

            if isinstance(error, discord.app_commands.CommandOnCooldown):
                logger.info(f"Command '/{cmd_name}' by {user_info} rejected: on cooldown ({error.retry_after:.1f}s remaining).")
                msg = f"⏳ You're on cooldown. Try again in `{error.retry_after:.1f}s`."
                try:
                    if interaction.response.is_done():
                        await interaction.followup.send(msg, ephemeral=True)
                    else:
                        await interaction.response.send_message(msg, ephemeral=True)
                except Exception as send_err:
                    logger.warning(f"Could not send cooldown message to {user_info}: {send_err}")
                return
            elif isinstance(error, discord.app_commands.MissingPermissions):
                logger.warning(f"Command '/{cmd_name}' by {user_info} rejected: missing permissions in '{guild_name}'.")
                msg = "🚫 You need **Administrator** permissions to execute this command."
                try:
                    if interaction.response.is_done():
                        await interaction.followup.send(msg, ephemeral=True)
                    else:
                        await interaction.response.send_message(msg, ephemeral=True)
                except Exception as send_err:
                    logger.warning(f"Could not send missing permissions message to {user_info}: {send_err}")
                return
            elif isinstance(error, discord.app_commands.BotMissingPermissions):
                missing = ", ".join(error.missing_permissions)
                logger.warning(f"Command '/{cmd_name}' cannot execute: bot missing permissions '{missing}' in '{guild_name}'.")
                msg = f"🚫 I am missing the required permissions in this channel: `{missing}`."
                try:
                    if interaction.response.is_done():
                        await interaction.followup.send(msg, ephemeral=True)
                    else:
                        await interaction.response.send_message(msg, ephemeral=True)
                except Exception as send_err:
                    logger.warning(f"Could not send bot missing permissions message to {user_info}: {send_err}")
                return
            elif isinstance(error, discord.app_commands.CheckFailure):
                logger.info(f"Command '/{cmd_name}' by {user_info} check failed in '{guild_name}'.")
                msg = "❌ Command check failed. Ensure you are enrolled via `/enroll`."
                try:
                    if interaction.response.is_done():
                        await interaction.followup.send(msg, ephemeral=True)
                    else:
                        await interaction.response.send_message(msg, ephemeral=True)
                except Exception as send_err:
                    logger.warning(f"Could not send check failure message to {user_info}: {send_err}")
                return

            orig = getattr(error, "original", error)
            if (
                isinstance(orig, (discord.errors.NotFound, discord.errors.InteractionResponded))
                or (isinstance(orig, discord.errors.HTTPException) and getattr(orig, "code", None) in (10062, 40060))
                or interaction.is_expired()
            ):
                logger.debug(
                    f"Interaction for '/{cmd_name}' expired or was cancelled by Discord ({orig}). User: {user_info} in '{guild_name}' #{channel_name}"
                )
                return

            if isinstance(orig, discord.errors.Forbidden):
                logger.warning(f"Forbidden error executing '/{cmd_name}' for {user_info} in '{guild_name}': {orig}")
                msg = "🚫 Discord permission error: I do not have permission to post or edit messages here."
                try:
                    if interaction.response.is_done():
                        await interaction.followup.send(msg, ephemeral=True)
                    else:
                        await interaction.response.send_message(msg, ephemeral=True)
                except Exception:
                    pass
                return

            logger.error(
                f"Slash command '/{cmd_name}' failed for {user_info} in '{guild_name}' #{channel_name}: {error}",
                exc_info=error
            )
            msg = "❌ An unexpected error occurred while executing this command."
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
            except Exception as send_err:
                logger.warning(f"Could not send error response for '/{cmd_name}' to {user_info}: {send_err}")

        self.tree.on_error = on_tree_error

        # 5. Global slash command tree synchronization if application_id is available
        if self.application_id:
            try:
                synced = await self.tree.sync()
                self._synced = True
                logger.info(f"Slash command tree synchronized ({len(synced)} commands registered).")
            except Exception as e:
                logger.error(f"Failed to sync slash commands in setup_hook: {e}")

    async def on_ready(self):
        """Called when gateway connection is established."""
        if getattr(self, "_has_started", False):
            logger.info("🔁 Discord Gateway connection resumed. Active session and command state preserved.")
            return

        self._has_started = True

        logger.info("=" * 60)
        logger.info(f"🐺 AMAROK IS ACTIVE: Online as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} Discord server(s):")
        for g in self.guilds:
            logger.info(f"  • {g.name} (ID: {g.id}) - {g.member_count} members")
        logger.info("=" * 60)

        # Check and purge leftover guild-scoped commands only if any actually exist
        for g in self.guilds:
            try:
                existing_guild_cmds = await self.tree.fetch_commands(guild=g)
                if existing_guild_cmds:
                    self.tree.clear_commands(guild=g)
                    await self.tree.sync(guild=g)
                    logger.info(f"🧹 Purged {len(existing_guild_cmds)} legacy guild-scoped command duplicate(s) from '{g.name}'.")
                else:
                    logger.debug(f"Guild '{g.name}' has 0 guild-scoped commands; skipping redundant purge.")
            except Exception as e:
                logger.warning(f"Could not check/purge guild commands for {g.name}: {e}")

        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.competing,
                name="Winter Arc (500 pts daily)"
            ),
            status=discord.Status.online
        )

        if self.scheduler:
            self.scheduler.start()

        # Send activation confirmation log to server channel
        await self._send_startup_log()

    async def _send_startup_log(self):
        """Dispatches an activation log message to the server's designated channel."""
        for guild in self.guilds:
            try:
                target_channel = None
                # 1. Check database server_settings
                settings = db.get_server_settings(guild.id)
                ch_id = settings.get("channel_id")
                if ch_id:
                    target_channel = guild.get_channel(ch_id)

                # 2. Check WINTER_ARC_CHANNEL_ID, LOG_CHANNEL_ID, or DAILY_RESULTS_CHANNEL_ID env vars
                if not target_channel:
                    from config import DEFAULT_CHANNEL_ID
                    env_log_id = os.getenv("WINTER_ARC_CHANNEL_ID") or os.getenv("LOG_CHANNEL_ID") or os.getenv("DAILY_RESULTS_CHANNEL_ID") or str(DEFAULT_CHANNEL_ID)
                    if env_log_id and env_log_id.strip().isdigit() and int(env_log_id.strip()) != 0:
                        target_channel = guild.get_channel(int(env_log_id.strip()))

                # 3. Fallback: discover #server_logs, #winter-arc, or #bot_chat
                if not target_channel:
                    for keyword in ["server_logs", "winter-arc", "bot_chat"]:
                        for ch in guild.text_channels:
                            if keyword in ch.name.lower():
                                perms = ch.permissions_for(guild.me)
                                if perms.send_messages:
                                    target_channel = ch
                                    break
                        if target_channel:
                            break

                if target_channel:
                    embed = discord.Embed(
                        title="🐺 Winter Arc • Systems Active",
                        description=(
                            "The flame burns against the cold. **Winter Arc systems are online and active.**\n\n"
                            "• All 12-rank leveling & streak trackers are armed.\n"
                            "• AI Grind & Workout logging active (`/quick`, `/grind`).\n"
                            "• Run `/help` or `/today` to inspect your daily disciplines."
                        ),
                        color=0x00D2FF
                    )
                    latency = round(self.latency * 1000, 1) if self.latency else 0.0
                    embed.add_field(name="Gateway Latency", value=f"`{latency} ms`", inline=True)
                    embed.add_field(name="Enrolled Warriors", value=f"`{len(db.get_enrolled_users())}`", inline=True)
                    embed.set_footer(text="Winter Arc • Discipline over motivation")
                    await target_channel.send(embed=embed)
                    logger.info(f"Startup log message dispatched to #{target_channel.name} in {guild.name}")
            except Exception as e:
                logger.warning(f"Could not send startup log in {guild.name}: {e}")

    async def on_message(self, message: discord.Message):
        """Processes commands and handles subtle mascot reactions."""
        if message.author.bot or not message.content:
            return

        # Subtle mascot reactions when replied to or mentioned
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


async def shutdown(bot_instance: WinterArcBot):
    """Graceful shutdown handler for SIGTERM and SIGINT."""
    logger.info("Shutdown signal received. Closing scheduler and gateway connection...")
    if bot_instance.scheduler:
        bot_instance.scheduler.stop()
    await bot_instance.close()
    logger.info("Winter Arc Bot closed cleanly.")


def handle_signals(bot_instance: WinterArcBot, loop: asyncio.AbstractEventLoop):
    """Registers POSIX termination signals for graceful shutdown."""
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(bot_instance)))
        except (NotImplementedError, RuntimeError):
            # Fallback for non-main thread or unsupported platforms
            signal.signal(sig, lambda *_: asyncio.create_task(shutdown(bot_instance)))


async def main():
    async with bot:
        loop = asyncio.get_running_loop()
        handle_signals(bot, loop)
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.error("❌ DISCORD_TOKEN is not set in your .env file!")
        sys.exit(1)

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Winter Arc Bot process terminated.")
