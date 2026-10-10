"""
todo_db.py - Dedicated SQLite Database Layer for Todo & Smart Reminder Addon

Completely isolated from winter_arc.db with independent connection handling,
relative sequential user numbering (#1, #2... and T1, T2...), 7-day trash auto-retention,
DND quiet-window math, and smart reminder tracking.
"""

import os
import json
import time
import sqlite3
import logging
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional, Tuple
from config import TODO_DB_PATH, BOT_TZ

from contextlib import contextmanager

logger = logging.getLogger("winter_arc.todo.db")


@contextmanager
def get_todo_connection(db_path: Optional[str] = None):
    """Creates a thread-safe connection to the isolated todo database with auto-close."""
    target_path = db_path if db_path is not None else TODO_DB_PATH
    conn = sqlite3.connect(target_path, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
    finally:
        conn.close()


def init_todo_db(db_path: Optional[str] = None):
    """Initializes tables for the standalone todo database."""
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # 1. User preferences & DND settings
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS todo_user_settings (
                user_id INTEGER PRIMARY KEY,
                dnd_enabled BOOLEAN DEFAULT 0,
                dnd_start TEXT,
                dnd_end TEXT,
                timezone TEXT DEFAULT 'Asia/Kolkata',
                default_dm BOOLEAN DEFAULT 1,
                created_at INTEGER NOT NULL
            );
        """)

        # 2. Tasks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                task_text TEXT NOT NULL,
                priority TEXT DEFAULT 'normal',
                remind_spec TEXT,
                remind_type TEXT,
                remind_interval_mins INTEGER,
                remind_fixed_times TEXT,
                remind_window_start TEXT,
                until_spec TEXT,
                until_timestamp INTEGER,
                dm_only BOOLEAN DEFAULT 1,
                origin_channel_id INTEGER,
                assigned_by_user_id INTEGER,
                status TEXT DEFAULT 'active',
                next_reminder_at INTEGER,
                last_reminded_at INTEGER,
                completed_at INTEGER,
                trashed_at INTEGER,
                created_at INTEGER NOT NULL
            );
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_todos_user_status ON todos(user_id, status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_todos_reminders ON todos(status, next_reminder_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_todos_trashed ON todos(trashed_at);")
        conn.commit()
    logger.info("Initialized isolated todo.db schema.")


# =====================================================================
# User Settings & DND (Do Not Disturb) Logic
# =====================================================================

def get_user_settings(user_id: int, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Fetches user todo settings, inserting defaults if none exist."""
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM todo_user_settings WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        
        # Insert default
        now_ts = int(time.time())
        cursor.execute("""
            INSERT INTO todo_user_settings (user_id, dnd_enabled, dnd_start, dnd_end, timezone, default_dm, created_at)
            VALUES (?, 0, '22:00', '06:00', 'Asia/Kolkata', 1, ?)
        """, (user_id, now_ts))
        conn.commit()
        return {
            "user_id": user_id,
            "dnd_enabled": 0,
            "dnd_start": "22:00",
            "dnd_end": "06:00",
            "timezone": "Asia/Kolkata",
            "default_dm": 1,
            "created_at": now_ts,
        }


def update_user_settings(
    user_id: int,
    dnd_enabled: Optional[bool] = None,
    dnd_start: Optional[str] = None,
    dnd_end: Optional[str] = None,
    default_dm: Optional[bool] = None,
    timezone_name: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Updates user DND and reminder delivery preferences."""
    current = get_user_settings(user_id, db_path)
    new_enabled = int(dnd_enabled) if dnd_enabled is not None else current["dnd_enabled"]
    new_start = dnd_start if dnd_start is not None else current.get("dnd_start", "22:00")
    new_end = dnd_end if dnd_end is not None else current.get("dnd_end", "06:00")
    new_default_dm = int(default_dm) if default_dm is not None else current.get("default_dm", 1)
    new_tz = timezone_name if timezone_name is not None else current.get("timezone", "Asia/Kolkata")

    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE todo_user_settings
            SET dnd_enabled = ?, dnd_start = ?, dnd_end = ?, default_dm = ?, timezone = ?
            WHERE user_id = ?
        """, (new_enabled, new_start, new_end, new_default_dm, new_tz, user_id))
        conn.commit()
    return get_user_settings(user_id, db_path)


def is_user_in_dnd(user_id: int, check_dt: Optional[datetime] = None, db_path: Optional[str] = None) -> bool:
    """
    Evaluates whether the user is currently within their configured DND window.
    Handles cross-midnight ranges (e.g. 22:00 to 06:00) and same-day ranges (e.g. 13:00 to 15:00).
    """
    settings = get_user_settings(user_id, db_path)
    if not settings.get("dnd_enabled"):
        return False

    start_str = settings.get("dnd_start") or "22:00"
    end_str = settings.get("dnd_end") or "06:00"

    try:
        sh, sm = [int(p) for p in start_str.split(":", 1)]
        eh, em = [int(p) for p in end_str.split(":", 1)]
        t_start = dt_time(sh, sm)
        t_end = dt_time(eh, em)
    except Exception:
        return False

    tz_str = settings.get("timezone") or "Asia/Kolkata"
    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        tz = BOT_TZ

    now = check_dt if check_dt is not None else datetime.now(tz)
    cur_time = now.time()

    if t_start < t_end:
        # Same-day range (e.g. 13:00 to 17:00)
        return t_start <= cur_time < t_end
    else:
        # Cross-midnight range (e.g. 22:00 to 06:00)
        return cur_time >= t_start or cur_time < t_end


# =====================================================================
# Task CRUD with Relative Sequential Numbering (#1..#N and T1..TN)
# =====================================================================

def add_task(
    user_id: int,
    task_text: str,
    priority: str = "normal",
    remind_spec: Optional[str] = None,
    remind_type: Optional[str] = None,
    remind_interval_mins: Optional[int] = None,
    remind_fixed_times: Optional[List[str]] = None,
    remind_window_start: Optional[str] = None,
    until_spec: Optional[str] = None,
    until_timestamp: Optional[int] = None,
    dm_only: bool = True,
    origin_channel_id: Optional[int] = None,
    assigned_by_user_id: Optional[int] = None,
    next_reminder_at: Optional[int] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Adds a new task and returns its dict representation with its relative task number."""
    now_ts = int(time.time())
    fixed_json = json.dumps(remind_fixed_times) if remind_fixed_times else None

    # Priority normalization
    p_norm = priority.lower().strip()
    if p_norm not in ["high", "medium", "low", "normal"]:
        p_norm = "normal"

    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO todos (
                user_id, task_text, priority, remind_spec, remind_type,
                remind_interval_mins, remind_fixed_times, remind_window_start,
                until_spec, until_timestamp, dm_only, origin_channel_id,
                assigned_by_user_id, status, next_reminder_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
        """, (
            user_id, task_text.strip(), p_norm, remind_spec, remind_type,
            remind_interval_mins, fixed_json, remind_window_start,
            until_spec, until_timestamp, int(dm_only), origin_channel_id,
            assigned_by_user_id, next_reminder_at, now_ts
        ))
        conn.commit()
        task_id = cursor.lastrowid

    # Find its relative task number in the active list
    active_tasks = get_active_tasks(user_id, db_path=db_path)
    for t in active_tasks:
        if t["id"] == task_id:
            return t

    return {"id": task_id, "num": len(active_tasks), "task_text": task_text}


def get_active_tasks(
    user_id: int,
    priority_filter: Optional[str] = None,
    with_reminders_only: bool = False,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Returns active tasks for user ordered by priority (high -> medium -> normal -> low)
    and creation time, annotated with dynamic relative 1-based sequential numbers (#1, #2, ...).
    """
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        # Custom priority ordering: high = 1, medium = 2, normal = 3, low = 4
        cursor.execute("""
            SELECT * FROM todos
            WHERE user_id = ? AND status IN ('active', 'silenced')
            ORDER BY 
                CASE priority 
                    WHEN 'high' THEN 1 
                    WHEN 'medium' THEN 2 
                    WHEN 'normal' THEN 3 
                    WHEN 'low' THEN 4 
                    ELSE 5 
                END ASC,
                created_at ASC
        """, (user_id,))
        rows = [dict(r) for r in cursor.fetchall()]

    # Annotate with relative 1-based sequential numbers #1, #2, ...
    for idx, item in enumerate(rows, start=1):
        item["num"] = idx
        if item.get("remind_fixed_times"):
            try:
                item["fixed_times_list"] = json.loads(item["remind_fixed_times"])
            except Exception:
                item["fixed_times_list"] = []
        else:
            item["fixed_times_list"] = []

    # Apply optional memory-level filters while preserving base numbers
    filtered = rows
    if priority_filter:
        p_match = priority_filter.lower().strip()
        filtered = [t for t in filtered if t.get("priority") == p_match]
    if with_reminders_only:
        filtered = [t for t in filtered if t.get("next_reminder_at") or t.get("remind_spec")]

    return filtered


def get_trashed_tasks(user_id: int, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns tasks in trash (completed or deleted within the 7-day retention window),
    annotated with sequential Trash IDs (T1, T2, ...).
    """
    purge_expired_trash(days=7, db_path=db_path)
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM todos
            WHERE user_id = ? AND status IN ('completed', 'deleted')
            ORDER BY trashed_at DESC
        """, (user_id,))
        rows = [dict(r) for r in cursor.fetchall()]

    for idx, item in enumerate(rows, start=1):
        item["trash_id"] = f"T{idx}"
        item["trash_num"] = idx

    return rows


def get_task_by_relative_num(user_id: int, num: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Finds an active task by its current relative number (#1..#N)."""
    tasks = get_active_tasks(user_id, db_path=db_path)
    for t in tasks:
        if t["num"] == num:
            return t
    return None


def get_trash_by_relative_num(user_id: int, num: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Finds a trashed task by its trash number (e.g. 1 for T1)."""
    trash = get_trashed_tasks(user_id, db_path=db_path)
    for t in trash:
        if t["trash_num"] == num:
            return t
    return None


def mark_task_done(user_id: int, num: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Marks task completed, clears pending reminder, moves to trash, and returns the modified task."""
    task = get_task_by_relative_num(user_id, num, db_path=db_path)
    if not task:
        return None

    now_ts = int(time.time())
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE todos
            SET status = 'completed', completed_at = ?, trashed_at = ?, next_reminder_at = NULL
            WHERE id = ?
        """, (now_ts, now_ts, task["id"]))
        conn.commit()

    task["status"] = "completed"
    task["completed_at"] = now_ts
    task["trashed_at"] = now_ts
    return task


def silence_task(user_id: int, num: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Silences reminders for a task while keeping it on the active task list."""
    task = get_task_by_relative_num(user_id, num, db_path=db_path)
    if not task:
        return None

    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE todos
            SET status = 'silenced', next_reminder_at = NULL
            WHERE id = ?
        """, (task["id"],))
        conn.commit()

    task["status"] = "silenced"
    task["next_reminder_at"] = None
    return task


def delete_task(user_id: int, num: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Moves an active task directly to trash."""
    task = get_task_by_relative_num(user_id, num, db_path=db_path)
    if not task:
        return None

    now_ts = int(time.time())
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE todos
            SET status = 'deleted', trashed_at = ?, next_reminder_at = NULL
            WHERE id = ?
        """, (now_ts, task["id"]))
        conn.commit()

    task["status"] = "deleted"
    task["trashed_at"] = now_ts
    return task


def restore_task(user_id: int, trash_num: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Restores a task from trash back to the active list."""
    trash_item = get_trash_by_relative_num(user_id, trash_num, db_path=db_path)
    if not trash_item:
        return None

    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE todos
            SET status = 'active', trashed_at = NULL, completed_at = NULL
            WHERE id = ?
        """, (trash_item["id"],))
        conn.commit()

    active_tasks = get_active_tasks(user_id, db_path=db_path)
    for t in active_tasks:
        if t["id"] == trash_item["id"]:
            return t
    return trash_item


def edit_task(
    user_id: int,
    num: int,
    new_task_text: Optional[str] = None,
    new_priority: Optional[str] = None,
    new_remind_spec: Optional[str] = None,
    remove_reminder: bool = False,
    next_reminder_at: Optional[int] = None,
    remind_type: Optional[str] = None,
    remind_interval_mins: Optional[int] = None,
    remind_fixed_times: Optional[List[str]] = None,
    remind_window_start: Optional[str] = None,
    until_spec: Optional[str] = None,
    until_timestamp: Optional[int] = None,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Edits an active task's description, priority, or reminder parameters."""
    task = get_task_by_relative_num(user_id, num, db_path=db_path)
    if not task:
        return None

    task_id = task["id"]
    text = new_task_text.strip() if new_task_text else task["task_text"]
    priority = new_priority.lower().strip() if new_priority else task["priority"]
    if priority not in ["high", "medium", "low", "normal"]:
        priority = task["priority"]

    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        if remove_reminder:
            cursor.execute("""
                UPDATE todos
                SET task_text = ?, priority = ?, remind_spec = NULL, remind_type = NULL,
                    remind_interval_mins = NULL, remind_fixed_times = NULL, remind_window_start = NULL,
                    until_spec = NULL, until_timestamp = NULL, next_reminder_at = NULL, status = 'active'
                WHERE id = ?
            """, (text, priority, task_id))
        elif new_remind_spec:
            fixed_json = json.dumps(remind_fixed_times) if remind_fixed_times else None
            cursor.execute("""
                UPDATE todos
                SET task_text = ?, priority = ?, remind_spec = ?, remind_type = ?,
                    remind_interval_mins = ?, remind_fixed_times = ?, remind_window_start = ?,
                    until_spec = ?, until_timestamp = ?, next_reminder_at = ?, status = 'active'
                WHERE id = ?
            """, (
                text, priority, new_remind_spec, remind_type,
                remind_interval_mins, fixed_json, remind_window_start,
                until_spec, until_timestamp, next_reminder_at, task_id
            ))
        else:
            cursor.execute("""
                UPDATE todos
                SET task_text = ?, priority = ?
                WHERE id = ?
            """, (text, priority, task_id))
        conn.commit()

    return get_task_by_relative_num(user_id, num, db_path=db_path)


def clear_trash(user_id: int, db_path: Optional[str] = None) -> int:
    """Instantly purges all trashed/completed tasks for a user."""
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM todos
            WHERE user_id = ? AND status IN ('completed', 'deleted')
        """, (user_id,))
        count = cursor.rowcount
        conn.commit()
    return count


def purge_expired_trash(days: int = 7, db_path: Optional[str] = None) -> int:
    """Removes trashed tasks that exceed the retention window (default 7 days)."""
    cutoff_ts = int(time.time()) - (days * 86400)
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM todos
            WHERE status IN ('completed', 'deleted') AND trashed_at < ?
        """, (cutoff_ts,))
        count = cursor.rowcount
        conn.commit()
    if count > 0:
        logger.info(f"Auto-purged {count} expired tasks from todo trash (> {days} days old).")
    return count


# =====================================================================
# Reminder Ticker Support Queries
# =====================================================================

def get_due_reminders(now_ts: int, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns all active tasks where next_reminder_at has arrived."""
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM todos
            WHERE status = 'active' 
              AND next_reminder_at IS NOT NULL 
              AND next_reminder_at <= ?
            ORDER BY next_reminder_at ASC
        """, (now_ts,))
        rows = [dict(r) for r in cursor.fetchall()]

    for r in rows:
        if r.get("remind_fixed_times"):
            try:
                r["fixed_times_list"] = json.loads(r["remind_fixed_times"])
            except Exception:
                r["fixed_times_list"] = []
        else:
            r["fixed_times_list"] = []
    return rows


def advance_reminder(task_id: int, next_reminder_ts: Optional[int], db_path: Optional[str] = None):
    """Updates last_reminded_at to now and sets the next scheduled reminder timestamp."""
    now_ts = int(time.time())
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE todos
            SET last_reminded_at = ?, next_reminder_at = ?
            WHERE id = ?
        """, (now_ts, next_reminder_ts, task_id))
        conn.commit()


def snooze_task_by_id(task_id: int, snooze_mins: int = 30, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Postpones next reminder by snooze_mins minutes."""
    new_next = int(time.time()) + (snooze_mins * 60)
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE todos
            SET next_reminder_at = ?
            WHERE id = ? AND status = 'active'
        """, (new_next, task_id))
        conn.commit()
        cursor.execute("SELECT * FROM todos WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
