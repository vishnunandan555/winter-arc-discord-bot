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
from contextlib import contextmanager
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple

from config import DB_PATH, MIN_STREAK_POINTS

DEFAULT_TASKS = [
    {"name": "Push-ups", "description": "Works chest, shoulders, and triceps (1 pt / rep)", "target": 100.0, "unit": "reps", "max_points": 100},
    {"name": "Pull-ups", "description": "Works lats, upper back, and biceps (1 pt / rep)", "target": 100.0, "unit": "reps", "max_points": 100},
    {"name": "Squats", "description": "Strengthens quads, glutes, and legs (1 pt / rep)", "target": 100.0, "unit": "reps", "max_points": 100},
    {"name": "Sit-ups", "description": "Targets core and hip flexors (1 pt / rep)", "target": 100.0, "unit": "reps", "max_points": 100},
    {"name": "Running", "description": "Cardiovascular endurance (1 pt / 100m = 10 pts / km)", "target": 10.0, "unit": "km", "max_points": 100},
]


@contextmanager
def get_connection(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA cache_size = -2000;")         # Cap memory cache to ~2 MB
    conn.execute("PRAGMA wal_autocheckpoint = 500;")   # Frequent WAL flush to keep disk usage minimal
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: str = DB_PATH):
    """Initializes schema, settings, and seeds default tasks."""
    with get_connection(db_path) as conn:
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

def enroll_user(discord_id: int, username: str, db_path: str = DB_PATH) -> Dict[str, Any]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,))
        row = cursor.fetchone()
        if row:
            cursor.execute("""
                UPDATE users
                SET username = ?, enrolled = 1
                WHERE discord_id = ?;
            """, (username, discord_id))
        else:
            cursor.execute("""
                INSERT INTO users (discord_id, username, enrolled)
                VALUES (?, ?, 1);
            """, (discord_id, username))
        conn.commit()

        cursor.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,))
        return dict(cursor.fetchone())


def unenroll_user(discord_id: int, db_path: str = DB_PATH) -> bool:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET enrolled = 0 WHERE discord_id = ?", (discord_id,))
        conn.commit()
        return cursor.rowcount > 0


def is_user_enrolled(discord_id: int, db_path: str = DB_PATH) -> bool:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT enrolled FROM users WHERE discord_id = ?", (discord_id,))
        row = cursor.fetchone()
        if not row:
            return False
        return bool(row["enrolled"])


