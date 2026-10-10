"""
ui/todo_views.py - Modern, Neutral Interactive UI Components for Todo Addon

Features:
- 15-item scrollable pagination ([ ◀️ Prev ], [ Next ▶️ ])
- Active List vs 7-Day Trash view toggling ([ 🗑️ View Trash ] / [ 📋 Active Tasks ])
- Interactive task completion, silencing, and restoration menus
- Reminder alert notification card with instant [ ✅ Done ], [ 🔕 Silence ], [ ⏰ Snooze ] buttons
- Task assignment invitation with [ ✅ Accept ] and [ ❌ Decline ] buttons
"""

import math
import time
from typing import List, Dict, Any, Optional
import discord
from discord.ext import commands

import todo_db as db
from config import BOT_TZ


def format_priority_badge(priority: str) -> str:
    """Returns a clean visual indicator for task priority."""
    p = priority.lower().strip()
    if p == "high":
        return "`🔴 High`"
    elif p == "medium":
        return "`🟡 Med`"
    elif p == "low":
        return "`⚪ Low`"
    return ""


def build_todo_list_embed(
    tasks: List[Dict[str, Any]],
    page: int = 1,
    total_pages: int = 1,
    is_trash: bool = False,
    user: Optional[discord.User] = None,
    total_items: int = 0,
) -> discord.Embed:
    """
    Builds a clean, neutral, distraction-free embed for active tasks or 7-day trash.
    Strictly up to 15 items per page.
    """
    username = user.display_name if user else "Your"
    
    if is_trash:
        title = f"🗑️ {username}'s Todo Trash & History"
        color = 0x7F8C8D # Muted slate gray
        empty_msg = "Your trash is currently empty.\nCompleted and deleted tasks are kept here for 7 days before being automatically cleaned."
    else:
        title = f"📋 {username}'s Active Todo List"
        color = 0x2ECC71 # Clean emerald green
        empty_msg = "You have no active tasks!\nAdd one using `/todo add task: \"...\"` or click **Quick Add** below."

    embed = discord.Embed(
        title=title,
        color=color
    )

    if not tasks:
        embed.description = empty_msg
        embed.set_footer(text=f"Page {page} of {max(1, total_pages)} • 0 items")
        return embed

    lines = []
    for t in tasks:
        p_badge = format_priority_badge(t.get("priority", "normal"))
        badge_str = f" {p_badge}" if p_badge else ""

        if is_trash:
            t_id = t.get("trash_id", f"T{t.get('trash_num', 1)}")
            status_emoji = "✅" if t.get("status") == "completed" else "🗑️"
            trashed_ts = t.get("trashed_at") or t.get("created_at") or int(time.time())
            lines.append(f"**`{t_id}`** {status_emoji} {t['task_text']}{badge_str}\n-# Moved to trash <t:{trashed_ts}:R>")
        else:
            num = t.get("num", 1)
            remind_str = ""
            if t.get("status") == "silenced":
                remind_str = " • 🔕 *Silenced*"
            elif t.get("remind_spec"):
                next_ts = t.get("next_reminder_at")
                if next_ts:
                    remind_str = f" • ⏰ <t:{next_ts}:R>"
                else:
                    remind_str = f" • 🔁 *{t['remind_spec']}*"

            dm_badge = " `DM`" if t.get("dm_only") else ""
            lines.append(f"**`#{num}`** {t['task_text']}{badge_str}{remind_str}{dm_badge}")

    embed.description = "\n\n".join(lines)
    
    footer_text = f"Page {page} of {total_pages} • {total_items} total item(s)"
    if is_trash:
        footer_text += " • Auto-purged after 7 days"
    else:
        footer_text += " • Use /todo done [id] or buttons below"
        
    embed.set_footer(text=footer_text)
    return embed


# =====================================================================
# Main 15-Item Paginated List View
# =====================================================================

