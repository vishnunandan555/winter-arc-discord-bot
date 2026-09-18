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
from typing import List, Dict, Any, Optional

DB_PATH = os.getenv("WINTER_ARC_DB", "winter_arc.db")

DEFAULT_TASKS = [
    {"name": "Push-ups", "description": "Works chest, shoulders, and triceps (1 pt / rep)", "target": 100.0, "unit": "reps", "max_points": 100},
    {"name": "Pull-ups", "description": "Works lats, upper back, and biceps (1 pt / rep)", "target": 100.0, "unit": "reps", "max_points": 100},
    {"name": "Squats", "description": "Strengthens quads, glutes, and legs (1 pt / rep)", "target": 100.0, "unit": "reps", "max_points": 100},
    {"name": "Sit-ups", "description": "Targets core and hip flexors (1 pt / rep)", "target": 100.0, "unit": "reps", "max_points": 100},
    {"name": "Running", "description": "Cardiovascular endurance (1 pt / 100m = 10 pts / km)", "target": 10.0, "unit": "km", "max_points": 100},
]


@contextmanager
def get_connection(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, date),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)

        # Indices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_user_date ON daily_logs(user_id, date);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_summaries_user_date ON daily_summaries(user_id, date);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_summaries_date ON daily_summaries(date);")

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

    return {
        "user_id": user["id"],
        "username": user["username"],
        "task_name": task["name"],
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
                "target": target,
                "unit": t["unit"],
                "current_amount": total_amount,
                "max_points": max_pts,
                "points_earned": task_pts,
                "completion_ratio": completion_ratio,
                "completed": total_amount >= target,
            })

    overall_completion = (total_points / total_max_points) if total_max_points > 0 else 0.0

    return {
        "date": target_date,
        "user_id": user["id"],
        "username": user["username"],
        "tasks": task_summaries,
        "total_points": total_points,
        "max_possible_points": total_max_points,
        "overall_completion_rate": round(overall_completion, 4),
        "perfect_day": all_targets_met,
    }


def calculate_streak(discord_id: int, as_of_date: Optional[str] = None, db_path: str = DB_PATH) -> int:
    user = get_user_by_discord_id(discord_id, db_path)
    if not user or not user["enrolled"]:
        return 0

    ref_date = date.fromisoformat(as_of_date) if as_of_date else date.today()
    
    today_progress = get_user_daily_progress(discord_id, ref_date.isoformat(), db_path)
    streak = 0
    if today_progress["perfect_day"]:
        streak += 1
        current_check = ref_date - timedelta(days=1)
    else:
        current_check = ref_date - timedelta(days=1)

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        for _ in range(365):
            date_str = current_check.isoformat()
            cursor.execute("""
                SELECT perfect_day, completion_rate
                FROM daily_summaries
                WHERE user_id = ? AND date = ?;
            """, (user["id"], date_str))
            summary_row = cursor.fetchone()

            if summary_row:
                if summary_row["perfect_day"] or summary_row["completion_rate"] >= 0.999:
                    streak += 1
                    current_check -= timedelta(days=1)
                    continue
                else:
                    break
            else:
                day_prog = get_user_daily_progress(discord_id, date_str, db_path)
                if day_prog["perfect_day"] and day_prog["total_points"] > 0:
                    streak += 1
                    current_check -= timedelta(days=1)
                else:
                    break

    return streak


# ==========================================
# Midnight Finalization & Leaderboards
# ==========================================

