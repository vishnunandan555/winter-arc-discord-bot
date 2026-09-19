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


def format_rank_badge(idx: int, pts: int = 1) -> str:
    """Returns clean, distinct medals or position numbers for leaderboard standings."""
    pos = idx + 1
    if pts <= 0:
        return f"`#{pos}`"
    if pos == 1:
        return "🥇"
    elif pos == 2:
        return "🥈"
    elif pos == 3:
        return "🥉"
    else:
        return f"`#{pos}`"
