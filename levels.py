"""
levels.py - 12-Level Winter Pack Progression System

Calibrated for a 90-day Winter Arc horizon with Apex achieved at
12,000 Lifetime Points (~133 points/day average).
"""

from typing import Optional, Dict, Any, List

# 12-Level Progression Hierarchy
RANKS: List[Dict[str, Any]] = [
    {"level": 1,  "title": "Lone Stray", "badge": "🐾", "min_pts": 0,      "max_pts": 499,   "color": 0x7F8C8D},
    {"level": 2,  "title": "Stray",      "badge": "🐺", "min_pts": 500,    "max_pts": 1199,  "color": 0x95A5A6},
    {"level": 3,  "title": "Scout",      "badge": "🧭", "min_pts": 1200,   "max_pts": 1999,  "color": 0x3498DB},
    {"level": 4,  "title": "Prowler",    "badge": "🐾", "min_pts": 2000,   "max_pts": 2999,  "color": 0x2980B9},
    {"level": 5,  "title": "Tracker",    "badge": "🏹", "min_pts": 3000,   "max_pts": 4199,  "color": 0x1ABC9C},
    {"level": 6,  "title": "Hunter",     "badge": "🗡️", "min_pts": 4200,   "max_pts": 5499,  "color": 0x16A085},
    {"level": 7,  "title": "Savage",     "badge": "⚔️", "min_pts": 5500,   "max_pts": 6999,  "color": 0xE67E22},
    {"level": 8,  "title": "Vanguard",   "badge": "🛡️", "min_pts": 7000,   "max_pts": 8499,  "color": 0xD35400},
    {"level": 9,  "title": "Frostborn",  "badge": "❄️", "min_pts": 8500,   "max_pts": 9799,  "color": 0x00D2FF},
    {"level": 10, "title": "Predator",   "badge": "⚡", "min_pts": 9800,   "max_pts": 10799, "color": 0x9B59B6},
    {"level": 11, "title": "Alpha",      "badge": "🔥", "min_pts": 10800,  "max_pts": 11999, "color": 0xE74C3C},
    {"level": 12, "title": "Apex",       "badge": "👑", "min_pts": 12000,  "max_pts": None,  "color": 0xF1C40F},
]

APEX_THRESHOLD = 12000


def get_level_info(lifetime_points: int) -> Dict[str, Any]:
    """
    Computes user rank, level, tier progress, and distance to next level
    from lifetime points.
    """
    pts = max(0, int(lifetime_points))
    current_rank = RANKS[0]

    for rank in RANKS:
        if rank["max_pts"] is None:
            if pts >= rank["min_pts"]:
                current_rank = rank
                break
        else:
            if rank["min_pts"] <= pts <= rank["max_pts"]:
                current_rank = rank
                break

    is_apex = current_rank["max_pts"] is None
    if is_apex:
        pts_in_tier = pts - current_rank["min_pts"]
        tier_size = 0
        tier_pct = 100
        pts_to_next = 0
        next_rank = None
    else:
        tier_size = (current_rank["max_pts"] - current_rank["min_pts"]) + 1
        pts_in_tier = pts - current_rank["min_pts"]
        tier_pct = min(100, max(0, int((pts_in_tier / tier_size) * 100)))
        pts_to_next = (current_rank["max_pts"] + 1) - pts
        next_level_num = current_rank["level"] + 1
        next_rank = next((r for r in RANKS if r["level"] == next_level_num), None)

    arc_pct = min(100.0, round((pts / APEX_THRESHOLD) * 100, 1))

    return {
        "level": current_rank["level"],
        "title": current_rank["title"],
        "badge": current_rank["badge"],
        "color": current_rank["color"],
        "min_pts": current_rank["min_pts"],
        "max_pts": current_rank["max_pts"],
        "lifetime_points": pts,
        "points_in_tier": pts_in_tier,
        "tier_size": tier_size,
        "tier_pct": tier_pct,
        "pts_to_next": pts_to_next,
        "next_rank": next_rank,
        "is_apex": is_apex,
        "arc_pct": arc_pct,
    }


def check_level_up(old_points: int, new_points: int) -> Optional[Dict[str, Any]]:
    """
    Compares previous lifetime points to new lifetime points.
    Returns level info dict if user crossed a level milestone, otherwise None.
    """
    old_info = get_level_info(old_points)
    new_info = get_level_info(new_points)

    if new_info["level"] > old_info["level"]:
        return new_info
    return None


def get_all_ranks() -> List[Dict[str, Any]]:
    """Returns the full ranks list for directory display."""
    return RANKS
