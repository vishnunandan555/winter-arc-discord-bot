"""
levels.py - 12-Level Progression System for Winter Arc Bot

Calibrated around 12,000 Lifetime Points for Level 12 (Apex) across a 90-day arc (~133 pts/day).
Provides level lookup, progress bar rendering, and rank-up detection.
"""

from typing import Optional, Dict, Any, List

APEX_THRESHOLD = 12000

RANKS: List[Dict[str, Any]] = [
    {
        "level": 1,
        "title": "Initiate",
        "min_pts": 0,
        "max_pts": 499,
        "badge": "🥉",
        "color": 0x7F8C8D,  # Slate Grey
        "description": "The journey begins. First steps on the board.",
    },
    {
        "level": 2,
        "title": "Novice",
        "min_pts": 500,
        "max_pts": 1199,
        "badge": "🥉",
        "color": 0x95A5A6,  # Ash Grey
        "description": "Surviving week one. Developing the daily habit.",
    },
    {
        "level": 3,
        "title": "Challenger",
        "min_pts": 1200,
        "max_pts": 1999,
        "badge": "🥈",
        "color": 0x3498DB,  # Frost Blue
        "description": "Routine taking root. Consistency building.",
    },
    {
        "level": 4,
        "title": "Dedicated",
        "min_pts": 2000,
        "max_pts": 2999,
        "badge": "🥈",
        "color": 0x2980B9,  # Deep Arctic Blue
        "description": "Body adapting. Soreness fading, rhythm locked.",
    },
    {
        "level": 5,
        "title": "Disciplined",
        "min_pts": 3000,
        "max_pts": 4199,
        "badge": "🥇",
        "color": 0x1ABC9C,  # Mountain Pine / Teal
        "description": "Month 1 completed. Execution on autopilot.",
    },
    {
        "level": 6,
        "title": "Hardened",
        "min_pts": 4200,
        "max_pts": 5499,
        "badge": "🥇",
        "color": 0x16A085,  # Dark Teal
        "description": "Daily execution without negotiation.",
    },
    {
        "level": 7,
        "title": "Iron",
        "min_pts": 5500,
        "max_pts": 6999,
        "badge": "⚡",
        "color": 0xE67E22,  # Ember Amber
        "description": "Halfway mark reached. Resilient momentum.",
    },
    {
        "level": 8,
        "title": "Vanguard",
        "min_pts": 7000,
        "max_pts": 8499,
        "badge": "🛡️",
        "color": 0xD35400,  # Deep Ember
        "description": "Month 2 milestone. Unshakable standard.",
    },
    {
        "level": 9,
        "title": "Relentless",
        "min_pts": 8500,
        "max_pts": 9799,
        "badge": "❄️",
        "color": 0x00D2FF,  # Glacial Cyan
        "description": "Rain, cold, or fatigue—the work gets done.",
    },
    {
        "level": 10,
        "title": "Veteran",
        "min_pts": 9800,
        "max_pts": 10799,
        "badge": "🔥",
        "color": 0xE74C3C,  # Crimson Fury
        "description": "Final stretch. High standards daily.",
    },
    {
        "level": 11,
        "title": "Master",
        "min_pts": 10800,
        "max_pts": 11999,
        "badge": "👑",
        "color": 0xF1C40F,  # Golden Crown
        "description": "Elite consistency. Top tier execution.",
    },
    {
        "level": 12,
        "title": "Apex",
        "min_pts": 12000,
        "max_pts": None,
        "badge": "💎",
        "color": 0x9B59B6,  # Royal Amethyst / Diamond
        "description": "Arc Conquered. 90-day total discipline.",
    },
]


def render_progress_bar(pct: float, length: int = 10) -> str:
    """Renders a sleek text progress bar: [████████░░░░░░] 60%"""
    clamped_pct = max(0.0, min(100.0, pct))
    filled = int(round((clamped_pct / 100.0) * length))
    filled = max(0, min(length, filled))
    empty = length - filled
    return f"`[{'█' * filled}{'░' * empty}]` {int(clamped_pct)}%"


def get_level_info(lifetime_points: int) -> Dict[str, Any]:
    """
    Computes user rank info, current tier progress, distance to next level,
    and visual progress bar focused on the immediate next rank.
    """
    pts = max(0, int(lifetime_points))
    current_rank = RANKS[0]
    next_rank: Optional[Dict[str, Any]] = None

    for idx, r in enumerate(RANKS):
        if r["max_pts"] is None:
            # Level 12 (Apex)
            if pts >= r["min_pts"]:
                current_rank = r
                next_rank = None
                break
        else:
            if r["min_pts"] <= pts <= r["max_pts"]:
                current_rank = r
                next_rank = RANKS[idx + 1] if (idx + 1) < len(RANKS) else None
                break
            elif pts > r["max_pts"] and idx == len(RANKS) - 1:
                current_rank = r
                next_rank = None

    is_apex = (current_rank["max_pts"] is None)

    if is_apex:
        pts_in_tier = pts - current_rank["min_pts"]
        tier_size = 0
        tier_pct = 100
        pts_to_next = 0
        progress_bar_str = render_progress_bar(100.0)
    else:
        tier_size = (current_rank["max_pts"] - current_rank["min_pts"]) + 1
        pts_in_tier = pts - current_rank["min_pts"]
        tier_pct = min(99, max(0, int((pts_in_tier / tier_size) * 100)))
        pts_to_next = (current_rank["max_pts"] + 1) - pts
        progress_bar_str = render_progress_bar(tier_pct)

    arc_pct = min(100.0, round((pts / APEX_THRESHOLD) * 100, 1))

    return {
        "level": current_rank["level"],
        "title": current_rank["title"],
        "badge": current_rank["badge"],
        "color": current_rank["color"],
        "description": current_rank["description"],
        "min_pts": current_rank["min_pts"],
        "max_pts": current_rank["max_pts"],
        "lifetime_points": pts,
        "points_in_tier": pts_in_tier,
        "tier_size": tier_size,
        "tier_pct": tier_pct,
        "progress_pct": tier_pct,
        "pts_to_next": pts_to_next,
        "points_to_next": pts_to_next,
        "next_rank": next_rank,
        "next_level": next_rank["level"] if next_rank else None,
        "next_title": next_rank["title"] if next_rank else None,
        "next_badge": next_rank["badge"] if next_rank else None,
        "next_threshold": next_rank["min_pts"] if next_rank else None,
        "is_apex": is_apex,
        "is_max_level": is_apex,
        "arc_pct": arc_pct,
        "progress_bar": progress_bar_str,
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
