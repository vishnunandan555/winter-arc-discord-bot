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
from datetime import datetime, time as dt_time, timedelta
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
                current_count INTEGER DEFAULT 0,
                target_count INTEGER DEFAULT 1,
                reset_period TEXT DEFAULT 'none',
                reset_interval_days INTEGER DEFAULT 0,
                last_reset_date TEXT,
                next_reset_ts INTEGER,
                remind_spec TEXT,
                remind_type TEXT,
                remind_interval_mins INTEGER,
                remind_fixed_times TEXT,
                remind_window_start TEXT,
                until_spec TEXT,
                until_timestamp INTEGER,
                dm_only BOOLEAN DEFAULT 1,
                delivery_mode TEXT DEFAULT 'channel',
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

        # Migration: Ensure incognito column exists in todo_user_settings
        cursor.execute("PRAGMA table_info(todo_user_settings);")
        cols = [c[1] for c in cursor.fetchall()]
        if "incognito" not in cols:
            cursor.execute("ALTER TABLE todo_user_settings ADD COLUMN incognito BOOLEAN DEFAULT 0;")
            logger.info("Added 'incognito' column to todo_user_settings.")

        # Migration: Ensure counter & reset columns exist in todos
        cursor.execute("PRAGMA table_info(todos);")
        t_cols = [c[1] for c in cursor.fetchall()]
        if "current_count" not in t_cols:
            cursor.execute("ALTER TABLE todos ADD COLUMN current_count INTEGER DEFAULT 0;")
        if "target_count" not in t_cols:
            cursor.execute("ALTER TABLE todos ADD COLUMN target_count INTEGER DEFAULT 1;")
        if "reset_period" not in t_cols:
            cursor.execute("ALTER TABLE todos ADD COLUMN reset_period TEXT DEFAULT 'none';")
        if "reset_interval_days" not in t_cols:
            cursor.execute("ALTER TABLE todos ADD COLUMN reset_interval_days INTEGER DEFAULT 0;")
        if "last_reset_date" not in t_cols:
            cursor.execute("ALTER TABLE todos ADD COLUMN last_reset_date TEXT;")
        if "next_reset_ts" not in t_cols:
            cursor.execute("ALTER TABLE todos ADD COLUMN next_reset_ts INTEGER;")
        if "delivery_mode" not in t_cols:
            cursor.execute("ALTER TABLE todos ADD COLUMN delivery_mode TEXT DEFAULT 'channel';")
            cursor.execute("UPDATE todos SET delivery_mode = CASE WHEN dm_only = 1 THEN 'dm' ELSE 'channel' END;")
            logger.info("Added 'delivery_mode' column to todos.")

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
            res = dict(row)
            res.setdefault("incognito", 0)
            return res
        
        # Insert default
        now_ts = int(time.time())
        cursor.execute("""
            INSERT INTO todo_user_settings (user_id, dnd_enabled, dnd_start, dnd_end, timezone, default_dm, incognito, created_at)
            VALUES (?, 0, '22:00', '06:00', 'Asia/Kolkata', 1, 0, ?)
        """, (user_id, now_ts))
        conn.commit()
        return {
            "user_id": user_id,
            "dnd_enabled": 0,
            "dnd_start": "22:00",
            "dnd_end": "06:00",
            "timezone": "Asia/Kolkata",
            "default_dm": 1,
            "incognito": 0,
            "created_at": now_ts,
        }


def set_user_incognito(user_id: int, incognito: bool, db_path: Optional[str] = None) -> bool:
    """Sets the incognito mode for a user (True = ON, False = OFF)."""
    val = 1 if incognito else 0
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        now_ts = int(time.time())
        cursor.execute("""
            INSERT INTO todo_user_settings (user_id, dnd_enabled, dnd_start, dnd_end, timezone, default_dm, incognito, created_at)
            VALUES (?, 0, '22:00', '06:00', 'Asia/Kolkata', 1, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET incognito = excluded.incognito;
        """, (user_id, val, now_ts))
        conn.commit()
    logger.info(f"User {user_id} set todo incognito mode to {bool(val)}")
    return bool(val)


