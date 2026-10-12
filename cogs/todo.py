"""
cogs/todo.py - Modern Standalone Todo & Smart Reminder Cog

Completely isolated from Winter Arc. Uses dedicated todo.db with:
- Relative user task numbering (#1, #2, ...)
- Smart recurring reminders (with optional 'until')
- 15-item scrollable pagination & 7-day auto-retained trash (T1, T2, ...)
- DND quiet hours protection
- Task assignment with Accept/Decline flow
"""

import time
import logging
from typing import Optional, List
import discord
from discord import app_commands
from discord.ext import commands

import todo_db as db
import todo_parser as parser
from todo_reminders import TodoReminderService
from ui.todo_views import (
    TodoListView,
    TaskAssignmentView,
    TodoIncognitoView,
    build_todo_incognito_embed,
    format_priority_badge,
    build_todo_list_embed,
    TaskDetailView,
    build_task_detail_embed,
)
from config import BOT_TZ

logger = logging.getLogger("winter_arc.cogs.todo")


async def todo_remind_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> List[app_commands.Choice[str]]:
    """Contextual autocomplete suggestions for reminder schedule input."""
    presets = [
        ("⏰ in 15 mins", "in 15 mins"),
        ("⏰ in 30 mins", "in 30 mins"),
        ("⏰ in 1 hour", "in 1 hour"),
        ("⏰ in 2 hours", "in 2 hours"),
        ("🔁 3 times a day", "3 times a day"),
        ("🔁 5 times a day", "5 times a day"),
        ("🔁 every hour", "every hour"),
        ("🔁 every 2 hours", "every 2 hours"),
        ("🔁 every 30 mins", "every 30 mins"),
        ("🔁 every hour after 6pm", "every hour after 6pm"),
        ("🌅 tomorrow 9:00 AM", "tomorrow 9:00"),
        ("🌆 tomorrow 6:00 PM", "tomorrow 18:00"),
        ("🌙 today 18:00", "today 18:00"),
        ("🌙 today 21:00", "today 21:00"),
    ]
    curr = (current or "").strip().lower()
    choices = []
    for label, val in presets:
        if not curr or curr in label.lower() or curr in val.lower():
            choices.append(app_commands.Choice(name=label, value=val))
        if len(choices) >= 24:
            break
    if curr and not any(c.value.lower() == curr for c in choices):
        choices.insert(0, app_commands.Choice(name=f"✍️ Custom: \"{current.strip()}\"", value=current.strip()[:100]))
    return choices[:25]


async def todo_until_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> List[app_commands.Choice[str]]:
    """Contextual autocomplete suggestions for 'until' recurring reminder stop conditions."""
    presets = [
        ("✅ done (Until marked completed)", "done"),
        ("🌙 today 20:00 (Today 8:00 PM)", "today 20:00"),
        ("🌙 today 23:59 (End of today)", "today 23:59"),
        ("🌅 tomorrow 12:00 (Tomorrow noon)", "tomorrow 12:00"),
        ("🌅 tomorrow 20:00 (Tomorrow 8:00 PM)", "tomorrow 20:00"),
        ("🌅 tomorrow 23:59 (End of tomorrow)", "tomorrow 23:59"),
        ("📅 in 3 days", "in 3 days"),
        ("📅 in 7 days", "in 7 days"),
    ]
    curr = (current or "").strip().lower()
    choices = []
    for label, val in presets:
        if not curr or curr in label.lower() or curr in val.lower():
            choices.append(app_commands.Choice(name=label, value=val))
        if len(choices) >= 24:
            break
    if curr and not any(c.value.lower() == curr for c in choices):
        choices.insert(0, app_commands.Choice(name=f"✍️ Custom: \"{current.strip()}\"", value=current.strip()[:100]))
    return choices[:25]


async def todo_delivery_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> List[app_commands.Choice[str]]:
    """Contextual delivery mode suggestions based on whether the command is run in a Server or Bot DMs."""
    curr = (current or "").strip().lower()
    if interaction.guild is None:
        # In Bot DMs: Server channel does not exist, so only DM is offered
        choices = [
            app_commands.Choice(name="🔒 Here in DM (Default)", value="dm"),
        ]
    else:
        # In Server: All 3 options available
        choices = [
            app_commands.Choice(name="📍 This Channel (Default / Off)", value="channel"),
            app_commands.Choice(name="🔒 Only DM (Private)", value="dm"),
            app_commands.Choice(name="📢 Both (Channel & DM / On)", value="both"),
        ]
    if not curr:
        return choices
    return [c for c in choices if curr in c.name.lower() or curr in c.value.lower()]


