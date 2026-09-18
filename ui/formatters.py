"""
ui/formatters.py - Visual Formatting Utilities for Winter Arc Bot

Provides progress bars, rank badges, and discipline icons.
"""

from typing import Dict

TASK_ICONS: Dict[str, str] = {
    "push-ups": "💪",
    "pull-ups": "🧗",
    "squats": "🦵",
    "sit-ups": "🧘",
    "running": "🏃",
}


def make_progress_bar(current: float, target: float, length: int = 10, filled: str = "🟩", empty: str = "⬜") -> str:
    """Generates a visual progress bar representation."""
    if target <= 0:
        return filled * length
    ratio = min(max(current / target, 0.0), 1.0)
    fill_count = int(round(ratio * length))
    empty_count = length - fill_count
    return (filled * fill_count) + (empty * empty_count)


def format_rank_badge(idx: int) -> str:
    """Returns distinctive, cross-platform rank badge icon for leaderboard positions."""
    if idx == 0:
        return "👑"
    elif idx == 1:
        return "⚔️"
    elif idx == 2:
        return "🛡️"
    else:
        return f"▫️ #{idx+1}"