def is_user_incognito(user_id: int, db_path: Optional[str] = None) -> bool:
    """Checks if a user has incognito mode enabled (True = ON, False = OFF)."""
    settings = get_user_settings(user_id, db_path)
    return bool(settings.get("incognito", 0))


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
# Reset Calculation & Lazy Reset Engine
# =====================================================================

def compute_next_midnight_reset(
    reset_period: str,
    reset_interval_days: int = 0,
    from_dt: Optional[datetime] = None,
) -> Optional[int]:
    """
    Calculates Unix timestamp of the next midnight (00:00:00 IST) for the reset period.
    - 'daily': Next midnight (00:00 IST tomorrow).
    - 'weekly': Upcoming Sunday midnight (00:00 IST).
    - 'custom_days': N days from now at 00:00 IST.
    - 'none': None.
    """
    if not reset_period or reset_period == "none":
        return None

    now = from_dt if from_dt is not None else datetime.now(BOT_TZ)
    today = now.date()

    if reset_period == "daily":
        next_date = today + timedelta(days=1)
    elif reset_period == "weekly":
        # Days until next Sunday (Monday=0 ... Sunday=6)
        days_ahead = 6 - today.weekday()
        if days_ahead <= 0:  # If today is Sunday, next reset is next Sunday
            days_ahead += 7
        next_date = today + timedelta(days=days_ahead)
    elif reset_period == "custom_days":
        interval = max(1, reset_interval_days)
        next_date = today + timedelta(days=interval)
    else:
        next_date = today + timedelta(days=1)

    next_dt = datetime(next_date.year, next_date.month, next_date.day, 0, 0, 0, tzinfo=BOT_TZ)
    return int(next_dt.timestamp())