async def todo_active_tasks_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> List[app_commands.Choice[int]]:
    """Provides autocomplete dropdown of user's active tasks by relative number."""
    try:
        tasks = db.get_active_tasks(interaction.user.id)
    except Exception:
        return []
    curr = (current or "").strip().lower()
    choices = []
    for t in tasks:
        num = t.get("num", 1)
        text = t.get("task_text", "")
        prio = t.get("priority", "normal")
        prio_icon = "🔴 " if prio == "high" else ("🟡 " if prio == "medium" else "")
        label = f"#{num}: {prio_icon}{text}"
        if not curr or curr in str(num) or curr in text.lower():
            choices.append(app_commands.Choice(name=label[:100], value=num))
        if len(choices) >= 25:
            break
    return choices[:25]


async def todo_trash_tasks_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> List[app_commands.Choice[int]]:
    """Provides autocomplete dropdown of user's trashed tasks for restore."""
    try:
        tasks = db.get_trashed_tasks(interaction.user.id)
    except Exception:
        return []
    curr = (current or "").strip().lower()
    choices = []
    for t in tasks:
        num = t.get("num", 1)
        text = t.get("task_text", "")
        label = f"T{num}: {text}"
        if not curr or curr in str(num) or curr in text.lower() or curr in f"t{num}":
            choices.append(app_commands.Choice(name=label[:100], value=num))
        if len(choices) >= 25:
            break
    return choices[:25]