def finalize_daily_summaries(target_date_str: Optional[str] = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    if not target_date_str:
        target_date_str = (date.today() - timedelta(days=1)).isoformat()

    leaderboard = []

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, discord_id, username FROM users WHERE enrolled = 1")
        users = cursor.fetchall()

        for u in users:
            progress = get_user_daily_progress(u["discord_id"], target_date_str, db_path)
            points = progress["total_points"]
            completion = progress["overall_completion_rate"]
            perfect = 1 if progress["perfect_day"] else 0

            cursor.execute("""
                INSERT INTO daily_summaries (user_id, date, points, completion_rate, perfect_day)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, date) DO UPDATE SET
                    points = excluded.points,
                    completion_rate = excluded.completion_rate,
                    perfect_day = excluded.perfect_day;
            """, (u["id"], target_date_str, points, completion, perfect))

            leaderboard.append({
                "discord_id": u["discord_id"],
                "username": u["username"],
                "points": points,
                "completion_rate": completion,
                "perfect_day": bool(perfect),
            })

        conn.commit()

    leaderboard.sort(key=lambda x: (x["points"], x["completion_rate"]), reverse=True)
    return leaderboard


def get_daily_leaderboard(target_date_str: Optional[str] = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    if not target_date_str:
        target_date_str = date.today().isoformat()

    results = []
    users = get_enrolled_users(db_path)

    for u in users:
        prog = get_user_daily_progress(u["discord_id"], target_date_str, db_path)
        results.append({
            "discord_id": u["discord_id"],
            "username": u["username"],
            "points": prog["total_points"],
            "max_points": prog["max_possible_points"],
            "completion_rate": prog["overall_completion_rate"],
            "perfect_day": prog["perfect_day"],
        })

    results.sort(key=lambda x: (x["points"], x["completion_rate"]), reverse=True)
    return results


def get_monthly_leaderboard(year: int, month: int, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    month_prefix = f"{year:04d}-{month:02d}%"
    today_str = date.today().isoformat()
    users = get_enrolled_users(db_path)

    monthly_stats = []
    for u in users:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COALESCE(SUM(points), 0) AS total_points,
                    COALESCE(SUM(perfect_day), 0) AS perfect_days,
                    COUNT(DISTINCT date) AS recorded_days
                FROM daily_summaries
                WHERE user_id = ? AND date LIKE ? AND date != ?;
            """, (u["id"], month_prefix, today_str))
            row = cursor.fetchone()
            past_points = int(row["total_points"]) if row else 0
            perfect_days = int(row["perfect_days"]) if row else 0
            recorded_days = int(row["recorded_days"]) if row else 0

        if today_str.startswith(f"{year:04d}-{month:02d}"):
            today_prog = get_user_daily_progress(u["discord_id"], today_str, db_path)
            total_points = past_points + today_prog["total_points"]
            if today_prog["perfect_day"]:
                perfect_days += 1
            if today_prog["total_points"] > 0:
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


def get_user_stats(discord_id: int, db_path: str = DB_PATH) -> Dict[str, Any]:
    user = get_user_by_discord_id(discord_id, db_path)
    if not user:
        return {}

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COALESCE(SUM(points), 0) AS lifetime_points,
                COALESCE(SUM(perfect_day), 0) AS perfect_days,
                COUNT(DISTINCT date) AS active_days
            FROM daily_summaries
            WHERE user_id = ?;
        """, (user["id"],))
        summary = cursor.fetchone()

        cursor.execute("""
            SELECT t.name, t.unit, COALESCE(SUM(l.amount), 0) as total_volume
            FROM tasks t
            LEFT JOIN daily_logs l ON t.id = l.task_id AND l.user_id = ?
            GROUP BY t.id
            ORDER BY t.id ASC;
        """, (user["id"],))
        task_totals = [dict(r) for r in cursor.fetchall()]

    streak = calculate_streak(discord_id, db_path=db_path)

    return {
        "user_id": user["id"],
        "discord_id": user["discord_id"],
        "username": user["username"],
        "enrolled": bool(user["enrolled"]),
        "joined_at": user["joined_at"],
        "current_streak": streak,
        "lifetime_points": int(summary["lifetime_points"]) if summary else 0,
        "perfect_days": int(summary["perfect_days"]) if summary else 0,
        "active_days": int(summary["active_days"]) if summary else 0,
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
