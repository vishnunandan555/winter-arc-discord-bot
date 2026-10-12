"""
ui/todo_views.py - Modern, Neutral Interactive UI Components for Todo & Habit Addon

Features:
- Progress bar generator for counters and habits
- 15-item scrollable pagination ([ ◀️ Prev ], [ Next ▶️ ])
- Active List vs 7-Day Trash view toggling ([ 🗑️ View Trash ] / [ 📋 Active Tasks ])
- Dedicated Task Detail Control Center ([ ➕ Log +1 ], [ ➖ Undo -1 ], [ ✅ Toggle Done ], [ 🔕 Silence ], [ 🗑️ Delete ])
- Interactive task selector menu for 1-click execution
- Anti-spam, single-click self-disabling reminder alert cards
- Task assignment invitation with [ ✅ Accept ] and [ ❌ Decline ] buttons
- Incognito mode toggle dashboard
"""

from __future__ import annotations
import math
import time
from typing import List, Dict, Any, Optional, Tuple
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


def make_todo_progress_bar(cur: int, tgt: int, length: int = 8) -> str:
    """
    Builds a sleek text progress bar e.g. [▰▰▰▰▱▱▱▱] 4/8.
    Clamps display cleanly without breaking layout.
    """
    if tgt <= 0:
        return f"`{cur}`"
    cur_clamped = max(0, min(cur, tgt))
    filled = int(round((cur_clamped / tgt) * length))
    empty = max(0, length - filled)
    bar = "▰" * filled + "▱" * empty
    return f"[{bar}] `{cur}/{tgt}`"


def build_todo_list_embed(
    tasks: List[Dict[str, Any]],
    page: int = 1,
    total_pages: int = 1,
    is_trash: bool = False,
    user: Optional[discord.User] = None,
    total_items: int = 0,
    completed_cycle_tasks: Optional[List[Dict[str, Any]]] = None,
) -> discord.Embed:
    """
    Builds a clean, neutral, distraction-free embed for active tasks or 7-day trash.
    Strictly up to 15 items per page, with dedicated completed cycle section on page 1.
    """
    username = user.display_name if user else "Your"

    if is_trash:
        title = f"🗑️ {username}'s Todo Trash & History"
        color = 0x7F8C8D  # Muted slate gray
        empty_msg = "Your trash is currently empty.\nCompleted and deleted tasks are kept here for 7 days before being automatically cleaned."
    else:
        title = f"📋 {username}'s Active Todo List"
        color = 0x2ECC71  # Clean emerald green
        empty_msg = "You have no active tasks!\nAdd one using `/todo add task: \"...\"` or use `/todo` commands."

    embed = discord.Embed(
        title=title,
        color=color
    )

    if not tasks and not (completed_cycle_tasks and not is_trash):
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

            # Progress bar for counters/habits
            counter_str = ""
            if t.get("target_count") and t["target_count"] > 0:
                cur = t.get("current_count", 0)
                tgt = t["target_count"]
                counter_str = f" {make_todo_progress_bar(cur, tgt)}"

            # Reminder info
            remind_str = ""
            if t.get("status") == "silenced":
                remind_str = " • 🔕 *Silenced*"
            elif t.get("remind_spec"):
                next_ts = t.get("next_reminder_at")
                if next_ts:
                    remind_str = f" • ⏰ <t:{next_ts}:R>"
                else:
                    remind_str = f" • 🔁 *{t['remind_spec']}*"

            # Reset cadence info
            reset_str = ""
            if t.get("reset_period") and t["reset_period"] != "none":
                if t.get("reset_interval_days") and t["reset_interval_days"] > 1:
                    reset_str = f" • 🔁 *Resets every {t['reset_interval_days']}d*"
                else:
                    reset_str = f" • 🔁 *Resets {t['reset_period']}*"

            d_mode = t.get("delivery_mode") or ("dm" if t.get("dm_only") else "channel")
            if d_mode == "both":
                dm_badge = " `Channel+DM`"
            elif d_mode == "dm":
                dm_badge = " `DM`"
            else:
                dm_badge = ""
            lines.append(f"**`#{num}`** {t['task_text']}{badge_str}{counter_str}{remind_str}{reset_str}{dm_badge}")

    # Append completed cycle tasks at bottom of page 1
    if not is_trash and completed_cycle_tasks and page == 1:
        cycle_lines = []
        for ct in completed_cycle_tasks:
            c_p_badge = format_priority_badge(ct.get("priority", "normal"))
            c_badge_str = f" {c_p_badge}" if c_p_badge else ""
            c_num = ct.get("num", "?")
            if ct.get("target_count") and ct["target_count"] > 0:
                c_bar = f" {make_todo_progress_bar(ct.get('current_count', 0), ct['target_count'])}"
            else:
                c_bar = " ✅"
            cycle_lines.append(f"~~**`#{c_num}`** {ct['task_text']}~~{c_badge_str}{c_bar} • 🔁 *Resets 00:00 IST*")

        if lines:
            lines.append("───────────────────────────────")
        lines.append("✨ **Completed Today / This Cycle**")
        lines.extend(cycle_lines)

    embed.description = "\n\n".join(lines) if lines else empty_msg

    footer_text = f"Page {page} of {total_pages} • {total_items} active item(s)"
    if is_trash:
        footer_text = f"Page {page} of {total_pages} • {total_items} trashed item(s) • Auto-purged after 7 days"
    else:
        footer_text += " • Click 🔍 Open Task or use /todo done [id]"

    embed.set_footer(text=footer_text)
    return embed


