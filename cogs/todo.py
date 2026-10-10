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
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

import todo_db as db
import todo_parser as parser
from todo_reminders import TodoReminderService
from ui.todo_views import (
    TodoListView,
    TaskAssignmentView,
    format_priority_badge,
    build_todo_list_embed,
)
from config import BOT_TZ

logger = logging.getLogger("winter_arc.cogs.todo")


class TodoCog(commands.Cog, name="Todo & Reminders"):
    """Standalone Todo & Smart Reminder Management System."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reminder_service = TodoReminderService(bot)

    async def cog_load(self):
        db.init_todo_db()
        self.reminder_service.start()
        logger.info("TodoCog loaded and reminder ticker active.")

    async def cog_unload(self):
        self.reminder_service.stop()
        logger.info("TodoCog unloaded and reminder ticker stopped.")

    # =====================================================================
    # Slash Command Group: /todo
    # =====================================================================

    todo_group = app_commands.Group(name="todo", description="Standalone Todo & Smart Reminder System.")

    @todo_group.command(name="add", description="Add a task to your to-do list with optional smart reminders.")
    @app_commands.describe(
        task="What needs to be done?",
        remind="When/how to remind? (e.g. '18:00', 'tomorrow 10:00', 'every hour after 6pm', '3 times a day')",
        until="Optional stop condition for recurring reminders (e.g. 'done', 'tomorrow 20:00')",
        priority="Task importance level (High, Medium, Low)",
        dm="Send reminders via private DM (True, default) or in this channel (False)"
    )
    @app_commands.choices(priority=[
        app_commands.Choice(name="🔴 High", value="high"),
        app_commands.Choice(name="🟡 Medium", value="medium"),
        app_commands.Choice(name="⚪ Low", value="low"),
    ])
    async def todo_add(
        self,
        interaction: discord.Interaction,
        task: str,
        remind: Optional[str] = None,
        until: Optional[str] = None,
        priority: Optional[app_commands.Choice[str]] = None,
        dm: Optional[bool] = True,
    ):
        p_val = priority.value if priority else "normal"
        dm_val = True if dm is None else bool(dm)

        # Parse schedule
        parsed = parser.parse_remind_spec(remind, until_text=until)

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
            origin_channel_id=interaction.channel_id,
            next_reminder_at=parsed["next_reminder_at"],
        )

        num = new_item.get("num", 1)
        p_badge = format_priority_badge(p_val)
        p_str = f" {p_badge}" if p_badge else ""
        delivery_str = "🔒 Direct Message" if dm_val else f"💬 <#{interaction.channel_id}>"

        resp = (
            f"✅ Added task **`#{num}`**: **{task}**{p_str}\n"
            f"• **Delivery**: {delivery_str}\n"
            f"• **Status**: {parsed['confirmation_msg']}"
        )
        await interaction.response.send_message(resp, ephemeral=True)

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
        )

        embed = view.build_current_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @todo_group.command(name="done", description="Mark a task completed and move it to 7-day trash.")
    @app_commands.describe(id="The relative task number (e.g. 1 for #1)")
    async def todo_done(self, interaction: discord.Interaction, id: int):
        res = db.mark_task_done(interaction.user.id, id)
        if res:
            await interaction.response.send_message(
                f"✅ **Completed!** Task **`#{id}`** (*{res['task_text']}*) marked done and moved to trash.\n"
                f"-# All pending reminders cancelled. Kept in trash for 7 days.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Task **`#{id}`** not found. Run `/todo list` to check your current task numbers.",
                ephemeral=True
            )

    @todo_group.command(name="silence", description="Turn off future reminders for a task while keeping it on your list.")
    @app_commands.describe(id="The relative task number (e.g. 1 for #1)")
    async def todo_silence(self, interaction: discord.Interaction, id: int):
        res = db.silence_task(interaction.user.id, id)
        if res:
            await interaction.response.send_message(
                f"🔕 **Reminders Silenced!** Task **`#{id}`** (*{res['task_text']}*) will no longer send alerts.\n"
                f"-# The task remains active on your `/todo list`.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Task **`#{id}`** not found.",
                ephemeral=True
            )

    @todo_group.command(name="delete", description="Remove an active task directly to 7-day trash.")
    @app_commands.describe(id="The relative task number (e.g. 1 for #1)")
    async def todo_delete(self, interaction: discord.Interaction, id: int):
        res = db.delete_task(interaction.user.id, id)
        if res:
            await interaction.response.send_message(
                f"🗑️ Task **`#{id}`** (*{res['task_text']}*) moved to trash.\n"
                f"-# You can restore it from trash within 7 days via `/todo restore`.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(f"❌ Task **`#{id}`** not found.", ephemeral=True)

    @todo_group.command(name="restore", description="Restore a task from 7-day trash back to your active list.")
    @app_commands.describe(trash_id="The trash number (e.g. 1 for T1)")
    async def todo_restore(self, interaction: discord.Interaction, trash_id: int):
        res = db.restore_task(interaction.user.id, trash_id)
        if res:
            await interaction.response.send_message(
                f"♻️ Restored task **`T{trash_id}`** (*{res['task_text']}*) back to your active list as **`#{res.get('num', 1)}`**.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Trash item **`T{trash_id}`** not found. Run `/todo list filter: Trash` to inspect trash.",
                ephemeral=True
            )

    @todo_group.command(name="edit", description="Modify an existing task's description, priority, or reminder.")
    @app_commands.describe(
        id="The relative task number (e.g. 1 for #1)",
        task="New task description",
        priority="Updated priority level",
        remind="New reminder schedule",
        remove_reminder="Remove reminder schedule completely (True/False)"
    )
    @app_commands.choices(priority=[
        app_commands.Choice(name="🔴 High", value="high"),
        app_commands.Choice(name="🟡 Medium", value="medium"),
        app_commands.Choice(name="⚪ Low", value="low"),
    ])
    async def todo_edit(
        self,
        interaction: discord.Interaction,
        id: int,
        task: Optional[str] = None,
        priority: Optional[app_commands.Choice[str]] = None,
        remind: Optional[str] = None,
        remove_reminder: Optional[bool] = False,
    ):
        p_val = priority.value if priority else None
        
        parsed = None
        if remind and not remove_reminder:
            parsed = parser.parse_remind_spec(remind)

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
            until_spec=parsed["until_spec"] if parsed else None,
            until_timestamp=parsed["until_timestamp"] if parsed else None,
        )

        if res:
            note = " Reminders removed." if remove_reminder else (f" {parsed['confirmation_msg']}" if parsed else "")
            await interaction.response.send_message(
                f"✏️ Updated task **`#{id}`**: **{res['task_text']}**.{note}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(f"❌ Task **`#{id}`** not found.", ephemeral=True)

    @todo_group.command(name="assign", description="Assign a task to a friend with an interactive Accept/Decline flow.")
    @app_commands.describe(
        member="Friend to assign task to",
        task="Task description",
        remind="Optional reminder schedule",
        priority="Priority level"
    )
    @app_commands.choices(priority=[
        app_commands.Choice(name="🔴 High", value="high"),
        app_commands.Choice(name="🟡 Medium", value="medium"),
        app_commands.Choice(name="⚪ Low", value="low"),
    ])
    async def todo_assign(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        task: str,
        remind: Optional[str] = None,
        priority: Optional[app_commands.Choice[str]] = None,
    ):
        if member.id == interaction.user.id:
            await interaction.response.send_message("❌ You cannot assign a task to yourself. Use `/todo add` instead.", ephemeral=True)
            return
        if member.bot:
            await interaction.response.send_message("❌ You cannot assign tasks to bots.", ephemeral=True)
            return

        p_val = priority.value if priority else "normal"
        parsed = parser.parse_remind_spec(remind)

        task_data = {
            "task_text": task,
            "priority": p_val,
            "remind_spec": parsed["remind_spec"],
            "remind_type": parsed["remind_type"],
            "remind_interval_mins": parsed["remind_interval_mins"],
            "remind_fixed_times": parsed["remind_fixed_times"],
            "remind_window_start": parsed["remind_window_start"],
            "until_spec": parsed["until_spec"],
            "until_timestamp": parsed["until_timestamp"],
            "next_reminder_at": parsed["next_reminder_at"],
            "dm_only": True,
        }

        view = TaskAssignmentView(
            assignee_id=member.id,
            assigner_id=interaction.user.id,
            task_data=task_data,
        )

        p_badge = format_priority_badge(p_val)
        p_str = f" • {p_badge}" if p_badge else ""
        r_str = f"\n• ⏰ **Reminder**: {parsed['remind_spec']}" if parsed["remind_spec"] else ""

        invite_msg = (
            f"📩 **Task Assignment Request**\n"
            f"**From**: <@{interaction.user.id}>\n"
            f"**Task**: **{task}**{p_str}{r_str}\n\n"
            f"Click below to accept or decline:"
        )

        # 1. Send in channel with ping
        await interaction.response.send_message(
            content=f"<@{member.id}>, you were assigned a new task by {interaction.user.mention}!",
            view=view
        )

        # 2. Also dispatch to friend's DM
        try:
            dm_view = TaskAssignmentView(
                assignee_id=member.id,
                assigner_id=interaction.user.id,
                task_data=task_data,
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

        if act == "off":
            db.update_user_settings(interaction.user.id, dnd_enabled=False)
            await interaction.response.send_message("🔕 **DND Mode Disabled.** Reminders will fire anytime they are due.", ephemeral=True)
            return

        if act == "status":
            st = db.get_user_settings(interaction.user.id)
            is_on = bool(st.get("dnd_enabled"))
            s_time = st.get("dnd_start", "22:00")
            e_time = st.get("dnd_end", "06:00")
            state_text = f"🟢 **Active** (`{s_time}` to `{e_time}`)" if is_on else "⚪ **Disabled**"
            await interaction.response.send_message(
                f"🌙 **Do Not Disturb (DND) Status**:\n"
                f"• State: {state_text}\n"
                f"• Timezone: `{st.get('timezone', 'Asia/Kolkata')}`\n\n"
                f"-# Configure using `/todo dnd action: Set start: \"22:00\" end: \"06:00\"`",
                ephemeral=True
            )
            return

        # Action: 'set'
        t_start = parser.parse_time_component(start) if start else (22, 0)
        t_end = parser.parse_time_component(end) if end else (6, 0)

        if not t_start or not t_end:
            await interaction.response.send_message(
                "❌ Could not parse times. Please format like `22:00` (or `10 PM`) and `06:00` (or `6 AM`).",
                ephemeral=True
            )
            return

        s_formatted = f"{t_start[0]:02d}:{t_start[1]:02d}"
        e_formatted = f"{t_end[0]:02d}:{t_end[1]:02d}"

        db.update_user_settings(
            user_id=interaction.user.id,
            dnd_enabled=True,
            dnd_start=s_formatted,
            dnd_end=e_formatted
        )

        await interaction.response.send_message(
            f"🌙 **DND Quiet Hours Enabled!**\n"
            f"• **Quiet Window**: `{s_formatted}` to `{e_formatted}` daily.\n"
            f"• During this window, reminders will be silently postponed to avoid waking or disturbing you.",
            ephemeral=True
        )

    @todo_group.command(name="clear", description="Instantly purge all completed and trashed items.")
    @app_commands.describe(confirm="Confirm permanent deletion of trash")
    async def todo_clear(self, interaction: discord.Interaction, confirm: bool = False):
        if not confirm:
            await interaction.response.send_message(
                "⚠️ This will permanently delete all tasks in your trash! Run `/todo clear confirm: True` to proceed.",
                ephemeral=True
            )
            return

        count = db.clear_trash(interaction.user.id)
        await interaction.response.send_message(
            f"🧹 **Trash Cleared.** Permanently removed **{count}** trashed task(s).",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(TodoCog(bot))