class TodoCog(commands.Cog, name="Todo & Reminders"):
    """Standalone Todo & Smart Reminder Management System."""

    def __init__(self, bot: commands.Bot, db_path: Optional[str] = None):
        self.bot = bot
        self.db_path = db_path
        self.reminder_service = TodoReminderService(bot, db_path=db_path)

    def _is_ephemeral(self, user_id: int) -> bool:
        """Returns True (ephemeral/private) if user is in incognito mode; False (public) if incognito is OFF."""
        return db.is_user_incognito(user_id, db_path=self.db_path)

    async def cog_load(self):
        db.init_todo_db(self.db_path)
        self.reminder_service.start()
        logger.info("TodoCog loaded and reminder ticker active.")

    async def cog_unload(self):
        self.reminder_service.stop()
        logger.info("TodoCog unloaded and reminder ticker stopped.")

    # =====================================================================
    # Slash Command Group: /todo
    # =====================================================================

    todo_group = app_commands.Group(name="todo", description="Standalone Todo & Smart Reminder System.")

    @todo_group.command(name="add", description="Add a task to your to-do list with optional smart reminders & counters.")
    @app_commands.describe(
        task="What needs to be done?",
        remind="When/how to remind? (e.g. '18:00', 'tomorrow 10:00', '7 times between 7am and 10pm', 'every 4 days at 10am')",
        until="Optional stop condition for recurring reminders (e.g. 'done', 'tomorrow 20:00')",
        count="Target goal count if tracking a counter or habit (e.g. 7 for 7 times/glasses)",
        reset="How often the counter resets back to 0",
        priority="Task importance level (High, Medium, Low)",
        dm="Where to remind? Default: Current chat. Options: 'channel' (off), 'dm' (only DM), 'both' (on)"
    )
    @app_commands.choices(priority=[
        app_commands.Choice(name="🔴 High", value="high"),
        app_commands.Choice(name="🟡 Medium", value="medium"),
        app_commands.Choice(name="⚪ Low", value="low"),
    ])
    @app_commands.choices(reset=[
        app_commands.Choice(name="🔁 Reset Everyday (at 00:00 IST)", value="daily"),
        app_commands.Choice(name="🔁 Reset Every Week (at 00:00 IST)", value="weekly"),
        app_commands.Choice(name="🚫 No Reset (Keep count until cleared)", value="none"),
    ])
    @app_commands.autocomplete(remind=todo_remind_autocomplete, until=todo_until_autocomplete, dm=todo_delivery_autocomplete)
    async def todo_add(
        self,
        interaction: discord.Interaction,
        task: str,
        remind: Optional[str] = None,
        until: Optional[str] = None,
        count: Optional[int] = None,
        reset: Optional[app_commands.Choice[str]] = None,
        priority: Optional[app_commands.Choice[str]] = None,
        dm: Optional[str] = None,
    ):
        p_val = priority.value if priority else "normal"
        reset_val = reset.value if reset else None

        is_in_dm = (interaction.guild is None)

        # Context-aware delivery mode resolution
        if dm is None or not str(dm).strip():
            delivery_mode = "dm" if is_in_dm else "channel"
        else:
            dm_raw = str(dm).strip().lower()
            if dm_raw in ["dm", "only_dm", "only dm", "true", "1", "private"]:
                delivery_mode = "dm"
            elif dm_raw in ["both", "all", "on"]:
                if is_in_dm:
                    delivery_mode = "dm"  # Graceful fallback in DMs
                else:
                    delivery_mode = "both"
            elif dm_raw in ["channel", "here", "default", "false", "0", "off"]:
                delivery_mode = "dm" if is_in_dm else "channel"
            else:
                delivery_mode = "dm" if is_in_dm else "channel"

        dm_val = (delivery_mode in ["dm", "both"])

        origin_ch = None
        if not is_in_dm and interaction.channel_id is not None:
            try:
                origin_ch = int(interaction.channel_id)
            except (ValueError, TypeError):
                origin_ch = None

        try:
            parsed = parser.parse_remind_spec(remind, until_text=until)
            counter_cfg = parser.infer_task_counter_and_reset(parsed, raw_count=count, raw_reset=reset_val)
        except ValueError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return

        new_item = db.add_task(
            user_id=interaction.user.id,
            task_text=task,
            priority=p_val,
            remind_spec=parsed["remind_spec"],
            remind_type=parsed["remind_type"],
            remind_interval_mins=parsed["remind_interval_mins"],
            remind_fixed_times=parsed["remind_fixed_times"],
            remind_window_start=parsed["remind_window_start"],
            until_spec=parsed["until_spec"],
            until_timestamp=parsed["until_timestamp"],
            dm_only=dm_val,
            delivery_mode=delivery_mode,
            origin_channel_id=origin_ch,
            next_reminder_at=parsed["next_reminder_at"],
            target_count=counter_cfg["target_count"],
            reset_period=counter_cfg["reset_period"],
            reset_interval_days=counter_cfg["reset_interval_days"],
            db_path=self.db_path,
        )

        num = new_item.get("num", 1)
        p_badge = format_priority_badge(p_val)
        p_str = f" {p_badge}" if p_badge else ""

        if delivery_mode == "both":
            ch_tag = f"<#{interaction.channel_id}>" if interaction.channel_id else "This Channel"
            delivery_str = f"📢 Both ({ch_tag} & 🔒 Direct Message)"
        elif delivery_mode == "dm":
            if is_in_dm:
                delivery_str = "🔒 Direct Message"
            else:
                delivery_str = "🔒 Private DM (Only to you)"
        else:
            ch_tag = f"<#{interaction.channel_id}>" if interaction.channel_id else "This Channel"
            delivery_str = f"💬 Current Channel ({ch_tag})"

        if is_in_dm and dm and str(dm).strip().lower() in ["both", "on", "channel", "off"]:
            delivery_str += " *(Delivered in DM; server channel unavailable)*"

        details = [
            f"• **Delivery**: {delivery_str}",
            f"• **Status**: {parsed['confirmation_msg']}"
        ]

        if counter_cfg["target_count"] > 0:
            details.append(f"• **Counter Goal**: `0/{counter_cfg['target_count']}` (open with `/todo view` or detail buttons)")

        if counter_cfg["reset_period"] != "none":
            if counter_cfg["reset_interval_days"] > 1:
                details.append(f"• **Reset Cadence**: Every {counter_cfg['reset_interval_days']} days at 00:00 IST")
            else:
                details.append(f"• **Reset Cadence**: {counter_cfg['reset_period'].title()} at 00:00 IST")

        is_eph = self._is_ephemeral(interaction.user.id)
        del_after = None if is_eph else 60.0
        resp = f"✅ Added task **`#{num}`**: **{task}**{p_str}\n" + "\n".join(details)
        await interaction.response.send_message(resp, ephemeral=is_eph, delete_after=del_after)

    @todo_group.command(name="list", description="View and manage your active tasks and 7-day trash history.")
    @app_commands.describe(filter="Filter tasks by status or priority")
    @app_commands.choices(filter=[
        app_commands.Choice(name="All Active Tasks", value="all"),
        app_commands.Choice(name="🔴 High Priority Only", value="high"),
        app_commands.Choice(name="⏰ Tasks with Reminders Only", value="reminders"),
        app_commands.Choice(name="🗑️ Trash & Completed History (Last 7 Days)", value="trash"),
    ])
    async def todo_list(
        self,
        interaction: discord.Interaction,
        filter: Optional[app_commands.Choice[str]] = None,
    ):
        f_val = filter.value if filter else "all"
        is_trash = (f_val == "trash")
        p_filter = "high" if f_val == "high" else None
        with_reminders = (f_val == "reminders")

        view = TodoListView(
            user_id=interaction.user.id,
            user=interaction.user,
            is_trash=is_trash,
            page=1,
            priority_filter=p_filter,
            with_reminders_only=with_reminders,
            db_path=self.db_path,
        )

        embed = view.build_current_embed()
        is_eph = self._is_ephemeral(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=is_eph)
        if not is_eph:
            try:
                view.message = await interaction.original_response()
            except Exception:
                pass

    @todo_group.command(name="view", description="Open the interactive Control Center for a task.")
    @app_commands.describe(id="The relative task number (e.g. 1 for #1)")
    @app_commands.autocomplete(id=todo_active_tasks_autocomplete)
    async def todo_view(self, interaction: discord.Interaction, id: int):
        is_eph = self._is_ephemeral(interaction.user.id)
        del_after = None if is_eph else 60.0
        task = db.get_task_by_relative_num(interaction.user.id, id, db_path=self.db_path)
        if not task:
            await interaction.response.send_message(
                f"❌ Task **`#{id}`** not found. Run `/todo list` to check your current task numbers.",
                ephemeral=is_eph,
                delete_after=del_after
            )
            return

        view = TaskDetailView(task_id=task["id"], user_id=interaction.user.id, parent_view=None, db_path=self.db_path)
        embed = build_task_detail_embed(task, user=interaction.user)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=is_eph)
        if not is_eph:
            try:
                view.message = await interaction.original_response()
            except Exception:
                pass

    @todo_group.command(name="done", description="Mark a task completed for today or move it to 7-day trash.")
    @app_commands.describe(id="The relative task number (e.g. 1 for #1)")
    @app_commands.autocomplete(id=todo_active_tasks_autocomplete)
    async def todo_done(self, interaction: discord.Interaction, id: int):
        is_eph = self._is_ephemeral(interaction.user.id)
        del_after = None if is_eph else 60.0
        res = db.mark_task_done(interaction.user.id, id, db_path=self.db_path)
        if res:
            if res.get("reset_period", "none") != "none":
                await interaction.response.send_message(
                    f"✅ **Completed for today!** Task **`#{id}`** (*{res['task_text']}*) marked done.\n"
                    f"-# Next reminder will fire on schedule. Resets at 00:00 IST.",
                    ephemeral=is_eph,
                    delete_after=del_after
                )
            else:
                await interaction.response.send_message(
                    f"✅ **Completed!** Task **`#{id}`** (*{res['task_text']}*) marked done and moved to trash.\n"
                    f"-# Kept in trash for 7 days. Restore anytime via `/todo restore`.",
                    ephemeral=is_eph,
                    delete_after=del_after
                )
        else:
            await interaction.response.send_message(
                f"❌ Task **`#{id}`** not found. Run `/todo list` to check your current task numbers.",
                ephemeral=is_eph,
                delete_after=del_after
            )

    @todo_group.command(name="silence", description="Turn off future reminders for a task while keeping it on your list.")
    @app_commands.describe(id="The relative task number (e.g. 1 for #1)")
    @app_commands.autocomplete(id=todo_active_tasks_autocomplete)
    async def todo_silence(self, interaction: discord.Interaction, id: int):
        is_eph = self._is_ephemeral(interaction.user.id)
        del_after = None if is_eph else 60.0
        res = db.silence_task(interaction.user.id, id, db_path=self.db_path)
        if res:
            await interaction.response.send_message(
                f"🔕 **Reminders Silenced!** Task **`#{id}`** (*{res['task_text']}*) will no longer send alerts.\n"
                f"-# The task remains active on your `/todo list`.",
                ephemeral=is_eph,
                delete_after=del_after
            )
        else:
            await interaction.response.send_message(
                f"❌ Task **`#{id}`** not found.",
                ephemeral=is_eph,
                delete_after=del_after
            )

    @todo_group.command(name="delete", description="Remove an active task directly to 7-day trash.")
    @app_commands.describe(id="The relative task number (e.g. 1 for #1)")
    @app_commands.autocomplete(id=todo_active_tasks_autocomplete)
    async def todo_delete(self, interaction: discord.Interaction, id: int):
        is_eph = self._is_ephemeral(interaction.user.id)
        del_after = None if is_eph else 60.0
        res = db.delete_task(interaction.user.id, id, db_path=self.db_path)
        if res:
            await interaction.response.send_message(
                f"🗑️ Task **`#{id}`** (*{res['task_text']}*) moved to trash.\n"
                f"-# You can restore it from trash within 7 days via `/todo restore`.",
                ephemeral=is_eph,
                delete_after=del_after
            )
        else:
            await interaction.response.send_message(f"❌ Task **`#{id}`** not found.", ephemeral=is_eph, delete_after=del_after)

    @todo_group.command(name="restore", description="Restore a task from 7-day trash back to your active list.")
    @app_commands.describe(trash_id="The trash number (e.g. 1 for T1)")
    @app_commands.autocomplete(trash_id=todo_trash_tasks_autocomplete)
    async def todo_restore(self, interaction: discord.Interaction, trash_id: int):
        is_eph = self._is_ephemeral(interaction.user.id)
        del_after = None if is_eph else 60.0
        res = db.restore_task(interaction.user.id, trash_id, db_path=self.db_path)
        if res:
            await interaction.response.send_message(
                f"♻️ Restored task **`T{trash_id}`** (*{res['task_text']}*) back to your active list as **`#{res.get('num', 1)}`**.",
                ephemeral=is_eph,
                delete_after=del_after
            )
        else:
            await interaction.response.send_message(
                f"❌ Trash item **`T{trash_id}`** not found. Run `/todo list filter: Trash` to inspect trash.",
                ephemeral=is_eph,
                delete_after=del_after
            )

    @todo_group.command(name="edit", description="Modify an existing task's description, priority, reminder, delivery, or counter.")
    @app_commands.describe(
        id="The relative task number (e.g. 1 for #1)",
        task="New task description",
        priority="Updated priority level",
        remind="New reminder schedule (e.g. 'everyday at 4:30PM')",
        dm="Delivery mode: 'channel', 'dm', or 'both'",
        until="Task deadline or expiration date (e.g. 'until next Friday')",
        count="Target goal count (e.g. 5, or 0 to turn off counter)",
        reset="Reset schedule cadence",
        remove_reminder="Remove reminder schedule completely (True/False)",
        remove_until="Remove deadline / expiration date completely (True/False)"
    )
    @app_commands.choices(priority=[
        app_commands.Choice(name="🔴 High", value="high"),
        app_commands.Choice(name="🟡 Medium", value="medium"),
        app_commands.Choice(name="⚪ Low", value="low"),
    ])
    @app_commands.choices(reset=[
        app_commands.Choice(name="🔁 Reset Every Day (at 00:00 IST)", value="daily"),
        app_commands.Choice(name="🔁 Reset Every Week (at 00:00 IST)", value="weekly"),
        app_commands.Choice(name="🚫 No Reset (Keep count until cleared)", value="none"),
    ])
    @app_commands.autocomplete(
        id=todo_active_tasks_autocomplete,
        remind=todo_remind_autocomplete,
        dm=todo_delivery_autocomplete,
        until=todo_until_autocomplete
    )
    async def todo_edit(
        self,
        interaction: discord.Interaction,
        id: int,
        task: Optional[str] = None,
        priority: Optional[app_commands.Choice[str]] = None,
        remind: Optional[str] = None,
        dm: Optional[str] = None,
        until: Optional[str] = None,
        count: Optional[int] = None,
        reset: Optional[app_commands.Choice[str]] = None,
        remove_reminder: Optional[bool] = False,
        remove_until: Optional[bool] = False,
    ):
        is_eph = self._is_ephemeral(interaction.user.id)
        p_val = priority.value if priority else None
        reset_val = reset.value if reset else None

        is_in_dm = (interaction.guild is None)
        delivery_mode = None
        dm_val = None
        origin_ch = None

        if dm is not None and str(dm).strip():
            dm_raw = str(dm).strip().lower()
            if dm_raw in ["dm", "only_dm", "only dm", "true", "1", "private"]:
                delivery_mode = "dm"
            elif dm_raw in ["both", "all", "on"]:
                delivery_mode = "dm" if is_in_dm else "both"
            elif dm_raw in ["channel", "here", "default", "false", "0", "off"]:
                delivery_mode = "dm" if is_in_dm else "channel"
            else:
                delivery_mode = "dm" if is_in_dm else "channel"

            dm_val = (delivery_mode in ["dm", "both"])
            if not is_in_dm and interaction.channel_id is not None:
                origin_ch = interaction.channel_id

        parsed = None
        if remind and not remove_reminder:
            parsed = parser.parse_remind_spec(remind)

        until_spec = None
        until_ts = None
        if until and not remove_until:
            until_spec, until_ts = parser.parse_until_spec(until)

        res = db.edit_task(
            user_id=interaction.user.id,
            num=id,
            new_task_text=task,
            new_priority=p_val,
            new_remind_spec=parsed["remind_spec"] if parsed else None,
            remove_reminder=bool(remove_reminder),
            next_reminder_at=parsed["next_reminder_at"] if parsed else None,
            remind_type=parsed["remind_type"] if parsed else None,
            remind_interval_mins=parsed["remind_interval_mins"] if parsed else None,
            remind_fixed_times=parsed["remind_fixed_times"] if parsed else None,
            remind_window_start=parsed["remind_window_start"] if parsed else None,
            until_spec=until_spec,
            until_timestamp=until_ts,
            remove_until=bool(remove_until),
            target_count=count,
            reset_period=reset_val,
            delivery_mode=delivery_mode,
            dm_only=dm_val,
            origin_channel_id=origin_ch,
            db_path=self.db_path,
        )

        del_after = None if is_eph else 60.0
        if res:
            changes = []
            if task:
                changes.append(f"• **Task**: {res['task_text']}")
            if priority:
                changes.append(f"• **Priority**: {format_priority_badge(p_val)}")
            if remove_reminder:
                changes.append("• **Reminders**: 🔕 Removed")
            elif parsed:
                changes.append(f"• **Reminder**: {parsed['confirmation_msg']}")
            if delivery_mode:
                if delivery_mode == "both":
                    ch_tag = f"<#{interaction.channel_id}>" if interaction.channel_id else "Channel"
                    d_desc = f"📢 Both ({ch_tag} & 🔒 DM)"
                elif delivery_mode == "dm":
                    d_desc = "🔒 Direct Message"
                else:
                    ch_tag = f"<#{interaction.channel_id}>" if interaction.channel_id else "This Channel"
                    d_desc = f"💬 Current Channel ({ch_tag})"
                changes.append(f"• **Delivery**: {d_desc}")
            if remove_until:
                changes.append("• **Deadline**: Cleared")
            elif until and until_spec:
                deadline_str = f"• **Deadline**: {until_spec}"
                if until_ts:
                    deadline_str += f" (<t:{until_ts}:f>)"
                changes.append(deadline_str)
            if count is not None:
                if count > 0:
                    changes.append(f"• **Goal Count**: `0/{count}`")
                else:
                    changes.append("• **Goal Count**: Turned off (Checkmark mode)")
            if reset is not None:
                changes.append(f"• **Reset**: {reset.name}")

            summary = "\n".join(changes) if changes else "No fields changed."
            await interaction.response.send_message(
                f"✏️ Updated task **`#{id}`**: **{res['task_text']}**\n{summary}",
                ephemeral=is_eph,
                delete_after=del_after
            )
        else:
            await interaction.response.send_message(f"❌ Task **`#{id}`** not found.", ephemeral=is_eph, delete_after=del_after)

    @todo_group.command(name="assign", description="Assign a task to a friend with an interactive Accept/Decline flow.")
    @app_commands.describe(
        member="Friend to assign task to",
        task="Task description",
        remind="Optional reminder schedule (e.g. 'everyday at 4:30PM')",
        dm="Delivery mode: 'channel', 'dm', or 'both'",
        until="Task deadline or expiration date (e.g. 'until next Friday')",
        count="Target goal count (e.g. 5 reps)",
        reset="Reset schedule cadence",
        priority="Priority level"
    )
    @app_commands.choices(priority=[
        app_commands.Choice(name="🔴 High", value="high"),
        app_commands.Choice(name="🟡 Medium", value="medium"),
        app_commands.Choice(name="⚪ Low", value="low"),
    ])
    @app_commands.choices(reset=[
        app_commands.Choice(name="🔁 Reset Every Day (at 00:00 IST)", value="daily"),
        app_commands.Choice(name="🔁 Reset Every Week (at 00:00 IST)", value="weekly"),
        app_commands.Choice(name="🚫 No Reset (Keep count until cleared)", value="none"),
    ])
    @app_commands.autocomplete(
        remind=todo_remind_autocomplete,
        dm=todo_delivery_autocomplete,
        until=todo_until_autocomplete
    )
    async def todo_assign(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        task: str,
        remind: Optional[str] = None,
        until: Optional[str] = None,
        count: Optional[int] = None,
        reset: Optional[app_commands.Choice[str]] = None,
        priority: Optional[app_commands.Choice[str]] = None,
        dm: Optional[str] = None,
    ):
        if member.id == interaction.user.id:
            await interaction.response.send_message("❌ You cannot assign a task to yourself. Use `/todo add` instead.", ephemeral=True)
            return
        if member.bot:
            await interaction.response.send_message("❌ You cannot assign tasks to bots.", ephemeral=True)
            return

        p_val = priority.value if priority else "normal"
        reset_val = reset.value if reset else None

        is_in_dm = (interaction.guild is None)

        # Context-aware delivery mode resolution
        if dm is None or not str(dm).strip():
            delivery_mode = "dm" if is_in_dm else "channel"
        else:
            dm_raw = str(dm).strip().lower()
            if dm_raw in ["dm", "only_dm", "only dm", "true", "1", "private"]:
                delivery_mode = "dm"
            elif dm_raw in ["both", "all", "on"]:
                delivery_mode = "dm" if is_in_dm else "both"
            elif dm_raw in ["channel", "here", "default", "false", "0", "off"]:
                delivery_mode = "dm" if is_in_dm else "channel"
            else:
                delivery_mode = "dm" if is_in_dm else "channel"

        dm_val = (delivery_mode in ["dm", "both"])
        origin_ch = None
        if not is_in_dm and interaction.channel_id is not None:
            origin_ch = interaction.channel_id

        try:
            parsed = parser.parse_remind_spec(remind, until_text=until)
            counter_cfg = parser.infer_task_counter_and_reset(
                parsed,
                raw_count=count,
                raw_reset=reset_val
            )
        except ValueError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return

        until_spec = parsed["until_spec"]
        until_ts = parsed["until_timestamp"]

        task_data = {
            "task_text": task,
            "priority": p_val,
            "remind_spec": parsed["remind_spec"],
            "remind_type": parsed["remind_type"],
            "remind_interval_mins": parsed["remind_interval_mins"],
            "remind_fixed_times": parsed["remind_fixed_times"],
            "remind_window_start": parsed["remind_window_start"],
            "until_spec": until_spec,
            "until_timestamp": until_ts,
            "next_reminder_at": parsed["next_reminder_at"],
            "target_count": counter_cfg["target_count"],
            "reset_period": counter_cfg["reset_period"],
            "reset_interval_days": counter_cfg["reset_interval_days"],
            "dm_only": dm_val,
            "delivery_mode": delivery_mode,
            "origin_channel_id": origin_ch,
        }

        view = TaskAssignmentView(
            assignee_id=member.id,
            assigner_id=interaction.user.id,
            task_data=task_data,
            db_path=self.db_path,
        )

        meta_items = []
        if p_val and p_val != "normal":
            meta_items.append(f"Priority: `{p_val.title()}`")
        if parsed["remind_spec"]:
            meta_items.append(f"Reminder: `{parsed['remind_spec']}`")
        if counter_cfg["target_count"] > 0:
            reset_txt = f"/{counter_cfg['reset_period']}" if counter_cfg["reset_period"] != "none" else ""
            meta_items.append(f"Goal: `{counter_cfg['target_count']}{reset_txt}`")
        if until_spec:
            meta_items.append(f"Deadline: `{until_spec}`")

        meta_line = f"\n> *{' • '.join(meta_items)}*" if meta_items else ""

        channel_msg = (
            f"<@{member.id}>, you were assigned a new task by {interaction.user.mention}!\n"
            f"> **{task}**{meta_line}"
        )

        invite_msg = (
            f"**Task Assignment Request**\n"
            f"**From**: <@{interaction.user.id}>\n"
            f"> **{task}**{meta_line}\n\n"
            f"Click below to accept or decline:"
        )

        # 1. Send in channel with ping
        await interaction.response.send_message(
            content=channel_msg,
            view=view
        )

        # 2. Also dispatch to friend's DM
        try:
            dm_view = TaskAssignmentView(
                assignee_id=member.id,
                assigner_id=interaction.user.id,
                task_data=task_data,
                db_path=self.db_path,
            )
            await member.send(content=invite_msg, view=dm_view)
        except Exception:
            pass

    @todo_group.command(name="dnd", description="Configure Do Not Disturb quiet hours (no pings/DMs during this window).")
    @app_commands.describe(
        action="What would you like to configure?",
        start="Quiet window start time (e.g. '22:00' or '10 PM')",
        end="Quiet window end time (e.g. '06:00' or '6 AM')"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Set DND Window (e.g. 10 PM to 6 AM)", value="set"),
        app_commands.Choice(name="Turn Off DND", value="off"),
        app_commands.Choice(name="View Current DND Status", value="status"),
    ])
    async def todo_dnd(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        start: Optional[str] = None,
        end: Optional[str] = None,
    ):
        act = action.value

        is_eph = self._is_ephemeral(interaction.user.id)
        if act == "off":
            db.update_user_settings(interaction.user.id, dnd_enabled=False, db_path=self.db_path)
            await interaction.response.send_message("🔕 **DND Mode Disabled.** Reminders will fire anytime they are due.", ephemeral=is_eph)
            return

        if act == "status":
            st = db.get_user_settings(interaction.user.id, db_path=self.db_path)
            is_on = bool(st.get("dnd_enabled"))
            s_time = st.get("dnd_start", "22:00")
            e_time = st.get("dnd_end", "06:00")
            state_text = f"🟢 **Active** (`{s_time}` to `{e_time}`)" if is_on else "⚪ **Disabled**"
            await interaction.response.send_message(
                f"🌙 **Do Not Disturb (DND) Status**:\n"
                f"• State: {state_text}\n"
                f"• Timezone: `{st.get('timezone', 'Asia/Kolkata')}`\n\n"
                f"-# Configure using `/todo dnd action: Set start: \"22:00\" end: \"06:00\"`",
                ephemeral=is_eph
            )
            return

        # Action: 'set'
        t_start = parser.parse_time_component(start) if start else (22, 0)
        t_end = parser.parse_time_component(end) if end else (6, 0)

        if not t_start or not t_end:
            await interaction.response.send_message(
                "❌ Could not parse times. Please format like `22:00` (or `10 PM`) and `06:00` (or `6 AM`).",
                ephemeral=is_eph
            )
            return

        s_formatted = f"{t_start[0]:02d}:{t_start[1]:02d}"
        e_formatted = f"{t_end[0]:02d}:{t_end[1]:02d}"

        db.update_user_settings(
            user_id=interaction.user.id,
            dnd_enabled=True,
            dnd_start=s_formatted,
            dnd_end=e_formatted,
            db_path=self.db_path,
        )

        await interaction.response.send_message(
            f"🌙 **DND Quiet Hours Enabled!**\n"
            f"• **Quiet Window**: `{s_formatted}` to `{e_formatted}` daily.\n"
            f"• During this window, reminders will be silently postponed to avoid waking or disturbing you.",
            ephemeral=is_eph
        )

    @todo_group.command(name="clear", description="Instantly purge all completed and trashed items.")
    @app_commands.describe(confirm="Confirm permanent deletion of trash")
    async def todo_clear(self, interaction: discord.Interaction, confirm: bool = False):
        is_eph = self._is_ephemeral(interaction.user.id)
        del_after = None if is_eph else 60.0
        if not confirm:
            await interaction.response.send_message(
                "⚠️ This will permanently delete all tasks in your trash! Run `/todo clear confirm: True` to proceed.",
                ephemeral=is_eph,
                delete_after=del_after
            )
            return

        count = db.clear_trash(interaction.user.id, db_path=self.db_path)
        await interaction.response.send_message(
            f"🧹 **Trash Cleared.** Permanently removed **{count}** trashed task(s).",
            ephemeral=is_eph,
            delete_after=del_after
        )

    @todo_group.command(name="incognito", description="Manage or check Incognito Mode for your /todo commands.")
    @app_commands.describe(
        mode="Set Incognito Mode (On, Off, or Check)",
        user="Optional user to check incognito status for"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Turn ON", value="on"),
        app_commands.Choice(name="Turn OFF", value="off"),
        app_commands.Choice(name="Check Status", value="check"),
    ])
    async def todo_incognito(
        self,
        interaction: discord.Interaction,
        mode: Optional[app_commands.Choice[str]] = None,
        user: Optional[discord.User] = None,
    ):
        target_mode = mode.value if mode else None

        # 1. If checking another user, or mode == 'check'
        if user is not None or target_mode == "check":
            target = user if user is not None else interaction.user
            target_incog = db.is_user_incognito(target.id, db_path=self.db_path)
            state_text = "ON" if target_incog else "OFF"
            emoji = "🔒" if target_incog else "🔓"
            if target.id == interaction.user.id:
                msg = f"{emoji} Your Incognito Mode is **{state_text}**"
            else:
                msg = f"{emoji} **{target.display_name}** is in Incognito Mode: **{state_text}**"
            await interaction.response.send_message(msg, ephemeral=False)
            return

        # 2. Turn ON
        if target_mode == "on":
            db.set_user_incognito(interaction.user.id, True, db_path=self.db_path)
            await interaction.response.send_message("🔒 Incognito Mode Turned ON", ephemeral=False)
            return

        # 3. Turn OFF
        if target_mode == "off":
            db.set_user_incognito(interaction.user.id, False, db_path=self.db_path)
            await interaction.response.send_message("🔓 Incognito Mode Turned OFF", ephemeral=False)
            return

        # 4. Default: Interactive card with Turn On and Turn Off buttons
        current_state = db.is_user_incognito(interaction.user.id, db_path=self.db_path)
        embed = build_todo_incognito_embed(interaction.user, is_incognito=current_state)
        view = TodoIncognitoView(interaction.user.id, current_state=current_state, db_path=self.db_path)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(TodoCog(bot))
