"""
helpers.py - Shared Bot Utilities, Guards, and Autocomplete Providers

Provides reusable functions across cogs and scheduler:
- Enrollment guard (require_enrolled)
- Task name autocomplete provider
- Server Winter Arc role resolution and creation
- Non-blocking emoji reactions
"""

import logging
from typing import List, Optional, Any
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
    """Provides autocomplete choices for active challenge tasks with discipline icons and targets."""
    icons = {"push-ups": "💪", "pull-ups": "🧗", "squats": "🦵", "sit-ups": "🧘", "running": "🏃"}
    tasks = db.get_active_tasks()
    choices = []
    for t in tasks:
        if current.lower() in t["name"].lower():
            target_disp = int(t["target"]) if t["target"].is_integer() else t["target"]
            icon = icons.get(t["name"].lower(), "🎯")
            choices.append(app_commands.Choice(
                name=f"{icon} {t['name']} ({target_disp} {t['unit']})",
                value=t["name"]
            ))
    return choices[:25]


async def all_tasks_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Provides autocomplete for all tasks (active & disabled) so admins can toggle them on/off."""
    tasks = db.get_all_tasks()
    choices = []
    for t in tasks:
        if current.lower() in t["name"].lower():
            status_icon = "🟢" if t["active"] else "🔴"
            status_label = "Active" if t["active"] else "Disabled"
            choices.append(app_commands.Choice(
                name=f"{status_icon} {t['name']} ({status_label})",
                value=t["name"]
            ))
    return choices[:25]


async def unit_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Provides autocomplete for common exercise units in task creation."""
    common_units = ["reps", "km", "minutes", "seconds", "sets", "meters", "miles", "laps"]
    choices = []
    for u in common_units:
        if current.lower() in u.lower():
            choices.append(app_commands.Choice(name=u, value=u))
    return choices[:25]


async def target_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[float]]:
    """Provides autocomplete for standard daily targets."""
    presets = [5.0, 10.0, 20.0, 25.0, 30.0, 50.0, 100.0]
    choices = []
    if current:
        try:
            val = float(current)
            if val > 0 and val not in presets:
                choices.append(app_commands.Choice(name=f"Target: {val:g}", value=val))
        except ValueError:
            pass
    for p in presets:
        if not current or current in str(p) or current in f"{p:g}":
            choices.append(app_commands.Choice(name=f"Target: {p:g}", value=p))
    return choices[:25]


async def max_points_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[int]]:
    """Provides autocomplete for standard discipline point allocations."""
    presets = [50, 100, 150, 200]
    choices = []
    if current:
        try:
            val = int(current)
            if val > 0 and val not in presets:
                choices.append(app_commands.Choice(name=f"{val} points", value=val))
        except ValueError:
            pass
    for p in presets:
        if not current or current in str(p):
            choices.append(app_commands.Choice(name=f"{p} points (Standard)" if p == 100 else f"{p} points", value=p))
    return choices[:25]


async def history_days_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[int]]:
    """Provides autocomplete for history timeframe options."""
    options = [
        ("7 days (Past Week)", 7),
        ("14 days (Past 2 Weeks)", 14),
        ("21 days (Past 3 Weeks)", 21),
        ("30 days (Past Month)", 30),
    ]
    choices = []
    for label, val in options:
        if current.lower() in label.lower() or current in str(val):
            choices.append(app_commands.Choice(name=label, value=val))
    return choices[:25]


async def log_amount_autocomplete(interaction: discord.Interaction, current: Any) -> List[app_commands.Choice[float]]:
    """Provides contextual autocomplete for amount to log based on selected task."""
    selected_task = getattr(interaction.namespace, "task", "") or ""
    is_running = "run" in selected_task.lower()

    if is_running:
        presets = [1.0, 2.0, 2.5, 3.0, 5.0, 7.5, 10.0]
    else:
        presets = [10.0, 20.0, 25.0, 30.0, 50.0, 75.0, 100.0]

    choices = []
    if current is not None and str(current).strip():
        try:
            val = float(current)
            if val > 0 and val not in presets:
                unit_str = "km" if is_running else "reps"
                choices.append(app_commands.Choice(name=f"+{val:g} {unit_str}", value=val))
        except ValueError:
            pass

    curr_str = str(current).strip() if current is not None else ""
    for p in presets:
        unit_str = "km" if is_running else "reps"
        if not curr_str or curr_str in str(p) or curr_str in f"{p:g}":
            choices.append(app_commands.Choice(name=f"+{p:g} {unit_str}", value=p))

    return choices[:25]


async def set_amount_autocomplete(interaction: discord.Interaction, current: Any) -> List[app_commands.Choice[float]]:
    """Provides contextual autocomplete for set/override amounts."""
    selected_task = getattr(interaction.namespace, "task", "") or ""
    is_running = "run" in selected_task.lower()

    if is_running:
        presets = [0.0, 2.5, 5.0, 7.5, 10.0]
    else:
        presets = [0.0, 25.0, 50.0, 75.0, 100.0]

    choices = []
    if current is not None and str(current).strip():
        try:
            val = float(current)
            if val >= 0 and val not in presets:
                choices.append(app_commands.Choice(name=f"Set to {val:g}", value=val))
        except ValueError:
            pass

    curr_str = str(current).strip() if current is not None else ""
    for p in presets:
        unit_str = "km" if is_running else "reps"
        label = "0 (Reset discipline)" if p == 0.0 else f"Set to {p:g} {unit_str}"
        if not curr_str or curr_str in str(p) or curr_str in f"{p:g}":
            choices.append(app_commands.Choice(name=label, value=p))

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
