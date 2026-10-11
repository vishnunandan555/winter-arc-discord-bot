"""
ui/embed_builders/common.py - Common formatting utilities, sanitization, and helpers for embed builders.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional, Dict, List
import re
import discord

from config import BOT_TZ
from phases import is_recovery_day as _phases_is_recovery_day


def is_recovery_day(*args, **kwargs):
    """Dynamic resolution for is_recovery_day to preserve patch('ui.embeds.is_recovery_day') in tests."""
    import sys
    mod = sys.modules.get("ui.embeds")
    if mod and hasattr(mod, "is_recovery_day") and mod.is_recovery_day is not is_recovery_day:
        return mod.is_recovery_day(*args, **kwargs)
    return _phases_is_recovery_day(*args, **kwargs)

# Embed Theme Colors
COLOR_PRIMARY = 0x2B2D31
COLOR_SUCCESS = 0x2ECC71
COLOR_WARNING = 0xF39C12
COLOR_ERROR = 0xE74C3C
COLOR_GOLD = 0xF1C40F
COLOR_CYAN = 0x00D2D3
COLOR_PURPLE = 0x9B59B6

LEADERBOARD_NAV_GUIDE = ""

STREAK_LEGEND_FOOTER = "🟩 Streaked • ⭐ Perfect Day (100%) • ❤️ ARD • 🛡️ Shield Used • 🟥 Missed • ▫️ Upcoming"
STREAK_LEGEND_SUBTEXT = STREAK_LEGEND_FOOTER

AUTHENTIC_REST_QUOTES = [
    '"He who knows when he can fight and when he cannot, will be victorious." — Sun Tzu',
    '"Even a bow breaks if it is kept always bent." — Publilius Syrus',
    '"Take rest; a field that has rested gives a bountiful crop." — Ovid',
    '"In intervals of rest, the mind and body find renewed vigor." — Seneca',
    '"No man is free who is not master of himself." — Epictetus',
    '"Nature does not hurry, yet everything is accomplished." — Lao Tzu',
    '"Rest when you are weary. Refresh and renew yourself, your body, your mind, your spirit." — Marcus Aurelius',
]

LEAK_PATTERNS = [
    r"<\s*(?:think|thought|reasoning|analysis)\b[^>]*>",
    r"<\s*/\s*(?:think|thought|reasoning|analysis)\s*>",
    r"(?i)here(?:'s|\s+is)\s+(?:a\s+)?(?:thinking\s+process|thought\s+process|analysis|reasoning)",
    r"(?i)\b(?:thinking\s+process|thought\s+process)\b",
    r"(?i)\banalyze\s+user\s+request\b",
    r"(?i)\banalyzing\s+the\s+request\b",
    r"(?i)\bthe\s+user\s+wants\s+(?:a|to)\b",
    r"(?i)\binternal\s+reasoning\b",
    r"(?i)^\s*(?:thought|reasoning|thinking):\s*",
]


def format_num(val: Any) -> Any:
    """Safely converts numeric float/int to clean int if whole, without crashing if already int."""
    if val is None:
        return 0
    try:
        f = float(val)
        return int(f) if f.is_integer() else round(f, 2)
    except (ValueError, TypeError):
        return val


def sanitize_display_text(text: Optional[str], fallback: str = "") -> str:
    """Sanitizes text meant for Discord display against LLM thought/reasoning leakage."""
    if not text:
        return fallback
    clean = str(text).strip()

    # 1. Strip known XML/HTML tags
    clean = re.sub(
        r"<\s*(?:think|thought|reasoning|analysis)\b[^>]*>[\s\S]*?<\s*/\s*(?:think|thought|reasoning|analysis)\s*>",
        "",
        clean,
        flags=re.IGNORECASE,
    ).strip()
    clean = re.sub(r"<\s*/?\s*(?:think|thought|reasoning|analysis)\b[^>]*>", "", clean, flags=re.IGNORECASE).strip()

    # 2. Check for leakage marker patterns
    has_leak = any(re.search(pat, clean) for pat in LEAK_PATTERNS)
    if has_leak:
        match = re.search(r"(?:^|\n)\s*([\"“][^\"”\n]+[\"”]\s*—\s*[^—\n]+)\s*$", clean)
        if match:
            clean = match.group(1).strip()
        else:
            sections = re.split(r"\n\s*\n", clean)
            valid_sections = [
                s.strip()
                for s in sections
                if not any(re.search(pat, s) for pat in LEAK_PATTERNS) and len(s.strip()) > 10
            ]
            if valid_sections:
                clean = valid_sections[-1]
            else:
                return fallback

    if not clean or any(re.search(pat, clean) for pat in LEAK_PATTERNS):
        return fallback
    return clean


def get_midnight_reset_timestamp() -> int:
    """Returns the Unix epoch timestamp for 00:00:00 IST of tomorrow (daily rollover)."""
    now = datetime.now(BOT_TZ)
    tomorrow_midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=BOT_TZ)
    return int(tomorrow_midnight.timestamp())


def _format_day_ordinal(n: int) -> str:
    """Returns day with ordinal suffix, e.g. 1st, 2nd, 3rd, 4th, 11th, 12th, 21st, 22nd."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def format_embed_as_text(embed: discord.Embed) -> str:
    """Extracts all text fields from a Discord Embed into a clean unedited string representation."""
    parts = []
    if embed.title:
        parts.append(embed.title)
    if embed.description:
        parts.append(embed.description)
    for field in embed.fields:
        parts.append(f"{field.name}:\n{field.value}")
    if embed.footer and embed.footer.text:
        parts.append(f"Footer: {embed.footer.text}")
    return "\n\n".join(parts).strip()