def apply_all_due_lazy_resets(db_path: Optional[str] = None):
    """Evaluates all recurring tasks across all users and resets any whose next_reset_ts has passed."""
    now_ts = int(time.time())
    now_dt = datetime.now(BOT_TZ)
    today_str = now_dt.strftime("%Y-%m-%d")
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, reset_period, reset_interval_days
            FROM todos
            WHERE reset_period != 'none' 
              AND next_reset_ts IS NOT NULL 
              AND next_reset_ts <= ?
        """, (now_ts,))
        due = cursor.fetchall()
        for t in due:
            new_ts = compute_next_midnight_reset(t["reset_period"], t["reset_interval_days"], from_dt=now_dt)
            cursor.execute("""
                UPDATE todos
                SET current_count = 0,
                    status = 'active',
                    last_reset_date = ?,
                    next_reset_ts = ?
                WHERE id = ?
            """, (today_str, new_ts, t["id"]))
        if due:
            conn.commit()


def apply_lazy_resets_for_user(user_id: int, db_path: Optional[str] = None):
    """Evaluates recurring tasks for a specific user and rolls over counts/status if reset window passed."""
    now_ts = int(time.time())
    now_dt = datetime.now(BOT_TZ)
    today_str = now_dt.strftime("%Y-%m-%d")
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, reset_period, reset_interval_days
            FROM todos
            WHERE user_id = ? 
              AND reset_period != 'none' 
              AND next_reset_ts IS NOT NULL 
              AND next_reset_ts <= ?
        """, (user_id, now_ts))
        due = cursor.fetchall()
        for t in due:
            new_ts = compute_next_midnight_reset(t["reset_period"], t["reset_interval_days"], from_dt=now_dt)
            cursor.execute("""
                UPDATE todos
                SET current_count = 0,
                    status = 'active',
                    last_reset_date = ?,
                    next_reset_ts = ?
                WHERE id = ?
            """, (today_str, new_ts, t["id"]))
        if due:
            conn.commit()


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
    current_count: int = 0,
    target_count: int = 1,
    reset_period: str = "none",
    reset_interval_days: int = 0,
    delivery_mode: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Adds a new task and returns its dict representation with its relative task number."""
    now_ts = int(time.time())
    now_dt = datetime.now(BOT_TZ)
    today_str = now_dt.strftime("%Y-%m-%d")
    fixed_json = json.dumps(remind_fixed_times) if remind_fixed_times else None

    # Priority normalization
    p_norm = priority.lower().strip()
    if p_norm not in ["high", "medium", "low", "normal"]:
        p_norm = "normal"

    # Delivery mode normalization
    if delivery_mode is not None:
        deliv = delivery_mode.lower().strip()
        if deliv not in ["channel", "dm", "both"]:
            deliv = "channel"
    else:
        deliv = "dm" if dm_only else "channel"
    dm_only_flag = 1 if deliv in ["dm", "both"] else 0

    tgt = max(1, int(target_count))
    cur = max(0, int(current_count))
    r_period = reset_period.lower().strip() if reset_period else "none"
    r_days = max(0, int(reset_interval_days))
    next_reset = compute_next_midnight_reset(r_period, r_days, from_dt=now_dt)

    status = "completed" if cur >= tgt else "active"

    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO todos (
                user_id, task_text, priority, current_count, target_count,
                reset_period, reset_interval_days, last_reset_date, next_reset_ts,
                remind_spec, remind_type, remind_interval_mins, remind_fixed_times,
                remind_window_start, until_spec, until_timestamp, dm_only, delivery_mode,
                origin_channel_id, assigned_by_user_id, status, next_reminder_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, task_text.strip(), p_norm, cur, tgt,
            r_period, r_days, today_str, next_reset,
            remind_spec, remind_type, remind_interval_mins, fixed_json,
            remind_window_start, until_spec, until_timestamp, dm_only_flag, deliv,
            origin_channel_id, assigned_by_user_id, status, next_reminder_at, now_ts
        ))
        conn.commit()
        task_id = cursor.lastrowid

    # Find its relative task number in the active list
    active_tasks = get_active_tasks(user_id, db_path=db_path)
    for t in active_tasks:
        if t["id"] == task_id:
            return t

    # If it completed immediately, retrieve directly
    t_obj = get_task_by_id(task_id, db_path=db_path)
    if t_obj:
        t_obj["num"] = 1
        return t_obj

    return {"id": task_id, "num": len(active_tasks) or 1, "task_text": task_text}


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
    apply_lazy_resets_for_user(user_id, db_path=db_path)
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


def get_completed_cycle_tasks(user_id: int, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns recurring tasks that have completed their goal for the current cycle
    (they sleep until next midnight reset, NOT sent to 7-day trash).
    """
    apply_lazy_resets_for_user(user_id, db_path=db_path)
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM todos
            WHERE user_id = ? 
              AND reset_period != 'none' 
              AND status = 'completed'
            ORDER BY completed_at DESC
        """, (user_id,))
        rows = [dict(r) for r in cursor.fetchall()]

    for item in rows:
        if item.get("remind_fixed_times"):
            try:
                item["fixed_times_list"] = json.loads(item["remind_fixed_times"])
            except Exception:
                item["fixed_times_list"] = []
        else:
            item["fixed_times_list"] = []

    return rows


def get_trashed_tasks(user_id: int, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns tasks in trash (deleted tasks, or completed one-off tasks within the 7-day retention window),
    annotated with sequential Trash IDs (T1, T2, ...).
    """
    purge_expired_trash(days=7, db_path=db_path)
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM todos
            WHERE user_id = ? 
              AND (status = 'deleted' OR (reset_period = 'none' AND status = 'completed'))
            ORDER BY trashed_at DESC
        """, (user_id,))
        rows = [dict(r) for r in cursor.fetchall()]

    for idx, item in enumerate(rows, start=1):
        item["trash_id"] = f"T{idx}"
        item["trash_num"] = idx

    return rows


def get_task_by_relative_num(user_id: int, num: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Finds an active task by relative number (#1..#N), or looks in completed cycle tasks."""
    tasks = get_active_tasks(user_id, db_path=db_path)
    for t in tasks:
        if t["num"] == num:
            return t
    completed = get_completed_cycle_tasks(user_id, db_path=db_path)
    for idx, t in enumerate(completed, start=len(tasks) + 1):
        if idx == num or t["id"] == num:
            t["num"] = idx
            return t
    return None