class TodoListView(discord.ui.View):
    """
    Interactive View displaying up to 15 tasks per page with navigation,
    trash toggling, task completion, silencing, and quick add.
    """
    PAGE_SIZE = 15

    def __init__(
        self,
        user_id: int,
        user: discord.User,
        is_trash: bool = False,
        page: int = 1,
        priority_filter: Optional[str] = None,
        with_reminders_only: bool = False,
        db_path: Optional[str] = None,
    ):
        super().__init__(timeout=180.0)
        self.user_id = user_id
        self.user = user
        self.is_trash = is_trash
        self.page = page
        self.priority_filter = priority_filter
        self.with_reminders_only = with_reminders_only
        self.db_path = db_path
        self._update_buttons()

    def _get_current_items(self) -> Tuple[List[Dict[str, Any]], int, int]:
        """Fetches items for the current page and calculates total pages."""
        if self.is_trash:
            all_items = db.get_trashed_tasks(self.user_id, db_path=self.db_path)
        else:
            all_items = db.get_active_tasks(
                self.user_id,
                priority_filter=self.priority_filter,
                with_reminders_only=self.with_reminders_only,
                db_path=self.db_path
            )

        total_items = len(all_items)
        total_pages = max(1, math.ceil(total_items / self.PAGE_SIZE))
        if self.page > total_pages:
            self.page = total_pages
        if self.page < 1:
            self.page = 1

        start_idx = (self.page - 1) * self.PAGE_SIZE
        end_idx = start_idx + self.PAGE_SIZE
        page_items = all_items[start_idx:end_idx]
        return page_items, total_pages, total_items

    def _update_buttons(self):
        """Updates button labels, states, and pagination controls."""
        page_items, total_pages, _ = self._get_current_items()

        # Update Prev/Next states
        self.btn_prev.disabled = (self.page <= 1)
        self.btn_next.disabled = (self.page >= total_pages)
        self.btn_page_num.label = f"Page {self.page}/{total_pages}"

        # Update View Trash / Active List toggle button
        if self.is_trash:
            self.btn_trash_toggle.label = "📋 Active Tasks"
            self.btn_trash_toggle.style = discord.ButtonStyle.primary
            self.btn_action_done.label = "♻️ Restore"
            self.btn_action_done.disabled = (len(page_items) == 0)
            self.btn_silence.disabled = True
        else:
            self.btn_trash_toggle.label = "🗑️ Trash / History"
            self.btn_trash_toggle.style = discord.ButtonStyle.secondary
            self.btn_action_done.label = "✅ Mark Done"
            self.btn_action_done.disabled = (len(page_items) == 0)
            self.btn_silence.disabled = (len(page_items) == 0)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ This to-do dashboard belongs to another user. Run `/todo list` to view your own.",
                ephemeral=True
            )
            return False
        return True

    def build_current_embed(self) -> discord.Embed:
        page_items, total_pages, total_items = self._get_current_items()
        return build_todo_list_embed(
            tasks=page_items,
            page=self.page,
            total_pages=total_pages,
            is_trash=self.is_trash,
            user=self.user,
            total_items=total_items
        )

    # ---------------- Buttons ----------------

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary, custom_id="btn_todo_prev")
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_current_embed(), view=self)

    @discord.ui.button(label="Page 1/1", style=discord.ButtonStyle.secondary, disabled=True, custom_id="btn_todo_page_num")
    async def btn_page_num(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary, custom_id="btn_todo_next")
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_current_embed(), view=self)

    @discord.ui.button(label="🗑️ Trash / History", style=discord.ButtonStyle.secondary, custom_id="btn_todo_trash_toggle")
    async def btn_trash_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.is_trash = not self.is_trash
        self.page = 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_current_embed(), view=self)

    @discord.ui.button(label="✅ Mark Done", style=discord.ButtonStyle.success, custom_id="btn_todo_done_action")
    async def btn_action_done(self, interaction: discord.Interaction, button: discord.ui.Button):
        page_items, _, _ = self._get_current_items()
        if not page_items:
            await interaction.response.send_message("No tasks available to select.", ephemeral=True)
            return

        if self.is_trash:
            # Show restore selector
            view = TaskSelectorView(
                user_id=self.user_id,
                items=page_items,
                action_type="restore",
                parent_view=self,
                db_path=self.db_path
            )
            await interaction.response.send_message("Select a trashed task to restore back to active:", view=view, ephemeral=True)
        else:
            # Show mark done selector
            view = TaskSelectorView(
                user_id=self.user_id,
                items=page_items,
                action_type="done",
                parent_view=self,
                db_path=self.db_path
            )
            await interaction.response.send_message("Select a task to mark completed:", view=view, ephemeral=True)

    @discord.ui.button(label="🔕 Silence", style=discord.ButtonStyle.secondary, custom_id="btn_todo_silence")
    async def btn_silence(self, interaction: discord.Interaction, button: discord.ui.Button):
        page_items, _, _ = self._get_current_items()
        active_with_remind = [t for t in page_items if t.get("remind_spec") and t.get("status") == "active"]
        if not active_with_remind:
            await interaction.response.send_message("No tasks on this page currently have active reminders.", ephemeral=True)
            return

        view = TaskSelectorView(
            user_id=self.user_id,
            items=active_with_remind,
            action_type="silence",
            parent_view=self,
            db_path=self.db_path
        )
        await interaction.response.send_message("Select a task to silence future reminders:", view=view, ephemeral=True)


