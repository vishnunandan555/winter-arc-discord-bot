"""
database.py - SQLite Data Access Object (DAO) for Winter Arc Bot

Handles:
- User enrollment & management
- Challenge tasks configuration
- Granular daily activity logging & scoring calculations
- Midnight daily summaries & dynamic streak calculation
- Server configuration persistence (dedicated channel, ping role)
"""

import os
import sqlite3
import math
import re
import logging
from contextlib import contextmanager
from datetime import datetime, date, timedelta
import calendar
from typing import List, Dict, Any, Optional, Tuple

from config import DB_PATH, MIN_STREAK_POINTS, BOT_TZ

logger = logging.getLogger("winter_arc.database")


def get_today_date() -> date:
    """Returns today's date in BOT_TZ (Asia/Kolkata / IST)."""
    return datetime.now(BOT_TZ).date()


def get_today_str() -> str:
    """Returns today's ISO date string in BOT_TZ."""
    return get_today_date().isoformat()

DEFAULT_TASKS = [
    {"name": "Push-ups", "description": "Works chest, shoulders, and triceps (1 pt / rep)", "target": 100.0, "unit": "reps", "max_points": 100},
    {"name": "Pull-ups", "description": "Works lats, upper back, and biceps (1 pt / rep)", "target": 100.0, "unit": "reps", "max_points": 100},
    {"name": "Squats", "description": "Strengthens quads, glutes, and legs (1 pt / rep)", "target": 100.0, "unit": "reps", "max_points": 100},
    {"name": "Sit-ups", "description": "Targets core and hip flexors (1 pt / rep)", "target": 100.0, "unit": "reps", "max_points": 100},
    {"name": "Running", "description": "Cardiovascular endurance (1 pt / 100m = 10 pts / km)", "target": 10.0, "unit": "km", "max_points": 100},
]


@contextmanager
def get_connection(db_path: str = DB_PATH):
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
    except sqlite3.Error as e:
        logger.error(f"Failed to connect to SQLite database at '{db_path}': {e}", exc_info=e)
        raise
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA synchronous = NORMAL;")
    except sqlite3.Error as e:
        logger.warning(f"Error applying PRAGMAs on '{db_path}': {e}")
    try:
        yield conn
    except sqlite3.Error as e:
        logger.error(f"SQLite error executing statement on '{db_path}': {e}", exc_info=e)
        raise
    finally:
        try:
            conn.close()
        except Exception as e:
            logger.debug(f"Error closing SQLite connection for '{db_path}': {e}")


def init_db(db_path: str = DB_PATH):
    """Initializes schema, settings, and seeds default tasks."""
    with get_connection(db_path) as conn:
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA wal_autocheckpoint = 500;")
            conn.execute("PRAGMA cache_size = -2000;")  # Cap memory cache to ~2 MB
        except sqlite3.Error as e:
            logger.warning(f"Error applying WAL PRAGMAs during init_db on '{db_path}': {e}")

        cursor = conn.cursor()

        # 1. Server settings table (persists dedicated channel and ping role)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS server_settings (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER DEFAULT 0,
                role_id INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. Users table (with enrolled gate)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id INTEGER UNIQUE NOT NULL,
                username TEXT NOT NULL,
                enrolled BOOLEAN DEFAULT 1,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 3. Tasks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL COLLATE NOCASE,
                description TEXT,
                target REAL NOT NULL,
                unit TEXT NOT NULL,
                max_points INTEGER NOT NULL,
                active BOOLEAN DEFAULT 1
            );
        """)

        # 4. Daily logs table (raw activity)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                task_id INTEGER NOT NULL,
                date DATE NOT NULL,
                amount REAL NOT NULL,
                logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );
        """)

        # 5. Daily summaries table (finalized at midnight)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date DATE NOT NULL,
                points INTEGER NOT NULL,
                completion_rate REAL NOT NULL,
                perfect_day BOOLEAN DEFAULT 0,
                is_shielded BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, date),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)

        # 6. Shield usage logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shield_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date DATE NOT NULL,
                reason TEXT DEFAULT 'Manual rest day',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, date),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)

        # Safe migrations for existing databases
        user_columns = [
            ("frost_shields", "INTEGER DEFAULT 0"),
            ("last_shield_milestone", "INTEGER DEFAULT 0"),
            ("dm_reminders", "BOOLEAN DEFAULT 0"),
            ("dm_morning", "BOOLEAN DEFAULT 1"),
            ("dm_afternoon", "BOOLEAN DEFAULT 1"),
            ("dm_evening", "BOOLEAN DEFAULT 1"),
        ]
        for col_name, col_def in user_columns:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def};")
            except sqlite3.OperationalError:
                pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE daily_summaries ADD COLUMN is_shielded BOOLEAN DEFAULT 0;")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # 7. Grind logs table (daily academic / mental friction logs evaluated by Gemini)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS grind_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date DATE NOT NULL,
                raw_input TEXT NOT NULL,
                verdict TEXT NOT NULL,
                points_awarded INTEGER DEFAULT 0,
                key_learning TEXT,
                commentary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, date),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)

        # Safe migrations for grind_logs if table was created in an earlier build
        grind_columns = [
            ("points_awarded", "INTEGER DEFAULT 0"),
            ("key_learning", "TEXT"),
            ("commentary", "TEXT"),
        ]
        for col_name, col_def in grind_columns:
            try:
                cursor.execute(f"ALTER TABLE grind_logs ADD COLUMN {col_name} {col_def};")
            except sqlite3.OperationalError:
                pass  # Column already exists

        # 8. Bot State table (persists scheduler triggers and operational state across restarts)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Indices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_user_date ON daily_logs(user_id, date);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_summaries_user_date ON daily_summaries(user_id, date);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_summaries_date ON daily_summaries(date);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_shield_logs_user_date ON shield_logs(user_id, date);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_grind_logs_user_date ON grind_logs(user_id, date);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_grind_logs_date ON grind_logs(date);")

        # Seed default tasks (ensures all 5 tasks and targets are present)
        for task in DEFAULT_TASKS:
            cursor.execute("""
                INSERT INTO tasks (name, description, target, unit, max_points, active)
                VALUES (:name, :description, :target, :unit, :max_points, 1)
                ON CONFLICT(name) DO UPDATE SET
                    description = excluded.description,
                    target = excluded.target,
                    unit = excluded.unit,
                    max_points = excluded.max_points,
                    active = 1;
            """, task)

        conn.commit()


# ==========================================
# Bot State Persistence DAO
# ==========================================

def get_bot_state(key: str, default: Optional[str] = None, db_path: str = DB_PATH) -> Optional[str]:
    """Retrieves a persistent key-value state for the bot (e.g. scheduler trigger dates)."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM bot_state WHERE key = ?;", (key,))
        row = cursor.fetchone()
        return str(row["value"]) if row else default


def set_bot_state(key: str, value: str, db_path: str = DB_PATH) -> None:
    """Sets a persistent key-value state for the bot."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO bot_state (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP;
        """, (key, value))
        conn.commit()


# ==========================================
# Server Settings
# ==========================================

def get_server_settings(guild_id: int, db_path: str = DB_PATH) -> Dict[str, Any]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM server_settings WHERE guild_id = ?", (guild_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return {"guild_id": guild_id, "channel_id": 0, "role_id": 0}


def set_server_channel(guild_id: int, channel_id: int, db_path: str = DB_PATH):
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO server_settings (guild_id, channel_id, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                updated_at = CURRENT_TIMESTAMP;
        """, (guild_id, channel_id))
        conn.commit()


def set_server_role(guild_id: int, role_id: int, db_path: str = DB_PATH):
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO server_settings (guild_id, role_id, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                role_id = excluded.role_id,
                updated_at = CURRENT_TIMESTAMP;
        """, (guild_id, role_id))
        conn.commit()


def get_all_server_settings(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM server_settings")
        return [dict(r) for r in cursor.fetchall()]


# ==========================================
# User & Enrollment Operations
# ==========================================

def enroll_user(discord_id: int, username: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    db_path = db_path or DB_PATH
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (discord_id, username, enrolled)
            VALUES (?, ?, 1)
            ON CONFLICT(discord_id) DO UPDATE SET username = excluded.username, enrolled = 1;
        """, (discord_id, username))
        conn.commit()

        cursor.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,))
        return dict(cursor.fetchone())


def unenroll_user(discord_id: int, db_path: Optional[str] = None) -> bool:
    db_path = db_path or DB_PATH
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET enrolled = 0 WHERE discord_id = ?", (discord_id,))
        conn.commit()
        return cursor.rowcount > 0


def is_user_enrolled(discord_id: int, db_path: Optional[str] = None) -> bool:
    db_path = db_path or DB_PATH
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT enrolled FROM users WHERE discord_id = ?", (discord_id,))
        row = cursor.fetchone()
        if not row:
            return False
        return bool(row["enrolled"])