def get_user_by_discord_id(discord_id: int, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_enrolled_users(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
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
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE name = ? COLLATE NOCASE", (name.strip(),))
        row = cursor.fetchone()
        return dict(row) if row else None


def add_task(name: str, target: float, unit: str, max_points: int, description: str = "", db_path: str = DB_PATH) -> Dict[str, Any]:
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
        log_date = date.today().isoformat()

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

    pts_before = math.floor(min(total_before / target, 1.0) * max_pts)
    pts_after = math.floor(min(total_after / target, 1.0) * max_pts)
    pts_delta = pts_after - pts_before

    daily_progress = get_user_daily_progress(discord_id, log_date, db_path)
    shield_awarded = False
    if daily_progress["perfect_day"]:
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
        "task_points_total": pts_after,
        "task_max_points": max_pts,
        "is_target_reached": total_after >= target,
        "daily_points_total": daily_progress["total_points"],
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
        log_date = date.today().isoformat()

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
    if daily_progress["perfect_day"]:
        streak = calculate_streak(discord_id, log_date, db_path)
        shield_awarded = check_and_award_shield(discord_id, streak, db_path)

    return {
        "user_id": user["id"],
        "username": user["username"],
        "task_name": task["name"],
        "target": target,
        "unit": task["unit"],
        "amount_set": target_amount,
        "previous_total": total_before,
        "new_total": total_after,
        "points_earned_delta": pts_delta,
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
        target_date = date.today().isoformat()

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

    ref_date = date.fromisoformat(as_of_date) if as_of_date else date.today()
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
        target_date_str = (date.today() - timedelta(days=1)).isoformat()

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
        if not streak_qualifies and not shielded and shields_available > 0:
            past_streak = calculate_streak(u["discord_id"], day_before, db_path)
            if past_streak > 0:
                auto_shield_applied = True
                shielded = 1
                shields_available -= 1

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
            "current_streak": current_streak,
        })

    leaderboard.sort(key=lambda x: (x["points"], x["completion_rate"]), reverse=True)
    return leaderboard


def get_daily_leaderboard(target_date_str: Optional[str] = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """
    Computes daily standings for all enrolled users using single batched SQL queries.
    """
    if not target_date_str:
        target_date_str = date.today().isoformat()

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
    today = date.today()
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
    today_str = date.today().isoformat()
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
    today_str = date.today().isoformat()
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

    today_str = date.today().isoformat()
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

    today_str = date.today().isoformat()

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
    today = date.today()
    for i in range(days):
        d_str = (today - timedelta(days=i)).isoformat()
        prog = get_user_daily_progress(discord_id, d_str, db_path)
        history.append({
            "date": d_str,
            "points": prog["total_points"],
            "max_points": prog["max_possible_points"],
            "completion_rate": prog["overall_completion_rate"],
            "perfect_day": prog["perfect_day"],
        })

    return history


# ==========================================
# Frost Shield & Streak Protection DAO
# ==========================================

def get_user_shield_status(discord_id: int, db_path: str = DB_PATH) -> Dict[str, Any]:
    """Returns current shield capacity, availability, and progress to next shield."""
    user = get_user_by_discord_id(discord_id, db_path)
    if not user:
        return {
            "frost_shields": 0,
            "inventory": 0,
            "max_shields": 2,
            "is_today_shielded": False,
            "is_shielded_today": False,
            "current_streak": 0,
            "days_until_next_shield": 7,
            "recent_uses": [],
        }

    today_str = date.today().isoformat()
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

    return {
        "frost_shields": user.get("frost_shields", 0) or 0,
        "inventory": user.get("frost_shields", 0) or 0,
        "max_shields": 2,
        "is_today_shielded": is_today_shielded,
        "is_shielded_today": is_today_shielded,
        "current_streak": streak,
        "days_until_next_shield": days_until_next,
        "recent_uses": recent_uses,
    }


def activate_frost_shield(discord_id: int, target_date: Optional[str] = None, reason: str = "Manual rest day", db_path: str = DB_PATH) -> Dict[str, Any]:
    """Consumes 1 Frost Shield for the user and protects their streak on target_date."""
    user = get_user_by_discord_id(discord_id, db_path)
    if not user or not user["enrolled"]:
        raise ValueError("You must be enrolled in Winter Arc to use a Frost Shield.")

    shields = user.get("frost_shields", 0) or 0
    if shields <= 0:
        raise ValueError("You have 0 Frost Shields available. Maintain a 7-day streak to earn a shield.")

    target_date_str = target_date or date.today().isoformat()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM shield_logs WHERE user_id = ? AND date = ?;", (user["id"], target_date_str))
        if cursor.fetchone():
            raise ValueError(f"A Frost Shield is already active for {target_date_str}.")

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


def check_and_award_shield(discord_id: int, streak: int, db_path: str = DB_PATH) -> bool:
    """Awards +1 Frost Shield (up to 2) if streak reaches a new 7-day milestone."""
    if streak < 7:
        return False

    user = get_user_by_discord_id(discord_id, db_path)
    if not user:
        return False

    milestone = (streak // 7) * 7
    last_milestone = user.get("last_shield_milestone", 0) or 0
    current_shields = user.get("frost_shields", 0) or 0

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
            "dm_evening": True,
        }
    return {
        "dm_reminders": bool(user.get("dm_reminders", 0)),
        "dm_morning": bool(user.get("dm_morning", 1) if user.get("dm_morning") is not None else 1),
        "dm_evening": bool(user.get("dm_evening", 1) if user.get("dm_evening") is not None else 1),
    }


def update_user_dm_settings(
    discord_id: int,
    dm_reminders: Optional[bool] = None,
    dm_morning: Optional[bool] = None,
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
    if dm_evening is not None:
        updates.append("dm_evening = ?")
        params.append(1 if dm_evening else 0)

    if updates:
        allowed_clauses = {"dm_reminders = ?", "dm_morning = ?", "dm_evening = ?"}
        if not all(clause in allowed_clauses for clause in updates):
            raise ValueError("Unauthorized column modification attempt.")
        params.append(user["id"])
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?;", params)
            conn.commit()

    return get_user_dm_settings(discord_id, db_path)


def get_opted_in_dm_users(category: str = "all", db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Fetches users who have enabled DMs, optionally filtered by category (morning/evening)."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM users WHERE enrolled = 1 AND dm_reminders = 1"
        if category == "morning":
            query += " AND dm_morning = 1"
        elif category == "evening":
            query += " AND dm_evening = 1"
        query += " ORDER BY id ASC;"
        cursor.execute(query)
        return [dict(r) for r in cursor.fetchall()]


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

    target_date = date_str or date.today().isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM grind_logs WHERE user_id = ? AND date = ?;
        """, (user["id"], target_date))
        row = cursor.fetchone()
        return dict(row) if row else None


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


