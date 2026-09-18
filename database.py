"""
database.py - SQLite Data Access Object (DAO) for Winter Arc Bot

Handles users, tasks, daily activity logs, daily summaries, scoring calculations,
and streaks with no Discord-specific dependencies.
"""

import os
import sqlite3
import math
from contextlib import contextmanager
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple

DB_PATH = os.getenv("WINTER_ARC_DB", "winter_arc.db")

DEFAULT_TASKS = [
    {"name": "Push-ups", "description": "Complete push-ups", "target": 100.0, "unit": "reps", "max_points": 100},
    {"name": "Pull-ups", "description": "Complete pull-ups", "target": 20.0, "unit": "reps", "max_points": 100},
    {"name": "Squats", "description": "Complete squats", "target": 100.0, "unit": "reps", "max_points": 100},
    {"name": "Running", "description": "Running or cardio distance", "target": 5.0, "unit": "km", "max_points": 100},
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
    """Initializes schema and seeds default tasks if not already present."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # 1. Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id INTEGER UNIQUE NOT NULL,
                username TEXT NOT NULL,
                timezone TEXT DEFAULT 'Asia/Kolkata',
                morning_reminder BOOLEAN DEFAULT 1,
                afternoon_reminder BOOLEAN DEFAULT 1,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. Tasks table
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

        # 3. Daily logs table (granular activity)
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

        # 4. Daily summaries table (finalized at midnight)
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

        # Indices for efficient lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_user_date ON daily_logs(user_id, date);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_summaries_user_date ON daily_summaries(user_id, date);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_summaries_date ON daily_summaries(date);")

        # Seed default tasks
        for task in DEFAULT_TASKS:
            cursor.execute("""
                INSERT OR IGNORE INTO tasks (name, description, target, unit, max_points, active)
                VALUES (:name, :description, :target, :unit, :max_points, 1);
            """, task)

        conn.commit()


# ==========================================
# User Operations
# ==========================================

def get_or_create_user(discord_id: int, username: str, db_path: str = DB_PATH) -> Dict[str, Any]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,))
        row = cursor.fetchone()
        if row:
            # Update username if changed
            if row["username"] != username:
                cursor.execute("UPDATE users SET username = ? WHERE discord_id = ?", (username, discord_id))
                conn.commit()
            return dict(row)

        cursor.execute("""
            INSERT INTO users (discord_id, username, timezone, morning_reminder, afternoon_reminder)
            VALUES (?, ?, 'Asia/Kolkata', 1, 1);
        """, (discord_id, username))
        conn.commit()

        cursor.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,))
        return dict(cursor.fetchone())


def get_user_by_discord_id(discord_id: int, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_reminder_preferences(discord_id: int, morning: Optional[bool] = None, afternoon: Optional[bool] = None, db_path: str = DB_PATH) -> Dict[str, Any]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"User with discord_id {discord_id} not found.")

        current_morning = row["morning_reminder"]
        current_afternoon = row["afternoon_reminder"]

        new_morning = morning if morning is not None else current_morning
        new_afternoon = afternoon if afternoon is not None else current_afternoon

        cursor.execute("""
            UPDATE users
            SET morning_reminder = ?, afternoon_reminder = ?
            WHERE discord_id = ?;
        """, (1 if new_morning else 0, 1 if new_afternoon else 0, discord_id))
        conn.commit()

        cursor.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,))
        return dict(cursor.fetchone())


def get_users_for_reminder(reminder_type: str, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    col = "morning_reminder" if reminder_type == "morning" else "afternoon_reminder"
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM users WHERE {col} = 1")
        return [dict(r) for r in cursor.fetchall()]


# ==========================================
# Task Operations
# ==========================================

def get_active_tasks(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE active = 1 ORDER BY id ASC")
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


def edit_task(name: str, target: Optional[float] = None, unit: Optional[str] = None, max_points: Optional[int] = None, description: Optional[str] = None, db_path: str = DB_PATH) -> Dict[str, Any]:
    task = get_task_by_name(name, db_path)
    if not task:
        raise ValueError(f"Task '{name}' does not exist.")

    new_target = target if target is not None else task["target"]
    new_unit = unit.strip() if unit is not None else task["unit"]
    new_max = max_points if max_points is not None else task["max_points"]
    new_desc = description.strip() if description is not None else task["description"]

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tasks
            SET target = ?, unit = ?, max_points = ?, description = ?
            WHERE id = ?;
        """, (new_target, new_unit, new_max, new_desc, task["id"]))
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
    """
    Logs an amount for a user and task on a given date (default: today).
    Points formula:
        completion = min(total_amount / target, 1.0)
        points = floor(completion * max_points)
    """
    if amount <= 0:
        raise ValueError("Amount must be greater than 0.")
    if amount > 5000:
        raise ValueError("Amount exceeds realistic single entry limit (5,000).")

    user = get_or_create_user(discord_id, username, db_path)
    task = get_task_by_name(task_name, db_path)
    if not task:
        raise ValueError(f"Task '{task_name}' not found.")
    if not task["active"]:
        raise ValueError(f"Task '{task_name}' is currently inactive.")

    if not log_date:
        log_date = date.today().isoformat()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # 1. Get existing sum before this log
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total_before
            FROM daily_logs
            WHERE user_id = ? AND task_id = ? AND date = ?;
        """, (user["id"], task["id"], log_date))
        total_before = float(cursor.fetchone()["total_before"])

        # 2. Insert new log
        cursor.execute("""
            INSERT INTO daily_logs (user_id, task_id, date, amount)
            VALUES (?, ?, ?, ?);
        """, (user["id"], task["id"], log_date, amount))
        conn.commit()

    total_after = total_before + amount
    target = float(task["target"])
    max_pts = int(task["max_points"])

    # Calculate points delta
    pts_before = math.floor(min(total_before / target, 1.0) * max_pts)
    pts_after = math.floor(min(total_after / target, 1.0) * max_pts)
    pts_delta = pts_after - pts_before

    # Get overall daily points after this update
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
    """
    Retrieves progress across all active tasks for a specific date (defaults to today).
    Calculates per-task completion, points, and total day completion.
    """
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


# ==========================================
# Streak Calculation
# ==========================================

def calculate_streak(discord_id: int, as_of_date: Optional[str] = None, db_path: str = DB_PATH) -> int:
    """
    Dynamically computes consecutive completed days.
    A day counts towards streak if overall_completion_rate >= 1.0 (or perfect_day = True).
    Scans backwards starting from today (if finished) or yesterday.
    """
    user = get_user_by_discord_id(discord_id, db_path)
    if not user:
        return 0

    ref_date = date.fromisoformat(as_of_date) if as_of_date else date.today()
    
    # Check if today is completed
    today_progress = get_user_daily_progress(discord_id, ref_date.isoformat(), db_path)
    
    streak = 0
    if today_progress["perfect_day"]:
        streak += 1
        current_check = ref_date - timedelta(days=1)
    else:
        # Today not completed yet; scan begins from yesterday
        current_check = ref_date - timedelta(days=1)

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Scan backwards up to 365 days
        for _ in range(365):
            date_str = current_check.isoformat()
            
            # Check daily_summaries first
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
                # Check raw daily logs fallback
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
    """
    Calculates and persists final daily summary records for all users for a given date.
    Typically called at 00:00 IST for (today - 1 day).
    Returns the leaderboard list for that day sorted by points DESC.
    """
    if not target_date_str:
        # Defaults to yesterday
        target_date_str = (date.today() - timedelta(days=1)).isoformat()

    leaderboard = []

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, discord_id, username FROM users")
        users = cursor.fetchall()

        for u in users:
            progress = get_user_daily_progress(u["discord_id"], target_date_str, db_path)
            
            # Only summarize if user has points or exists
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
    """Fetches or calculates ranking for a specific day."""
    if not target_date_str:
        target_date_str = date.today().isoformat()

    results = []
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT discord_id, username FROM users")
        users = cursor.fetchall()

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
    """
    Aggregates points across a calendar month (YYYY-MM).
    Pulls from daily_summaries and daily_logs to ensure full historical accuracy.
    """
    month_prefix = f"{year:04d}-{month:02d}%"
    today_str = date.today().isoformat()

    # Ensure today's active progress is summarized temporarily in query if in same month
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, discord_id, username FROM users")
        users = cursor.fetchall()

    monthly_stats = []
    for u in users:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            # 1. Sum from daily_summaries for past finalized days in this month
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

        # 2. Add today's live progress if today is in this month
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
    """Lifetime statistics and task breakdown for a user."""
    user = get_user_by_discord_id(discord_id, db_path)
    if not user:
        return {}

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Perfect days and all-time points
        cursor.execute("""
            SELECT
                COALESCE(SUM(points), 0) AS lifetime_points,
                COALESCE(SUM(perfect_day), 0) AS perfect_days,
                COUNT(DISTINCT date) AS active_days
            FROM daily_summaries
            WHERE user_id = ?;
        """, (user["id"],))
        summary = cursor.fetchone()

        # Task lifetime volume
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
        "joined_at": user["joined_at"],
        "current_streak": streak,
        "lifetime_points": int(summary["lifetime_points"]) if summary else 0,
        "perfect_days": int(summary["perfect_days"]) if summary else 0,
        "active_days": int(summary["active_days"]) if summary else 0,
        "task_totals": task_totals,
    }


def get_user_history(discord_id: int, days: int = 7, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Returns past N days breakdown for graphs or history embed."""
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
