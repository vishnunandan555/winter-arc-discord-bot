"""
export_web_stats.py - Exports Winter Arc Database to Web JSON

Generates docs/stats.json used by the GitHub Pages / Vercel web dashboard.
Can be executed manually or automatically via scheduler.py.
"""

import os
import json
import logging
from datetime import datetime, date

import database as db
from config import BOT_TZ, DB_PATH
from levels import get_all_ranks, get_level_info

logger = logging.getLogger("winter_arc.export_web")


def export_stats_to_json(output_path: str = "docs/stats.json", db_path: str = DB_PATH) -> dict:
    """Exports active standings, disciplines, server stats, and levels to JSON."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    db.init_db(db_path)

    now = datetime.now(BOT_TZ)
    today_str = now.strftime("%Y-%m-%d")
    date_display = now.strftime("%A, %B %d, %Y")

    # 1. Enrolled Warriors
    enrolled_users = db.get_enrolled_users(db_path)
    total_warriors = len(enrolled_users)

    # 2. Daily Standings
    daily_raw = db.get_daily_leaderboard(today_str, db_path)
    daily_standings = []
    for idx, row in enumerate(daily_raw):
        daily_standings.append({
            "rank": idx + 1,
            "username": row["username"],
            "points": row["points"],
            "max_points": row.get("max_points", 500),
            "completion_rate": round(row["completion_rate"] * 100, 1),
            "perfect_day": bool(row["perfect_day"]),
        })

    # 3. Overall Standings with Level Info
    overall_raw = db.get_overall_leaderboard(db_path)
    overall_standings = []
    total_collective_points = 0
    for idx, row in enumerate(overall_raw):
        pts = row["total_points"]
        total_collective_points += pts
        lvl_info = get_level_info(pts)

        overall_standings.append({
            "rank": idx + 1,
            "discord_id": str(row["discord_id"]),
            "username": row["username"],
            "total_points": pts,
            "streak": row.get("streak", 0),
            "perfect_days": row.get("perfect_days", 0),
            "recorded_days": row.get("recorded_days", 0),
            "level": lvl_info["level"],
            "title": lvl_info["title"],
            "badge": lvl_info["badge"],
            "color": hex(lvl_info["color"]),
            "tier_pct": lvl_info["tier_pct"],
            "pts_to_next": lvl_info["pts_to_next"],
            "arc_pct": lvl_info["arc_pct"],
        })

    # 4. Disciplines
    active_tasks = db.get_active_tasks(db_path)
    disciplines = []
    for t in active_tasks:
        disciplines.append({
            "name": t["name"],
            "description": t["description"],
            "target": int(t["target"]) if t["target"].is_integer() else t["target"],
            "unit": t["unit"],
            "max_points": t["max_points"],
        })

    # 5. 12-Level Hierarchy
    ranks = get_all_ranks()
    ranks_data = []
    for r in ranks:
        ranks_data.append({
            "level": r["level"],
            "title": r["title"],
            "badge": r["badge"],
            "min_pts": r["min_pts"],
            "max_pts": r["max_pts"],
            "color": hex(r["color"]),
        })

    # 6. Academic / Mental Grind Highlights
    academic_highlights = []
    try:
        with db.get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.username, g.date, g.key_learning, g.points_awarded, g.commentary
                FROM grind_logs g
                JOIN users u ON g.user_id = u.id
                WHERE g.verdict = 'ACCEPTED'
                ORDER BY g.date DESC, g.points_awarded DESC
                LIMIT 10;
            """)
            for r in cursor.fetchall():
                academic_highlights.append({
                    "username": r["username"],
                    "date": r["date"],
                    "key_learning": r["key_learning"],
                    "points_awarded": r["points_awarded"],
                    "commentary": r["commentary"],
                })
    except Exception as e:
        logger.warning(f"Could not load academic grind highlights: {e}")

    payload = {
        "meta": {
            "generated_at": now.isoformat(),
            "date_display": date_display,
            "today_str": today_str,
            "timezone": "Asia/Kolkata (IST)",
            "total_warriors": total_warriors,
            "total_collective_points": total_collective_points,
            "apex_threshold": 12000,
            "daily_point_cap": 500,
        },
        "schedule": [
            {"time": "05:00 IST", "name": "Morning Kickoff", "description": "Daily motivation & discipline targets announced."},
            {"time": "16:30 IST", "name": "Afternoon Check-in", "description": "Midday pack progress update."},
            {"time": "00:00 IST", "name": "Midnight Finalization", "description": "Scores locked in & podium broadcast."},
        ],
        "disciplines": disciplines,
        "daily_standings": daily_standings,
        "overall_standings": overall_standings,
        "ranks": ranks_data,
        "academic_highlights": academic_highlights,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    logger.info(f"Successfully exported web statistics to {output_path}")
    return payload


if __name__ == "__main__":
    export_stats_to_json()
    logger.info("Export complete: docs/stats.json updated successfully.")