def get_user_by_discord_id(discord_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    db_path = db_path or DB_PATH
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_enrolled_users(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    db_path = db_path or DB_PATH
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE enrolled = 1 ORDER BY joined_at ASC")
        return [dict(r) for r in cursor.fetchall()]


# ==========================================
# Task Operations
# ==========================================

def get_active_tasks(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE active = 1 ORDER BY id ASC")
        return [dict(r) for r in cursor.fetchall()]


def get_all_tasks(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks ORDER BY id ASC")
        return [dict(r) for r in cursor.fetchall()]


def get_task_by_name(name: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """
    Intelligently retrieves a task by name, resolving:
    - Exact match (e.g. 'Push-ups')
    - Autocomplete labels with emojis & targets (e.g. '💪 Push-ups (100 reps)')
    - Admin autocomplete labels (e.g. '🟢 Push-ups (Active)')
    - Casual aliases & singular/plural forms (e.g. 'pushups', 'pushup', 'squat', 'situps', 'jog', 'chin-ups')
    """
    if not name or not str(name).strip():
        return None
    raw = str(name).strip()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Exact case-insensitive match
        cursor.execute("SELECT * FROM tasks WHERE name = ? COLLATE NOCASE;", (raw,))
        row = cursor.fetchone()
        if row:
            return dict(row)

        # Retrieve all tasks to match against normalized labels & aliases
        cursor.execute("SELECT * FROM tasks;")
        all_tasks = [dict(r) for r in cursor.fetchall()]
        if not all_tasks:
            return None

        # 2. Clean display label: remove leading symbols/emojis and trailing parentheticals
        # E.g.: "💪 Push-ups (100 reps)" -> "Push-ups", "🟢 Push-ups (Active)" -> "Push-ups"
        cleaned = re.sub(r'^[^\w\s]+', '', raw).strip()
        cleaned = re.sub(r'\s*\([^)]*\)\s*$', '', cleaned).strip()
        if cleaned:
            for t in all_tasks:
                if t["name"].lower() == cleaned.lower():
                    return t

        # Helper for alphanumeric canonical form
        def to_alphanumeric(s: str) -> str:
            return re.sub(r'[^a-z0-9]', '', s.lower())

        raw_alpha = to_alphanumeric(cleaned if cleaned else raw)
        if raw_alpha:
            # 3. Direct alphanumeric match (ignoring hyphens, spaces, underscores)
            # E.g.: "pushups" <-> "Push-ups", "pullups" <-> "Pull-ups"
            for t in all_tasks:
                if to_alphanumeric(t["name"]) == raw_alpha:
                    return t

            # Singular / plural normalization (e.g. "squat" vs "squats", "pushup" vs "pushups")
            raw_singular = raw_alpha[:-1] if raw_alpha.endswith('s') and len(raw_alpha) > 3 else raw_alpha
            for t in all_tasks:
                t_alpha = to_alphanumeric(t["name"])
                t_singular = t_alpha[:-1] if t_alpha.endswith('s') and len(t_alpha) > 3 else t_alpha
                if raw_singular == t_singular:
                    return t

        # 4. Standard workout aliases mapping
        alias_map = {
            "pushup": "Push-ups",
            "pushups": "Push-ups",
            "pushie": "Push-ups",
            "pushies": "Push-ups",
            "pullup": "Pull-ups",
            "pullups": "Pull-ups",
            "chinup": "Pull-ups",
            "chinups": "Pull-ups",
            "chin": "Pull-ups",
            "chins": "Pull-ups",
            "squat": "Squats",
            "squats": "Squats",
            "situp": "Sit-ups",
            "situps": "Sit-ups",
            "crunch": "Sit-ups",
            "crunches": "Sit-ups",
            "ab": "Sit-ups",
            "abs": "Sit-ups",
            "run": "Running",
            "running": "Running",
            "jog": "Running",
            "jogging": "Running",
            "cardio": "Running",
        }
        for alias, target_name in alias_map.items():
            if raw_alpha == alias or alias in raw_alpha:
                for t in all_tasks:
                    if t["name"].lower() == target_name.lower():
                        return t

        # 5. Substring matching as final fallback
        for t in all_tasks:
            t_alpha = to_alphanumeric(t["name"])
            if t_alpha and raw_alpha and (t_alpha in raw_alpha or raw_alpha in t_alpha):
                return t

        return None


def add_task(name: str, target: float, unit: str, max_points: int, description: str = "", db_path: str = DB_PATH) -> Dict[str, Any]:
    if not name or not str(name).strip():
        raise ValueError("Task name cannot be empty.")
    if float(target) <= 0:
        raise ValueError("Task target must be greater than 0.")
    if int(max_points) <= 0:
        raise ValueError("Task max points must be greater than 0.")
    if not unit or not str(unit).strip():
        raise ValueError("Task unit cannot be empty.")

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tasks (name, description, target, unit, max_points, active)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(name) DO UPDATE SET
                description = excluded.description,
                target = excluded.target,
                unit = excluded.unit,
                max_points = excluded.max_points,
                active = 1;
        """, (name.strip(), description.strip(), target, unit.strip(), max_points))
        conn.commit()
        return get_task_by_name(name, db_path)


def toggle_task(name: str, active: Optional[bool] = None, db_path: str = DB_PATH) -> Dict[str, Any]:
    task = get_task_by_name(name, db_path)
    if not task:
        raise ValueError(f"Task '{name}' does not exist.")

    new_active = (not bool(task["active"])) if active is None else bool(active)

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET active = ? WHERE id = ?", (1 if new_active else 0, task["id"]))
        conn.commit()
        return get_task_by_name(name, db_path)


# ==========================================
# Activity Logging & Scoring Engine
# ==========================================

def log_activity(discord_id: int, username: str, task_name: str, amount: float, log_date: Optional[str] = None, db_path: str = DB_PATH) -> Dict[str, Any]:
    if amount <= 0:
        raise ValueError("Amount must be greater than 0.")
    if amount > 5000:
        raise ValueError("Amount exceeds realistic single entry limit (5,000).")

    if not is_user_enrolled(discord_id, db_path):
        raise ValueError("You are not enrolled in Winter Arc. Use /enroll first.")

    user = get_user_by_discord_id(discord_id, db_path)
    task = get_task_by_name(task_name, db_path)
    if not task:
        raise ValueError(f"Task '{task_name}' not found.")
    if not task["active"]:
        raise ValueError(f"Task '{task_name}' is currently inactive.")

    if not log_date:
        log_date = get_today_str()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total_before
            FROM daily_logs
            WHERE user_id = ? AND task_id = ? AND date = ?;
        """, (user["id"], task["id"], log_date))
        total_before = float(cursor.fetchone()["total_before"])

        cursor.execute("""
            INSERT INTO daily_logs (user_id, task_id, date, amount)
            VALUES (?, ?, ?, ?);
        """, (user["id"], task["id"], log_date, amount))
        conn.commit()

    total_after = total_before + amount
    target = float(task["target"])
    max_pts = int(task["max_points"])

    pts_before = math.floor(min(total_before / target, 1.0) * max_pts) if target > 0 else 0
    pts_after = math.floor(min(total_after / target, 1.0) * max_pts) if target > 0 else 0
    pts_delta = pts_after - pts_before

    daily_progress = get_user_daily_progress(discord_id, log_date, db_path)
    shield_awarded = False
    if daily_progress["perfect_day"] or daily_progress["total_points"] >= MIN_STREAK_POINTS:
        streak = calculate_streak(discord_id, log_date, db_path)
        shield_awarded = check_and_award_shield(discord_id, streak, db_path)

    return {
        "discord_id": discord_id,
        "username": username,
        "task_name": task["name"],
        "task_target": target,
        "target": target,
        "unit": task["unit"],
        "amount_logged": amount,
        "previous_total": total_before,
        "new_total": total_after,
        "points_earned_delta": pts_delta,
        "points_added": pts_delta,
        "task_points_total": pts_after,
        "task_max_points": max_pts,
        "is_target_reached": total_after >= target,
        "daily_points_total": daily_progress["total_points"],
        "new_points": daily_progress["total_points"],
        "daily_points_max": daily_progress["max_possible_points"],
        "daily_completion_rate": daily_progress["overall_completion_rate"],
        "date": log_date,
        "shield_awarded": shield_awarded,
    }


def set_activity(discord_id: int, username: str, task_name: str, target_amount: float, log_date: Optional[str] = None, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Directly sets/overrides the user's logged amount for a task on a specific date.
    Allows target_amount >= 0 (e.g. 0 to reset mistakes).
    """
    if target_amount < 0:
        raise ValueError("Amount cannot be negative.")
    if target_amount > 5000:
        raise ValueError("Amount exceeds realistic single entry limit (5,000).")

    if not is_user_enrolled(discord_id, db_path):
        raise ValueError("You are not enrolled in Winter Arc. Use /enroll first.")

    user = get_user_by_discord_id(discord_id, db_path)
    task = get_task_by_name(task_name, db_path)
    if not task:
        raise ValueError(f"Task '{task_name}' not found.")
    if not task["active"]:
        raise ValueError(f"Task '{task_name}' is currently inactive.")

    if not log_date:
        log_date = get_today_str()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total_before
            FROM daily_logs
            WHERE user_id = ? AND task_id = ? AND date = ?;
        """, (user["id"], task["id"], log_date))
        total_before = float(cursor.fetchone()["total_before"])

        # Delete all existing logs for this task on this day
        cursor.execute("""
            DELETE FROM daily_logs
            WHERE user_id = ? AND task_id = ? AND date = ?;
        """, (user["id"], task["id"], log_date))

        # If setting to > 0, insert single clean record
        if target_amount > 0:
            cursor.execute("""
                INSERT INTO daily_logs (user_id, task_id, date, amount)
                VALUES (?, ?, ?, ?);
            """, (user["id"], task["id"], log_date, target_amount))
        conn.commit()

    total_after = float(target_amount)
    target = float(task["target"])
    max_pts = int(task["max_points"])

    pts_before = math.floor(min(total_before / target, 1.0) * max_pts) if target > 0 else 0
    pts_after = math.floor(min(total_after / target, 1.0) * max_pts) if target > 0 else 0
    pts_delta = pts_after - pts_before

    daily_progress = get_user_daily_progress(discord_id, log_date, db_path)
    shield_awarded = False
    if daily_progress["perfect_day"] or daily_progress["total_points"] >= MIN_STREAK_POINTS:
        streak = calculate_streak(discord_id, log_date, db_path)
        shield_awarded = check_and_award_shield(discord_id, streak, db_path)

    # If updating a past date, re-finalize daily_summaries for that day so historical data stays in sync
    if log_date != get_today_str():
        try:
            finalize_daily_summaries(target_date_str=log_date, db_path=db_path)
        except Exception:
            pass

    return {
        "user_id": user["id"],
        "discord_id": discord_id,
        "username": user["username"],
        "task_name": task["name"],
        "target": target,
        "unit": task["unit"],
        "amount_set": target_amount,
        "previous_total": total_before,
        "new_total": total_after,
        "points_earned_delta": pts_delta,
        "points_added": pts_delta,
        "old_points": pts_before,
        "new_points": pts_after,
        "task_points_total": pts_after,
        "task_max_points": max_pts,
        "is_target_reached": total_after >= target,
        "daily_points_total": daily_progress["total_points"],
        "daily_points_max": daily_progress["max_possible_points"],
        "daily_completion_rate": daily_progress["overall_completion_rate"],
        "date": log_date,
        "shield_awarded": shield_awarded,
    }


def get_user_daily_progress(discord_id: int, target_date: Optional[str] = None, db_path: str = DB_PATH) -> Dict[str, Any]:
    if not target_date:
        target_date = get_today_str()

    user = get_user_by_discord_id(discord_id, db_path)
    active_tasks = get_active_tasks(db_path)

    if not user:
        return {
            "date": target_date,
            "tasks": [],
            "total_points": 0,
            "max_possible_points": sum(t["max_points"] for t in active_tasks),
            "overall_completion_rate": 0.0,
            "perfect_day": False,
        }

    task_summaries = []
    total_points = 0
    total_max_points = sum(t["max_points"] for t in active_tasks)
    all_targets_met = len(active_tasks) > 0

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        for t in active_tasks:
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) AS total_amount
                FROM daily_logs
                WHERE user_id = ? AND task_id = ? AND date = ?;
            """, (user["id"], t["id"], target_date))
            total_amount = float(cursor.fetchone()["total_amount"])
            target = float(t["target"])
            max_pts = int(t["max_points"])

            completion_ratio = min(total_amount / target, 1.0) if target > 0 else 1.0
            task_pts = math.floor(completion_ratio * max_pts)
            total_points += task_pts

            if total_amount < target:
                all_targets_met = False

            task_summaries.append({
                "task_id": t["id"],
                "name": t["name"],
                "description": t.get("description", "") or "",
                "target": target,
                "unit": t["unit"],
                "current_amount": total_amount,
                "max_points": max_pts,
                "points_earned": task_pts,
                "completion_ratio": completion_ratio,
                "completed": total_amount >= target,
            })

        cursor.execute("""
            SELECT points_awarded, verdict, key_learning, commentary, created_at
            FROM grind_logs
            WHERE user_id = ? AND date = ?;
        """, (user["id"], target_date))
        grind_row = cursor.fetchone()
        grind_points = int(grind_row["points_awarded"]) if grind_row else 0
        grind_entry = dict(grind_row) if grind_row else None

    physical_points = total_points
    total_combined_points = physical_points + grind_points
    overall_completion = (physical_points / total_max_points) if total_max_points > 0 else 0.0

    return {
        "date": target_date,
        "user_id": user["id"],
        "username": user["username"],
        "tasks": task_summaries,
        "physical_points": physical_points,
        "grind_points": grind_points,
        "grind_entry": grind_entry,
        "total_points": total_combined_points,
        "max_possible_points": total_max_points,
        "overall_completion_rate": round(overall_completion, 4),
        "perfect_day": all_targets_met,
    }


def calculate_streak(discord_id: int, as_of_date: Optional[str] = None, db_path: str = DB_PATH) -> int:
    """
    Computes active consecutive day streak up to as_of_date using an in-memory batch lookup.
    Fetches historical summaries and shield logs in 2 fast queries rather than 365 sequential DB calls.
    """
    user = get_user_by_discord_id(discord_id, db_path)
    if not user or not user["enrolled"]:
        return 0

    ref_date = date.fromisoformat(as_of_date) if as_of_date else get_today_date()
    ref_date_str = ref_date.isoformat()
    start_date_str = (ref_date - timedelta(days=365)).isoformat()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date, points, perfect_day, completion_rate, is_shielded
            FROM daily_summaries
            WHERE user_id = ? AND date >= ? AND date <= ?;
        """, (user["id"], start_date_str, ref_date_str))
        summaries = {
            r["date"]: {
                "points": int(r["points"]),
                "perfect_day": bool(r["perfect_day"]),
                "completion_rate": float(r["completion_rate"]),
                "is_shielded": bool(r["is_shielded"])
            }
            for r in cursor.fetchall()
        }

        cursor.execute("""
            SELECT date FROM shield_logs
            WHERE user_id = ? AND date >= ? AND date <= ?;
        """, (user["id"], start_date_str, ref_date_str))
        shielded_dates = {r["date"] for r in cursor.fetchall()}

    # Check ref_date completion status
    today_shielded = ref_date_str in shielded_dates
    if ref_date_str in summaries:
        s = summaries[ref_date_str]
        ref_completed = s["points"] >= MIN_STREAK_POINTS or s["perfect_day"] or s["is_shielded"]
    else:
        today_prog = get_user_daily_progress(discord_id, ref_date_str, db_path)
        ref_completed = today_prog["total_points"] >= MIN_STREAK_POINTS or today_prog["perfect_day"]

    # If ref_date was finalized in daily_summaries and was neither completed nor shielded, the streak on that day is 0
    if ref_date_str in summaries and not ref_completed and not today_shielded:
        return 0

    streak = 0
    if ref_completed or today_shielded:
        streak += 1

    current_check = ref_date - timedelta(days=1)
    for _ in range(365):
        d_str = current_check.isoformat()
        if d_str in shielded_dates:
            streak += 1
            current_check -= timedelta(days=1)
            continue

        if d_str in summaries:
            s = summaries[d_str]
            if s["points"] >= MIN_STREAK_POINTS or s["perfect_day"] or s["is_shielded"]:
                streak += 1
                current_check -= timedelta(days=1)
                continue
            else:
                break
        else:
            # Fallback for unfinalized day without summary
            day_prog = get_user_daily_progress(discord_id, d_str, db_path)
            if (day_prog["total_points"] >= MIN_STREAK_POINTS or day_prog["perfect_day"]) and day_prog["total_points"] > 0:
                streak += 1
                current_check -= timedelta(days=1)
            else:
                break

    return streak


# ==========================================
# Midnight Finalization & Leaderboards
# ==========================================

def finalize_daily_summaries(target_date_str: Optional[str] = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """
    Finalizes scores for target_date_str without holding nested SQLite locks.
    Stage 1: Gather progress and determine auto-shield decisions.
    Stage 2: Atomic write batch for summaries and shield logs.
    Stage 3: Calculate streaks and milestone rewards.
    """
    if not target_date_str:
        target_date_str = (get_today_date() - timedelta(days=1)).isoformat()

    # Stage 1: Read-only data gathering
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, discord_id, username, frost_shields FROM users WHERE enrolled = 1;")
        users = cursor.fetchall()

    user_plans = []
    day_before = (date.fromisoformat(target_date_str) - timedelta(days=1)).isoformat()

    for u in users:
        progress = get_user_daily_progress(u["discord_id"], target_date_str, db_path)
        points = progress["total_points"]
        completion = progress["overall_completion_rate"]
        perfect = 1 if progress["perfect_day"] else 0

        # Check if already manually shielded
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM shield_logs WHERE user_id = ? AND date = ?;", (u["id"], target_date_str))
            shielded = 1 if cursor.fetchone() is not None else 0

        # Auto-shield logic: if points < MIN_STREAK_POINTS and not perfect, not already shielded, has shields and past streak
        streak_qualifies = points >= MIN_STREAK_POINTS or bool(perfect)
        shields_available = u["frost_shields"] or 0
        auto_shield_applied = False
        streak_broken = False
        broken_streak_count = 0

        if not streak_qualifies and not shielded:
            past_streak = calculate_streak(u["discord_id"], day_before, db_path)
            if past_streak > 0:
                if shields_available > 0:
                    auto_shield_applied = True
                    shielded = 1
                    shields_available -= 1
                else:
                    streak_broken = True
                    broken_streak_count = past_streak

        user_plans.append({
            "id": u["id"],
            "discord_id": u["discord_id"],
            "username": u["username"],
            "points": points,
            "completion_rate": completion,
            "perfect_day": bool(perfect),
            "is_shielded": bool(shielded),
            "auto_shield_applied": auto_shield_applied,
            "frost_shields": shields_available,
            "streak_broken": streak_broken,
            "broken_streak_count": broken_streak_count,
        })

    # Stage 2: Single atomic write transaction
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        for p in user_plans:
            if p["auto_shield_applied"]:
                cursor.execute("UPDATE users SET frost_shields = ? WHERE id = ?;", (p["frost_shields"], p["id"]))
                cursor.execute("""
                    INSERT INTO shield_logs (user_id, date, reason)
                    VALUES (?, ?, 'Auto-protection (Midnight Finalization)')
                    ON CONFLICT(user_id, date) DO NOTHING;
                """, (p["id"], target_date_str))

            cursor.execute("""
                INSERT INTO daily_summaries (user_id, date, points, completion_rate, perfect_day, is_shielded)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, date) DO UPDATE SET
                    points = excluded.points,
                    completion_rate = excluded.completion_rate,
                    perfect_day = excluded.perfect_day,
                    is_shielded = excluded.is_shielded;
            """, (p["id"], target_date_str, p["points"], p["completion_rate"], 1 if p["perfect_day"] else 0, 1 if p["is_shielded"] else 0))

        conn.commit()

    # Stage 3: Compute updated streaks & award milestones outside outer lock
    leaderboard = []
    for p in user_plans:
        current_streak = calculate_streak(p["discord_id"], target_date_str, db_path)
        check_and_award_shield(p["discord_id"], current_streak, db_path)
        leaderboard.append({
            "discord_id": p["discord_id"],
            "username": p["username"],
            "points": p["points"],
            "completion_rate": p["completion_rate"],
            "perfect_day": p["perfect_day"],
            "is_shielded": p["is_shielded"],
            "auto_shield_applied": p["auto_shield_applied"],
            "shields_left": p["frost_shields"],
            "streak_broken": p["streak_broken"],
            "broken_streak_count": p["broken_streak_count"],
            "current_streak": current_streak,
        })

    leaderboard.sort(key=lambda x: (x["points"], x["completion_rate"]), reverse=True)
    return leaderboard


def get_daily_leaderboard(target_date_str: Optional[str] = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """
    Computes daily standings for all enrolled users using single batched SQL queries.
    """
    if not target_date_str:
        target_date_str = get_today_str()

    users = get_enrolled_users(db_path)
    if not users:
        return []

    active_tasks = get_active_tasks(db_path)
    total_max_points = sum(t["max_points"] for t in active_tasks)

    # 1 batch query for all users' daily logs on this date
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, task_id, COALESCE(SUM(amount), 0.0) as total_amount
            FROM daily_logs
            WHERE date = ?
            GROUP BY user_id, task_id;
        """, (target_date_str,))
        log_rows = cursor.fetchall()

        cursor.execute("""
            SELECT user_id, points_awarded
            FROM grind_logs
            WHERE date = ?;
        """, (target_date_str,))
        grind_rows = cursor.fetchall()

    user_logs: Dict[int, Dict[int, float]] = {}
    for r in log_rows:
        u_id = r["user_id"]
        if u_id not in user_logs:
            user_logs[u_id] = {}
        user_logs[u_id][r["task_id"]] = float(r["total_amount"])

    user_grinds: Dict[int, int] = {r["user_id"]: int(r["points_awarded"]) for r in grind_rows}

    results = []
    for u in users:
        u_id = u["id"]
        phys_pts = 0
        all_completed = True
        u_task_amounts = user_logs.get(u_id, {})

        for t in active_tasks:
            amt = u_task_amounts.get(t["id"], 0.0)
            target = t["target"]
            max_pts = t["max_points"]
            ratio = amt / target if target > 0 else 0.0
            task_pts = min(max_pts, math.floor(ratio * max_pts))
            phys_pts += task_pts
            if amt < target:
                all_completed = False

        grind_pts = user_grinds.get(u_id, 0)
        total_pts = phys_pts + grind_pts
        completion_rate = (phys_pts / total_max_points) if total_max_points > 0 else 0.0

        results.append({
            "discord_id": u["discord_id"],
            "username": u["username"],
            "points": total_pts,
            "max_points": total_max_points,
            "completion_rate": round(completion_rate, 4),
            "perfect_day": all_completed and len(active_tasks) > 0,
        })

    results.sort(key=lambda x: (x["points"], x["completion_rate"]), reverse=True)
    return results


def get_weekly_leaderboard(start_date_str: Optional[str] = None, end_date_str: Optional[str] = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Computes weekly standings for all enrolled users for a specific week (Monday to Sunday)."""
    today = get_today_date()
    if not start_date_str or not end_date_str:
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        start_date_str = start_of_week.isoformat()
        end_date_str = end_of_week.isoformat()

    today_str = today.isoformat()
    users = get_enrolled_users(db_path)
    if not users:
        return []

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                user_id,
                COALESCE(SUM(points), 0) AS total_points,
                COALESCE(SUM(perfect_day), 0) AS perfect_days,
                COUNT(DISTINCT date) AS recorded_days
            FROM daily_summaries
            WHERE date >= ? AND date <= ? AND date != ?
            GROUP BY user_id;
        """, (start_date_str, end_date_str, today_str))
        past_map = {r["user_id"]: r for r in cursor.fetchall()}

    today_standings = {}
    if start_date_str <= today_str <= end_date_str:
        today_standings = {d["discord_id"]: d for d in get_daily_leaderboard(today_str, db_path)}

    weekly_stats = []
    for u in users:
        past = past_map.get(u["id"])
        past_points = int(past["total_points"]) if past else 0
        perfect_days = int(past["perfect_days"]) if past else 0
        recorded_days = int(past["recorded_days"]) if past else 0

        if u["discord_id"] in today_standings:
            today_prog = today_standings[u["discord_id"]]
            total_points = past_points + today_prog["points"]
            if today_prog["perfect_day"]:
                perfect_days += 1
            if today_prog["points"] > 0:
                recorded_days += 1
        else:
            total_points = past_points

        weekly_stats.append({
            "discord_id": u["discord_id"],
            "username": u["username"],
            "total_points": total_points,
            "perfect_days": perfect_days,
            "recorded_days": recorded_days,
            "start_date": start_date_str,
            "end_date": end_date_str,
        })

    weekly_stats.sort(key=lambda x: (x["total_points"], x["perfect_days"]), reverse=True)
    return weekly_stats


def get_monthly_leaderboard(year: int, month: int, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Computes monthly standings for all enrolled users."""
    month_prefix = f"{year:04d}-{month:02d}%"
    today_str = get_today_str()
    users = get_enrolled_users(db_path)
    if not users:
        return []

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                user_id,
                COALESCE(SUM(points), 0) AS total_points,
                COALESCE(SUM(perfect_day), 0) AS perfect_days,
                COUNT(DISTINCT date) AS recorded_days
            FROM daily_summaries
            WHERE date LIKE ? AND date != ?
            GROUP BY user_id;
        """, (month_prefix, today_str))
        past_map = {r["user_id"]: r for r in cursor.fetchall()}

    today_standings = {}
    if today_str.startswith(f"{year:04d}-{month:02d}"):
        today_standings = {d["discord_id"]: d for d in get_daily_leaderboard(today_str, db_path)}

    monthly_stats = []
    for u in users:
        past = past_map.get(u["id"])
        past_points = int(past["total_points"]) if past else 0
        perfect_days = int(past["perfect_days"]) if past else 0
        recorded_days = int(past["recorded_days"]) if past else 0

        if u["discord_id"] in today_standings:
            today_prog = today_standings[u["discord_id"]]
            total_points = past_points + today_prog["points"]
            if today_prog["perfect_day"]:
                perfect_days += 1
            if today_prog["points"] > 0:
                recorded_days += 1
        else:
            total_points = past_points

        monthly_stats.append({
            "discord_id": u["discord_id"],
            "username": u["username"],
            "total_points": total_points,
            "perfect_days": perfect_days,
            "recorded_days": recorded_days,
        })

    monthly_stats.sort(key=lambda x: (x["total_points"], x["perfect_days"]), reverse=True)
    return monthly_stats


def get_overall_leaderboard(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """
    Computes all-time overall standings for all enrolled users:
    Sums all past finalized days from daily_summaries + today's live activity from daily_logs.
    """
    today_str = get_today_str()
    users = get_enrolled_users(db_path)
    if not users:
        return []

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                user_id,
                COALESCE(SUM(points), 0) AS total_points,
                COALESCE(SUM(perfect_day), 0) AS perfect_days,
                COUNT(DISTINCT date) AS recorded_days
            FROM daily_summaries
            WHERE date != ?
            GROUP BY user_id;
        """, (today_str,))
        past_map = {r["user_id"]: r for r in cursor.fetchall()}

    today_standings = {d["discord_id"]: d for d in get_daily_leaderboard(today_str, db_path)}

    overall_stats = []
    for u in users:
        past = past_map.get(u["id"])
        past_points = int(past["total_points"]) if past else 0
        perfect_days = int(past["perfect_days"]) if past else 0
        recorded_days = int(past["recorded_days"]) if past else 0

        today_prog = today_standings.get(u["discord_id"], {"points": 0, "perfect_day": False})
        total_points = past_points + today_prog["points"]
        if today_prog["perfect_day"]:
            perfect_days += 1
        if today_prog["points"] > 0:
            recorded_days += 1

        streak = calculate_streak(u["discord_id"], today_str, db_path)

        overall_stats.append({
            "discord_id": u["discord_id"],
            "username": u["username"],
            "total_points": total_points,
            "perfect_days": perfect_days,
            "recorded_days": recorded_days,
            "streak": streak,
        })

    overall_stats.sort(key=lambda x: (x["total_points"], x["perfect_days"], x["streak"]), reverse=True)
    return overall_stats


def get_user_all_time_rank(discord_id: int, db_path: str = DB_PATH) -> Tuple[int, int]:
    """
    Returns (rank, total_warriors) for the user on the all-time overall leaderboard (1-indexed).
    If user is not enrolled or not found, returns (0, total_warriors).
    """
    overall = get_overall_leaderboard(db_path)
    total = len(overall)
    for idx, entry in enumerate(overall):
        if entry["discord_id"] == discord_id:
            return idx + 1, total
    return 0, total


def get_user_lifetime_points(discord_id: int, db_path: str = DB_PATH) -> int:
    """Returns the user's live all-time total points (finalized days + today's points)."""
    user = get_user_by_discord_id(discord_id, db_path)
    if not user:
        return 0

    today_str = get_today_str()
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COALESCE(SUM(points), 0) AS past_points
            FROM daily_summaries
            WHERE user_id = ? AND date != ?;
        """, (user["id"], today_str))
        row = cursor.fetchone()
        past_points = int(row["past_points"]) if row else 0

    today_prog = get_user_daily_progress(discord_id, today_str, db_path)
    return past_points + today_prog["total_points"]


def get_user_stats(discord_id: int, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Returns user's comprehensive statistics including streak, live lifetime points,
    perfect days, active days, and total volume logged per discipline.
    """
    user = get_user_by_discord_id(discord_id, db_path)
    if not user:
        return {}

    today_str = get_today_str()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COALESCE(SUM(points), 0) AS past_points,
                COALESCE(SUM(perfect_day), 0) AS perfect_days,
                COUNT(DISTINCT date) AS past_active_days
            FROM daily_summaries
            WHERE user_id = ? AND date != ?;
        """, (user["id"], today_str))
        summary = cursor.fetchone()
        past_points = int(summary["past_points"]) if summary else 0
        perfect_days = int(summary["perfect_days"]) if summary else 0
        active_days = int(summary["past_active_days"]) if summary else 0

        cursor.execute("""
            SELECT t.name, t.unit, COALESCE(SUM(l.amount), 0) as total_volume
            FROM tasks t
            LEFT JOIN daily_logs l ON t.id = l.task_id AND l.user_id = ?
            GROUP BY t.id
            ORDER BY t.id ASC;
        """, (user["id"],))
        task_totals = [dict(r) for r in cursor.fetchall()]

    today_prog = get_user_daily_progress(discord_id, today_str, db_path)
    total_lifetime_points = past_points + today_prog["total_points"]
    if today_prog["perfect_day"]:
        perfect_days += 1
    if today_prog["total_points"] > 0:
        active_days += 1

    streak = calculate_streak(discord_id, db_path=db_path)

    return {
        "user_id": user["id"],
        "discord_id": user["discord_id"],
        "username": user["username"],
        "enrolled": bool(user["enrolled"]),
        "joined_at": user["joined_at"],
        "current_streak": streak,
        "lifetime_points": total_lifetime_points,
        "perfect_days": perfect_days,
        "active_days": active_days,
        "task_totals": task_totals,
    }


def get_user_history(discord_id: int, days: int = 7, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    user = get_user_by_discord_id(discord_id, db_path)
    if not user:
        return []

    history = []
    today = get_today_date()
    today_str = today.isoformat()
    start_d_str = (today - timedelta(days=days)).isoformat()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date, points, completion_rate, perfect_day
            FROM daily_summaries
            WHERE user_id = ? AND date >= ? AND date < ?;
        """, (user["id"], start_d_str, today_str))
        past_summaries = {r["date"]: dict(r) for r in cursor.fetchall()}

        cursor.execute("""
            SELECT date, verdict, points_awarded, key_learning
            FROM grind_logs
            WHERE user_id = ? AND date >= ? AND date <= ?;
        """, (user["id"], start_d_str, today_str))
        grinds_by_date = {r["date"]: dict(r) for r in cursor.fetchall()}

    for i in range(days):
        d_str = (today - timedelta(days=i)).isoformat()
        day_grind = grinds_by_date.get(d_str)
        if d_str in past_summaries:
            s = past_summaries[d_str]
            history.append({
                "date": d_str,
                "points": int(s["points"]),
                "max_points": 500,
                "completion_rate": float(s["completion_rate"]),
                "perfect_day": bool(s["perfect_day"]),
                "grind_entry": day_grind,
            })
        else:
            prog = get_user_daily_progress(discord_id, d_str, db_path)
            history.append({
                "date": d_str,
                "points": prog["total_points"],
                "max_points": prog["max_possible_points"],
                "completion_rate": prog["overall_completion_rate"],
                "perfect_day": prog["perfect_day"],
                "grind_entry": day_grind or prog.get("grind_entry"),
            })

    return history


# ==========================================
# Frost Shield & Streak Protection DAO
# ==========================================

def get_user_shield_status(discord_id: int, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Returns current shield capacity, availability, and progress to next shield."""
    db_path = db_path or DB_PATH
    user = get_user_by_discord_id(discord_id, db_path)
    if not user:
        return {
            "frost_shields": 0,
            "inventory": 0,
            "max_shields": 2,
            "is_today_shielded": False,
            "is_shielded_today": False,
            "auto_protect_ready": False,
            "current_streak": 0,
            "days_until_next_shield": 7,
            "recent_uses": [],
        }

    today_str = get_today_str()
    streak = calculate_streak(discord_id, today_str, db_path)

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM shield_logs WHERE user_id = ? AND date = ?;", (user["id"], today_str))
        is_today_shielded = cursor.fetchone() is not None

        cursor.execute("""
            SELECT date, reason, created_at
            FROM shield_logs
            WHERE user_id = ?
            ORDER BY date DESC
            LIMIT 5;
        """, (user["id"],))
        recent_uses = [dict(r) for r in cursor.fetchall()]

    days_into_cycle = streak % 7
    days_until_next = 7 if (days_into_cycle == 0 and streak == 0) else (7 - days_into_cycle)

    shields = user.get("frost_shields", 0) or 0
    return {
        "frost_shields": shields,
        "inventory": shields,
        "max_shields": 2,
        "is_today_shielded": is_today_shielded,
        "is_shielded_today": is_today_shielded,
        "auto_protect_ready": shields > 0,
        "current_streak": streak,
        "days_until_next_shield": days_until_next,
        "recent_uses": recent_uses,
    }


def activate_frost_shield(discord_id: int, target_date: Optional[str] = None, reason: str = "Manual rest day", db_path: Optional[str] = None) -> Dict[str, Any]:
    """Consumes 1 Streak Shield for the user and protects their streak on target_date."""
    db_path = db_path or DB_PATH
    user = get_user_by_discord_id(discord_id, db_path)
    if not user or not user["enrolled"]:
        raise ValueError("You must be enrolled in Winter Arc to use a Streak Shield.")

    shields = user.get("frost_shields", 0) or 0
    if shields <= 0:
        raise ValueError("You have 0 Streak Shields available. Maintain a 7-day streak to earn a shield.")

    target_date_str = target_date or get_today_str()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM shield_logs WHERE user_id = ? AND date = ?;", (user["id"], target_date_str))
        if cursor.fetchone():
            raise ValueError(f"A Streak Shield is already active for {target_date_str}.")

        cursor.execute("UPDATE users SET frost_shields = frost_shields - 1 WHERE id = ?;", (user["id"],))
        cursor.execute("""
            INSERT INTO shield_logs (user_id, date, reason)
            VALUES (?, ?, ?);
        """, (user["id"], target_date_str, reason))

        cursor.execute("UPDATE daily_summaries SET is_shielded = 1 WHERE user_id = ? AND date = ?;", (user["id"], target_date_str))
        conn.commit()

    return {
        "success": True,
        "target_date": target_date_str,
        "remaining_shields": shields - 1,
        "reason": reason,
    }


def check_and_award_shield(discord_id: int, streak: int, db_path: Optional[str] = None) -> bool:
    """Awards +1 Frost Shield (up to 2) if streak reaches a new 7-day milestone."""
    db_path = db_path or DB_PATH
    user = get_user_by_discord_id(discord_id, db_path)
    if not user:
        return False

    last_milestone = user.get("last_shield_milestone", 0) or 0
    current_shields = user.get("frost_shields", 0) or 0

    # If the user's streak fell below their previous milestone (streak broken), reset the tracked milestone
    if streak < last_milestone:
        last_milestone = (streak // 7) * 7
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users
                SET last_shield_milestone = ?
                WHERE id = ?;
            """, (last_milestone, user["id"]))
            conn.commit()

    if streak < 7:
        return False

    milestone = (streak // 7) * 7
    if milestone > last_milestone:
        new_shields = min(2, current_shields + 1)
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users
                SET frost_shields = ?, last_shield_milestone = ?
                WHERE id = ?;
            """, (new_shields, milestone, user["id"]))
            conn.commit()
        return new_shields > current_shields

    return False


# ==========================================
# Direct Messaging Preferences DAO
# ==========================================

def get_user_dm_settings(discord_id: int, db_path: str = DB_PATH) -> Dict[str, Any]:
    """Retrieves user's private DM notification preferences."""
    user = get_user_by_discord_id(discord_id, db_path)
    if not user:
        return {
            "dm_reminders": False,
            "dm_morning": True,
            "dm_afternoon": True,
            "dm_evening": True,
        }
    return {
        "dm_reminders": bool(user.get("dm_reminders", 0)),
        "dm_morning": bool(user.get("dm_morning", 1) if user.get("dm_morning") is not None else 1),
        "dm_afternoon": bool(user.get("dm_afternoon", 1) if user.get("dm_afternoon") is not None else 1),
        "dm_evening": bool(user.get("dm_evening", 1) if user.get("dm_evening") is not None else 1),
    }


def update_user_dm_settings(
    discord_id: int,
    dm_reminders: Optional[bool] = None,
    dm_morning: Optional[bool] = None,
    dm_afternoon: Optional[bool] = None,
    dm_evening: Optional[bool] = None,
    db_path: str = DB_PATH
) -> Dict[str, Any]:
    """Updates user's private DM notification preferences."""
    user = get_user_by_discord_id(discord_id, db_path)
    if not user:
        raise ValueError("User not found in Winter Arc database.")

    updates = []
    params = []
    if dm_reminders is not None:
        updates.append("dm_reminders = ?")
        params.append(1 if dm_reminders else 0)
    if dm_morning is not None:
        updates.append("dm_morning = ?")
        params.append(1 if dm_morning else 0)
    if dm_afternoon is not None:
        updates.append("dm_afternoon = ?")
        params.append(1 if dm_afternoon else 0)
    if dm_evening is not None:
        updates.append("dm_evening = ?")
        params.append(1 if dm_evening else 0)

    if updates:
        allowed_clauses = {"dm_reminders = ?", "dm_morning = ?", "dm_afternoon = ?", "dm_evening = ?"}
        if not all(clause in allowed_clauses for clause in updates):
            raise ValueError("Unauthorized column modification attempt.")
        params.append(user["id"])
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?;", params)
            conn.commit()

    return get_user_dm_settings(discord_id, db_path)


def get_opted_in_dm_users(category: str = "all", db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Fetches users who have enabled DMs, optionally filtered by category (morning/afternoon/evening)."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM users WHERE enrolled = 1 AND dm_reminders = 1"
        if category == "morning":
            query += " AND dm_morning = 1"
        elif category == "afternoon":
            query += " AND dm_afternoon = 1"
        elif category == "evening":
            query += " AND dm_evening = 1"
        query += " ORDER BY id ASC;"
        cursor.execute(query)
        return [dict(r) for r in cursor.fetchall()]


def get_user_weekly_briefing_context(discord_id: int, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Gathers 7-day personal accountability context for dynamic morning AI briefing:
    - Active streak
    - Past 7 days score breakdown (points, shield use, completion rate)
    - Total points logged across the week
    - Days hitting minimum (>= 30 pts) vs missed/shielded days
    - Primary physical disciplines trained
    - Recent deep work / grind topics
    - Remaining Frost Shield inventory
    """
    user = get_user_by_discord_id(discord_id, db_path)
    if not user:
        return {}

    today_str = get_today_str()
    streak = calculate_streak(discord_id, today_str, db_path)
    history_7d = get_user_history(discord_id, days=7, db_path=db_path)
    recent_logs = get_user_recent_logs(discord_id, limit=6, db_path=db_path)
    recent_grinds = get_user_recent_grinds(discord_id, limit=3, db_path=db_path)

    total_pts_7d = sum(d.get("points", 0) for d in history_7d)
    solid_days = sum(1 for d in history_7d if d.get("points", 0) >= 30)
    perfect_days = sum(1 for d in history_7d if d.get("perfect_day", False) or d.get("points", 0) >= 500)
    zero_days = sum(1 for d in history_7d if d.get("points", 0) == 0)

    # Aggregate physical volume
    task_vol: Dict[str, float] = {}
    for l in recent_logs:
        t_name = l.get("task_name", "task")
        task_vol[t_name] = task_vol.get(t_name, 0.0) + float(l.get("amount", 0))

    top_disciplines = [f"{v:.0f} {k}" for k, v in sorted(task_vol.items(), key=lambda x: x[1], reverse=True)[:3]]
    recent_grind_topics = [g.get("key_learning") or g.get("raw_input", "")[:40] for g in recent_grinds if g.get("key_learning") or g.get("raw_input")]

    return {
        "discord_id": discord_id,
        "username": user.get("username", "Warrior"),
        "streak": streak,
        "frost_shields": user.get("frost_shields", 0),
        "total_pts_7d": total_pts_7d,
        "solid_days": solid_days,
        "perfect_days": perfect_days,
        "zero_days": zero_days,
        "history_7d": history_7d,
        "top_disciplines": top_disciplines,
        "recent_grinds": recent_grind_topics,
    }


# ==========================================
# Grind Logs & Academic Friction DAO
# ==========================================

def record_grind_entry(
    discord_id: int,
    date_str: str,
    raw_input: str,
    verdict: str,
    points: int,
    key_learning: str,
    commentary: str,
    db_path: str = DB_PATH
) -> Dict[str, Any]:
    """Records an evaluated grind entry. Strictly enforces 1 submission per calendar day."""
    user = get_user_by_discord_id(discord_id, db_path)
    if not user or not user["enrolled"]:
        raise ValueError("You must be enrolled in Winter Arc to submit daily grind evaluations.")

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM grind_logs WHERE user_id = ? AND date = ?;", (user["id"], date_str))
        if cursor.fetchone():
            raise ValueError("You have already submitted your daily /grind evaluation for today. Returns at 00:00 IST.")

        cursor.execute("""
            INSERT INTO grind_logs (user_id, date, raw_input, verdict, points_awarded, key_learning, commentary)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (user["id"], date_str, raw_input, verdict, points, key_learning, commentary))
        conn.commit()

        cursor.execute("SELECT * FROM grind_logs WHERE id = last_insert_rowid();")
        return dict(cursor.fetchone())


# Alias for backward compatibility / tests
log_grind = record_grind_entry


def get_user_daily_grind(discord_id: int, date_str: Optional[str] = None, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Retrieves user's grind log entry for a specific date."""
    user = get_user_by_discord_id(discord_id, db_path)
    if not user:
        return None

    target_date = date_str or get_today_str()
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM grind_logs WHERE user_id = ? AND date = ?;
        """, (user["id"], target_date))
        row = cursor.fetchone()
        if row:
            res = dict(row)
            res["points"] = res["points_awarded"]
            return res
        return None


def cap_user_grind(discord_id: int, date_str: Optional[str] = None, reason: str = "Cap confirmed", db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Zeroes out grind points for a user on date_str and marks verdict as CAPPED."""
    user = get_user_by_discord_id(discord_id, db_path)
    if not user:
        return None
    target_date = date_str or get_today_str()
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, points_awarded, raw_input, key_learning FROM grind_logs WHERE user_id = ? AND date = ?;", (user["id"], target_date))
        row = cursor.fetchone()
        if not row:
            return None
        old_points = row["points_awarded"]
        cursor.execute("""
            UPDATE grind_logs
            SET points_awarded = 0, verdict = 'CAPPED', commentary = ?
            WHERE id = ?;
        """, (f"[CAPPED]: {reason}", row["id"]))

        # If a finalized daily_summary already exists for this date, adjust its points
        cursor.execute("""
            UPDATE daily_summaries
            SET points = MAX(0, points - ?)
            WHERE user_id = ? AND date = ?;
        """, (old_points, user["id"], target_date))

        conn.commit()
        return {
            "grind_id": row["id"],
            "old_points": old_points,
            "date": target_date,
            "user_id": user["id"],
            "raw_input": row["raw_input"],
            "key_learning": row["key_learning"]
        }


def set_grind_probation(discord_id: int, days: Optional[int] = None, db_path: str = DB_PATH) -> str:
    """Sets grind probation for a user. If days is None or <=0, sets indefinite probation."""
    from datetime import datetime, timedelta
    from config import BOT_TZ
    if days is not None and days > 0:
        until_dt = datetime.now(BOT_TZ) + timedelta(days=days)
        val = until_dt.isoformat()
    else:
        val = "INDEFINITE"
    set_bot_state(f"grind_ban_{discord_id}", val, db_path=db_path)
    return val


def get_grind_probation(discord_id: int, db_path: str = DB_PATH) -> Dict[str, Any]:
    """Checks if a user is currently on grind probation. Returns dict with is_blocked and remaining_days."""
    from datetime import datetime
    from config import BOT_TZ
    val = get_bot_state(f"grind_ban_{discord_id}", db_path=db_path)
    if not val:
        return {"is_blocked": False, "remaining_days": None, "until_iso": None}

    if val == "INDEFINITE":
        return {"is_blocked": True, "remaining_days": None, "until_iso": "INDEFINITE"}

    try:
        until_dt = datetime.fromisoformat(val)
        now = datetime.now(BOT_TZ)
        if now < until_dt:
            delta = until_dt - now
            rem_days = max(1, delta.days + (1 if delta.seconds > 0 else 0))
            return {
                "is_blocked": True,
                "remaining_days": rem_days,
                "until_iso": val,
                "until_dt": until_dt
            }
        else:
            clear_grind_probation(discord_id, db_path=db_path)
            return {"is_blocked": False, "remaining_days": None, "until_iso": None}
    except Exception:
        return {"is_blocked": False, "remaining_days": None, "until_iso": None}


def clear_grind_probation(discord_id: int, db_path: str = DB_PATH) -> bool:
    """Removes grind probation for a user."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bot_state WHERE key = ?;", (f"grind_ban_{discord_id}",))
        conn.commit()
        return cursor.rowcount > 0


def get_daily_grind_highlights(date_str: str, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Fetches accepted, non-zero grind achievements for a given date."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT g.*, u.username, u.discord_id
            FROM grind_logs g
            JOIN users u ON g.user_id = u.id
            WHERE g.date = ? AND g.verdict = 'ACCEPTED' AND g.points_awarded > 0
            ORDER BY g.points_awarded DESC;
        """, (date_str,))
        return [dict(r) for r in cursor.fetchall()]


def get_weekly_grind_highlights(start_date_str: str, end_date_str: str, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Fetches accepted grind achievements within a date range."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT g.*, u.username, u.discord_id
            FROM grind_logs g
            JOIN users u ON g.user_id = u.id
            WHERE g.date >= ? AND g.date <= ? AND g.verdict = 'ACCEPTED' AND g.points_awarded > 0
            ORDER BY g.points_awarded DESC
            LIMIT 10;
        """, (start_date_str, end_date_str))
        return [dict(r) for r in cursor.fetchall()]


def get_user_recent_logs(discord_id: int, limit: int = 5, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Fetches user's most recent physical activity logs."""
    user = get_user_by_discord_id(discord_id, db_path)
    if not user:
        return []
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT l.date, l.amount, t.name as task_name, t.unit
            FROM daily_logs l
            JOIN tasks t ON l.task_id = t.id
            WHERE l.user_id = ?
            ORDER BY l.date DESC, l.id DESC
            LIMIT ?;
        """, (user["id"], limit))
        return [dict(r) for r in cursor.fetchall()]


def get_user_recent_grinds(discord_id: int, limit: int = 3, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Fetches user's most recent technical grind logs."""
    user = get_user_by_discord_id(discord_id, db_path)
    if not user:
        return []
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT g.date, g.verdict, g.points_awarded, g.key_learning
            FROM grind_logs g
            WHERE g.user_id = ?
            ORDER BY g.date DESC, g.id DESC
            LIMIT ?;
        """, (user["id"], limit))
        return [dict(r) for r in cursor.fetchall()]


# ==========================================
# Phase Progression, Standings & Snapshots
# ==========================================

def get_phase_leaderboard(phase_id: int, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """
    Computes standings for all enrolled users strictly within phase date boundaries.
    Aggregates finalized daily_summaries within [start_date, end_date] plus today's live progress if today falls in the phase.
    """
    from phases import get_phase_by_id
    phase = get_phase_by_id(phase_id)
    if not phase:
        return []

    start_date = phase["start_date"]
    end_date = phase["end_date"]
    today_str = get_today_str()
    include_today = (start_date <= today_str <= end_date)

    enrolled = get_enrolled_users(db_path)
    if not enrolled:
        return []

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        exclude_date = today_str if include_today else ""
        cursor.execute("""
            SELECT user_id, 
                   COALESCE(SUM(points), 0) AS total_pts, 
                   COALESCE(SUM(perfect_day), 0) AS perfect_days,
                   COUNT(DISTINCT date) AS active_days
            FROM daily_summaries
            WHERE date >= ? AND date <= ? AND date != ?
            GROUP BY user_id;
        """, (start_date, end_date, exclude_date))
        summary_map = {r["user_id"]: dict(r) for r in cursor.fetchall()}

    leaderboard = []
    for u in enrolled:
        u_id = u["id"]
        d_id = u["discord_id"]
        sm = summary_map.get(u_id, {"total_pts": 0, "perfect_days": 0, "active_days": 0})
        pts = int(sm["total_pts"])
        perfect = int(sm["perfect_days"])
        active = int(sm["active_days"])

        if include_today:
            today_prog = get_user_daily_progress(d_id, today_str, db_path)
            today_pts = int(today_prog.get("total_points", 0))
            pts += today_pts
            if today_prog.get("perfect_day"):
                perfect += 1
            if today_pts > 0:
                active += 1

        streak = calculate_streak(d_id, end_date if not include_today else today_str, db_path)

        leaderboard.append({
            "user_id": u_id,
            "discord_id": d_id,
            "username": u["username"],
            "total_points": pts,
            "perfect_days": perfect,
            "active_days": active,
            "streak": streak,
        })

    leaderboard.sort(key=lambda x: (x["total_points"], x["perfect_days"]), reverse=True)
    for idx, item in enumerate(leaderboard, start=1):
        item["rank"] = idx

    return leaderboard


def get_user_phase_stats(discord_id: int, phase_id: int, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Returns user's detailed performance for a specific phase:
    - Phase rank & total participants
    - Total points earned in phase
    - Perfect days & active days in phase
    - Discipline totals (pushups, pullups, etc.) in phase
    - Shields used in phase
    - Grind logs in phase
    """
    from phases import get_phase_by_id
    phase = get_phase_by_id(phase_id)
    if not phase:
        return {}

    user = get_user_by_discord_id(discord_id, db_path)
    if not user:
        return {}

    start_date = phase["start_date"]
    end_date = phase["end_date"]
    today_str = get_today_str()
    include_today = (start_date <= today_str <= end_date)

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        exclude_date = today_str if include_today else ""
        cursor.execute("""
            SELECT COALESCE(SUM(points), 0) AS total_pts,
                   COALESCE(SUM(perfect_day), 0) AS perfect_days,
                   COUNT(DISTINCT date) AS active_days
            FROM daily_summaries
            WHERE user_id = ? AND date >= ? AND date <= ? AND date != ?;
        """, (user["id"], start_date, end_date, exclude_date))
        row = cursor.fetchone()
        past_pts = int(row["total_pts"]) if row else 0
        perfect_days = int(row["perfect_days"]) if row else 0
        active_days = int(row["active_days"]) if row else 0

        # Discipline volume strictly within phase
        cursor.execute("""
            SELECT t.name, t.unit, COALESCE(SUM(l.amount), 0) as total_volume
            FROM tasks t
            LEFT JOIN daily_logs l ON t.id = l.task_id AND l.user_id = ? AND l.date >= ? AND l.date <= ?
            GROUP BY t.id
            ORDER BY t.id ASC;
        """, (user["id"], start_date, end_date))
        task_totals = [dict(r) for r in cursor.fetchall()]

        # Shields used in phase
        cursor.execute("""
            SELECT COUNT(*) AS shields_used
            FROM shield_logs
            WHERE user_id = ? AND date >= ? AND date <= ?;
        """, (user["id"], start_date, end_date))
        s_row = cursor.fetchone()
        shields_used = int(s_row["shields_used"]) if s_row else 0

        # Grind logs in phase
        cursor.execute("""
            SELECT COUNT(*) AS grind_count, COALESCE(SUM(points_awarded), 0) AS grind_points
            FROM grind_logs
            WHERE user_id = ? AND date >= ? AND date <= ?;
        """, (user["id"], start_date, end_date))
        grind_row = cursor.fetchone()
        grind_count = int(grind_row["grind_count"]) if grind_row else 0
        grind_points = int(grind_row["grind_points"]) if grind_row else 0

    total_points = past_pts
    if include_today:
        today_prog = get_user_daily_progress(discord_id, today_str, db_path)
        today_pts = int(today_prog.get("total_points", 0))
        total_points += today_pts
        if today_prog.get("perfect_day"):
            perfect_days += 1
        if today_pts > 0:
            active_days += 1

    # Find phase rank
    lb = get_phase_leaderboard(phase_id, db_path)
    total_participants = len(lb)
    phase_rank = 1
    for item in lb:
        if item["discord_id"] == discord_id:
            phase_rank = item["rank"]
            break

    return {
        "user_id": user["id"],
        "discord_id": user["discord_id"],
        "username": user["username"],
        "phase": phase,
        "phase_rank": phase_rank,
        "total_participants": total_participants,
        "total_points": total_points,
        "perfect_days": perfect_days,
        "active_days": active_days,
        "shields_used": shields_used,
        "grind_count": grind_count,
        "grind_points": grind_points,
        "task_totals": task_totals,
    }


def get_user_overall_recap(discord_id: int, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Summarizes user's overall Winter Arc performance across all phases (Oct 1 to Jan 31).
    """
    user = get_user_by_discord_id(discord_id, db_path)
    if not user:
        return {}

    stats = get_user_stats(discord_id, db_path)
    all_time_rank, total_warriors = get_user_all_time_rank(discord_id, db_path)

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS total_shields FROM shield_logs WHERE user_id = ?;", (user["id"],))
        s_row = cursor.fetchone()
        total_shields = int(s_row["total_shields"]) if s_row else 0

        cursor.execute("""
            SELECT COUNT(*) AS total_grinds, COALESCE(SUM(points_awarded), 0) AS grind_points 
            FROM grind_logs 
            WHERE user_id = ?;
        """, (user["id"],))
        grow = cursor.fetchone()
        total_grinds = int(grow["total_grinds"]) if grow else 0
        grind_points = int(grow["grind_points"]) if grow else 0

    return {
        "user_id": user["id"],
        "discord_id": user["discord_id"],
        "username": user["username"],
        "all_time_rank": all_time_rank,
        "total_warriors": total_warriors,
        "lifetime_points": stats.get("lifetime_points", 0),
        "current_streak": stats.get("current_streak", 0),
        "perfect_days": stats.get("perfect_days", 0),
        "active_days": stats.get("active_days", 0),
        "total_shields": total_shields,
        "total_grinds": total_grinds,
        "grind_points": grind_points,
        "task_totals": stats.get("task_totals", []),
    }


def get_server_records(phase_id: Optional[int] = None, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Computes server-wide benchmarks, records, and cumulative volume for a specific phase
    or the overall campaign:
    - Achievements & Records: Longest streak, Daily Maxers (highest single-day points),
      Most Perfect Days, Most Grinded Member, Single Day Peaks per exercise.
    - Server Totals: Total points, active contributors, total perfect days,
      deep work sessions, and total exercise volume.
    """
    from phases import get_phase_by_id
    phase = get_phase_by_id(phase_id) if phase_id is not None else None
    start_date = phase["start_date"] if phase else None
    end_date = phase["end_date"] if phase else None
    today_str = get_today_str()
    include_today = (start_date is None or (start_date <= today_str <= end_date))

    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        date_clause_summ = ""
        date_params_summ: List[Any] = []
        date_clause_logs = ""
        date_params_logs: List[Any] = []

        if start_date and end_date:
            date_clause_summ = "WHERE s.date >= ? AND s.date <= ?"
            date_params_summ = [start_date, end_date]
            date_clause_logs = "WHERE l.date >= ? AND l.date <= ?"
            date_params_logs = [start_date, end_date]

        # 1. Longest Streak
        longest_streak_record = None
        enrolled_users = get_enrolled_users(db_path)
        if not phase_id:
            best_streak = 0
            best_user = None
            for u in enrolled_users:
                u_streak = calculate_streak(u["discord_id"], db_path=db_path)
                if u_streak > best_streak:
                    best_streak = u_streak
                    best_user = u
            if best_user and best_streak > 0:
                longest_streak_record = {
                    "discord_id": best_user["discord_id"],
                    "username": best_user["username"],
                    "streak": best_streak,
                }
        else:
            cursor.execute(f"""
                SELECT u.discord_id, u.username, COUNT(s.id) as days_in_phase
                FROM daily_summaries s
                JOIN users u ON s.user_id = u.id
                {date_clause_summ} AND (s.points >= {MIN_STREAK_POINTS} OR s.is_shielded = 1)
                GROUP BY s.user_id
                ORDER BY days_in_phase DESC, SUM(s.points) DESC
                LIMIT 1;
            """, date_params_summ)
            s_row = cursor.fetchone()
            if s_row and int(s_row["days_in_phase"]) > 0:
                longest_streak_record = {
                    "discord_id": s_row["discord_id"],
                    "username": s_row["username"],
                    "streak": int(s_row["days_in_phase"]),
                }

        # 2. Daily Maxers (Highest single day score and who hit it)
        cursor.execute(f"""
            SELECT u.discord_id, u.username, s.points, s.date
            FROM daily_summaries s
            JOIN users u ON s.user_id = u.id
            {date_clause_summ}
            ORDER BY s.points DESC
            LIMIT 50;
        """, date_params_summ)
        summ_pts = cursor.fetchall()

        live_pts_map: Dict[int, Dict[str, Any]] = {}
        if include_today:
            active_enrolled = get_enrolled_users(db_path)
            for u in active_enrolled:
                prog = get_user_daily_progress(u["discord_id"], today_str, db_path)
                t_pts = prog.get("total_points", 0)
                if t_pts > 0:
                    live_pts_map[u["discord_id"]] = {
                        "discord_id": u["discord_id"],
                        "username": u["username"],
                        "points": t_pts,
                        "date": today_str,
                    }

        all_day_scores: List[Dict[str, Any]] = [dict(r) for r in summ_pts] + list(live_pts_map.values())
        max_score = 0
        max_users: List[Dict[str, Any]] = []
        if all_day_scores:
            max_score = max(r["points"] for r in all_day_scores)
            if max_score > 0:
                seen_uids = set()
                for r in all_day_scores:
                    if r["points"] == max_score and r["discord_id"] not in seen_uids:
                        seen_uids.add(r["discord_id"])
                        max_users.append({"discord_id": r["discord_id"], "username": r["username"]})

        # 3. Most Perfect Days
        cursor.execute(f"""
            SELECT u.discord_id, u.username, SUM(s.perfect_day) AS perfect_count
            FROM daily_summaries s
            JOIN users u ON s.user_id = u.id
            {date_clause_summ}
            GROUP BY s.user_id
            ORDER BY perfect_count DESC
            LIMIT 1;
        """, date_params_summ)
        perf_row = cursor.fetchone()
        most_perfect_record = None
        if perf_row and int(perf_row["perfect_count"]) > 0:
            most_perfect_record = {
                "discord_id": perf_row["discord_id"],
                "username": perf_row["username"],
                "count": int(perf_row["perfect_count"]),
            }

        # 4. Most Grinded Member
        grind_date_clause = "WHERE g.date >= ? AND g.date <= ?" if (start_date and end_date) else ""
        grind_params = [start_date, end_date] if (start_date and end_date) else []
        cursor.execute(f"""
            SELECT u.discord_id, u.username, COUNT(g.id) AS sessions, COALESCE(SUM(g.points_awarded), 0) AS total_pts
            FROM grind_logs g
            JOIN users u ON g.user_id = u.id
            {grind_date_clause}
            {'AND' if grind_date_clause else 'WHERE'} g.points_awarded > 0
            GROUP BY g.user_id
            ORDER BY sessions DESC, total_pts DESC
            LIMIT 1;
        """, grind_params)
        grind_row = cursor.fetchone()
        most_grinded_record = None
        if grind_row and int(grind_row["sessions"]) > 0:
            most_grinded_record = {
                "discord_id": grind_row["discord_id"],
                "username": grind_row["username"],
                "sessions": int(grind_row["sessions"]),
                "points": int(grind_row["total_pts"]),
            }

        # 5. Single Day Peaks (per exercise)
        active_tasks = get_active_tasks(db_path)
        single_day_peaks = []
        for t in active_tasks:
            t_params = list(date_params_logs) + [t["id"]]
            cursor.execute(f"""
                SELECT u.discord_id, u.username, SUM(l.amount) AS day_total, l.date
                FROM daily_logs l
                JOIN users u ON l.user_id = u.id
                {date_clause_logs} {'AND' if date_clause_logs else 'WHERE'} l.task_id = ?
                GROUP BY l.user_id, l.date
                ORDER BY day_total DESC
                LIMIT 1;
            """, t_params)
            p_row = cursor.fetchone()
            if p_row and float(p_row["day_total"]) > 0:
                single_day_peaks.append({
                    "task_name": t["name"],
                    "unit": t["unit"],
                    "amount": float(p_row["day_total"]),
                    "discord_id": p_row["discord_id"],
                    "username": p_row["username"],
                    "date": p_row["date"],
                })
            else:
                single_day_peaks.append({
                    "task_name": t["name"],
                    "unit": t["unit"],
                    "amount": 0.0,
                    "discord_id": None,
                    "username": None,
                    "date": None,
                })

        # 6. Server Totals
        cursor.execute(f"""
            SELECT COALESCE(SUM(points), 0) AS total_pts, COALESCE(SUM(perfect_day), 0) AS total_perfect
            FROM daily_summaries s
            {date_clause_summ};
        """, date_params_summ)
        tot_row = cursor.fetchone()
        server_total_pts = int(tot_row["total_pts"]) if tot_row else 0
        server_perfect_days = int(tot_row["total_perfect"]) if tot_row else 0

        if include_today:
            for l_item in live_pts_map.values():
                server_total_pts += l_item["points"]

        cursor.execute(f"""
            SELECT COUNT(DISTINCT user_id) AS cnt
            FROM (
                SELECT user_id FROM daily_logs l {date_clause_logs}
                UNION
                SELECT user_id FROM daily_summaries s {date_clause_summ}
            );
        """, date_params_logs + date_params_summ)
        active_contrib_row = cursor.fetchone()
        active_contributors = int(active_contrib_row["cnt"]) if active_contrib_row else 0

        cursor.execute(f"""
            SELECT COUNT(id) AS cnt, COALESCE(SUM(points_awarded), 0) AS pts
            FROM grind_logs g
            {grind_date_clause} {'AND' if grind_date_clause else 'WHERE'} g.points_awarded > 0;
        """, grind_params)
        g_tot_row = cursor.fetchone()
        total_grind_sessions = int(g_tot_row["cnt"]) if g_tot_row else 0
        total_grind_pts = int(g_tot_row["pts"]) if g_tot_row else 0

        server_task_totals = []
        for t in active_tasks:
            t_params = [t["id"]] + list(date_params_logs)
            cursor.execute(f"""
                SELECT COALESCE(SUM(l.amount), 0) AS total_volume
                FROM daily_logs l
                WHERE l.task_id = ? {'AND l.date >= ? AND l.date <= ?' if start_date and end_date else ''};
            """, t_params)
            vol_row = cursor.fetchone()
            total_vol = float(vol_row["total_volume"]) if vol_row else 0.0
            server_task_totals.append({
                "name": t["name"],
                "unit": t["unit"],
                "total_volume": total_vol,
            })

    return {
        "phase": phase,
        "phase_id": phase_id,
        "longest_streak": longest_streak_record,
        "daily_maxers": {
            "max_score": max_score,
            "users": max_users,
        },
        "most_perfect_days": most_perfect_record,
        "most_grinded": most_grinded_record,
        "single_day_peaks": single_day_peaks,
        "server_totals": {
            "total_points": server_total_pts,
            "active_contributors": active_contributors,
            "total_perfect_days": server_perfect_days,
            "deep_work_sessions": total_grind_sessions,
            "deep_work_points": total_grind_pts,
            "task_totals": server_task_totals,
        },
    }


def archive_phase_snapshot(phase_id: int, db_path: str = DB_PATH, backup_dir: str = "backups") -> str:
    """
    Creates a dedicated, isolated SQLite snapshot for the specified phase.
    Contains user table, tasks, daily_summaries, daily_logs, shield_logs, grind_logs,
    and a pre-calculated phase_standings table.
    """
    from phases import get_phase_by_id
    phase = get_phase_by_id(phase_id)
    if not phase:
        raise ValueError(f"Invalid phase_id: {phase_id}")

    os.makedirs(backup_dir, exist_ok=True)
    code_name = re.sub(r'[^a-z0-9_]', '', phase["name"].lower().replace(" ", "_"))
    snapshot_filename = f"phase_{phase['id']}_{code_name}_{phase['year']}.db"
    snapshot_path = os.path.join(backup_dir, snapshot_filename)

    start_date = phase["start_date"]
    end_date = phase["end_date"]

    with sqlite3.connect(snapshot_path) as s_conn:
        s_cursor = s_conn.cursor()
        s_cursor.execute("PRAGMA journal_mode=WAL;")

        s_cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                discord_id INTEGER UNIQUE NOT NULL,
                username TEXT NOT NULL,
                enrolled BOOLEAN DEFAULT 1,
                joined_at TIMESTAMP
            );
        """)
        s_cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                target REAL NOT NULL,
                unit TEXT NOT NULL,
                max_points INTEGER NOT NULL
            );
        """)
        s_cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date DATE NOT NULL,
                points INTEGER NOT NULL,
                completion_rate REAL NOT NULL,
                perfect_day BOOLEAN DEFAULT 0,
                is_shielded BOOLEAN DEFAULT 0
            );
        """)
        s_cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                task_id INTEGER NOT NULL,
                date DATE NOT NULL,
                amount REAL NOT NULL,
                logged_at TIMESTAMP
            );
        """)
        s_cursor.execute("""
            CREATE TABLE IF NOT EXISTS shield_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date DATE NOT NULL,
                reason TEXT
            );
        """)
        s_cursor.execute("""
            CREATE TABLE IF NOT EXISTS grind_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date DATE NOT NULL,
                raw_input TEXT NOT NULL,
                verdict TEXT NOT NULL,
                points_awarded INTEGER DEFAULT 0,
                key_learning TEXT,
                commentary TEXT
            );
        """)
        s_cursor.execute("""
            CREATE TABLE IF NOT EXISTS phase_standings (
                rank INTEGER PRIMARY KEY,
                discord_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                total_points INTEGER NOT NULL,
                perfect_days INTEGER NOT NULL,
                active_days INTEGER NOT NULL
            );
        """)

        with get_connection(db_path) as src_conn:
            src = src_conn.cursor()

            src.execute("SELECT id, discord_id, username, enrolled, joined_at FROM users;")
            s_cursor.executemany("INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, ?);", src.fetchall())

            src.execute("SELECT id, name, description, target, unit, max_points FROM tasks;")
            s_cursor.executemany("INSERT OR REPLACE INTO tasks VALUES (?, ?, ?, ?, ?, ?);", src.fetchall())

            src.execute("""
                SELECT id, user_id, date, points, completion_rate, perfect_day, is_shielded
                FROM daily_summaries
                WHERE date >= ? AND date <= ?;
            """, (start_date, end_date))
            s_cursor.executemany("INSERT OR REPLACE INTO daily_summaries VALUES (?, ?, ?, ?, ?, ?, ?);", src.fetchall())

            src.execute("""
                SELECT id, user_id, task_id, date, amount, logged_at
                FROM daily_logs
                WHERE date >= ? AND date <= ?;
            """, (start_date, end_date))
            s_cursor.executemany("INSERT OR REPLACE INTO daily_logs VALUES (?, ?, ?, ?, ?, ?);", src.fetchall())

            src.execute("""
                SELECT id, user_id, date, reason
                FROM shield_logs
                WHERE date >= ? AND date <= ?;
            """, (start_date, end_date))
            s_cursor.executemany("INSERT OR REPLACE INTO shield_logs VALUES (?, ?, ?, ?);", src.fetchall())

            src.execute("""
                SELECT id, user_id, date, raw_input, verdict, points_awarded, key_learning, commentary
                FROM grind_logs
                WHERE date >= ? AND date <= ?;
            """, (start_date, end_date))
            s_cursor.executemany("INSERT OR REPLACE INTO grind_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?);", src.fetchall())

        lb = get_phase_leaderboard(phase_id, db_path)
        for row in lb:
            s_cursor.execute("""
                INSERT OR REPLACE INTO phase_standings (rank, discord_id, username, total_points, perfect_days, active_days)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (row["rank"], row["discord_id"], row["username"], row["total_points"], row["perfect_days"], row["active_days"]))

        s_conn.commit()
    s_conn.close()

    return os.path.abspath(snapshot_path)


def get_user_longest_streak(discord_id: int, db_path: str = DB_PATH) -> int:
    """Computes the user's all-time longest streak from historical daily_summaries, shield_logs, and live progress."""
    user = get_user_by_discord_id(discord_id, db_path)
    if not user or not user["enrolled"]:
        return 0

    today = get_today_date()
    today_str = today.isoformat()

    completed_dates = set()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        # 1. Past dates meeting streak criteria
        cursor.execute(f"""
            SELECT date
            FROM daily_summaries
            WHERE user_id = ? AND (points >= {MIN_STREAK_POINTS} OR perfect_day = 1 OR is_shielded = 1);
        """, (user["id"],))
        for r in cursor.fetchall():
            try:
                completed_dates.add(date.fromisoformat(r["date"]))
            except Exception:
                pass

        # 2. Shielded dates
        cursor.execute("SELECT date FROM shield_logs WHERE user_id = ?;", (user["id"],))
        for r in cursor.fetchall():
            try:
                completed_dates.add(date.fromisoformat(r["date"]))
            except Exception:
                pass

    # 3. Check today's live completion
    today_prog = get_user_daily_progress(discord_id, today_str, db_path)
    shield_status = get_user_shield_status(discord_id, db_path)
    if today_prog["total_points"] >= MIN_STREAK_POINTS or today_prog["perfect_day"] or shield_status.get("is_today_shielded"):
        completed_dates.add(today)

    if not completed_dates:
        return 0

    sorted_dates = sorted(completed_dates)
    longest = 1
    curr = 1
    for i in range(1, len(sorted_dates)):
        if sorted_dates[i] == sorted_dates[i - 1] + timedelta(days=1):
            curr += 1
            if curr > longest:
                longest = curr
        elif sorted_dates[i] > sorted_dates[i - 1] + timedelta(days=1):
            curr = 1

    current_streak = calculate_streak(discord_id, db_path=db_path)
    return max(longest, current_streak)


def get_user_monthly_consistency(
    discord_id: int,
    year: Optional[int] = None,
    month: Optional[int] = None,
    db_path: str = DB_PATH,
    cached_user: Optional[Dict[str, Any]] = None,
    cached_stats: Optional[Dict[str, Any]] = None,
    cached_shield_status: Optional[Dict[str, Any]] = None,
    cached_highest_streak: Optional[int] = None,
    cached_current_streak: Optional[int] = None
) -> Dict[str, Any]:
    """
    Constructs the monthly consistency matrix and statistics for the streak dashboard.
    Returns:
    - month_name, year
    - rank_title (e.g. Dedicated, Initiate, etc.)
    - calendar_grid: Mon-Sun formatted codeblock text with W1..W5 rows, ▪️ for other months, ▫️ for future days
    - highlights: highest_streak, current_streak, active_days, elapsed_days, consistency_pct,
                 total_points, avg_points, perfect_days, shields_used, shields_left
    """
    today = get_today_date()
    target_year = year if year else today.year
    target_month = month if month else today.month

    user = cached_user if cached_user is not None else get_user_by_discord_id(discord_id, db_path)
    if not user:
        return {
            "user_id": 0,
            "discord_id": discord_id,
            "username": "Unknown",
            "year": target_year,
            "month": target_month,
            "month_name": calendar.month_name[target_month],
            "rank_title": "Initiate",
            "calendar_grid": "",
            "highlights": {
                "highest_streak": 0,
                "current_streak": 0,
                "active_days": 0,
                "elapsed_days": 0,
                "consistency_pct": 0,
                "total_points": 0,
                "avg_points": 0,
                "perfect_days": 0,
                "shields_used": 0,
                "shields_left": 0
            }
        }

    # Discipline rank level
    from levels import get_level_info
    stats = cached_stats if cached_stats is not None else get_user_stats(discord_id, db_path)
    lvl_info = get_level_info(stats.get("lifetime_points", 0))

    first_weekday, num_days = calendar.monthrange(target_year, target_month)
    month_name = calendar.month_name[target_month]

    start_date_str = f"{target_year:04d}-{target_month:02d}-01"
    end_date_str = f"{target_year:04d}-{target_month:02d}-{num_days:02d}"

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date, points, perfect_day, completion_rate, is_shielded
            FROM daily_summaries
            WHERE user_id = ? AND date >= ? AND date <= ?;
        """, (user["id"], start_date_str, end_date_str))
        summaries = {r["date"]: dict(r) for r in cursor.fetchall()}

        cursor.execute("""
            SELECT date, reason
            FROM shield_logs
            WHERE user_id = ? AND date >= ? AND date <= ?;
        """, (user["id"], start_date_str, end_date_str))
        shield_records = {r["date"]: dict(r) for r in cursor.fetchall()}

    # Live today if today is in this month
    today_in_month = (today.year == target_year and today.month == target_month)
    today_prog = {}
    today_shielded = False
    if today_in_month:
        today_prog = get_user_daily_progress(discord_id, today.isoformat(), db_path)
        sh_status = get_user_shield_status(discord_id, db_path)
        today_shielded = sh_status.get("is_today_shielded", False)

    # Build per-day details for days 1..num_days
    day_details = {}
    for d in range(1, num_days + 1):
        d_obj = date(target_year, target_month, d)
        d_str = d_obj.isoformat()

        if d_obj == today:
            summary_today = summaries.get(d_str, {})
            pts = max(today_prog.get("total_points", 0), summary_today.get("points", 0))
            is_perfect = today_prog.get("perfect_day", False) or bool(summary_today.get("perfect_day", 0))
            is_shielded = today_shielded or bool(summary_today.get("is_shielded", 0))
            if is_shielded:
                status = "🛡️"
                completed = True
            elif is_perfect:
                status = "⭐"
                completed = True
            elif pts >= MIN_STREAK_POINTS:
                status = "🟩"
                completed = True
            else:
                status = "⏳"
                completed = False

            day_details[d] = {
                "status": status,
                "points": pts,
                "completed": completed,
                "is_perfect": is_perfect,
                "is_shielded": today_shielded
            }
        elif d_str in summaries or d_str in shield_records:
            # Recorded day in summaries or shield records
            summ = summaries.get(d_str)
            sh = shield_records.get(d_str)
            pts = summ["points"] if summ else 0
            is_shielded = bool(sh or (summ and summ["is_shielded"]))
            is_perfect = bool(summ and summ["perfect_day"])

            if is_shielded:
                status = "🛡️"
                completed = True
            elif is_perfect:
                status = "⭐"
                completed = True
            elif pts >= MIN_STREAK_POINTS:
                status = "🟩"
                completed = True
            else:
                status = "🟥"
                completed = False

            day_details[d] = {
                "status": status,
                "points": pts,
                "completed": completed,
                "is_perfect": is_perfect,
                "is_shielded": is_shielded
            }
        elif d_obj > today:
            # Future day in this month without records
            day_details[d] = {
                "status": "▫️",
                "points": 0,
                "completed": False,
                "is_perfect": False,
                "is_shielded": False
            }
        else:
            # Past day without records (missed)
            day_details[d] = {
                "status": "🟥",
                "points": 0,
                "completed": False,
                "is_perfect": False,
                "is_shielded": False
            }

    # Group into Monday-Sunday calendar weeks
    weeks = []
    current_week = []

    # 1. Leading days from other month
    for _ in range(first_weekday):
        current_week.append(("other_month", "▪️", 0, False))

    # 2. Month days
    for d in range(1, num_days + 1):
        info = day_details[d]
        current_week.append(("month_day", info["status"], info["points"], info["completed"]))
        if len(current_week) == 7:
            weeks.append(current_week)
            current_week = []

    # 3. Trailing days from next month
    if current_week:
        trailing = 7 - len(current_week)
        trailing_status = "▫️" if (date(target_year, target_month, num_days) >= today) else "▪️"
        for _ in range(trailing):
            current_week.append(("other_month", trailing_status, 0, False))
        weeks.append(current_week)

    grid_lines = ["     Mo  Tu  We  Th  Fr  Sa  Su"]
    for idx, w in enumerate(weeks, 1):
        month_cells = [c for c in w if c[0] == "month_day"]
        month_days_count = len(month_cells)
        completed_count = sum(1 for c in month_cells if c[3])
        week_pts = sum(c[2] for c in month_cells)
        emojis_str = "  ".join(c[1] for c in w)
        grid_lines.append(f"W{idx}   {emojis_str}  — {completed_count}/{month_days_count} days ({week_pts:,} pts)")

    calendar_grid = "\n".join(grid_lines)

    # Highlights
    active_days = sum(1 for d in day_details.values() if d["completed"])
    if today_in_month:
        elapsed_days = min(today.day, num_days)
    elif date(target_year, target_month, 1) < today:
        elapsed_days = num_days
    else:
        recorded_days = [d for d, v in day_details.items() if v["points"] > 0 or v["completed"]]
        elapsed_days = max(recorded_days) if recorded_days else 0

    consistency_pct = round((active_days / elapsed_days) * 100) if elapsed_days > 0 else 0
    total_month_points = sum(d["points"] for d in day_details.values())
    avg_points = round(total_month_points / elapsed_days) if elapsed_days > 0 else 0
    perfect_days = sum(1 for d in day_details.values() if d["is_perfect"])
    shields_used = sum(1 for d in day_details.values() if d["is_shielded"])

    shield_status = cached_shield_status if cached_shield_status is not None else get_user_shield_status(discord_id, db_path)
    shields_left = shield_status.get("frost_shields", 0)

    highest_streak = cached_highest_streak if cached_highest_streak is not None else get_user_longest_streak(discord_id, db_path)
    current_streak = cached_current_streak if cached_current_streak is not None else calculate_streak(discord_id, db_path=db_path)

    return {
        "user_id": user["id"],
        "discord_id": user["discord_id"],
        "username": user["username"],
        "year": target_year,
        "month": target_month,
        "month_name": month_name,
        "rank_title": lvl_info["title"],
        "calendar_grid": calendar_grid,
        "highlights": {
            "highest_streak": highest_streak,
            "current_streak": current_streak,
            "active_days": active_days,
            "elapsed_days": elapsed_days,
            "consistency_pct": consistency_pct,
            "total_points": total_month_points,
            "avg_points": avg_points,
            "perfect_days": perfect_days,
            "shields_used": shields_used,
            "shields_left": shields_left
        }
    }


def get_user_full_campaign_calendar(discord_id: int, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Constructs the 3-phase full Winter Arc campaign calendar (Oct, Nov, Dec - 92 days) and cumulative highlights.
    """
    today = get_today_date()
    from phases import BASE_YEAR
    base_year = BASE_YEAR

    months_phases = [
        {"phase": 1, "name": "FIRST FROST", "month": 10, "emoji": "❄️", "total_days": 31},
        {"phase": 2, "name": "THE HUNT", "month": 11, "emoji": "🐺", "total_days": 30},
        {"phase": 3, "name": "THE ENDGAME", "month": 12, "emoji": "⚔️", "total_days": 31},
    ]

    user = get_user_by_discord_id(discord_id, db_path)
    from levels import get_level_info
    stats = get_user_stats(discord_id, db_path)
    lvl_info = get_level_info(stats.get("lifetime_points", 0))

    shield_status = get_user_shield_status(discord_id, db_path)
    shields_left = shield_status.get("frost_shields", 0)

    highest_streak = get_user_longest_streak(discord_id, db_path)
    current_streak = calculate_streak(discord_id, db_path=db_path)

    phase_blocks = []
    total_campaign_points = 0
    total_perfect_days = 0
    total_shields_used = 0
    total_active_days = 0
    total_elapsed_days = 0

    for p in months_phases:
        m_data = get_user_monthly_consistency(
            discord_id,
            year=base_year,
            month=p["month"],
            db_path=db_path,
            cached_user=user,
            cached_stats=stats,
            cached_shield_status=shield_status,
            cached_highest_streak=highest_streak,
            cached_current_streak=current_streak
        )
        h = m_data.get("highlights", {})
        total_campaign_points += h.get("total_points", 0)
        total_perfect_days += h.get("perfect_days", 0)
        total_shields_used += h.get("shields_used", 0)
        total_active_days += h.get("active_days", 0)
        total_elapsed_days += h.get("elapsed_days", 0)

        pts = h.get("total_points", 0)
        act = h.get("active_days", 0)
        tot = p["total_days"]
        month_name = m_data.get("month_name", "Month").upper()

        if date(base_year, p["month"], 1) > today and pts == 0:
            status_tag = f"Upcoming ({tot} days)"
        elif today.year == base_year and today.month == p["month"]:
            status_tag = f"In Progress • {act}/{tot} days ({pts:,} pts)"
        else:
            status_tag = f"{act}/{tot} days ({pts:,} pts)"

        phase_header = f"{p['emoji']} PHASE {p['phase']}: {month_name} ({p['name']}) • {status_tag}"
        grid = m_data.get("calendar_grid", "")
        phase_blocks.append(f"{phase_header}\n{grid}")

    calendar_text = "\n\n".join(phase_blocks)

    total_elapsed_days = min(92, max(0, total_elapsed_days))
    consistency_pct = round((total_active_days / total_elapsed_days) * 100) if total_elapsed_days > 0 else 0
    avg_points = round(total_campaign_points / total_elapsed_days) if total_elapsed_days > 0 else 0

    return {
        "user_id": user["id"] if user else 0,
        "discord_id": discord_id,
        "username": user["username"] if user else "Unknown",
        "rank_title": lvl_info["title"],
        "calendar_text": calendar_text,
        "highlights": {
            "overall_consistency_pct": consistency_pct,
            "active_days": total_active_days,
            "elapsed_days": total_elapsed_days,
            "total_days": 92,
            "longest_streak": highest_streak,
            "current_streak": current_streak,
            "total_points": total_campaign_points,
            "avg_points": avg_points,
            "perfect_days": total_perfect_days,
            "shields_used": total_shields_used,
            "shields_left": shields_left
        }
    }