def build_task_detail_embed(task: Dict[str, Any], user: Optional[discord.User] = None) -> discord.Embed:
    """Builds a rich, focused control center embed for an individual task."""
    num = task.get("num", 1)
    status = task.get("status", "active")
    prio = format_priority_badge(task.get("priority", "normal"))
    prio_str = f" • {prio}" if prio else ""

    if status == "completed":
        color = 0x9B59B6  # Purple
        status_label = "✨ Completed for Cycle (Resets at 00:00 IST)"
    elif status == "silenced":
        color = 0xF39C12  # Orange
        status_label = "🔕 Silenced (No Alert Reminders)"
    elif status == "deleted":
        color = 0x7F8C8D  # Muted slate
        status_label = "🗑️ In Trash"
    else:
        color = 0x2ECC71  # Emerald green
        status_label = "🟢 Active"

    embed = discord.Embed(
        title=f"📋 Task #{num}: {task.get('task_text', '')}",
        color=color
    )

    fields = [
        f"**Status**: {status_label}{prio_str}"
    ]

    target = task.get("target_count") or 0
    cur = task.get("current_count") or 0
    if target > 0:
        bar = make_todo_progress_bar(cur, target, length=10)
        fields.append(f"**Progress**: {bar}")

    if task.get("remind_spec"):
        r_str = f"`{task['remind_spec']}`"
        next_r = task.get("next_reminder_at")
        if next_r:
            r_str += f" (Next alert: <t:{next_r}:R>)"
        fields.append(f"⏰ **Reminder**: {r_str}")

    reset_period = task.get("reset_period", "none")
    if reset_period != "none":
        r_cadence = f"`{reset_period}`"
        if task.get("reset_interval_days") and task["reset_interval_days"] > 1:
            r_cadence = f"every `{task['reset_interval_days']}` days"
        next_reset = task.get("next_reset_ts")
        reset_time_str = f" <t:{next_reset}:R>" if next_reset else " at 00:00 IST"
        fields.append(f"🔁 **Reset Schedule**: {r_cadence} (Next reset:{reset_time_str})")

    d_mode = task.get("delivery_mode") or ("dm" if task.get("dm_only", 1) else "channel")
    if d_mode == "both":
        dm_mode = "Both (Channel & Direct Message)"
    elif d_mode == "dm":
        dm_mode = "Direct Message (Private)"
    else:
        dm_mode = "Channel Notification"
    fields.append(f"🔒 **Alert Mode**: {dm_mode}")

    created = task.get("created_at")
    if created:
        fields.append(f"📅 **Created**: <t:{created}:R>")

    embed.description = "\n\n".join(fields)
    embed.set_footer(text=f"Task ID: {task.get('id', '?')} • Use buttons below to adjust or manage")
    return embed


# =====================================================================
# Main 15-Item Paginated List View
# =====================================================================