# =====================================================================
# Dropdown Task Selector View (for Done, Silence, Restore)
# =====================================================================

class TaskSelectorView(discord.ui.View):
    """Temporary ephemeral select menu allowing 1-click action on tasks."""
    def __init__(
        self,
        user_id: int,
        items: List[Dict[str, Any]],
        action_type: str, # "done", "silence", "restore"
        parent_view: TodoListView,
        db_path: Optional[str] = None
    ):
        super().__init__(timeout=60.0)
        self.user_id = user_id
        self.action_type = action_type
        self.parent_view = parent_view
        self.db_path = db_path

        options = []
        for item in items[:25]:
            if action_type == "restore":
                label = f"[{item.get('trash_id', 'T?')}] {item['task_text'][:70]}"
                val = str(item.get("trash_num", 1))
            else:
                label = f"[#{item.get('num', 1)}] {item['task_text'][:70]}"
                val = str(item.get("num", 1))
            options.append(discord.SelectOption(label=label, value=val))

        select = discord.ui.Select(
            placeholder=f"Choose a task to {action_type}...",
            min_values=1,
            max_values=1,
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        select = self.children[0]
        selected_val = int(select.values[0])

        if self.action_type == "done":
            res = db.mark_task_done(self.user_id, selected_val, db_path=self.db_path)
            if res:
                msg = f"✅ Marked task **#{selected_val}** (*{res['task_text']}*) as **completed** and moved to trash."
            else:
                msg = "❌ Task could not be found."
        elif self.action_type == "silence":
            res = db.silence_task(self.user_id, selected_val, db_path=self.db_path)
            if res:
                msg = f"🔕 Silenced reminders for task **#{selected_val}** (*{res['task_text']}*)."
            else:
                msg = "❌ Task could not be found."
        elif self.action_type == "restore":
            res = db.restore_task(self.user_id, selected_val, db_path=self.db_path)
            if res:
                msg = f"♻️ Restored task **T{selected_val}** back to your active list."
            else:
                msg = "❌ Task could not be found."
        else:
            msg = "Action completed."

        self.parent_view._update_buttons()
        try:
            # Refresh parent message if possible
            await interaction.message.edit(content=msg, view=None)
        except Exception:
            await interaction.response.send_message(msg, ephemeral=True)


# =====================================================================
# Reminder Notification Alert View (Delivered when reminder fires)
# =====================================================================

class ReminderAlertView(discord.ui.View):
    """
    Attached directly to the reminder notification message (DM or channel).
    Provides instant [ ✅ Done ], [ 🔕 Silence ], [ ⏰ Snooze 30m ] buttons.
    """
    def __init__(self, task_id: int, user_id: int, db_path: Optional[str] = None):
        super().__init__(timeout=86400.0) # 24 hours
        self.task_id = task_id
        self.user_id = user_id
        self.db_path = db_path

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This reminder belongs to another user.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Mark Done", style=discord.ButtonStyle.success, custom_id="btn_alert_done")
    async def btn_alert_done(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Find relative task number
        tasks = db.get_active_tasks(self.user_id, db_path=self.db_path)
        matching = [t for t in tasks if t["id"] == self.task_id]
        if matching:
            num = matching[0]["num"]
            db.mark_task_done(self.user_id, num, db_path=self.db_path)
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("✅ Task marked as completed! Future reminders have been stopped.", ephemeral=True)
        else:
            await interaction.response.send_message("This task is already completed or deleted.", ephemeral=True)

    @discord.ui.button(label="🔕 Silence Reminder", style=discord.ButtonStyle.secondary, custom_id="btn_alert_silence")
    async def btn_alert_silence(self, interaction: discord.Interaction, button: discord.ui.Button):
        tasks = db.get_active_tasks(self.user_id, db_path=self.db_path)
        matching = [t for t in tasks if t["id"] == self.task_id]
        if matching:
            num = matching[0]["num"]
            db.silence_task(self.user_id, num, db_path=self.db_path)
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("🔕 Future reminders for this task are now silenced. Task remains on your active list.", ephemeral=True)
        else:
            await interaction.response.send_message("Task not found.", ephemeral=True)

    @discord.ui.button(label="⏰ Snooze 30m", style=discord.ButtonStyle.primary, custom_id="btn_alert_snooze")
    async def btn_alert_snooze(self, interaction: discord.Interaction, button: discord.ui.Button):
        res = db.snooze_task_by_id(self.task_id, snooze_mins=30, db_path=self.db_path)
        if res:
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("⏰ Snoozed! Next reminder will fire in **30 minutes**.", ephemeral=True)
        else:
            await interaction.response.send_message("Task not found or already completed.", ephemeral=True)


# =====================================================================
# Task Assignment View (Accept / Decline Flow)
# =====================================================================

class TaskAssignmentView(discord.ui.View):
    """
    Interactive invite view sent when User A assigns a task to User B.
    """
    def __init__(
        self,
        assignee_id: int,
        assigner_id: int,
        task_data: Dict[str, Any],
        db_path: Optional[str] = None
    ):
        super().__init__(timeout=86400.0)
        self.assignee_id = assignee_id
        self.assigner_id = assigner_id
        self.task_data = task_data
        self.db_path = db_path

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.assignee_id:
            await interaction.response.send_message("❌ This assignment request was sent to another user.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Accept Task", style=discord.ButtonStyle.success, custom_id="btn_assign_accept")
    async def btn_accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Insert task into assignee's active list
        new_task = db.add_task(
            user_id=self.assignee_id,
            task_text=self.task_data["task_text"],
            priority=self.task_data.get("priority", "normal"),
            remind_spec=self.task_data.get("remind_spec"),
            remind_type=self.task_data.get("remind_type"),
            remind_interval_mins=self.task_data.get("remind_interval_mins"),
            remind_fixed_times=self.task_data.get("remind_fixed_times"),
            remind_window_start=self.task_data.get("remind_window_start"),
            until_spec=self.task_data.get("until_spec"),
            until_timestamp=self.task_data.get("until_timestamp"),
            dm_only=self.task_data.get("dm_only", True),
            assigned_by_user_id=self.assigner_id,
            next_reminder_at=self.task_data.get("next_reminder_at"),
            db_path=self.db_path
        )
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content=f"✅ **Task Accepted!** Added to your active list as **#{new_task.get('num', 1)}**.",
            view=self
        )

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger, custom_id="btn_assign_decline")
    async def btn_decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="❌ **Task Declined.** The assignment was discarded.",
            view=self
        )