def get_task_by_id(task_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Finds any task by its primary database ID."""
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM todos WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        if res.get("remind_fixed_times"):
            try:
                res["fixed_times_list"] = json.loads(res["remind_fixed_times"])
            except Exception:
                res["fixed_times_list"] = []
        else:
            res["fixed_times_list"] = []
        return res


def get_trash_by_relative_num(user_id: int, num: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Finds a trashed task by its trash number (e.g. 1 for T1)."""
    trash = get_trashed_tasks(user_id, db_path=db_path)
    for t in trash:
        if t["trash_num"] == num:
            return t
    return None


def adjust_task_count(
    user_id: int,
    num: int,
    delta: int = 1,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Adjusts current_count by delta (+1 or -1) for a task.
    Clamps at minimum 0.
    Updates status:
      - If current_count >= target_count: status becomes 'completed'.
      - If current_count < target_count: status reverts to 'active'.
    Returns the updated task dict.
    """
    task = get_task_by_relative_num(user_id, num, db_path=db_path)
    if not task:
        # Check by id directly
        task = get_task_by_id(num, db_path=db_path)
        if not task or task.get("user_id") != user_id:
            return None

    task_id = task["id"]
    old_cur = int(task.get("current_count") or 0)
    target = max(1, int(task.get("target_count") or 1))
    new_cur = max(0, old_cur + delta)
    is_recurring = (task.get("reset_period", "none") != "none")

    new_status = "completed" if new_cur >= target else "active"
    now_ts = int(time.time())
    trashed = None if is_recurring else (now_ts if new_status == "completed" else None)

    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE todos
            SET current_count = ?,
                status = ?,
                completed_at = CASE WHEN ? = 'completed' THEN ? ELSE completed_at END,
                trashed_at = ?
            WHERE id = ?
        """, (new_cur, new_status, new_status, now_ts, trashed, task_id))
        conn.commit()

    task["current_count"] = new_cur
    task["status"] = new_status
    return task


def adjust_task_count_by_id(
    task_id: int,
    delta: int = 1,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Adjusts count directly by task primary database ID (used by reminder button callbacks)."""
    task = get_task_by_id(task_id, db_path=db_path)
    if not task:
        return None

    old_cur = int(task.get("current_count") or 0)
    target = max(1, int(task.get("target_count") or 1))
    new_cur = max(0, old_cur + delta)
    is_recurring = (task.get("reset_period", "none") != "none")

    new_status = "completed" if new_cur >= target else "active"
    now_ts = int(time.time())
    trashed = None if is_recurring else (now_ts if new_status == "completed" else None)

    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE todos
            SET current_count = ?,
                status = ?,
                completed_at = CASE WHEN ? = 'completed' THEN ? ELSE completed_at END,
                trashed_at = ?
            WHERE id = ?
        """, (new_cur, new_status, new_status, now_ts, trashed, task_id))
        conn.commit()

    task["current_count"] = new_cur
    task["status"] = new_status
    return task


def toggle_task_done(user_id: int, num: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Toggles task between active and completed for easy undo/completion in Control Center."""
    task = get_task_by_relative_num(user_id, num, db_path=db_path)
    if not task:
        task = get_task_by_id(num, db_path=db_path)
        if not task or task.get("user_id") != user_id:
            return None

    task_id = task["id"]
    target = max(1, int(task.get("target_count") or 1))
    is_recurring = (task.get("reset_period", "none") != "none")
    now_ts = int(time.time())

    if task["status"] == "completed":
        # Undo completion
        new_status = "active"
        new_cur = 0
        trashed = None
    else:
        # Mark done
        new_status = "completed"
        new_cur = target
        trashed = None if is_recurring else now_ts

    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE todos
            SET status = ?,
                current_count = ?,
                completed_at = CASE WHEN ? = 'completed' THEN ? ELSE NULL END,
                trashed_at = ?
            WHERE id = ?
        """, (new_status, new_cur, new_status, now_ts, trashed, task_id))
        conn.commit()

    task["status"] = new_status
    task["current_count"] = new_cur
    return task


def mark_task_done(user_id: int, num: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Marks task completed.
    - If recurring (reset_period != 'none'):
      sets current_count = target_count, status = 'completed', trashed_at = NULL (completes this cycle).
    - If one-off (reset_period == 'none'):
      sets current_count = target_count, status = 'completed', trashed_at = now_ts, next_reminder_at = NULL (moves to trash).
    """
    task = get_task_by_relative_num(user_id, num, db_path=db_path)
    if not task:
        task = get_task_by_id(num, db_path=db_path)
        if not task or task.get("user_id") != user_id:
            return None

    now_ts = int(time.time())
    is_recurring = (task.get("reset_period", "none") != "none")
    target = max(1, int(task.get("target_count") or 1))
    trashed = None if is_recurring else now_ts

    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        if is_recurring:
            cursor.execute("""
                UPDATE todos
                SET status = 'completed',
                    current_count = ?,
                    completed_at = ?,
                    trashed_at = NULL
                WHERE id = ?
            """, (target, now_ts, task["id"]))
        else:
            cursor.execute("""
                UPDATE todos
                SET status = 'completed',
                    current_count = ?,
                    completed_at = ?,
                    trashed_at = ?,
                    next_reminder_at = NULL
                WHERE id = ?
            """, (target, now_ts, trashed, task["id"]))
        conn.commit()

    task["status"] = "completed"
    task["current_count"] = target
    task["completed_at"] = now_ts
    task["trashed_at"] = trashed
    return task


def silence_task(user_id: int, num: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Silences reminders for a task while keeping it on the active task list."""
    task = get_task_by_relative_num(user_id, num, db_path=db_path)
    if not task:
        task = get_task_by_id(num, db_path=db_path)
        if not task or task.get("user_id") != user_id:
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


def unsilence_task(user_id: int, num: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Unsilences reminders for a task, returning its status to active and restoring next reminder timestamp."""
    task = get_task_by_relative_num(user_id, num, db_path=db_path)
    if not task:
        task = get_task_by_id(num, db_path=db_path)
        if not task or task.get("user_id") != user_id:
            return None

    import todo_parser as parser
    next_ts = parser.compute_next_reminder(task) if task.get("remind_spec") else None

    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE todos
            SET status = 'active', next_reminder_at = ?
            WHERE id = ?
        """, (next_ts, task["id"]))
        conn.commit()

    task["status"] = "active"
    task["next_reminder_at"] = next_ts
    return task


def delete_task(user_id: int, num: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Moves an active task directly to trash."""
    task = get_task_by_relative_num(user_id, num, db_path=db_path)
    if not task:
        task = get_task_by_id(num, db_path=db_path)
        if not task or task.get("user_id") != user_id:
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
    current_count: Optional[int] = None,
    target_count: Optional[int] = None,
    reset_period: Optional[str] = None,
    reset_interval_days: Optional[int] = None,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Edits an active task's description, priority, counter, or reminder parameters."""
    task = get_task_by_relative_num(user_id, num, db_path=db_path)
    if not task:
        task = get_task_by_id(num, db_path=db_path)
        if not task or task.get("user_id") != user_id:
            return None

    task_id = task["id"]
    text = new_task_text.strip() if new_task_text else task["task_text"]
    priority = new_priority.lower().strip() if new_priority else task["priority"]
    if priority not in ["high", "medium", "low", "normal"]:
        priority = task["priority"]

    cur = int(current_count) if current_count is not None else int(task.get("current_count") or 0)
    cur = max(0, cur)
    tgt = int(target_count) if target_count is not None else int(task.get("target_count") or 1)
    tgt = max(1, tgt)

    r_period = reset_period.lower().strip() if reset_period is not None else (task.get("reset_period") or "none")
    r_days = int(reset_interval_days) if reset_interval_days is not None else int(task.get("reset_interval_days") or 0)

    now_dt = datetime.now(BOT_TZ)
    new_reset_ts = compute_next_midnight_reset(r_period, r_days, from_dt=now_dt)

    new_status = "completed" if cur >= tgt else "active"

    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        if remove_reminder:
            cursor.execute("""
                UPDATE todos
                SET task_text = ?, priority = ?, current_count = ?, target_count = ?,
                    reset_period = ?, reset_interval_days = ?, next_reset_ts = ?,
                    remind_spec = NULL, remind_type = NULL, remind_interval_mins = NULL,
                    remind_fixed_times = NULL, remind_window_start = NULL,
                    until_spec = NULL, until_timestamp = NULL, next_reminder_at = NULL, status = ?
                WHERE id = ?
            """, (text, priority, cur, tgt, r_period, r_days, new_reset_ts, new_status, task_id))
        elif new_remind_spec:
            fixed_json = json.dumps(remind_fixed_times) if remind_fixed_times else None
            cursor.execute("""
                UPDATE todos
                SET task_text = ?, priority = ?, current_count = ?, target_count = ?,
                    reset_period = ?, reset_interval_days = ?, next_reset_ts = ?,
                    remind_spec = ?, remind_type = ?, remind_interval_mins = ?,
                    remind_fixed_times = ?, remind_window_start = ?,
                    until_spec = ?, until_timestamp = ?, next_reminder_at = ?, status = ?
                WHERE id = ?
            """, (
                text, priority, cur, tgt, r_period, r_days, new_reset_ts,
                new_remind_spec, remind_type, remind_interval_mins, fixed_json,
                remind_window_start, until_spec, until_timestamp, next_reminder_at,
                new_status, task_id
            ))
        else:
            cursor.execute("""
                UPDATE todos
                SET task_text = ?, priority = ?, current_count = ?, target_count = ?,
                    reset_period = ?, reset_interval_days = ?, next_reset_ts = ?, status = ?
                WHERE id = ?
            """, (text, priority, cur, tgt, r_period, r_days, new_reset_ts, new_status, task_id))
        conn.commit()

    return get_task_by_id(task_id, db_path=db_path)


def clear_trash(user_id: int, db_path: Optional[str] = None) -> int:
    """Instantly purges all trashed/completed one-off tasks for a user (never deletes active recurring habits)."""
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM todos
            WHERE user_id = ? 
              AND (status = 'deleted' OR (reset_period = 'none' AND status = 'completed'))
        """, (user_id,))
        count = cursor.rowcount
        conn.commit()
    return count


def purge_expired_trash(days: int = 7, db_path: Optional[str] = None) -> int:
    """Removes trashed one-off/deleted tasks exceeding the retention window (default 7 days)."""
    cutoff_ts = int(time.time()) - (days * 86400)
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM todos
            WHERE (status = 'deleted' OR (reset_period = 'none' AND status = 'completed'))
              AND trashed_at IS NOT NULL
              AND trashed_at < ?
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
    """Returns all active or completed-cycle recurring tasks where next_reminder_at has arrived."""
    apply_all_due_lazy_resets(db_path=db_path)
    with get_todo_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM todos
            WHERE status IN ('active', 'completed') 
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