class TodoListView(discord.ui.View):
    """
    Interactive View displaying up to 15 tasks per page with navigation,
    trash toggling, task detail opening, task completion, and silencing.
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
        self._pagination_visible = True
        self._update_buttons()

    def _get_current_items(self) -> Tuple[List[Dict[str, Any]], int, int]:
        """Fetches items for the current page and total item/page count."""
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
        needs_pagination = total_pages > 1

        if needs_pagination and not self._pagination_visible:
            self.add_item(self.btn_prev)
            self.add_item(self.btn_page_num)
            self.add_item(self.btn_next)
            self._pagination_visible = True
        elif not needs_pagination and self._pagination_visible:
            self.remove_item(self.btn_prev)
            self.remove_item(self.btn_page_num)
            self.remove_item(self.btn_next)
            self._pagination_visible = False

        if needs_pagination:
            self.btn_prev.disabled = (self.page <= 1)
            self.btn_next.disabled = (self.page >= total_pages)
            self.btn_page_num.label = f"Page {self.page}/{total_pages}"

        # Update labels & disabled states
        if self.is_trash:
            self.btn_trash_toggle.label = "📋 Active Tasks"
            self.btn_trash_toggle.style = discord.ButtonStyle.primary
            self.btn_action_done.label = "♻️ Restore"
            self.btn_action_done.disabled = (len(page_items) == 0)
            self.btn_open_detail.disabled = True
            self.btn_silence.disabled = True
        else:
            self.btn_trash_toggle.label = "🗑️ Trash / History"
            self.btn_trash_toggle.style = discord.ButtonStyle.secondary
            self.btn_action_done.label = "✅ Mark Done"
            self.btn_action_done.disabled = (len(page_items) == 0)
            self.btn_open_detail.disabled = (len(page_items) == 0)
            self.btn_silence.disabled = (len(page_items) == 0)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ This to-do dashboard belongs to another user. Run `/todo list` to view your own.",
                ephemeral=True
            )
            return False
        if interaction.message:
            self.message = interaction.message
        return True

    async def on_timeout(self) -> None:
        if hasattr(self, "message") and self.message:
            try:
                if getattr(self.message, "guild", None) is not None:
                    await self.message.delete()
                    return
            except Exception:
                pass
            try:
                for child in self.children:
                    child.disabled = True
                await self.message.edit(view=self)
            except Exception:
                pass

    def build_current_embed(self) -> discord.Embed:
        page_items, total_pages, total_items = self._get_current_items()
        completed_cycle = db.get_completed_cycle_tasks(self.user_id, db_path=self.db_path) if not self.is_trash else []
        return build_todo_list_embed(
            tasks=page_items,
            page=self.page,
            total_pages=total_pages,
            is_trash=self.is_trash,
            user=self.user,
            total_items=total_items,
            completed_cycle_tasks=completed_cycle
        )

    # ---------------- Buttons ----------------

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary, custom_id="btn_todo_prev", row=0)
    async def btn_prev(self, interaction: discord.Interaction, button: Optional[discord.ui.Button] = None):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_current_embed(), view=self)

    @discord.ui.button(label="Page 1/1", style=discord.ButtonStyle.secondary, disabled=True, custom_id="btn_todo_page_num", row=0)
    async def btn_page_num(self, interaction: discord.Interaction, button: Optional[discord.ui.Button] = None):
        pass

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary, custom_id="btn_todo_next", row=0)
    async def btn_next(self, interaction: discord.Interaction, button: Optional[discord.ui.Button] = None):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_current_embed(), view=self)

    @discord.ui.button(label="🗑️ Trash / History", style=discord.ButtonStyle.secondary, custom_id="btn_todo_trash_toggle", row=1)
    async def btn_trash_toggle(self, interaction: discord.Interaction, button: Optional[discord.ui.Button] = None):
        self.is_trash = not self.is_trash
        self.page = 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_current_embed(), view=self)

    @discord.ui.button(label="🔍 Open Task", style=discord.ButtonStyle.secondary, custom_id="btn_todo_open_detail", row=1)
    async def btn_open_detail(self, interaction: discord.Interaction, button: Optional[discord.ui.Button] = None):
        page_items, _, _ = self._get_current_items()
        completed_cycle = db.get_completed_cycle_tasks(self.user_id, db_path=self.db_path) if not self.is_trash else []
        all_viewable = page_items + completed_cycle
        if not all_viewable:
            await interaction.response.send_message("No tasks available on this page to open.", ephemeral=True)
            return

        view = TaskSelectorView(
            user_id=self.user_id,
            items=all_viewable,
            action_type="open",
            parent_view=self,
            db_path=self.db_path
        )
        await interaction.response.send_message("Select a task to open its Control Center:", view=view, ephemeral=True)

    @discord.ui.button(label="✅ Mark Done", style=discord.ButtonStyle.success, custom_id="btn_todo_done_action", row=1)
    async def btn_action_done(self, interaction: discord.Interaction, button: Optional[discord.ui.Button] = None):
        page_items, _, _ = self._get_current_items()
        if not page_items:
            await interaction.response.send_message("No tasks available to select.", ephemeral=True)
            return

        if self.is_trash:
            view = TaskSelectorView(
                user_id=self.user_id,
                items=page_items,
                action_type="restore",
                parent_view=self,
                db_path=self.db_path
            )
            await interaction.response.send_message("Select a trashed task to restore back to active:", view=view, ephemeral=True)
        else:
            view = TaskSelectorView(
                user_id=self.user_id,
                items=page_items,
                action_type="done",
                parent_view=self,
                db_path=self.db_path
            )
            await interaction.response.send_message("Select a task to mark completed:", view=view, ephemeral=True)

    @discord.ui.button(label="🔕 Silence", style=discord.ButtonStyle.secondary, custom_id="btn_todo_silence", row=1)
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
# Dropdown Task Selector View (for Open, Done, Silence, Restore)
# =====================================================================

class TaskSelectorView(discord.ui.View):
    """Temporary ephemeral select menu allowing 1-click action or opening tasks."""
    def __init__(
        self,
        user_id: int,
        items: List[Dict[str, Any]],
        action_type: str,  # "open", "done", "silence", "restore"
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
            elif action_type == "open":
                label = f"[#{item.get('num', 1)}] {item['task_text'][:70]}"
                val = str(item.get("id"))
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

        if self.action_type == "open":
            detail_view = TaskDetailView(
                task_id=selected_val,
                user_id=self.user_id,
                parent_view=self.parent_view,
                db_path=self.db_path
            )
            task = detail_view._get_task()
            if task:
                embed = build_task_detail_embed(task, user=interaction.user)
                await interaction.response.edit_message(content=None, embed=embed, view=detail_view)
            else:
                await interaction.response.send_message("❌ Task could not be found.", ephemeral=True)
            return

        if self.action_type == "done":
            res = db.mark_task_done(self.user_id, selected_val, db_path=self.db_path)
            if res:
                if res.get("reset_period", "none") != "none":
                    msg = f"✅ Marked task **#{selected_val}** (*{res['task_text']}*) **completed for today**.\n-# Resets at 00:00 IST."
                else:
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
            await interaction.message.edit(content=msg, view=None)
        except Exception:
            await interaction.response.send_message(msg, ephemeral=True)


# =====================================================================
# Dedicated Task Detail Control Center View
# =====================================================================

class TaskDetailView(discord.ui.View):
    """
    Dedicated Control Center for an individual task.
    Provides instant [ ➕ Log +1 ], [ ➖ Undo -1 ], [ ✅ Toggle Done ], [ 🔕 Silence ], [ 🗑️ Delete ], [ 📋 Back ].
    """
    def __init__(
        self,
        task_id: int,
        user_id: int,
        parent_view: Optional[TodoListView] = None,
        db_path: Optional[str] = None
    ):
        super().__init__(timeout=180.0)
        self.task_id = task_id
        self.user_id = user_id
        self.parent_view = parent_view
        self.db_path = db_path
        self._sync_buttons()

    def _get_task(self) -> Optional[Dict[str, Any]]:
        db.apply_lazy_resets_for_user(self.user_id, db_path=self.db_path)
        return db.get_task_by_id(self.task_id, db_path=self.db_path)

    def _sync_buttons(self):
        task = self._get_task()
        self.clear_items()
        if not task:
            return

        target = task.get("target_count") or 0
        cur = task.get("current_count") or 0
        status = task.get("status", "active")
        is_silenced = (status == "silenced")
        is_completed = (status == "completed")

        # Row 0: Counter adjustment buttons (if target_count > 0 or current_count > 0)
        if target > 0 or cur > 0:
            target_str = f"/{target}" if target > 0 else ""
            btn_add = discord.ui.Button(
                label=f"➕ Log +1 ({cur}{target_str})",
                style=discord.ButtonStyle.success,
                custom_id=f"detail_add_{self.task_id}",
                row=0
            )
            btn_add.callback = self.on_add_one
            self.add_item(btn_add)

            btn_sub = discord.ui.Button(
                label="➖ Undo -1",
                style=discord.ButtonStyle.secondary,
                custom_id=f"detail_sub_{self.task_id}",
                disabled=(cur <= 0),
                row=0
            )
            btn_sub.callback = self.on_sub_one
            self.add_item(btn_sub)

        # Row 1: Status toggle & reminder silence
        done_label = "↩️ Mark Incomplete" if is_completed else "✅ Mark Done"
        done_style = discord.ButtonStyle.secondary if is_completed else discord.ButtonStyle.primary
        btn_toggle = discord.ui.Button(
            label=done_label,
            style=done_style,
            custom_id=f"detail_done_{self.task_id}",
            row=1
        )
        btn_toggle.callback = self.on_toggle_done
        self.add_item(btn_toggle)

        if task.get("remind_spec"):
            silence_label = "🔔 Unsilence" if is_silenced else "🔕 Silence"
            btn_silence = discord.ui.Button(
                label=silence_label,
                style=discord.ButtonStyle.secondary,
                custom_id=f"detail_silence_{self.task_id}",
                row=1
            )
            btn_silence.callback = self.on_toggle_silence
            self.add_item(btn_silence)

        # Row 2: Delivery switcher, Delete & Back
        if task.get("remind_spec"):
            d_mode = task.get("delivery_mode") or ("dm" if task.get("dm_only", 1) else "channel")
            if d_mode == "both":
                d_label = "📢 Alert: Both"
            elif d_mode == "dm":
                d_label = "🔒 Alert: DM Only"
            else:
                d_label = "📍 Alert: Channel"

            btn_delivery = discord.ui.Button(
                label=d_label,
                style=discord.ButtonStyle.secondary,
                custom_id=f"detail_delivery_{self.task_id}",
                row=2
            )
            btn_delivery.callback = self.on_cycle_delivery
            self.add_item(btn_delivery)

        btn_del = discord.ui.Button(
            label="🗑️ Delete",
            style=discord.ButtonStyle.danger,
            custom_id=f"detail_del_{self.task_id}",
            row=2
        )
        btn_del.callback = self.on_delete
        self.add_item(btn_del)

        if self.parent_view:
            btn_back = discord.ui.Button(
                label="📋 Back to List",
                style=discord.ButtonStyle.secondary,
                custom_id=f"detail_back_{self.task_id}",
                row=2
            )
            btn_back.callback = self.on_back
            self.add_item(btn_back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This task belongs to another user.", ephemeral=True)
            return False
        if interaction.message:
            self.message = interaction.message
        return True

    async def on_timeout(self) -> None:
        if hasattr(self, "message") and self.message:
            try:
                if getattr(self.message, "guild", None) is not None:
                    await self.message.delete()
                    return
            except Exception:
                pass
            try:
                for child in self.children:
                    child.disabled = True
                await self.message.edit(view=self)
            except Exception:
                pass

    async def on_add_one(self, interaction: discord.Interaction):
        db.adjust_task_count_by_id(self.task_id, delta=1, db_path=self.db_path)
        self._sync_buttons()
        task = self._get_task()
        if task:
            embed = build_task_detail_embed(task, user=interaction.user)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Task not found.", ephemeral=True)

    async def on_sub_one(self, interaction: discord.Interaction):
        db.adjust_task_count_by_id(self.task_id, delta=-1, db_path=self.db_path)
        self._sync_buttons()
        task = self._get_task()
        if task:
            embed = build_task_detail_embed(task, user=interaction.user)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Task not found.", ephemeral=True)

    async def on_toggle_done(self, interaction: discord.Interaction):
        db.toggle_task_done(self.user_id, self.task_id, db_path=self.db_path)
        self._sync_buttons()
        task = self._get_task()
        if task:
            embed = build_task_detail_embed(task, user=interaction.user)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Task not found.", ephemeral=True)

    async def on_toggle_silence(self, interaction: discord.Interaction):
        task = self._get_task()
        if not task:
            await interaction.response.send_message("Task not found.", ephemeral=True)
            return
        if task.get("status") == "silenced":
            db.unsilence_task(self.user_id, self.task_id, db_path=self.db_path)
        else:
            db.silence_task(self.user_id, self.task_id, db_path=self.db_path)
        self._sync_buttons()
        updated = self._get_task()
        if updated:
            embed = build_task_detail_embed(updated, user=interaction.user)
            await interaction.response.edit_message(embed=embed, view=self)

    async def on_delete(self, interaction: discord.Interaction):
        db.delete_task(self.user_id, self.task_id, db_path=self.db_path)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="🗑️ Task moved to trash.",
            embed=None,
            view=self
        )

    async def on_cycle_delivery(self, interaction: discord.Interaction):
        ch_id = interaction.channel_id if interaction.guild else None
        db.cycle_task_delivery_mode(self.user_id, self.task_id, origin_channel_id=ch_id, db_path=self.db_path)
        self._sync_buttons()
        task = self._get_task()
        if task:
            embed = build_task_detail_embed(task, user=interaction.user)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Task not found.", ephemeral=True)

    async def on_back(self, interaction: discord.Interaction):
        if self.parent_view:
            self.parent_view._update_buttons()
            embed = self.parent_view.build_current_embed()
            await interaction.response.edit_message(content=None, embed=embed, view=self.parent_view)


# =====================================================================
# Reminder Notification Alert View (Delivered when reminder fires)
# =====================================================================

class ReminderAlertView(discord.ui.View):
    """
    Attached directly to the reminder notification message (DM or channel).
    Provides instant [ ➕ Log 1 (X/Y) ] or [ ✅ Done ], [ 🔕 Silence ], [ ⏰ Snooze 30m ] buttons.
    Uses single-click self-disabling to eliminate double-click duplicate logs.
    """
    def __init__(
        self,
        task_id: int,
        user_id: int,
        task_data: Optional[Dict[str, Any]] = None,
        db_path: Optional[str] = None
    ):
        super().__init__(timeout=86400.0)  # 24 hours
        self.task_id = task_id
        self.user_id = user_id
        self.task_data = task_data
        self.db_path = db_path

        task = self.task_data or db.get_task_by_id(self.task_id, db_path=self.db_path)
        target = (task.get("target_count") or 0) if task else 0
        cur = (task.get("current_count") or 0) if task else 0
        if target > 0:
            self.btn_alert_done.label = f"➕ Log 1 ({cur}/{target})"
        else:
            self.btn_alert_done.label = "✅ Mark Done"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This reminder belongs to another user.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Mark Done", style=discord.ButtonStyle.success, custom_id="btn_alert_done")
    async def btn_alert_done(self, interaction: discord.Interaction, button: Optional[discord.ui.Button] = None):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        task = self.task_data or db.get_task_by_id(self.task_id, db_path=self.db_path)
        if not task:
            await interaction.followup.send("Task not found or already completed.", ephemeral=True)
            return

        target = task.get("target_count") or 0
        if target > 0:
            res = db.adjust_task_count_by_id(self.task_id, delta=1, db_path=self.db_path)
            if res:
                cur = res.get("current_count", 0)
                tgt = res.get("target_count", 0)
                if tgt > 0 and cur >= tgt:
                    await interaction.followup.send(
                        f"🎉 **Goal Completed!** Task completed ({cur}/{tgt}) for **{res['task_text']}**.\n"
                        f"-# Resets at 00:00 IST.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"✅ **Logged 1!** Progress: `{cur}/{tgt}` for **{res['task_text']}**.",
                        ephemeral=True
                    )
            else:
                await interaction.followup.send("Task not found or already completed.", ephemeral=True)
        else:
            res = db.mark_task_done(self.user_id, task["id"], db_path=self.db_path)
            if task.get("reset_period", "none") != "none":
                await interaction.followup.send(
                    f"✅ **Task completed for today!** Next reminder will fire on schedule tomorrow.\n-# Resets at 00:00 IST.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"✅ **Task completed!** Kept in trash for 7 days.",
                    ephemeral=True
                )

        if interaction.guild is not None and interaction.message:
            try:
                await interaction.message.delete(delay=10.0)
            except Exception:
                pass

    @discord.ui.button(label="🔕 Silence Reminder", style=discord.ButtonStyle.secondary, custom_id="btn_alert_silence")
    async def btn_alert_silence(self, interaction: discord.Interaction, button: Optional[discord.ui.Button] = None):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        db.silence_task(self.user_id, self.task_id, db_path=self.db_path)
        await interaction.followup.send("🔕 Future reminders for this task are now silenced. Task remains on your active list.", ephemeral=True)
        if interaction.guild is not None and interaction.message:
            try:
                await interaction.message.delete(delay=10.0)
            except Exception:
                pass

    @discord.ui.button(label="⏰ Snooze 30m", style=discord.ButtonStyle.primary, custom_id="btn_alert_snooze")
    async def btn_alert_snooze(self, interaction: discord.Interaction, button: Optional[discord.ui.Button] = None):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        res = db.snooze_task_by_id(self.task_id, snooze_mins=30, db_path=self.db_path)
        if res:
            await interaction.followup.send("⏰ Snoozed! Next reminder will fire in **30 minutes**.", ephemeral=True)
        else:
            await interaction.followup.send("Task not found or already completed.", ephemeral=True)
        if interaction.guild is not None and interaction.message:
            try:
                await interaction.message.delete(delay=10.0)
            except Exception:
                pass


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
            delivery_mode=self.task_data.get("delivery_mode", "dm"),
            assigned_by_user_id=self.assigner_id,
            next_reminder_at=self.task_data.get("next_reminder_at"),
            target_count=self.task_data.get("target_count", 0),
            reset_period=self.task_data.get("reset_period", "none"),
            reset_interval_days=self.task_data.get("reset_interval_days", 1),
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


# =====================================================================
# Incognito Mode Embed & Interactive Toggle View
# =====================================================================

def build_todo_incognito_embed(user: discord.User, is_incognito: bool) -> discord.Embed:
    state_str = "**ON** (Private)" if is_incognito else "**OFF** (Public)"
    current_mode_tag = "ON (Private)" if is_incognito else "OFF (Public)"
    color = 0x9B59B6 if is_incognito else 0x3498DB
    desc = (
        f"**Incognito Mode Status**: {state_str}\n\n"
        "Incognito Mode controls the visibility of your `/todo` commands in server channels:\n\n"
        "• **OFF (Public)**\n"
        "  All your to-do actions (`/todo list`, `/todo done`, `/todo delete`, etc.) are posted publicly in the channel (others can see them).\n\n"
        "• **ON (Private)**\n"
        "  Only `/todo add` and `/todo assign` remain visible to the server. All other to-do management commands are completely private (visible only to you).\n\n"
        "Use the buttons below to toggle your preference at any time."
    )
    embed = discord.Embed(
        title="🕵🏻 To-Do Incognito Mode",
        description=desc,
        color=color
    )
    embed.set_footer(text=f"Toggle anytime with /todo incognito • Current Mode: {current_mode_tag}")
    return embed


class TodoIncognitoView(discord.ui.View):
    """Interactive toggle buttons for /todo incognito mode."""
    def __init__(self, user_id: int, current_state: bool, db_path: Optional[str] = None):
        super().__init__(timeout=180.0)
        self.user_id = user_id
        self.current_state = current_state
        self.db_path = db_path
        self._sync_buttons()

    def _sync_buttons(self):
        self.btn_on.style = discord.ButtonStyle.primary if self.current_state else discord.ButtonStyle.secondary
        self.btn_off.style = discord.ButtonStyle.secondary if self.current_state else discord.ButtonStyle.primary

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ These settings belong to another member. Run `/todo incognito` to manage yours.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Turn On", style=discord.ButtonStyle.secondary, custom_id="btn_incog_on")
    async def btn_on(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_state = True
        db.set_user_incognito(self.user_id, True, db_path=self.db_path)
        self._sync_buttons()
        embed = build_todo_incognito_embed(interaction.user, is_incognito=True)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Turn Off", style=discord.ButtonStyle.secondary, custom_id="btn_incog_off")
    async def btn_off(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_state = False
        db.set_user_incognito(self.user_id, False, db_path=self.db_path)
        self._sync_buttons()
        embed = build_todo_incognito_embed(interaction.user, is_incognito=False)
        await interaction.response.edit_message(embed=embed, view=self)
