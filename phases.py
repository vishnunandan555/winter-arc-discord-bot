"""
phases.py - Winter Arc Phase Progression and Metadata Engine

Defines the 4 official phases of the Winter Arc challenge:
- Phase 1 (October): FIRST FROST (The Shock of Discipline)
- Phase 2 (November): THE HUNT (The Relentless Pursuit)
- Phase 3 (December): THE ENDGAME (The Final Showdown)
- Phase 4 (January): AFTERMATH (The Sovereign Integration)

Provides date parsing, active phase discovery, and progression utilities.
"""

import os
from datetime import date, datetime
from typing import List, Dict, Any, Optional, Union, Tuple
from config import BOT_TZ

def _get_base_year() -> int:
    """Calculates the Winter Arc base year from env or current date."""
    env_yr = os.getenv("WINTER_ARC_YEAR")
    if env_yr:
        try:
            return int(env_yr)
        except ValueError:
            pass
    now_dt = datetime.now(BOT_TZ)
    # If currently in January (Phase 4), base year is previous year
    if now_dt.month == 1:
        return now_dt.year - 1
    return now_dt.year

BASE_YEAR: int = _get_base_year()

# Official Phase Schedule
PHASES: List[Dict[str, Any]] = [
    {
        "id": 1,
        "name": "FIRST FROST",
        "short_name": "Phase 1",
        "emoji": "❄️",
        "badge": "❄️",
        "start_date": f"{BASE_YEAR}-10-01",
        "end_date": f"{BASE_YEAR}-10-31",
        "total_days": 31,
        "month": 10,
        "year": BASE_YEAR,
        "subtitle": "The Shock of Discipline",
        "description": "Establishing the routine, severing distractions, and conquering the initial friction.",
        "color": 0x3498DB,  # Crisp ice blue
    },
    {
        "id": 2,
        "name": "THE HUNT",
        "short_name": "Phase 2",
        "emoji": "🐺",
        "badge": "🐺",
        "start_date": f"{BASE_YEAR}-11-01",
        "end_date": f"{BASE_YEAR}-11-30",
        "total_days": 30,
        "month": 11,
        "year": BASE_YEAR,
        "subtitle": "The Relentless Pursuit",
        "description": "The deep mid-arc grind. Motivation fades and pure discipline takes over. Hunt the standard daily.",
        "color": 0x9B59B6,  # Deep wolf purple
    },
    {
        "id": 3,
        "name": "THE ENDGAME",
        "short_name": "Phase 3",
        "emoji": "⚔️",
        "badge": "⚔️",
        "start_date": f"{BASE_YEAR}-12-01",
        "end_date": f"{BASE_YEAR}-12-31",
        "total_days": 31,
        "month": 12,
        "year": BASE_YEAR,
        "subtitle": "The Final Showdown",
        "description": "Peak blizzard. While the world parties and slacks off, conquer the climax of the Winter Arc.",
        "color": 0xE74C3C,  # Crimson combat red
    },
    {
        "id": 4,
        "name": "AFTERMATH",
        "short_name": "Phase 4",
        "emoji": "🌅",
        "badge": "🌅",
        "start_date": f"{BASE_YEAR + 1}-01-01",
        "end_date": f"{BASE_YEAR + 1}-01-31",
        "total_days": 31,
        "month": 1,
        "year": BASE_YEAR + 1,
        "subtitle": "The Sovereign Integration",
        "description": "Wind-down and lifestyle integration. Cementing the forged identity forever.",
        "color": 0xF39C12,  # Golden dawn
    },
]


def _normalize_date(target: Optional[Union[date, datetime, str]] = None) -> date:
    """Helper to convert date, datetime, or ISO string to standard date in BOT_TZ."""
    if target is None:
        return datetime.now(BOT_TZ).date()
    if isinstance(target, datetime):
        return target.date()
    if isinstance(target, date):
        return target
    if isinstance(target, str):
        return date.fromisoformat(target[:10])
    return datetime.now(BOT_TZ).date()


def get_phase_by_id(phase_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves phase definition by ID (1..4)."""
    for p in PHASES:
        if p["id"] == phase_id:
            return p.copy()
    return None


def get_current_phase(as_of: Optional[Union[date, datetime, str]] = None) -> Dict[str, Any]:
    """
    Returns the phase matching the specified date.
    If the date is before Phase 1 (pre-launch testing), returns Phase 1.
    If the date is after Phase 4, returns Phase 4.
    """
    d = _normalize_date(as_of)
    d_str = d.isoformat()

    # If before Arc start (e.g. Sept testing), map to Phase 1 for seamless testing
    if d_str < PHASES[0]["start_date"]:
        return PHASES[0].copy()

    for p in PHASES:
        if p["start_date"] <= d_str <= p["end_date"]:
            return p.copy()

    # If past Arc conclusion, return final phase
    return PHASES[-1].copy()


def get_unlocked_phases(as_of: Optional[Union[date, datetime, str]] = None) -> List[Dict[str, Any]]:
    """
    Returns a list of phases that have already started on or before `as_of`.
    Future phases that have not arrived yet are strictly omitted.
    """
    d = _normalize_date(as_of)
    d_str = d.isoformat()

    # If before Oct 1, return Phase 1 so UI has at least one selectable phase
    if d_str < PHASES[0]["start_date"]:
        return [PHASES[0].copy()]

    unlocked = [p.copy() for p in PHASES if p["start_date"] <= d_str]
    return unlocked if unlocked else [PHASES[0].copy()]


def get_phase_progress(phase_dict: Dict[str, Any], as_of: Optional[Union[date, datetime, str]] = None) -> Dict[str, Any]:
    """
    Calculates current day index, days remaining, and completion percentage for a given phase.
    """
    d = _normalize_date(as_of)
    start_d = date.fromisoformat(phase_dict["start_date"])
    end_d = date.fromisoformat(phase_dict["end_date"])
    total_days = (end_d - start_d).days + 1

    if d < start_d:
        day_num = 0
        days_remaining = total_days
        pct = 0.0
    elif d > end_d:
        day_num = total_days
        days_remaining = 0
        pct = 100.0
    else:
        day_num = (d - start_d).days + 1
        days_remaining = total_days - day_num
        pct = round((day_num / total_days) * 100, 1)

    return {
        "phase_id": phase_dict["id"],
        "name": phase_dict["name"],
        "total_days": total_days,
        "day_num": day_num,
        "days_remaining": days_remaining,
        "completion_pct": pct,
        "is_active": (start_d <= d <= end_d),
        "is_completed": (d > end_d),
    }


def is_last_day_of_phase(as_of: Optional[Union[date, datetime, str]] = None) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Checks if `as_of` is the final day of an active phase (e.g. Oct 31, Nov 30, Dec 31, Jan 31).
    Returns (True, phase_dict) if so, else (False, None).
    """
    d = _normalize_date(as_of)
    d_str = d.isoformat()

    for p in PHASES:
        if d_str == p["end_date"]:
            return True, p.copy()

    return False, None


def get_next_phase(phase_id: int) -> Optional[Dict[str, Any]]:
    """Returns the phase immediately following `phase_id`, or None if at final phase."""
    for i, p in enumerate(PHASES):
        if p["id"] == phase_id and i + 1 < len(PHASES):
            return PHASES[i + 1].copy()
    return None
