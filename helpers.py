"""
helpers.py - Shared Bot Utilities, Guards, and Autocomplete Providers

Provides reusable functions across cogs and scheduler:
- Enrollment guard (require_enrolled)
- Task name autocomplete provider
- Server Winter Arc role resolution and creation
- Non-blocking emoji reactions
"""

import logging
from typing import List, Optional
import discord
from discord import app_commands

import database as db
from config import DEFAULT_ROLE_ID

logger = logging.getLogger("winter_arc.helpers")


async def require_enrolled(interaction: discord.Interaction) -> bool:
    """Verifies that the user is enrolled in Winter Arc before allowing command execution."""
    if not db.is_user_enrolled(interaction.user.id):
        embed = discord.Embed(
            title="🚫 Not Enrolled in Winter Arc",
            description=(
                f"Hey {interaction.user.mention}, you haven't joined the Winter Arc yet!\n\n"
                "Type **/enroll** to enter the challenge, receive the role, and start logging."
            ),
            color=0xE74C3C
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False
    return True


async def task_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Provides autocomplete choices for active challenge tasks."""
    tasks = db.get_active_tasks()
    choices = []
    for t in tasks:
        if current.lower() in t["name"].lower():
            target_disp = int(t["target"]) if t["target"].is_integer() else t["target"]
            choices.append(app_commands.Choice(name=f"{t['name']} (target: {target_disp} {t['unit']})", value=t["name"]))
    return choices[:25]


async def get_or_create_arc_role(guild: discord.Guild) -> Optional[discord.Role]:
    """Finds configured role, or finds an existing 'Winter Arc' role, or auto-creates one."""
    settings = db.get_server_settings(guild.id)
    role_id = settings.get("role_id", 0) or DEFAULT_ROLE_ID
    if role_id:
        role = guild.get_role(role_id)
        if role:
            return role

    # Fallback 1: Look for existing role named "Winter Arc"
    for r in guild.roles:
        if r.name.lower() in ["winter arc", "winterarc", "the winter arc"]:
            db.set_server_role(guild.id, r.id)
            return r

    # Fallback 2: Auto-create "Winter Arc" role if bot has Manage Roles permission
    if guild.me.guild_permissions.manage_roles:
        try:
            new_role = await guild.create_role(
                name="Winter Arc",
                color=discord.Color.from_rgb(0, 210, 255),  # Frost Cyan
                hoist=True,
                mentionable=True,
                reason="Auto-created by Winter Arc Bot for challenge participants."
            )
            db.set_server_role(guild.id, new_role.id)
            logger.info(f"Auto-created 'Winter Arc' role (ID {new_role.id}) in '{guild.name}'")
            return new_role
        except Exception as e:
            logger.warning(f"Could not auto-create Winter Arc role in {guild.name}: {e}")

    return None


async def safe_react(interaction: discord.Interaction, *emojis: str):
    """Safely adds reactions to the original interaction response message without crashing."""
    try:
        msg = await interaction.original_response()
        for emoji in emojis:
            await msg.add_reaction(emoji)
    except Exception as e:
        logger.debug(f"Could not add reaction to interaction response: {e}")
