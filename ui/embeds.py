"""
ui/embeds.py - Reusable Discord Embed Builders for Winter Arc Bot

Centralizes all presentation styling, layout spacing, color palettes,
and progression information across user commands, admin tools, and scheduled announcements.
"""

from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional, Union, Tuple
import re
import discord

import database as db
from config import BOT_TZ, MIN_STREAK_POINTS
from phases import is_recovery_day
from levels import get_level_info, get_all_ranks, APEX_THRESHOLD
from ui.formatters import make_progress_bar, format_rank_badge, TASK_ICONS


def format_num(val: Any) -> Any:
    """Safely converts numeric float/int to clean int if whole, without crashing if already int."""
    if val is None:
        return 0
    try:
        f = float(val)
        return int(f) if f.is_integer() else round(f, 2)
    except (ValueError, TypeError):
        return val


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


def sanitize_display_text(text: Optional[str], fallback: str = "") -> str:
    """Sanitizes text meant for Discord display against LLM thought/reasoning leakage."""
    if not text:
        return fallback
    clean = str(text).strip()

    # 1. Strip known XML/HTML tags
    clean = re.sub(r"<\s*(?:think|thought|reasoning|analysis)\b[^>]*>[\s\S]*?<\s*/\s*(?:think|thought|reasoning|analysis)\s*>", "", clean, flags=re.IGNORECASE).strip()
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
                s.strip() for s in sections
                if not any(re.search(pat, s) for pat in LEAK_PATTERNS) and len(s.strip()) > 10
            ]
            if valid_sections:
                clean = valid_sections[-1]
            else:
                return fallback

    if not clean or any(re.search(pat, clean) for pat in LEAK_PATTERNS):
        return fallback
    return clean


LEADERBOARD_NAV_GUIDE = ""

AUTHENTIC_REST_QUOTES = [
    '"He who knows when he can fight and when he cannot, will be victorious." — Sun Tzu',
    '"Even a bow breaks if it is kept always bent." — Publilius Syrus',
    '"Take rest; a field that has rested gives a bountiful crop." — Ovid',
    '"In intervals of rest, the mind and body find renewed vigor." — Seneca',
    '"No man is free who is not master of himself." — Epictetus',
    '"Nature does not hurry, yet everything is accomplished." — Lao Tzu',
    '"Rest when you are weary. Refresh and renew yourself, your body, your mind, your spirit." — Marcus Aurelius',
]


def build_daily_leaderboard_embed() -> discord.Embed:
    """Builds the clean daily standing leaderboard embed (max top 10)."""
    now = datetime.now(BOT_TZ)
    today_str = now.strftime("%Y-%m-%d")
    date_display = now.strftime("%A, %B %d, %Y")

    if is_recovery_day(today_str):
        import random
        rest_quote = random.choice(AUTHENTIC_REST_QUOTES)
        embed = discord.Embed(
            title="Winter Arc — Active Recovery Day 🌿",
            description=(
                f"📅 **{date_display}**\n\n"
                "**The scoreboard is paused today.**\n"
                "The pack is observing Active Recovery. Daily scoring and competition are closed so everyone can rest and rebuild equally.\n\n"
                "🔥 **All streaks are automatically preserved.**\n\n"
                f"> {rest_quote}"
            ),
            color=0x27AE60
        )
        embed.set_footer(text="Active Recovery Day (ARD) ❤️ • Streaks protected • Competition resumes tomorrow")
        return embed

    data = db.get_daily_leaderboard(today_str)
    top_10 = data[:10]

    any_points = any(entry["points"] > 0 for entry in top_10)

    lines = []
    if not any_points:
        lines.append("_No disciplines logged today yet._")
        lines.append("_Log your workout with `/quick` or `/log` to claim #1!_")
    else:
        for idx, entry in enumerate(top_10):
            pts = entry["points"]
            badge = format_rank_badge(idx, pts=pts)
            if pts > 0:
                pct = int(entry["completion_rate"] * 100)
                star = " ⭐" if entry["perfect_day"] else ""
                lines.append(f"{badge} **{entry['username']}** — **{pts} pts** ({pct}%){star}")
            else:
                lines.append(f"{badge} **{entry['username']}** — **0 pts**")

    embed = discord.Embed(
        title="🏆 Winter Arc — Daily Standings",
        description=(
            f"📅 **{date_display}**\n\n"
            + "\n".join(lines)
        ),
        color=0xF1C40F
    )
    footer_text = "Updated live • Resets daily at 00:00 IST"
    if len(data) > 10:
        footer_text = f"Showing top 10 of {len(data)} participants • {footer_text}"
    embed.set_footer(text=footer_text)
    return embed


def build_weekly_leaderboard_embed(start_date: Optional[str] = None, end_date: Optional[str] = None) -> discord.Embed:
    """Builds the weekly standings leaderboard for a specific calendar week (max top 10, Sunday to Saturday)."""
    now = datetime.now(BOT_TZ)
    today = now.date()
    days_since_sunday = (today.weekday() + 1) % 7
    start_of_week = today - timedelta(days=days_since_sunday)
    end_of_week = start_of_week + timedelta(days=6)
    s_date = start_date or start_of_week.isoformat()
    e_date = end_date or end_of_week.isoformat()

    s_dt = date.fromisoformat(s_date)
    e_dt = date.fromisoformat(e_date)
    date_display = f"{s_dt.strftime('%b %d')} – {e_dt.strftime('%b %d, %Y')}"

    data = db.get_weekly_leaderboard(s_date, e_date)
    top_10 = data[:10]

    any_points = any(entry["total_points"] > 0 for entry in top_10)
    lines = []
    if not any_points:
        lines.append(f"_No activity recorded for this week ({date_display}) yet._")
    else:
        for idx, entry in enumerate(top_10):
            pts = entry["total_points"]
            badge = format_rank_badge(idx, pts=pts)
            clean = entry.get("perfect_days", 0)
            clean_str = f" • ⭐ {clean} perfect" if clean > 0 else ""
            lines.append(f"{badge} **{entry['username']}** — **{pts:,} pts**{clean_str}")

    embed = discord.Embed(
        title="🏆 Winter Arc — Weekly Standings",
        description=(
            f"📅 **Week of {date_display}**\n\n"
            + "\n".join(lines)
        ),
        color=0x2ECC71
    )
    footer_text = "Updated live • Ranked by weekly points (Sun–Sat)"
    if len(data) > 10:
        footer_text = f"Showing top 10 of {len(data)} participants • {footer_text}"
    embed.set_footer(text=footer_text)
    return embed


def build_overall_leaderboard_embed() -> discord.Embed:
    """Builds the all-time standings leaderboard (max top 10)."""
    data = db.get_overall_leaderboard()
    top_10 = data[:10]

    lines = []
    for idx, entry in enumerate(top_10):
        pts = entry["total_points"]
        badge = format_rank_badge(idx, pts=pts)
        lvl_info = get_level_info(pts)

        extras = []
        if entry.get("streak", 0) > 0:
            extras.append(f"🔥 {entry['streak']}d")
        if entry.get("perfect_days", 0) > 0:
            extras.append(f"⭐ {entry['perfect_days']} perfect")
        extra_str = f" • {' '.join(extras)}" if extras else ""

        lines.append(f"{badge} **{entry['username']}** — **{pts:,} pts** *(Lvl {lvl_info['level']} {lvl_info['title']})*{extra_str}")

    if not lines:
        lines.append("_No enrolled participants found._")

    embed = discord.Embed(
        title="🏆 Winter Arc — Overall Standings",
        description=(
            "🌐 **All-Time Leaderboard**\n\n"
            + "\n".join(lines)
        ),
        color=0x3498DB
    )
    footer_text = "Updated live • Ranked by lifetime points"
    if len(data) > 10:
        footer_text = f"Showing top 10 of {len(data)} participants • {footer_text}"
    embed.set_footer(text=footer_text)
    return embed


def build_monthly_leaderboard_embed(year: Optional[int] = None, month: Optional[int] = None) -> discord.Embed:
    """Builds the monthly standings leaderboard (max top 10), branded with the active Winter Arc phase."""
    now = datetime.now(BOT_TZ)
    y = year or now.year
    m = month or now.month
    month_name = datetime(y, m, 1).strftime("%B %Y")
    data = db.get_monthly_leaderboard(y, m)
    top_10 = data[:10]

    from phases import get_current_phase, get_phase_progress
    curr_phase = get_current_phase(datetime(y, m, min(now.day, 28)))
    is_phase_month = curr_phase and (curr_phase["month"] == m)

    phase_header = f"🏆 **Monthly Leaderboard • {month_name}**"
    embed_color = 0x9B59B6
    if is_phase_month:
        prog = get_phase_progress(curr_phase, now)
        phase_header = (
            f"🏆 **{curr_phase['badge']} {curr_phase['short_name']}: {curr_phase['name']} Standings • {month_name}**\n"
            f"*⏳ {prog['days_remaining']} days remaining in this phase (Day {prog['day_num']} of {prog['total_days']})*"
        )
        embed_color = curr_phase["color"]

    any_points = any(entry["total_points"] > 0 for entry in top_10)
    lines = []
    if not any_points:
        lines.append(f"_No activity recorded for {month_name} yet._")
    else:
        for idx, entry in enumerate(top_10):
            pts = entry["total_points"]
            badge = format_rank_badge(idx, pts=pts)
            clean = entry.get("perfect_days", 0)
            clean_str = f" • ⭐ {clean} perfect" if clean > 0 else ""
            lines.append(f"{badge} **{entry['username']}** — **{pts:,} pts**{clean_str}")

    title_text = f"📆 Winter Arc — {month_name} Standings"
    if is_phase_month:
        title_text = f"{curr_phase['badge']} Winter Arc — {curr_phase['name']} Standings ({month_name})"

    embed = discord.Embed(
        title=title_text,
        description=f"{phase_header}\n\n" + "\n".join(lines),
        color=embed_color
    )
    footer_text = "Updated live • Ranked by monthly points"
    if len(data) > 10:
        footer_text = f"Showing top 10 of {len(data)} participants • {footer_text}"
    embed.set_footer(text=footer_text)
    return embed


def get_midnight_reset_timestamp() -> int:
    """Returns the Unix epoch timestamp for 00:00:00 IST of tomorrow (daily rollover)."""
    now = datetime.now(BOT_TZ)
    tomorrow_midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=BOT_TZ)
    return int(tomorrow_midnight.timestamp())


def build_today_embed(target_user: discord.Member, progress: Dict[str, Any], streak: int, date_display: str) -> discord.Embed:
    """Builds the daily progress card with individual emoji progress bars per task and total percentage at the end."""
    task_lines = []
    for t in progress["tasks"]:
        name = t["name"]
        unit = t["unit"]
        pts = t["points_earned"]
        icon = TASK_ICONS.get(name.lower(), "🎯")
        cur = format_num(t["current_amount"])
        tgt = format_num(t["target"])
        check = " ✅" if t["completed"] else ""
        bar = make_progress_bar(cur, tgt, length=8)
        pct = int(round((cur / tgt) * 100)) if tgt > 0 else 0
        task_lines.append(f"{icon} **{name}** — {cur} / {tgt} {unit} *({pts} pts)*{check}\n{bar} `{pct}%`")

    total_pts = progress["total_points"]
    max_pts = progress["max_possible_points"]
    pct = int(round(progress["overall_completion_rate"] * 100))

    grind_pts = progress.get("grind_points", 0)
    grind_section = ""
    points_breakdown = ""
    if grind_pts > 0 or progress.get("grind_entry"):
        entry = progress.get("grind_entry") or {}
        learning = entry.get("key_learning", "Custom Grind") if isinstance(entry, dict) else "Custom Grind"
        grind_section = f"\n\n**⚔️ Grind Bonus**: +{grind_pts} pts *({learning})*"
        phys_pts = progress.get("physical_points", total_pts - grind_pts)
        points_breakdown = f"  *(Physical: {phys_pts} + Grind: {grind_pts})*"

    total_line = f"\n\n📊 **Total Daily Progress**: **{total_pts} / {max_pts} pts** (**{pct}%**){points_breakdown}"

    reset_ts = get_midnight_reset_timestamp()
    today_recovery = is_recovery_day()

    if today_recovery:
        if total_pts >= MIN_STREAK_POINTS or progress["perfect_day"]:
            streak_status = " *(Streak Secured ✅)*"
            footer_text = "Active Recovery Day (ARD) ❤️ • Streak secured with volume • Rebuild & recover!"
            color = 0x1ABC9C if progress["perfect_day"] else 0x2ECC71
        else:
            streak_status = " *(ARD ❤️ Streak Protected)*"
            footer_text = "Active Recovery Day (ARD) ❤️ • Light mobility & hydration • Streak automatically preserved"
            color = 0x9B59B6

        deadline_line = f"✨ **Next Day Unlocks**: <t:{reset_ts}:R> (<t:{reset_ts}:t>)"
        desc = (
            f"**{target_user.display_name}** • {date_display}\n"
            f"🔥 Current Streak: **{streak} days**{streak_status}\n"
            f"{deadline_line}\n\n"
            "🌿 **Active Recovery Day (ARD)**\n"
            "Competition and logging are paused today. Rest is not weakness — it is where the body adapts and rebuilds.\n\n"
            "**Recommended Recovery Protocol**:\n"
            "• 💧 **Hydration**: Drink 3–4L water\n"
            "• 🧘 **Gentle Mobility**: 15–30 min casual walk or stretching\n"
            "• 🧠 **Mental Deload**: Sleep 8+ hours, disconnect, read\n\n"
            "*Rest easy warrior. Your streak is safe. Tomorrow we hunt.*"
        )
        embed = discord.Embed(
            title="❄️ Winter Arc — Rest & Recovery Day",
            description=desc,
            color=color
        )
        embed.set_footer(text=footer_text)
        return embed

    if total_pts >= MIN_STREAK_POINTS or progress["perfect_day"]:
        streak_status = " *(Streak Secured ✅)*"
        deadline_line = f"✨ **Next Day Unlocks**: <t:{reset_ts}:R> (<t:{reset_ts}:t>)"
        footer_text = f"Log with /log • {MIN_STREAK_POINTS} pts/day minimum for streak"
        color = 0x1ABC9C if progress["perfect_day"] else 0x2ECC71
    else:
        streak_status = f" *({MIN_STREAK_POINTS - total_pts} pts to secure streak)*"
        deadline_line = f"⏳ **Deadline to Secure Streak**: <t:{reset_ts}:R> (<t:{reset_ts}:t>)"
        footer_text = f"Log with /log • {MIN_STREAK_POINTS} pts/day minimum for streak"
        color = 0x3498DB

    desc = (
        f"**{target_user.display_name}** • {date_display}\n"
        f"🔥 Current Streak: **{streak} days**{streak_status}\n"
        f"{deadline_line}\n\n"
        "**Daily Disciplines**\n"
        + "\n\n".join(task_lines)
        + grind_section
        + total_line
    )

    embed = discord.Embed(
        title="❄️ Winter Arc — Today",
        description=desc,
        color=color
    )
    embed.set_footer(text=footer_text)
    return embed


def build_tasks_embed(target_user: discord.Member, progress: Dict[str, Any], streak: int, date_display: str) -> discord.Embed:
    """Builds the comprehensive daily disciplines embed explaining each task alongside progress bars."""
    task_blocks = []
    for t in progress["tasks"]:
        name = t["name"]
        unit = t["unit"]
        pts = t["points_earned"]
        max_pts = t.get("max_points", 100)
        desc = t.get("description") or "Discipline workout target"
        icon = TASK_ICONS.get(name.lower(), "🎯")
        cur = format_num(t["current_amount"])
        tgt = format_num(t["target"])
        check = " ✅" if t["completed"] else ""
        bar = make_progress_bar(cur, tgt, length=8)
        pct = int(round((cur / tgt) * 100)) if tgt > 0 else 0
        task_blocks.append(
            f"{icon} **{name}** — **{cur} / {tgt} {unit}** *({pts}/{max_pts} pts)*{check}\n"
            f"{bar} `{pct}%`\n"
            f"> ℹ️ *{desc}*"
        )

    total_pts = progress["total_points"]
    max_pts = progress["max_possible_points"]
    pct = int(round(progress["overall_completion_rate"] * 100))

    grind_pts = progress.get("grind_points", 0)
    grind_section = ""
    points_breakdown = ""
    if grind_pts > 0 or progress.get("grind_entry"):
        entry = progress.get("grind_entry") or {}
        learning = entry.get("key_learning", "Custom Grind") if isinstance(entry, dict) else "Custom Grind"
        grind_section = f"\n\n**⚔️ Grind Bonus**: +{grind_pts} pts *({learning})*"
        phys_pts = progress.get("physical_points", total_pts - grind_pts)
        points_breakdown = f"  *(Physical: {phys_pts} + Grind: {grind_pts})*"

    total_line = f"\n\n📊 **Total Daily Progress**: **{total_pts} / {max_pts} pts** (**{pct}%**){points_breakdown}"

    today_recovery = is_recovery_day()
    if total_pts >= MIN_STREAK_POINTS or progress["perfect_day"]:
        streak_status = " *(Streak Secured ✅)*"
        footer_text = f"Log with /log • Set with /set • {MIN_STREAK_POINTS} pts/day minimum for streak"
        color = 0x1ABC9C if progress["perfect_day"] else 0x2ECC71
    elif today_recovery:
        streak_status = " *(ARD ❤️ Streak Protected)*"
        footer_text = "Active Recovery Day (ARD) ❤️ • Light mobility & hydration • Streak automatically preserved"
        color = 0x9B59B6
    else:
        streak_status = f" *({MIN_STREAK_POINTS - total_pts} pts to secure streak)*"
        footer_text = f"Log with /log • Set with /set • {MIN_STREAK_POINTS} pts/day minimum for streak"
        color = 0x3498DB

    description = (
        f"**{target_user.display_name}** • {date_display}\n"
        f"🔥 Current Streak: **{streak} days**{streak_status}\n\n"
        "**Daily Disciplines & Task Guide**\n\n"
        + "\n\n".join(task_blocks)
        + grind_section
        + total_line
    )

    embed = discord.Embed(
        title="📋 Winter Arc — Disciplines & Tasks",
        description=description,
        color=color
    )
    embed.set_footer(text=footer_text)
    return embed


def format_log_reply(result: Dict[str, Any], amount: float, level_up_info: Optional[Dict[str, Any]] = None) -> str:
    """Formats a clean, casual plain-text reply after logging sets."""
    cur = format_num(result["new_total"])
    tgt = format_num(result["target"])
    amt = format_num(amount)
    unit = result.get("unit", "reps")
    task_name = result["task_name"]
    today_total = format_num(result["daily_points_total"])
    today_max = format_num(result["daily_points_max"])

    star_msg = " ⭐ Target completed!" if (result["is_target_reached"] and result["previous_total"] < result["target"]) else ""
    msg = f"Logged **+{amt} {unit}** to **{task_name}** ({cur}/{tgt} {unit}){star_msg} • Today: **{today_total}/{today_max} pts**"

    if level_up_info:
        msg += f"\n🎉 **Rank Promotion!** You reached **Level {level_up_info['level']} — {level_up_info['badge']} {level_up_info['title']}**!"
    if result.get("shield_awarded"):
        msg += "\n🛡️ **Streak Shield Earned!** You hit a 7-day streak milestone (+1 Shield added to inventory)."

    daily_pts = result.get("daily_points_total", 0)
    if daily_pts < MIN_STREAK_POINTS:
        remaining_pts = MIN_STREAK_POINTS - daily_pts
        reset_ts = get_midnight_reset_timestamp()
        msg += f"\n⏳ Need **{remaining_pts} more pts** before midnight (<t:{reset_ts}:R>) to secure streak."

    return msg


def format_set_reply(result: Dict[str, Any], amount: float, level_up_info: Optional[Dict[str, Any]] = None) -> str:
    """Formats a clean, casual plain-text reply after setting/overriding sets."""
    cur = format_num(result["new_total"])
    tgt = format_num(result["target"])
    prev = format_num(result["previous_total"])
    unit = result.get("unit", "reps")
    task_name = result["task_name"]
    today_total = format_num(result["daily_points_total"])
    today_max = format_num(result["daily_points_max"])

    if amount == 0:
        msg = f"Reset **{task_name}** to **0 {unit}** (was {prev} {unit}) • Today: **{today_total}/{today_max} pts**"
    else:
        star_msg = " ⭐ Target completed!" if (result["is_target_reached"] and result["previous_total"] < result["target"]) else ""
        msg = f"Adjusted **{task_name}**: **{prev}** ➔ **{cur} {unit}** ({cur}/{tgt} {unit}){star_msg} • Today: **{today_total}/{today_max} pts**"

    if level_up_info:
        msg += f"\n🎉 **Rank Promotion!** You reached **Level {level_up_info['level']} — {level_up_info['badge']} {level_up_info['title']}**!"
    if result.get("shield_awarded"):
        msg += "\n🛡️ **Streak Shield Earned!** You hit a 7-day streak milestone (+1 Shield added to inventory)."

    return msg


def build_log_embed(result: Dict[str, Any], amount: float, level_up_info: Optional[Dict[str, Any]] = None) -> discord.Embed:
    """Builds the confirmation embed after logging sets, including level up promotion banners."""
    cur = format_num(result["new_total"])
    tgt = format_num(result["target"])
    amt = format_num(amount)

    bar = make_progress_bar(result["new_total"], result["target"], length=8)
    delta_str = f"+{result['points_earned_delta']} pts" if result['points_earned_delta'] > 0 else "Capped"

    promo_banner = ""
    if level_up_info:
        promo_banner = (
            f"\n\n🎉 **RANK PROMOTION!**\n"
            f"You reached **Level {level_up_info['level']} — {level_up_info['badge']} {level_up_info['title']}**!\n"
        )
    if result.get("shield_awarded"):
        promo_banner += "\n\n🛡️ **STREAK SHIELD EARNED!** You hit a 7-day streak milestone (+1 Shield added to inventory)."

    desc = (
        f"**+{amt} {result['unit']}** logged to **{result['task_name']}**\n\n"
        f"`{bar}`  **{cur} / {tgt} {result['unit']}**\n\n"
        f"🎯 Discipline: **{result['task_points_total']} / {result['task_max_points']} pts** ({delta_str})\n"
        f"📊 Today Total: **{result['daily_points_total']} / {result['daily_points_max']} pts**"
        f"{promo_banner}"
    )

    embed = discord.Embed(
        title=f"✅ {result['task_name']}",
        description=desc,
        color=0x2ECC71
    )
    if result["is_target_reached"] and result["previous_total"] < result["target"]:
        embed.set_footer(text="⭐ Target completed for this discipline!")

    return embed


def build_set_embed(result: Dict[str, Any], amount: float, level_up_info: Optional[Dict[str, Any]] = None) -> discord.Embed:
    """Builds the confirmation embed after overriding/resetting reps."""
    cur = format_num(result["new_total"])
    tgt = format_num(result["target"])
    prev = format_num(result["previous_total"])

    bar = make_progress_bar(result["new_total"], result["target"], length=8)

    promo_banner = ""
    if level_up_info:
        promo_banner = (
            f"\n\n🎉 **RANK PROMOTION!**\n"
            f"You reached **Level {level_up_info['level']} — {level_up_info['badge']} {level_up_info['title']}**!\n"
        )
    if result.get("shield_awarded"):
        promo_banner += "\n\n🛡️ **STREAK SHIELD EARNED!** You hit a 7-day streak milestone (+1 Shield added to inventory)."

    desc = (
        f"**{result['task_name']}** adjusted: **{prev}** ➔ **{cur} {result['unit']}**\n\n"
        f"`{bar}`  **{cur} / {tgt} {result['unit']}**\n\n"
        f"🎯 Discipline: **{result['task_points_total']} / {result['task_max_points']} pts**\n"
        f"📊 Today Total: **{result['daily_points_total']} / {result['daily_points_max']} pts**"
        f"{promo_banner}"
    )

    embed = discord.Embed(
        title=f"🔄 Set: {result['task_name']}",
        description=desc,
        color=0x3498DB
    )
    if amount == 0:
        embed.set_footer(text="Discipline reset to 0.")

    return embed


def build_stats_embed(target_user: discord.Member, data: Dict[str, Any]) -> discord.Embed:
    """Builds the lifetime statistics card featuring rank title & badge."""
    streak = data.get('current_streak', 0)
    clean = data.get('perfect_days', 0)
    active = data.get('active_days', 0)
    pts = data.get('lifetime_points', 0)

    lvl = get_level_info(pts)

    volume_lines = []
    for t in data.get("task_totals", []):
        vol = format_num(t["total_volume"])
        volume_lines.append(f"• **{t['name']}**: {vol:,} {t['unit']}")

    desc = (
        f"**{target_user.display_name}** • {lvl['badge']} **Level {lvl['level']}: {lvl['title']}**\n\n"
        f"🔥 **Current Streak**: {streak} days\n"
        f"⭐ **Perfect Days**: {clean}\n"
        f"💎 **Total Points**: {pts:,} pts\n"
        f"📅 **Active Days**: {active}\n\n"
        "**Lifetime Volume**\n"
        + ("\n".join(volume_lines) if volume_lines else "_No sets logged yet._")
    )

    embed = discord.Embed(
        title="⚡ Winter Arc — Lifetime Stats",
        description=desc,
        color=lvl["color"]
    )
    embed.set_footer(text="Lifetime statistics across all disciplines • Updated live")
    return embed


def build_history_embed(user: discord.Member, hist: List[Dict[str, Any]]) -> discord.Embed:
    """Builds the point, completion, and grind history card with human-formatted dates."""
    from phases import is_recovery_day

    lines = []
    for d in reversed(hist):
        raw_date = d["date"]
        try:
            d_obj = date.fromisoformat(raw_date)
            date_display = d_obj.strftime("%a, %b %d")
        except Exception:
            date_display = raw_date

        if d.get("is_rest_day") or is_recovery_day(raw_date):
            lines.append(f"• **{date_display}** — 🌿 **Active Recovery Day** *(Streak Protected ❤️)*")
            continue

        pct = int(round(d["completion_rate"] * 100))
        star = " ⭐" if d["perfect_day"] else ""

        grind_note = ""
        g = d.get("grind_entry")
        if g and g.get("points_awarded", 0) > 0:
            tag = g.get("key_learning") or "Custom Grind"
            grind_note = f"\n  ↳ ⚔️ *+{g['points_awarded']} pts grind ({tag})*"

        lines.append(f"• **{date_display}** — **{d['points']} pts** ({pct}%){star}{grind_note}")

    days_label = f"{len(hist)}-Day " if hist else ""
    embed = discord.Embed(
        title=f"📜 Winter Arc — {days_label}History",
        description=f"**{user.display_name}**\n\n" + ("\n\n".join(lines) if lines else "_No history recorded yet._"),
        color=0x34495E
    )
    embed.set_footer(text="Past finalized days are locked • Rollover occurs at 00:00 IST")
    return embed


def build_profile_embed(
    user: discord.Member,
    user_record: Dict[str, Any],
    streak: int,
    stats_data: Dict[str, Any],
    all_time_rank: Optional[int] = None,
    total_warriors: Optional[int] = None,
    today_progress: Optional[Dict[str, Any]] = None,
) -> discord.Embed:
    """Builds the comprehensive Member Profile card with distinct All-Time Rank, Pack Level, Next Level progression, and separate Daily Progress."""
    raw_id = user_record.get("discord_id") or getattr(user, "id", 0)
    discord_id = raw_id if isinstance(raw_id, int) else 0

    if all_time_rank is None or total_warriors is None:
        if discord_id:
            try:
                all_time_rank, total_warriors = db.get_user_all_time_rank(discord_id)
            except Exception:
                all_time_rank, total_warriors = 1, 1
        else:
            all_time_rank, total_warriors = 1, 1

    if today_progress is None:
        if discord_id:
            try:
                today_str = datetime.now(BOT_TZ).strftime("%Y-%m-%d")
                today_progress = db.get_user_daily_progress(discord_id, today_str)
            except Exception:
                today_progress = {}
        else:
            today_progress = {}

    pts = stats_data.get("lifetime_points", 0)
    lvl = get_level_info(pts)

    # 1. Rank & Level
    rank_str = f"**#{all_time_rank}** of {total_warriors}" if all_time_rank > 0 else "Unranked"

    # 2. Next Level Progression Block
    tier_bar = make_progress_bar(lvl["points_in_tier"], lvl["tier_size"] if not lvl["is_apex"] else 1, length=10)
    if not lvl["is_apex"]:
        next_lvl_num = lvl["level"] + 1
        next_title = lvl["next_rank"]["title"] if lvl["next_rank"] else f"Level {next_lvl_num}"
        next_target = lvl.get("next_threshold") or (lvl["min_pts"] + lvl["tier_size"])
        progress_block = (
            f"**Level {lvl['level']}** ➔ **Level {next_lvl_num} ({next_title})**\n"
            f"`{tier_bar}` **{lvl['tier_pct']}%** • `{pts:,} / {next_target:,} PTS` *({lvl['pts_to_next']:,} pts remaining)*"
        )
    else:
        progress_block = (
            "👑 **MAX LEVEL ACHIEVED (APEX)**\n"
            f"`{tier_bar}` **100%** • Arc Conquered"
        )

    # 3. Separate Daily Progress Block
    today_pts = today_progress.get("total_points", 0)
    today_max = today_progress.get("max_possible_points", 500) or 500
    today_bar = make_progress_bar(today_pts, today_max, length=10)
    today_pct = int(round((today_pts / today_max) * 100)) if today_max > 0 else 0

    tasks = today_progress.get("tasks", [])
    completed_count = sum(1 for t in tasks if t.get("completed"))
    total_tasks = len(tasks)

    today_extras = []
    if total_tasks > 0:
        today_extras.append(f"{completed_count}/{total_tasks} disciplines")
    grind_pts = today_progress.get("grind_points", 0)
    if grind_pts > 0:
        today_extras.append(f"+{grind_pts} grind")

    detail_str = f" • *({', '.join(today_extras)})*" if today_extras else ""
    daily_block = (
        f"`{today_bar}` **{today_pts} / {today_max} pts** ({today_pct}%){detail_str}"
    )

    # 4. Enrolled Date & Days in Arc
    joined_date_str = user_record.get("joined_at", "")[:10]
    days_note = ""
    if joined_date_str:
        try:
            j_date = datetime.fromisoformat(joined_date_str).date()
            diff_days = (datetime.now(BOT_TZ).date() - j_date).days + 1
            days_note = f" *(Day {diff_days} in Arc)*"
        except Exception:
            pass

    # 5. Phase Context
    from phases import get_current_phase, get_phase_progress
    curr_phase = get_current_phase()
    phase_line = ""
    if curr_phase:
        p_prog = get_phase_progress(curr_phase)
        phase_line = f"{curr_phase['badge']} **Active Phase**: **{curr_phase['short_name']}: {curr_phase['name']}** *(Day {p_prog['day_num']}/{p_prog['total_days']} • {p_prog['days_remaining']}d left)*\n"

    desc = (
        f"**{user.display_name}**\n\n"
        f"🏆 **All-Time Rank**: {rank_str}\n"
        f"🎖️ **Discipline Rank**: **Level {lvl['level']} — {lvl['title']}** {lvl['badge']}\n"
        f"*{lvl['description']}*\n\n"
        f"📈 **Level Progression**\n"
        f"{progress_block}\n\n"
        f"🎯 **Today's Daily Progress**\n"
        f"{daily_block}\n\n"
        f"🔥 **Current Streak**: **{streak} days** • 🛡️ **Streak Shields**: **{user_record.get('frost_shields', 0)}/2**\n"
        f"💎 **Lifetime Points**: **{pts:,} pts**\n"
        f"{phase_line}"
        f"📅 **Enrolled**: `{joined_date_str}`{days_note}"
    )

    embed = discord.Embed(
        title="❄️ Winter Arc — Profile",
        description=desc,
        color=lvl["color"]
    )
    if user.avatar:
        embed.set_thumbnail(url=user.avatar.url)

    embed.set_footer(text="Winter Arc • Daily standard: 500 points")
    return embed


def build_ranks_embed(current_points: int) -> discord.Embed:
    """Builds the 12-level Winter Pack progression directory, highlighting user's rank."""
    user_lvl = get_level_info(current_points)
    ranks = get_all_ranks()

    lines = []
    for r in ranks:
        is_current = (r["level"] == user_lvl["level"])
        marker = "👉 " if is_current else "   "
        max_str = f"{r['max_pts']:,} pts" if r['max_pts'] is not None else "MAX"
        range_str = f"`{r['min_pts']:,} – {max_str}`"
        lines.append(f"{marker}{r['badge']} **Lvl {r['level']}: {r['title']}** — {range_str}")

    desc = (
        "**The 12-Level Progression Hierarchy**\n"
        "Earn lifetime points across the 90-day arc to advance your rank:\n\n"
        + "\n".join(lines)
        + f"\n\nYour Current Standing: {user_lvl['badge']} **Level {user_lvl['level']}: {user_lvl['title']}** ({user_lvl['lifetime_points']:,} pts)"
    )

    embed = discord.Embed(
        title="❄️ Winter Arc — 12-Tier Progression Hierarchy",
        description=desc,
        color=user_lvl["color"]
    )
    embed.set_footer(text="Apex reached at 12,000 pts (~133 pts/day)")
    return embed


def build_help_embed(category: str = "overview") -> discord.Embed:
    """Builds the comprehensive command manual and rules overview."""
    category = category.lower()

    if category == "logging":
        embed = discord.Embed(
            title="⚡ Workout & AI Logging Engine",
            description=(
                "Log your physical and mental discipline every single day.\n"
                "Use natural language, shorthand, or direct counts — all supported."
            ),
            color=0x3498DB
        )
        embed.add_field(
            name="🤖 `/quick [text]` — AI Workout Parser",
            value=(
                "Log workouts in plain English. AI extracts exercises, aggregates sets, and converts units automatically.\n\n"
                "> `/quick text: did 50 pushups, 25 pullups, and ran 3.5 km`\n"
                "> `/quick text: 40 squats, 30 situps then 20 more squats`\n\n"
                "🛡️ *Safeguard*: Unrealistic single-set volume (>50 reps / >10 km) is rejected automatically to preserve integrity."
            ),
            inline=False
        )
        embed.add_field(
            name="📝 Traditional Set Logging (`/log` & `/set`)",
            value=(
                "• `/log [task] [amount]` — Add reps or km to your current daily count\n"
                "• `/set [task] [amount]` — Override today's count directly\n\n"
                "💡 Use `/set 0` to wipe an accidental entry clean without needing admin help."
            ),
            inline=False
        )
        embed.add_field(
            name="⚔️ `/grind [text]` — Custom Workouts & Deep Work",
            value=(
                "Submit custom workouts or heavy cognitive deep work for up to **+50 bonus pts/day** (limit: 1 entry/day).\n\n"
                "✅ *Accepted*: gym sets, yoga, Surya Namaskars, DSA problems, technical study\n"
                "❌ *Excluded*: core 5 disciplines (pushups, squats, pullups, situps, running)\n\n"
                "> `/grind text: 15 Surya Namaskars, 3×12 bicep curls, solved 2 graph DP problems`"
            ),
            inline=False
        )
        embed.add_field(
            name="⚖️ `/accuse [target]` — Community Council Verification",
            value=(
                "Challenge a suspicious `/grind` claim.\n"
                "Triggers an Honor Code prompt, then a 10-minute public council vote in the channel.\n"
                "If the brotherhood rules guilty, the suspect's grind points for today are stripped."
            ),
            inline=False
        )
        embed.add_field(
            name="⚡ Reactive AI Coach & Bot Tips",
            value=(
                "After most commands, Amarok (the AI coach) reacts with sharp accountability.\n"
                "Commands that trigger coaching: `/today`, `/tasks`, `/log`, `/quick`, `/profile`, `/ranks`,\n"
                "`/leaderboard`, `/stats`, `/history`, `/recap`, `/streak`, `/shield status`, `/shield use`, `/grind`.\n\n"
                "Coaching strictly excludes `/set`. Bot usage tips also appear periodically on a 10-minute timer."
            ),
            inline=False
        )
        embed.set_footer(text="Use the dropdown below to navigate categories • Day resets at 00:00 IST")
        return embed

    elif category == "progress":
        embed = discord.Embed(
            title="📊 Progression, Ranks & Analytics",
            description="Track your daily execution, climb the 12 discipline tiers, and explore community benchmarks.",
            color=0x9B59B6
        )
        embed.add_field(
            name="🎯 Daily & Habit Tracking",
            value=(
                "• `/today [member]` — Live daily progress card with progress bars, points breakdown & streak status\n"
                "• `/tasks [member]` — Full discipline targets, units, muscle groups & live progress bars\n"
                "• `/history [days]` — Point breakdown and completion rates over the past 7, 14, or 30 days"
            ),
            inline=False
        )
        embed.add_field(
            name="📅 Streak & Calendar",
            value=(
                "• `/streak [member]` — Habit consistency dashboard with an interactive button to switch to calendar view\n"
                "• `/calendar [member]` — Full 3-phase campaign habit calendar (Oct 1 – Dec 31, 92 days)\n\n"
                "Status tags: 🟩 Active day (30+ pts) · ⭐ Perfect Day (100%) · 🛡️ Shield used · 🟥 Missed · ▫️ Upcoming"
            ),
            inline=False
        )
        embed.add_field(
            name="🎖️ Profile & 12-Tier Rank System",
            value=(
                "• `/profile [member]` — Complete profile: All-Time Standing, Discipline Tier badge & XP to next rank\n"
                "• `/ranks` — Full 12-tier discipline roadmap from **Initiate (Level 1, 0 pts)** to **Apex (Level 12, 12,000+ pts)**"
            ),
            inline=False
        )
        embed.add_field(
            name="🏆 Standings, Benchmarks & Analytics",
            value=(
                "• `/leaderboard` — Weekly, Monthly & All-Time top 10 with interactive buttons\n"
                "• `/stats [phase]` — **Server Records & Benchmarks**: server PRs, longest streaks, single-day peak maxers, most Perfect Days & community volume\n"
                "• `/recap [member]` — Interactive Phase Explorer with dynamic buttons for active phases & overall campaign training volume breakdown"
            ),
            inline=False
        )
        embed.set_footer(text="Daily goal: 500 points (Perfect Day) • Apex tier unlocks at 12,000 points")
        return embed

    elif category == "shields":
        embed = discord.Embed(
            title="🛡️ Streak Shield & Recovery System",
            description=(
                "The Winter Arc demands relentless discipline, but intentional recovery prevents burnout.\n"
                "Streak Shields and Active Recovery Days protect your unbroken streak automatically."
            ),
            color=0x00D2FF
        )
        embed.add_field(
            name="❄️ How Streak Shields Work",
            value=(
                f"• **Streak Threshold**: Earn at least **{MIN_STREAK_POINTS} points** per day to maintain your streak\n"
                "• **Earning Shields**: +1 Shield earned at every **7-day streak milestone** (max 2 shields)\n"
                "• **Auto-Protection**: If you miss a day (< 30 pts), a shield is used automatically at midnight (00:00 IST)\n"
                "• **Safety Rule**: A streak breaks only if you miss on a normal day with zero shields remaining"
            ),
            inline=False
        )
        embed.add_field(
            name="❤️ Active Recovery Days (Sundays)",
            value=(
                "Every Sunday is an **Active Recovery Day** with a **0 pt daily requirement**.\n"
                "Your streak is preserved automatically — no shields burned.\n\n"
                "Rest, stretch, reflect. Rebuild your energy for the week ahead."
            ),
            inline=False
        )
        embed.add_field(
            name="🎮 Shield Commands",
            value=(
                "• `/shield status` — View your shield count (e.g. `1/2`), auto-protection status & countdown to next shield\n"
                "• `/shield use` — Learn how automated streak protection keeps your streak alive without manual intervention"
            ),
            inline=False
        )
        embed.set_footer(text="Max 2 shields stored • 1 shield awarded every 7-day streak milestone • Sundays auto-protected")
        return embed

    elif category == "todo":
        embed = discord.Embed(
            title="📋 Todo & Smart Reminders Addon",
            description=(
                "Personal and team task management with intelligent natural language reminders.\n"
                "Completely isolated in `todo.db` with a clean, distraction-free interface."
            ),
            color=0x3498DB
        )
        embed.add_field(
            name="➕ `/todo add [task] [when] [remind_me]`",
            value=(
                "Create a task with flexible scheduling and natural language reminders:\n\n"
                "> `remind_me:tomorrow 6pm`\n"
                "> `remind_me:every 2 hours`\n"
                "> `remind_me:every hour after 6 PM`\n"
                "> `remind_me:3 times a day` (09:00, 14:00, 20:00)\n\n"
                "Set `dm:True` (default) for private DMs or `False` for the current channel."
            ),
            inline=False
        )
        embed.add_field(
            name="📜 `/todo list [filter]` — Paginated Task View",
            value=(
                "View tasks with 15 items per page and `◀️ Prev` / `▶️ Next` pagination.\n"
                "Toggle between **Active Tasks** and **Trash Archive** (`T1, T2...`).\n"
                "Inline select menus to Mark Done, Silence, or Restore tasks directly from the list."
            ),
            inline=False
        )
        embed.add_field(
            name="⚡ Quick Actions",
            value=(
                "• `/todo done [id]` — Mark complete (moved to 7-day trash archive)\n"
                "• `/todo silence [id]` — Disable reminders while keeping the task active\n"
                "• `/todo delete [id]` — Move to trash archive\n"
                "• `/todo restore [id]` — Restore from trash (e.g. `T1` or `1`)\n"
                "• `/todo edit [id]` — Update description or remove reminders\n"
                "• `/todo clear [which]` — Wipe `active`, `trash`, or `all` tasks"
            ),
            inline=False
        )
        embed.add_field(
            name="🤝 `/todo assign [member] [task]` — Team Delegation",
            value=(
                "Assign a task to a server peer.\n"
                "They get a channel ping + private DM with `[ ✅ Accept Task ]` and `[ ❌ Decline ]` buttons.\n"
                "Upon acceptance, the task enters their active queue."
            ),
            inline=False
        )
        embed.add_field(
            name="🌙 `/todo dnd [start_time] [end_time]` — Quiet Hours",
            value=(
                "Configure Do Not Disturb hours (e.g. `22:00` to `06:00`).\n"
                "Reminders triggered during quiet hours are quietly postponed by 30 minutes — not lost."
            ),
            inline=False
        )
        embed.add_field(
            name="🕵🏻 `/todo incognito [mode]` — Privacy Mode",
            value=(
                "• **OFF (Public)** *(Default)*: Todo actions are posted publicly in the channel\n"
                "• **ON (Private)**: Personal actions are visible only to you (ephemeral)\n"
                "• Shared actions (`/todo add`, `/todo assign`) remain public regardless of mode"
            ),
            inline=False
        )
        embed.set_footer(text="Todo Addon • Fully isolated in todo.db • 7-day trash auto-pruning")
        return embed

    elif category == "settings":
        embed = discord.Embed(
            title="⚙️ Settings & Utilities",
            description="Manage your personal reminder alerts, notifications, and challenge lifecycle.",
            color=0x2ECC71
        )
        embed.add_field(
            name="🔔 `/reminders` & `/settings` — Personal DM Notifications",
            value=(
                "Toggle your automated daily DMs with interactive 1-click buttons:\n\n"
                "🌅 **05:00 IST** — Morning Kickoff: daily targets, motivation & clean slate\n"
                "☀️ **16:30 IST** — Afternoon Check-in: mid-day pulse & active standings\n"
                "⚠️ **21:00 IST** — Evening Streak Warning: fires only if you're below 30 pts\n\n"
                "💡 All three are ON by default. Ensure Discord allows DMs from server members."
            ),
            inline=False
        )
        embed.add_field(
            name="⚔️ Enrollment & Utilities",
            value=(
                "• `/enroll` — Join the Winter Arc and establish your warrior profile\n"
                "• `/leave_arc` — Unenroll from active rosters (lifetime stats & points preserved)\n"
                "• `/tips [on|off]` — Toggle periodic bot usage tips\n"
                "• `/ping` — Check bot latency, gateway response & timezone sync"
            ),
            inline=False
        )
        embed.set_footer(text="Automated broadcasts run on Asia/Kolkata (IST) time.")
        return embed

    elif category == "admin":
        embed = discord.Embed(
            title="👑 Server Administration & Maintenance",
            description="Server controls for administrators to configure channels, roles, disciplines, backups, and system health.",
            color=0xE67E22
        )
        embed.add_field(
            name="📢 Broadcast Configuration",
            value=(
                "• `/admin set_channel [channel]` — Set the channel for automated 05:00, 16:30, 21:00 & 00:00 broadcasts\n"
                "• `/admin set_role [role]` — Set the role to mention during scheduled announcements\n"
                "• `/admin overview` — View server channel, role ping, active disciplines & enrolled roster"
            ),
            inline=False
        )
        embed.add_field(
            name="🏋️ Discipline Management",
            value=(
                "• `/admin tasks_list` — List all disciplines in the database\n"
                "• `/admin task_add` — Add a new discipline with custom targets, units & point limits\n"
                "• `/admin task_toggle` — Enable or disable an existing discipline\n"
                "• `/admin grind [what] [member]` — Block or unlock a member's `/grind` access"
            ),
            inline=False
        )
        embed.add_field(
            name="🖥️ System Diagnostics & Maintenance",
            value=(
                "• `/admin backup` — Create a WAL-safe SQLite backup and download as `.db` file\n"
                "• `/admin sync [guild_only] [clean]` — Synchronize slash commands globally or guild-specific\n"
                "• `/admin health` — Live RAM monitor, SQLite sizes, uptime & **🧹 Collect GC & Free RAM** button\n"
                "• `/admin dm [member] [message]` — Send administrative DMs to enrolled members\n"
                "• `/admin finalize_day` — Manually trigger midnight point locks & streak rolls\n"
                "• `/test_reminder [type]` — Preview morning, afternoon, evening, midnight, or DM briefings\n"
                "• `/nuke` — Emergency factory reset with double confirmation modal"
            ),
            inline=False
        )
        embed.set_footer(text="Admin commands require Administrator permissions.")
        return embed

    else:
        # Default Overview
        embed = discord.Embed(
            title="❄️ Winter Arc — Master Command Manual",
            description=(
                "**Welcome to the Winter Arc (Oct 1 – Jan 31).**\n"
                "A 4-phase challenge of daily physical and mental discipline.\n\n"
                "🚀 **New here?** `/enroll` → log with `/quick` → check progress with `/today`\n\n"
                "Daily Standard: **500 points (Perfect Day)** · **30 pts/day minimum** to keep your streak alive.\n"
                "Use the dropdown below to deep-dive into each system."
            ),
            color=0x2B2D31
        )
        embed.add_field(
            name="🎯 Daily Disciplines (500 pts max)",
            value=(
                "• 💪 **Push-ups**: 100 reps *(1 pt / rep)*\n"
                "• 🧗 **Pull-ups**: 100 reps *(1 pt / rep)*\n"
                "• 🦵 **Squats**:   100 reps *(1 pt / rep)*\n"
                "• 🧘 **Sit-ups**:  100 reps *(1 pt / rep)*\n"
                "• 🏃 **Running**:  10 km *(10 pts / km)*\n\n"
                "• ⚔️ **Grind Bonus**: up to +50 pts/day via `/grind`"
            ),
            inline=False
        )
        embed.add_field(
            name="❄️ The 4 Official Arc Phases",
            value=(
                "• ❄️ **Phase 1: FIRST FROST** (Oct 1 – Oct 31) — Baseline habits & routine shock\n"
                "• 🐺 **Phase 2: THE HUNT** (Nov 1 – Nov 30) — Deep mid-arc grind when novelty fades\n"
                "• ⚔️ **Phase 3: THE ENDGAME** (Dec 1 – Dec 31) — Peak winter discipline & final push\n"
                "• 🌅 **Phase 4: AFTERMATH** (Jan 1 – Jan 31) — Wind-down, identity integration & lifestyle"
            ),
            inline=False
        )
        embed.add_field(
            name="⏰ Automated Daily Schedule (Asia/Kolkata)",
            value=(
                "• 🌅 `05:00 IST` — Morning Kickoff & Discipline Targets\n"
                "• ☀️ `16:30 IST` — Mid-day Check-in & Roster Standings\n"
                "• ⚠️ `21:00 IST` — Evening Streak Warning (Save Your Streak)\n"
                "• 🌑 `00:00 IST` — Midnight Reckoning & Final Day Tally\n"
                "• 🏆 `Sunday 10:00` — Winter Arc Weekly Recap & Volume Podium"
            ),
            inline=False
        )
        embed.add_field(
            name="⚡ Command Directory Cheat Sheet",
            value=(
                "**Logging** · `/quick` · `/log` · `/set` · `/grind`\n"
                "**Progress** · `/today` · `/tasks` · `/streak` · `/calendar` · `/profile` · `/ranks`\n"
                "**Standings** · `/leaderboard` · `/stats` · `/history` · `/recap`\n"
                "**Recovery** · `/shield status` · `/shield use`\n"
                "**Todo** · `/todo add` · `/todo list` · `/todo done` · `/todo assign` · `/todo dnd`\n"
                "**Settings** · `/settings` · `/enroll` · `/leave_arc` · `/ping`\n"
                "**Admin** · `/admin backup` · `/admin sync` · `/admin health` · `/test_reminder`"
            ),
            inline=False
        )
        embed.set_footer(text="Select a category from the dropdown menu below for complete details")
        return embed

def build_morning_kickoff_message(
    active_tasks: List[Dict[str, Any]],
    date_display: str,
    curr_phase: Optional[Dict[str, Any]] = None,
    phase_progress: Optional[Dict[str, Any]] = None,
    quote: Optional[str] = None,
    role_ping: str = "",
    is_recovery: Optional[bool] = None,
) -> str:
    """Builds native Discord broadcast for the 07:00 IST morning kickoff."""
    clean_ping = role_ping.strip()
    prefix = f"{clean_ping} " if clean_ping else ""

    if curr_phase and phase_progress:
        phase_header = f"Day {phase_progress['day_num']} of {curr_phase['name']} ({curr_phase['short_name']}) 🌅"
    else:
        phase_header = f"{date_display} 🌅"

    today_recovery = is_recovery if is_recovery is not None else is_recovery_day(date_display)
    if today_recovery:
        import random
        rest_emoji = random.choice(["🌱", "🌿", "🍃", "🪴", "🧘"])
        ping_part = f"{prefix}[WinterArc]\n\n" if prefix else ""
        header = f"{ping_part}**Today is Rest Day {rest_emoji}**"
        body = (
            "The pack is on active recovery today. Movement is medicine — don't stay idle; "
            "go for a light walk, stretch out tight joints, hydrate with plenty of water, and fuel your body with nutritious food. "
            "Your streak is completely safe today. Rebuild your energy."
        )
        quote_text = sanitize_display_text(quote, random.choice(AUTHENTIC_REST_QUOTES)).strip()
        quote_section = quote_text if quote_text.startswith(">") else f"> {quote_text}"
        subtext = "-# Active Recovery Day (ARD) ❤️ • Streaks protected • Move Lightly"
        return f"{header}\n\n{body}\n\n{quote_section}\n\n{subtext}"

    header = (
        f"{prefix}[WinterArc] {phase_header}\n"
        "A new day is on the board. 500 points available across today's disciplines."
    )

    task_lines = []
    for t in active_tasks:
        tgt = format_num(t["target"])
        task_lines.append(f"• **{t['name']}**: `{tgt} {t['unit']}` *({t.get('max_points', 100)} pts)*")
    tasks_section = "\n".join(task_lines) if task_lines else "_No active disciplines configured._"

    default_morning_q = '"When you arise in the morning think of what a privilege it is to be alive: to think, to enjoy, to love." — Marcus Aurelius'
    quote_text = sanitize_display_text(quote, default_morning_q).strip()
    quote_section = quote_text if quote_text.startswith(">") else f"> {quote_text}"

    subtext = "-# Log with /log or /quick • Deep work with /grind • Rollover at midnight"

    return f"{header}\n\n{tasks_section}\n\n{quote_section}\n\n{subtext}"


def build_afternoon_checkin_message(
    enrolled_users: List[Dict[str, Any]],
    today_str: str,
    quote: Optional[str] = None,
    role_ping: str = ""
) -> str:
    """Builds native Discord broadcast for the 16:30 IST afternoon check-in."""
    clean_ping = role_ping.strip()
    prefix = f"{clean_ping} " if clean_ping else ""

    today_recovery = is_recovery_day(today_str)
    if today_recovery:
        default_body = (
            "Midday check-in, warriors. Put your phone down for 10 minutes: drink a tall glass of water, "
            "get a clean meal in, step outside for a 15-minute mobility walk, and loosen up your back and hips. "
            "Keep the blood moving lightly today."
        )
        body = sanitize_display_text(quote, default_body).strip()
        header = f"**Winter Arc — Midday Pulse 🌿**\n\n{body}"
        subtext = "-# Active Recovery Day (ARD) ❤️ • Streaks protected • Stay hydrated & mobile"
        return f"{header}\n\n{subtext}"

    header = (
        f"{prefix}[WinterArc] Afternoon Check-in ⏳\n"
        "Halfway through the day. Check your numbers and get your remaining sets logged before tonight."
    )

    member_lines = []
    sorted_users = []
    for u in enrolled_users:
        prog = db.get_user_daily_progress(u["discord_id"], today_str)
        sorted_users.append({
            "discord_id": u["discord_id"],
            "username": u.get("username", "Member"),
            "points": prog["total_points"],
            "max_points": prog["max_possible_points"],
            "pct": int(round(prog["overall_completion_rate"] * 100)),
            "perfect_day": prog["perfect_day"],
        })
    sorted_users.sort(key=lambda x: (x["points"], x["pct"]), reverse=True)

    for m in sorted_users:
        star = " ⭐" if m["perfect_day"] else ""
        member_lines.append(f"- **{m['username']}** — **{m['points']} / {m['max_points']} pts** ({m['pct']}%){star}")

    members_section = "\n".join(member_lines) if member_lines else "- _No enrolled members yet._"

    default_q = '"Active recovery builds the foundation for tomorrow\'s strength." — Amarok' if today_recovery else '"First say to yourself what you would be; and then do what you have to do." — Epictetus'
    quote_text = sanitize_display_text(quote, default_q).strip()
    quote_section = quote_text if quote_text.startswith(">") else f"> {quote_text}"

    subtext = "-# Active Recovery Day (ARD) ❤️ • Streaks protected • Rollover at midnight" if today_recovery else "-# Log with /log • 30 pts/day minimum for streak • Rollover at midnight"

    return f"{header}\n\n{members_section}\n\n{quote_section}\n\n{subtext}"


def build_morning_kickoff_embed(active_tasks: List[Dict[str, Any]], date_display: str, quote: Optional[str] = None) -> discord.Embed:
    """Builds the 05:00 morning kickoff broadcast embed with active phase context."""
    from phases import get_current_phase, get_phase_progress
    curr_phase = get_current_phase()
    today_recovery = is_recovery_day(date_display)

    if today_recovery:
        import random
        rest_emoji = random.choice(["🌱", "🌿", "🍃", "🪴", "🧘"])
        embed = discord.Embed(
            title=f"Today is Rest Day {rest_emoji}",
            color=0x27AE60
        )
        body = (
            "The pack is on active recovery today. Movement is medicine — don't stay idle; "
            "go for a light walk, stretch out tight joints, hydrate with plenty of water, and fuel your body with nutritious food. "
            "Your streak is completely safe today. Rebuild your energy."
        )
        quote_text = sanitize_display_text(quote, random.choice(AUTHENTIC_REST_QUOTES)).strip()
        quote_section = quote_text if quote_text.startswith(">") else f"> {quote_text}"
        embed.description = f"{body}\n\n{quote_section}"
        embed.set_footer(text="Active Recovery Day (ARD) ❤️ • Streaks protected • Move Lightly")
        return embed

    embed_color = curr_phase["color"] if curr_phase else 0x2980B9

    embed = discord.Embed(
        title="🌅 Winter Arc — Daily Kickoff",
        color=embed_color
    )

    desc_lines = [
        f"📅 **{date_display}**",
        "A new day is on the board. **500 points** available across today's disciplines.",
    ]
    if curr_phase:
        prog = get_phase_progress(curr_phase)
        desc_lines.append(f"{curr_phase['badge']} **{curr_phase['name']}** — Day {prog['day_num']} of {prog['total_days']} ({prog['days_remaining']} days left in phase)")

    clean_quote = sanitize_display_text(quote, "")
    if clean_quote:
        clean_quote = clean_quote.lstrip(">").strip()
        desc_lines.append(f"\n> {clean_quote}")

    embed.description = "\n".join(desc_lines)

    task_lines = []
    for t in active_tasks:
        target_display = format_num(t["target"])
        task_lines.append(f"• **{t['name']}**: `{target_display} {t['unit']}` *(max {t.get('max_points', 100)} pts)*")

    embed.add_field(
        name="🎯 Today's Disciplines",
        value="\n".join(task_lines) if task_lines else "No active disciplines configured.",
        inline=False
    )

    embed.set_footer(text="Winter Arc • Log early with /log or /quick • Day resets at 00:00 IST")
    return embed


def build_afternoon_checkin_embed(enrolled_users: List[Dict[str, Any]], today_str: str, quote: Optional[str] = None) -> discord.Embed:
    """Builds the 16:30 afternoon check-in broadcast embed."""
    today_recovery = is_recovery_day(today_str)
    if today_recovery:
        default_desc = (
            "Midday check-in, warriors. Put your phone down for 10 minutes: drink a tall glass of water, "
            "get a clean meal in, step outside for a 15-minute mobility walk, and loosen up your back and hips. "
            "Keep the blood moving lightly today."
        )
        desc = sanitize_display_text(quote, default_desc).strip()
        embed = discord.Embed(
            title="Winter Arc — Midday Pulse 🌿",
            description=desc,
            color=0x27AE60
        )
        embed.set_footer(text="Active Recovery Day (ARD) ❤️ • Streaks protected • Stay hydrated & mobile")
        return embed

    embed = discord.Embed(
        title="⏳ Winter Arc — Afternoon Check-in",
        color=0xD35400
    )

    desc_lines = [
        "Halfway through the day. Check your numbers and get your remaining sets logged before tonight.",
    ]
    clean_quote = sanitize_display_text(quote, "")
    if clean_quote:
        clean_quote = clean_quote.lstrip(">").strip()
        desc_lines.append(f"\n> {clean_quote}")
    embed.description = "\n".join(desc_lines)

    member_lines = []
    sorted_users = []
    for u in enrolled_users:
        prog = db.get_user_daily_progress(u["discord_id"], today_str)
        sorted_users.append({
            "discord_id": u["discord_id"],
            "username": u.get("username", "Member"),
            "points": prog["total_points"],
            "max_points": prog["max_possible_points"],
            "pct": int(round(prog["overall_completion_rate"] * 100)),
            "perfect_day": prog["perfect_day"],
        })
    sorted_users.sort(key=lambda x: (x["points"], x["pct"]), reverse=True)

    for m in sorted_users:
        star = " ⭐" if m["perfect_day"] else ""
        if m["points"] > 0:
            member_lines.append(f"• **{m['username']}** — **{m['points']} / {m['max_points']} pts** ({m['pct']}%){star}")
        else:
            member_lines.append(f"• **{m['username']}** — **0 / {m['max_points']} pts**")

    embed.add_field(
        name="📊 Pack Progress So Far",
        value="\n".join(member_lines) if member_lines else "No enrolled members yet.",
        inline=False
    )

    embed.set_footer(text="Winter Arc • 30 pts/day minimum for streak • Finalizes at 00:00 IST")
    return embed


def build_evening_checkin_message(
    warriors_data: List[Dict[str, Any]],
    callouts: Optional[Dict[int, str]] = None,
    stoic_quote: Optional[str] = None,
    role_ping: str = "",
    is_recovery: Optional[bool] = None,
) -> str:
    """
    Builds the native Discord text broadcast for the 21:00 IST evening streak alert (3h before midnight).
    Formatted with raw pings, per-warrior accountability callouts, authentic stoic quote, and subtext.
    """
    clean_ping = role_ping.strip()
    header_ping = f"{clean_ping} " if clean_ping else ""

    today_recovery = is_recovery if is_recovery is not None else is_recovery_day()
    if today_recovery:
        default_body = (
            "Active Recovery Day is winding down. The pack observed recovery today and all streaks remain locked in and protected.\n\n"
            "Shut off screens, wind down early, and get 8 hours of deep restorative sleep. "
            "Tomorrow the hunt resumes at 100% intensity — be ready to give it your absolute all."
        )
        body = sanitize_display_text(stoic_quote, default_body).strip()
        header = f"**Winter Arc — Evening Wind-Down 🌙**\n\n{body}"
        subtext = "-# Active Recovery Day (ARD) ❤️ • Rest well • Tomorrow we hunt"
        return f"{header}\n\n{subtext}"

    header = (
        f"{header_ping}[WinterArc] 3 hours left until midnight rollover. ⏳\n"
        "If you haven't hit your 30 points yet, get your reps or run logged before midnight to keep your streak alive."
    )

    if not warriors_data:
        warriors_section = "- No enrolled warriors yet."
    else:
        sorted_warriors = sorted(
            warriors_data,
            key=lambda w: (w.get("points", 0), w.get("streak", 0))
        )
        lines = []
        for w in sorted_warriors:
            d_id = int(w["discord_id"])
            pts = w.get("points", 0)
            username = w.get("username", "Warrior")
            raw_c = (callouts or {}).get(d_id)
            callout = sanitize_display_text(raw_c, "").strip()
            if not callout:
                if pts == 0:
                    callout = "0 pts on the board. Stop scrolling, drop and get your 30 push-ups in before your streak breaks tonight."
                elif pts < 30:
                    needed = 30 - pts
                    callout = f"{pts} pts on the board. You need {needed} more points before midnight to save your streak."
                elif pts >= 500:
                    callout = f"{pts} pts, completely maxed out the board early. Rest up for tomorrow."
                else:
                    callout = f"{pts} pts, streak is safe! Solid execution, but see if you can squeeze in another set before midnight."
            
            lines.append(f"- **{username}** — {callout}")
        warriors_section = "\n".join(lines)

    default_eve_q = '"Waste no more time arguing what a good man should be. Be one." — Marcus Aurelius'
    quote = sanitize_display_text(stoic_quote, default_eve_q).strip()
    if quote.startswith(">"):
        quote_section = quote
    else:
        quote_section = f"> {quote}"

    subtext = "-# Log with /log • 30 pts/day minimum for streak • Rollover at midnight"

    return f"{header}\n\n{warriors_section}\n\n{quote_section}\n\n{subtext}"


def build_evening_checkin_embed(
    enrolled_users: List[Dict[str, Any]],
    today_str: str,
    quote: Optional[str] = None,
    callouts: Optional[Dict[int, str]] = None,
) -> discord.Embed:
    """Builds the 21:00 IST evening streak alert channel broadcast embed (3 hours before midnight)."""
    today_recovery = is_recovery_day(today_str)
    if today_recovery:
        default_desc = (
            "Active Recovery Day is winding down. The pack observed recovery today and all streaks remain locked in and protected.\n\n"
            "Shut off screens, wind down early, and get 8 hours of deep restorative sleep. "
            "Tomorrow the hunt resumes at 100% intensity — be ready to give it your absolute all."
        )
        desc = sanitize_display_text(quote, default_desc).strip()
        embed = discord.Embed(
            title="Winter Arc — Evening Wind-Down 🌙",
            description=desc,
            color=0x27AE60
        )
        embed.set_footer(text="Active Recovery Day (ARD) ❤️ • Rest well • Tomorrow we hunt")
        return embed

    secured_lines = []
    at_risk_lines = []

    for u in enrolled_users:
        prog = db.get_user_daily_progress(u["discord_id"], today_str)
        pts = prog["total_points"]
        max_pts = prog["max_possible_points"]
        streak = db.calculate_streak(u["discord_id"], today_str)
        username = u.get("username", "Warrior")

        if prog["perfect_day"]:
            secured_lines.append(f"• **{username}** — **{pts} / {max_pts} pts** (⭐ 100% Perfect Day • {streak}d streak)")
        elif pts >= MIN_STREAK_POINTS:
            secured_lines.append(f"• **{username}** — **{pts} / {max_pts} pts** (Streak Secured ✅ • {streak}d streak)")
        else:
            needed = MIN_STREAK_POINTS - pts
            raw_c = (callouts or {}).get(u["discord_id"])
            callout = sanitize_display_text(raw_c, "").strip()
            extra = f" — {callout}" if callout else f" — {needed} pts needed before midnight"
            at_risk_lines.append(f"• <@{u['discord_id']}> — **{pts} / {max_pts} pts**{extra}")

    desc = (
        "⏳ **3 Hours Remaining Until Midnight Rollover!**\n"
        f"Scores lock in at 00:00 IST. Earn at least **{MIN_STREAK_POINTS} pts** to defend your streak.\n\n"
    )
    if at_risk_lines:
        desc += "**⚠️ Streak at Risk (< 30 pts)**\n" + "\n".join(at_risk_lines) + "\n\n"
    if secured_lines:
        desc += "**🔥 Streak Secured**\n" + "\n".join(secured_lines) + "\n\n"
    color = 0xC0392B
    footer_text = f"Log with /log • {MIN_STREAK_POINTS} pts/day minimum for streak • Rollover at 00:00 IST"

    if not at_risk_lines and not secured_lines:
        desc += "No enrolled warriors yet.\n\n"

    clean_quote = sanitize_display_text(quote, "")
    if clean_quote:
        clean_quote = clean_quote.lstrip(">").strip()
        desc += f"> {clean_quote}\n\n"

    embed = discord.Embed(
        title="🌙 Winter Arc — Active Recovery Wind-down" if today_recovery else "🌙 Winter Arc — Evening Streak Alert",
        description=desc.strip(),
        color=color
    )
    embed.set_footer(text=footer_text)
    return embed


def build_midnight_finalization_message(
    date_str: str,
    leaderboard: List[Dict[str, Any]],
    ai_recap: Optional[str] = None,
    role_ping: str = ""
) -> str:
    """Builds native Discord broadcast for 00:00 midnight daily finalization."""
    try:
        d_obj = date.fromisoformat(date_str)
        title_date = d_obj.strftime("%A, %B %d")
    except Exception:
        title_date = date_str

    clean_ping = role_ping.strip()
    prefix = f"{clean_ping} " if clean_ping else ""

    header = (
        f"{prefix}[WinterArc] Day Finalized • {title_date} 🌙\n"
        "Scores are locked in for the day."
    )

    recap_section = ""
    clean_recap = sanitize_display_text(ai_recap, "").strip()
    if clean_recap:
        clean_recap = clean_recap.lstrip(">").strip()
        recap_section = f"> {clean_recap}"

    podium_lines = []
    perfect_count = 0
    for idx, entry in enumerate(leaderboard):
        pts = entry["points"]
        rank_badge = ["🥇", "🥈", "🥉"][idx] if idx < 3 else f"{idx+1}."
        perfect_star = " ⭐" if entry["perfect_day"] else ""
        if entry["perfect_day"]:
            perfect_count += 1
        pct = int(round(entry.get("completion_rate", 0) * 100))
        username = entry.get("username", "Warrior")
        podium_lines.append(f"{rank_badge} **{username}** — **{pts} pts** ({pct}%){perfect_star}")

    board_section = "\n".join(podium_lines) if podium_lines else "No activity logged for this day."
    clean_sweeps = f"\n\n🔥 **Perfect Days**: **{perfect_count}** member(s) hit 100%." if perfect_count > 0 else ""

    subtext = "-# Fresh slate is open • Check your board with /today • Rollover at midnight"

    sections = [header]
    if recap_section:
        sections.append(recap_section)
    sections.append(board_section + clean_sweeps)
    sections.append(subtext)

    return "\n\n".join(sections)


def build_podium_embed(
    date_str: str,
    leaderboard: List[Dict[str, Any]],
    ai_recap: Optional[str] = None,
    alerts: Optional[List[str]] = None,
) -> discord.Embed:
    """Builds the 00:00 midnight daily finalization embed with stylized visual hierarchy."""
    try:
        d_obj = date.fromisoformat(date_str)
        title_date = d_obj.strftime("%A, %B %d, %Y")
    except Exception:
        title_date = date_str

    from phases import get_current_phase
    curr_phase = get_current_phase()
    embed_color = curr_phase["color"] if curr_phase else 0x6C5CE7

    embed = discord.Embed(
        title="🌙 Winter Arc — Daily Finalization",
        color=embed_color,
    )

    desc_lines = [
        f"📅 **{title_date}**",
        "Scores are locked for the day. Final standings have been archived.",
    ]
    if curr_phase:
        desc_lines.append(f"{curr_phase['badge']} **{curr_phase['name']}**")

    clean_recap = sanitize_display_text(ai_recap, "").strip()
    if clean_recap:
        clean_recap = clean_recap.lstrip(">").strip()
        desc_lines.append(f"\n> {clean_recap}")

    embed.description = "\n".join(desc_lines)

    podium_lines = []
    perfect_count = 0
    for idx, entry in enumerate(leaderboard):
        pts = entry.get("points", 0)
        badge = ["🥇", "🥈", "🥉"][idx] if idx < 3 else f"{idx+1}."
        star = " ⭐" if entry.get("perfect_day") else ""
        if entry.get("perfect_day"):
            perfect_count += 1
        pct = int(round(entry.get("completion_rate", 0) * 100))
        username = entry.get("username", "Warrior")
        if pts > 0:
            podium_lines.append(f"{badge} **{username}** — **{pts} pts** ({pct}%){star}")
        else:
            podium_lines.append(f"{badge} **{username}** — **0 pts**")

    if not podium_lines:
        podium_lines.append("No disciplines logged for this day.")

    standings_text = "\n".join(podium_lines)
    if perfect_count > 0:
        standings_text += f"\n\n⭐ **Perfect Days**: **{perfect_count}** warrior(s) completed 100%."

    embed.add_field(
        name="🏆 Final Standings",
        value=standings_text,
        inline=False
    )

    if alerts:
        clean_alerts = [a.strip() for a in alerts if a and a.strip()]
        if clean_alerts:
            embed.add_field(
                name="🛡️ Streak Updates",
                value="\n".join(clean_alerts[:10]),
                inline=False
            )

    embed.set_footer(text="Winter Arc • Fresh slate is open • Rollover at 00:00 IST")
    return embed


def build_shield_status_embed(user: discord.Member, status: Dict[str, Any]) -> discord.Embed:
    """Builds the Frost Shield inventory, protection status, and earning progress embed."""
    shields = status["frost_shields"]
    max_shields = status.get("max_shields", 2)
    shield_icons = "🛡️ " * shields + "⚪ " * (max_shields - shields)
    shield_icons = shield_icons.strip()

    if status.get("is_today_shielded"):
        safety_status = "🛡️ **Protected Today** (Shield deployed for today)"
    elif shields > 0:
        safety_status = f"🟢 **Safety Net Active** ({shields} shield{'s' if shields > 1 else ''} ready if today is missed)"
    else:
        safety_status = "🔴 **At Risk** (0 shields left — streak breaks if 30 pts not logged)"

    next_tag = f"**{status['days_until_next_shield']} day(s)** of streak until next shield" if shields < max_shields else "💎 **MAX SHIELDS STORED (2/2)**"

    history_lines = []
    for h in status.get("recent_uses", []):
        history_lines.append(f"• `{h['date']}` — {h['reason']}")

    desc = (
        f"**{user.display_name}** • Streak Protection System\n\n"
        f"**Shield Inventory**: {shield_icons} `({shields}/{max_shields})`\n"
        f"**Safety Status**: {safety_status}\n"
        f"🔥 **Current Streak**: **{status['current_streak']} days**\n"
        f"⏳ **Next Unlock**: {next_tag}\n\n"
        "**How Streak Shields Work**\n"
        "• **Earn**: +1 Shield earned for every **7 consecutive streak days** *(cap 2)*.\n"
        "• **Automatic Midnight Usage**: If you miss a day (< 30 pts), an available shield is automatically used at **00:00 IST**.\n"
        "• **Never Lose Unnecessarily**: A day is missed only if you run out of Streak Shields!"
    )

    if history_lines:
        desc += "\n\n**Recent Auto-Protection Logs**\n" + "\n".join(history_lines)

    embed = discord.Embed(
        title="🛡️ Winter Arc — Streak Shield Status",
        description=desc,
        color=0x00D2FF
    )
    embed.set_footer(text="Max 2 shields stored • 1 shield awarded every 7-day streak")
    return embed


def build_shield_automated_info_embed(user: discord.Member, status: Dict[str, Any]) -> discord.Embed:
    """Informs the user that shields are 100% automated and auto-deploy at midnight."""
    shields = status["frost_shields"]
    max_shields = status.get("max_shields", 2)
    shield_icons = "🛡️ " * shields + "⚪ " * (max_shields - shields)
    shield_icons = shield_icons.strip()

    if shields > 0:
        headline = f"🟢 **Safety Net Active!** You have **{shields} Streak Shield{'s' if shields > 1 else ''}** ready."
        action_note = (
            "You do **not** need to manually activate a shield!\n"
            "If you miss your daily 30 points today, an available shield will be **automatically consumed at midnight (00:00 IST)** to protect your streak."
        )
    else:
        headline = "🔴 **0 Streak Shields Available**"
        action_note = (
            "You currently have no shields stored in your inventory.\n"
            "Log at least **30 points** today before midnight (00:00 IST) to keep your streak alive!\n"
            "Reaching your next 7-day streak milestone will award a new shield."
        )

    embed = discord.Embed(
        title="🛡️ Streak Shields Are 100% Automated",
        description=(
            f"**{user.display_name}**, streak shields work automatically as a safety cushion.\n\n"
            f"{headline}\n\n"
            f"{action_note}\n\n"
            f"• **Shield Inventory**: {shield_icons} `({shields}/{max_shields})`\n"
            f"• **Current Streak**: **{status['current_streak']} days**\n"
            f"• **Next Shield**: **{status['days_until_next_shield']} day(s)** until next unlock\n\n"
            "**Key Rule**:\n"
            "A day is missed **only if you run out of Streak Shields**."
        ),
        color=0x00D2FF if shields > 0 else 0xE74C3C
    )
    embed.set_footer(text="Automatic midnight protection • Max 2 shields")
    return embed


def build_shield_activated_embed(user: discord.Member, result: Dict[str, Any]) -> discord.Embed:
    """Builds confirmation embed after activating a Streak Shield."""
    embed = discord.Embed(
        title="🛡️ Streak Shield Activated",
        description=(
            f"**{user.display_name}**, your streak is protected for **{result['target_date']}**.\n\n"
            f"• **Remaining Shields**: `🛡️ {result['remaining_shields']} / 2`\n"
            f"• **Reason**: _{result['reason']}_\n\n"
            "Take today for intentional active recovery, hydration, and mental reset.\n"
            "Your streak will not break at midnight."
        ),
        color=0x2ECC71
    )
    embed.set_footer(text="Streak preserved • Resumes tomorrow at 00:00 IST")
    return embed


def build_tips_embed(user: Union[discord.User, discord.Member], is_enabled: bool) -> discord.Embed:
    """Builds the interactive tips configuration embed."""
    status_str = "**ON** 🟢 (Enabled)" if is_enabled else "**OFF** 🔕 (Disabled)"
    current_mode_tag = "ON (Enabled)" if is_enabled else "OFF (Disabled)"
    color = 0x2ECC71 if is_enabled else 0x95A5A6
    desc = (
        f"**Tips Status for {user.display_name}**: {status_str}\n\n"
        "Periodic tips appear after logging workouts with `/log`, `/quick`, `/streak`, etc., "
        "sharing feature guides, pro-tips, and challenge logic.\n\n"
        "• **ON (Enabled)**\n"
        "  You will occasionally receive helpful command tricks, habit guidance, and feature tips.\n\n"
        "• **OFF (Disabled)**\n"
        "  All periodic tip messages mentioning you are completely suppressed.\n\n"
        "Use the buttons below to toggle your preference at any time."
    )
    embed = discord.Embed(
        title="💡 Winter Arc — Usage Tips & Guidance",
        description=desc,
        color=color
    )
    embed.set_footer(text=f"Toggle anytime with /tips on or /tips off • Current: {current_mode_tag}")
    return embed


def build_settings_embed(user: discord.Member, settings: Dict[str, Any]) -> discord.Embed:
    """Builds the interactive private DM notification settings embed."""
    morning_icon = "🟢 On" if settings.get("dm_morning") else "⚪ Off"
    afternoon_icon = "🟢 On" if settings.get("dm_afternoon") else "⚪ Off"
    evening_icon = "🟢 On" if settings.get("dm_evening") else "⚪ Off"

    desc = (
        f"**{user.display_name}** • Personal Accountability Reminders\n\n"
        f"• 🌅 **Morning Kickoff (05:00 IST)**: {morning_icon}\n"
        f"• ☀️ **Afternoon Check-in (16:30 IST)**: {afternoon_icon}\n"
        f"• 🌙 **Evening Streak Warning (21:00 IST)**: {evening_icon}\n\n"
        "_Click the buttons below to toggle any reminder on or off._\n"
        "_Note: Ensure your Discord privacy settings allow Direct Messages from server members._"
    )

    embed = discord.Embed(
        title="⚙️ Winter Arc — Personal Reminders & DMs",
        description=desc,
        color=0x5865F2
    )
    embed.set_footer(text="Zero server spam • Direct personal accountability")
    return embed


def build_dm_morning_message(
    tasks: List[Dict[str, Any]],
    streak: int,
    date_display: str,
    quote: Optional[str] = None,
    curr_phase: Optional[Dict[str, Any]] = None,
    phase_progress: Optional[Dict[str, Any]] = None,
    user_mention: Optional[str] = None,
    is_recovery: bool = False,
) -> str:
    """Builds clean personal text message for the 05:00 IST morning DM briefing."""
    today_recovery = is_recovery
    if today_recovery:
        import random
        rest_emoji = random.choice(["🌱", "🌿", "🍃", "🪴", "🧘"])
        mention_prefix = f"{user_mention}\n" if user_mention else ""
        rest_quote = random.choice(AUTHENTIC_REST_QUOTES)
        default_dm_adv = "Movement is medicine today. Don't sit idle; take a light 20-minute walk, hydrate deeply, and mobilize tight joints to actively rebuild."
        advice = sanitize_display_text(quote, default_dm_adv).strip()
        subtext = "-# Active Recovery Day (ARD) ❤️ • Streak automatically preserved • Disable anytime using /reminders"
        return f"{mention_prefix}**Today is Rest Day! {rest_emoji}**\n\n> {rest_quote}\n\n{advice}\n\n{subtext}"

    if curr_phase and phase_progress:
        header = f"🌅 **Winter Arc — Day {phase_progress['day_num']} of {curr_phase['name']}**"
    else:
        header = f"🌅 **Winter Arc — Morning Briefing ({date_display})**"

    streak_line = f"🔥 **Active Streak**: **{streak} days**"

    default_dm_m_q = "When you arise in the morning think of what a privilege it is to be alive: to think, to enjoy, to love. — Marcus Aurelius"
    quote_text = sanitize_display_text(quote, default_dm_m_q).strip()
    quote_section = quote_text if quote_text.startswith(">") else f"> {quote_text}"

    task_lines = []
    for t in tasks:
        tgt = format_num(t["target"])
        task_lines.append(f"• **{t['name']}**: `{tgt} {t['unit']}` *({t.get('max_points', 100)} pts)*")
    tasks_block = "**Today's Challenge (500 pts max):**\n" + "\n".join(task_lines)

    subtext = "-# Log sets with /log or /quick • Disable anytime using /reminders"

    mention_prefix = f"{user_mention}\n" if user_mention else ""
    return f"{mention_prefix}{header}\n{streak_line}\n\n{quote_section}\n\n{tasks_block}\n\n{subtext}"


def build_dm_afternoon_message(
    user_name: str,
    points: int,
    max_points: int,
    streak: int,
    user_mention: Optional[str] = None,
    is_recovery: bool = False,
) -> str:
    """Builds clean personal text message for the 16:30 IST afternoon DM check-in."""
    pct = int(round((points / max_points * 100))) if max_points > 0 else 0
    target = user_mention if user_mention else (user_name if user_name.startswith("<@") else f"**{user_name}**")

    today_recovery = is_recovery
    if today_recovery:
        header = "☀️ **Winter Arc — ARD Afternoon Pulse (16:30 IST) 🧘**"
        body = (
            f"{target}, today is an official Pack Active Recovery Day (ARD).\n"
            f"Your **{streak}-day streak** is fully protected with zero stress.\n\n"
            "Don't stay idle—take a light walk, do mobility work or foam rolling, hydrate, and restore."
        )
        subtext = "-# Active Recovery Day (ARD) ❤️ • Streak protected • Disable anytime using /reminders"
        return f"{header}\n\n{body}\n\n{subtext}"

    header = "☀️ **Winter Arc — Afternoon Check-in (16:30 IST)**"

    if points >= 500:
        body = (
            f"{target}, you've completely maxed out the board today! **500 / 500 pts** (⭐ Perfect Day).\n"
            f"Your **{streak}-day streak** is fully defended. Rest up and recover."
        )
    elif points >= MIN_STREAK_POINTS:
        remaining = max_points - points
        body = (
            f"{target}, you're sitting at **{points} / {max_points} pts** ({pct}%).\n"
            f"🔥 **Streak is already secured for today ({streak} days)!**\n\n"
            f"You have **{remaining} points** remaining on the board if you want to push for a clean sweep."
        )
    else:
        needed = MIN_STREAK_POINTS - points
        body = (
            f"{target}, you have logged **{points} / {max_points} pts** ({pct}%) so far today.\n"
            f"⚠️ You need **{needed} more points** before midnight to defend your **{streak}-day streak**.\n\n"
            f"Drop and knock out a quick set of push-ups or squats before your evening gets busy."
        )

    subtext = "-# Log sets with /log or /quick • Disable anytime using /reminders"
    return f"{header}\n\n{body}\n\n{subtext}"


def build_dm_evening_message(
    user_name: str,
    points: int,
    max_points: int,
    streak: int,
    shields: int,
    quote: Optional[str] = None,
    user_mention: Optional[str] = None,
    is_recovery: bool = False,
) -> str:
    """Builds clean personal text message for the 21:00 IST evening streak warning DM (3h before midnight)."""
    target = user_mention if user_mention else (user_name if user_name.startswith("<@") else f"**{user_name}**")

    today_recovery = is_recovery
    if today_recovery:
        mention_prefix = f"{target}\n" if target else ""
        header = "**Active Recovery Day Complete! 🌙**"
        default_body = (
            "Good work taking care of your recovery today. Turn off notifications, stay off your screen, "
            "and get to bed early tonight. Tomorrow we go full throttle — make sure you're well-rested and ready to crush your sets."
        )
        body = sanitize_display_text(quote, default_body).strip()
        subtext = "-# Active Recovery Day (ARD) ❤️ • Rest well • Tomorrow we hunt"
        return f"{mention_prefix}{header}\n\n{body}\n\n{subtext}"

    header = "🌙 **Winter Arc — 3 Hours Until Midnight Rollover!**"

    if points >= 500:
        body = (
            f"{target}, scores lock in at 00:00 IST.\n"
            f"You finished at **500 pts** (⭐ Perfect Day). Your **{streak}-day streak** will advance cleanly at midnight."
        )
    elif points >= MIN_STREAK_POINTS:
        body = (
            f"{target}, scores lock in at 00:00 IST.\n"
            f"You logged **{points} pts** today. Your **{streak}-day streak** is safely secured for tomorrow!"
        )
    else:
        needed = MIN_STREAK_POINTS - points
        shield_text = (
            f"• Available Frost Shields: `{shields} / 2` (A shield will be auto-consumed at midnight)"
            if shields > 0
            else "• Available Frost Shields: `0 / 2` ⚠️ **No shields left! Your streak will break if you don't hit 30 pts!**"
        )
        body = (
            f"{target}, scores finalize at **00:00 IST**.\n"
            f"You currently have **{points} / 30 points** needed for your streak ({needed} pts missing).\n\n"
            f"{shield_text}\n\n"
            f"Get your reps in now and log with `/log` before the board resets!"
        )

    clean_dm_q = sanitize_display_text(quote, "").strip()
    quote_section = f"\n\n> {clean_dm_q}" if clean_dm_q else ""
    subtext = "-# Log sets with /log • Rollover at 00:00 IST • Disable anytime using /reminders"

    return f"{header}\n\n{body}{quote_section}\n\n{subtext}"


def build_dm_afternoon_embed(user: discord.User, points: int, max_points: int, streak: int) -> discord.Embed:
    """Builds private afternoon progress DM embed sent at 16:30 IST."""
    pct = int(round((points / max_points * 100))) if max_points > 0 else 0
    needed = max(0, MIN_STREAK_POINTS - points)

    if points >= 500:
        desc = (
            f"**{user.display_name}**, outstanding execution!\n\n"
            f"You reached **500 / 500 pts** (⭐ 100% Perfect Day).\n"
            f"🔥 **{streak}-day streak** safely preserved for midnight rollover."
        )
        color = 0x2ECC71
    elif points >= MIN_STREAK_POINTS:
        desc = (
            f"**{user.display_name}**, solid work so far.\n\n"
            f"📊 **Today's Score**: **{points} / {max_points} pts** ({pct}%)\n"
            f"🔥 **Streak Status**: Secured for today ({streak} days)!\n\n"
            f"Push for 500 pts before midnight to claim a Perfect Day."
        )
        color = 0x3498DB
    else:
        desc = (
            f"**{user.display_name}**, midday check-in.\n\n"
            f"📊 **Today's Score**: **{points} / {max_points} pts** ({pct}%)\n"
            f"⚠️ **{needed} more points needed** to secure your **{streak}-day streak**.\n\n"
            "_Drop and log a quick set with `/log` or `/quick` before the evening rush!_"
        )
        color = 0xE67E22

    embed = discord.Embed(
        title="☀️ Winter Arc — Afternoon Check-in",
        description=desc,
        color=color
    )
    embed.set_footer(text="Disable this notification anytime using /reminders • Day resets at 00:00 IST")
    return embed


def build_dm_morning_embed(tasks: List[Dict[str, Any]], streak: int, date_display: str, quote: Optional[str] = None) -> discord.Embed:
    """Builds private morning briefing DM sent at 05:00 IST."""
    task_lines = [
        f"• **{t['name']}**: `{format_num(t['target'])} {t['unit']}` *(max {t['max_points']} pts)*"
        for t in tasks
    ]

    clean_quote = sanitize_display_text(quote, "").strip()
    if clean_quote:
        clean_quote = clean_quote.lstrip(">").strip()
    quote_section = f"\n\n**Focus**:\n> {clean_quote}" if clean_quote else ""

    desc = (
        f"📅 **{date_display}**\n\n"
        f"🔥 **Your Streak**: **{streak} days**\n\n"
        "**Today's Challenge (500 pts ceiling)**\n"
        + "\n".join(task_lines)
        + quote_section
        + "\n\n_Rise early. Move your body. Log your reps in the server with `/log`._"
    )

    embed = discord.Embed(
        title="🌅 Winter Arc — Morning Briefing",
        description=desc,
        color=0x00D2FF
    )
    embed.set_footer(text="Disable this notification anytime using /reminders • Day resets at 00:00 IST")
    return embed


def build_dm_evening_embed(user: discord.User, progress: Dict[str, Any], streak: int, shield_status: Dict[str, Any], quote: Optional[str] = None) -> discord.Embed:
    """Builds private evening streak warning DM sent at 21:00 IST (3h before midnight)."""
    pts = progress["total_points"]
    max_pts = progress["max_possible_points"]
    pct = int(progress["overall_completion_rate"] * 100)
    clean_quote = sanitize_display_text(quote, "").strip()
    if clean_quote:
        clean_quote = clean_quote.lstrip(">").strip()
    quote_section = f"\n\n**Evening Note**:\n> {clean_quote}" if clean_quote else ""

    if progress["perfect_day"]:
        title = "⭐ Winter Arc — Perfect Day Secured!"
        color = 0x2ECC71
        desc = (
            f"Outstanding work, **{user.display_name}**.\n\n"
            f"You have reached **{pts} / {max_pts} pts** (100%) today.\n"
            f"Your **{streak}‑day streak** is fully protected at midnight.\n\n"
            + quote_section
            + "\n_Rest up and recover for tomorrow's grind._"
        )
    elif pts >= MIN_STREAK_POINTS:
        title = "🔥 Winter Arc — Streak Secured!"
        color = 0x2ECC71
        desc = (
            f"Solid work, **{user.display_name}**.\n\n"
            f"You logged **{pts} points** today, surpassing the {MIN_STREAK_POINTS}-point daily streak threshold.\n"
            f"Your **{streak}‑day streak** is locked in for midnight rollover.\n\n"
            + quote_section
            + "\n_Aim for 100% (500 pts) before midnight to claim a Perfect Day!_"
        )
    else:
        title = "⚠️ Winter Arc — Evening Streak Warning"
        color = 0xE74C3C
        needed = MIN_STREAK_POINTS - pts
        shield_info = (
            f"\n\n🛡️ **Safety Net**: You have **{shield_status['frost_shields']} Streak Shield(s)**. "
            "If you cannot finish today, an auto-shield will protect your streak at midnight."
            if shield_status["frost_shields"] > 0
            else f"\n\n⚠️ **No Streak Shields available!** Log {needed} more points before midnight to prevent your streak from resetting."
        )
        reset_ts = get_midnight_reset_timestamp()
        desc = (
            f"**{user.display_name}**, only **<t:{reset_ts}:R>** remain before midnight cutoff (<t:{reset_ts}:t>).\n\n"
            f"📊 **Today's Score**: **{pts} / {max_pts} pts** ({needed} more pts needed to defend streak)\n"
            f"🔥 **Streak at Risk**: **{streak} days**"
            f"{shield_info}"
            f"{quote_section}\n\n"
            "_Lock in your remaining sets with `/log` before midnight!_"
        )

    embed = discord.Embed(
        title=title,
        description=desc,
        color=color
    )
    embed.set_footer(text="Disable this notification anytime using /reminders • Rollover at 00:00 IST")
    return embed


def build_grind_embed(user: discord.Member, result: Dict[str, Any], total_daily_points: int) -> discord.Embed:
    """Builds a clean, human confirmation card for /grind custom workout and deep work entries."""
    verdict = result.get("verdict", "REJECTED")
    pts = result.get("points", 0)
    learning = result.get("key_learning")
    has_focus = learning and learning != "None"
    excluded = result.get("tracked_disciplines_excluded", [])

    if pts > 0:
        if verdict == "ROASTED":
            title = f"🔥 Effort Logged (+{pts} pts)"
            color = 0xE67E22
            header_tag = f"• `{learning}`" if has_focus else "• Effort Points"
        else:
            title = f"⚔️ Grind Logged (+{pts} pts)"
            color = 0x00D2FF
            header_tag = f"• `{learning}`" if has_focus else "• Custom Grind"
        pts_line = f"**+{pts} pts earned** • Today's Board: **{total_daily_points} pts**"
    else:
        title = "⚪ Grind Log (0 pts)"
        color = 0xE67E22 if verdict == "ROASTED" else 0x95A5A6
        header_tag = "• Grind"
        pts_line = f"**0 pts earned** • Today's Board: **{total_daily_points} pts**"

    commentary = result.get("commentary", "Session logged.")

    desc = (
        f"**{user.display_name}** {header_tag}\n"
        f"{pts_line}\n\n"
        f"> {commentary}"
    )

    if excluded:
        excluded_str = ", ".join(f"`{e}`" for e in excluded)
        desc += f"\n\nℹ️ *Excluded core disciplines: {excluded_str}. Log these with `/log` or `/quick` to advance your 500-pt daily challenge!*"

    embed = discord.Embed(
        title=title,
        description=desc,
        color=color
    )
    embed.set_footer(text="Evaluated by Gemini AI • 1 grind submission allowed per day (max 50 pts)")
    return embed


def format_grind_reply(result: Dict[str, Any]) -> str:
    """Formats /grind evaluation as a casual conversational Discord message reply in Amarok's voice."""
    commentary = (result.get("commentary") or "Session logged.").strip()
    pts = int(result.get("points", 0))
    learning = result.get("key_learning")
    verdict = str(result.get("verdict", "")).upper()
    excluded = result.get("tracked_disciplines_excluded", [])

    if pts > 0:
        if learning and learning.lower() != "none":
            task_label = learning
        elif verdict == "ROASTED":
            task_label = "Effort / Grind Attempt"
        else:
            task_label = "Custom Grind"
        reply = f"{commentary}\n\n⚔️ **Points Earned**: {pts} pts\n📋 **Logged**: {task_label}"
        if excluded:
            excluded_str = ", ".join(f"`{e}`" for e in excluded)
            reply += f"\n\nℹ️ *Excluded core disciplines: {excluded_str}. Log these with `/log` or `/quick` to advance your 500-pt daily challenge!*"
        return reply

    if excluded:
        excluded_str = ", ".join(f"`{e}`" for e in excluded)
        return f"{commentary}\n\nℹ️ *Excluded core disciplines: {excluded_str}. Log these with `/log` or `/quick` to advance your 500-pt daily challenge!*"

    return commentary


def build_quicklog_embed(
    user: discord.Member,
    log_results: List[Dict[str, Any]],
    commentary: str,
    unrecognized: List[str] = None,
    level_up_info: Optional[Dict[str, Any]] = None
) -> discord.Embed:
    """Builds the combined confirmation embed for natural language /quick logging."""
    lines = []
    total_delta = sum(r["points_earned_delta"] for r in log_results)
    daily_total = log_results[-1]["daily_points_total"] if log_results else 0
    daily_max = log_results[-1]["daily_points_max"] if log_results else 500

    for r in log_results:
        raw_tgt = r.get("target") or r.get("task_target") or 100.0
        cur = format_num(r["new_total"])
        tgt = format_num(raw_tgt)
        amt = format_num(r["amount_logged"])
        bar = make_progress_bar(r["new_total"], tgt, length=8)
        delta_tag = f"+{r['points_earned_delta']} pts" if r['points_earned_delta'] > 0 else "Capped"
        lines.append(f"• **{r['task_name']}**: `+{amt} {r['unit']}` ➔ `{cur} / {tgt} {r['unit']}` ({delta_tag})\n  `{bar}`")

    unrec_line = f"\n\n⚠️ *Ignored non-Arc disciplines*: `{', '.join(unrecognized)}`" if unrecognized else ""

    promo_banner = ""
    if level_up_info:
        promo_banner = (
            f"\n\n🎉 **RANK PROMOTION!**\n"
            f"You reached **Level {level_up_info['level']} — {level_up_info['badge']} {level_up_info['title']}**!"
        )
    if any(r.get("shield_awarded") for r in log_results):
        promo_banner += "\n\n🛡️ **STREAK SHIELD EARNED!** You hit a 7-day streak milestone (+1 Shield added to inventory)."

    desc = (
        f"**{user.display_name}** • Fast Workout Log\n\n"
        + "\n\n".join(lines)
        + unrec_line
        + f"\n\n📊 **Today's Points**: **{daily_total} / {daily_max} pts** (+{total_delta} pts earned)"
        + promo_banner
    )

    embed = discord.Embed(
        title="⚡ Quick-Log Processed",
        description=desc,
        color=0x2ECC71
    )
    embed.set_footer(text="Natural language parsing • 500 daily points available across disciplines")
    return embed


def _format_day_ordinal(n: int) -> str:
    """Returns day with ordinal suffix, e.g. 1st, 2nd, 3rd, 4th, 11th, 12th, 21st, 22nd."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def build_weekly_recap_message(
    weekly_stats: Dict[str, Any],
    top_warriors: List[Dict[str, Any]],
    ai_speech: Optional[str] = None,
    role_ping: str = "",
    date_dt: Optional[datetime] = None
) -> str:
    """Builds native Discord broadcast for Sunday 10:00 weekly recap."""
    header = "### Winter Arc | Weekly Recap"

    ai_section = ""
    clean_ai = sanitize_display_text(ai_speech, "").strip()
    if clean_ai:
        clean_ai = clean_ai.lstrip(">").strip()
        ai_section = f"> {clean_ai}"

    podium_lines = []
    badges = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for idx, w in enumerate(top_warriors[:5]):
        badge = badges[idx] if idx < len(badges) else f"#{idx+1}"
        username = w.get("username", "Warrior")
        pts = w.get("points", w.get("total_points", 0))
        podium_lines.append(f"{badge} **{username}** — **{pts:,} pts**")

    podium_block = "**Weekly Top 5**\n" + ("\n".join(podium_lines) if podium_lines else "_No scores logged this week._")

    vol_lines = [
        f"• Push-ups: `{weekly_stats.get('total_pushups', 0):,}` reps",
        f"• Pull-ups: `{weekly_stats.get('total_pullups', 0):,}` reps",
        f"• Squats: `{weekly_stats.get('total_squats', 0):,}` reps",
        f"• Sit-ups: `{weekly_stats.get('total_situps', 0):,}` reps",
        f"• Running: `{weekly_stats.get('total_km', 0):,.1f}` km",
    ]
    vol_block = "**Weekly Workout Volume**\n" + "\n".join(vol_lines)

    clean_ping = role_ping.strip()
    ping_section = clean_ping if clean_ping else ""

    if not date_dt:
        date_dt = datetime.now(BOT_TZ)
    day_str = _format_day_ordinal(date_dt.day)
    date_display = date_dt.strftime(f"%A, {day_str} %B %Y")
    subtext = f"-# {date_display} | Winter Arc"

    sections = [header]
    if ai_section:
        sections.append(ai_section)
    sections.append(podium_block)
    sections.append(vol_block)
    if ping_section:
        sections.append(ping_section)
    sections.append(subtext)

    return "\n\n".join(sections)


def build_weekly_state_of_the_pack_embed(
    weekly_stats: Dict[str, Any],
    top_warriors: List[Dict[str, Any]],
    ai_speech: str
) -> discord.Embed:
    """Builds the Sunday 10:00 IST community broadcast embed."""
    now_dt = datetime.now(BOT_TZ)
    day_str = _format_day_ordinal(now_dt.day)
    date_display = now_dt.strftime(f"%A, {day_str} %B %Y")

    podium_lines = []
    badges = ["🥇", "🥈", "🥉", "4.", "5."]
    for idx, w in enumerate(top_warriors[:5]):
        badge = badges[idx] if idx < len(badges) else f"{idx+1}."
        pts = w.get("points", w.get("total_points", 0))
        podium_lines.append(f"{badge} **{w.get('username', 'Warrior')}** — **{pts:,} pts**")

    clean_speech = sanitize_display_text(ai_speech, "").strip()
    if clean_speech:
        clean_speech = clean_speech.lstrip(">").strip()
    ai_block = f"> {clean_speech}\n\n" if clean_speech else ""
    desc = (
        ai_block
        + "**Weekly Top Warriors**\n"
        + ("\n".join(podium_lines) if podium_lines else "No scores logged this week.")
        + "\n\n**Collective Pack Volume**\n"
        f"• Push-ups: `{weekly_stats.get('total_pushups', 0):,}` reps\n"
        f"• Pull-ups: `{weekly_stats.get('total_pullups', 0):,}` reps\n"
        f"• Squats: `{weekly_stats.get('total_squats', 0):,}` reps\n"
        f"• Sit-ups: `{weekly_stats.get('total_situps', 0):,}` reps\n"
        f"• Running: `{weekly_stats.get('total_km', 0):,.1f}` km"
    )

    embed = discord.Embed(
        title="Winter Arc | Weekly Recap",
        description=desc,
        color=0xD4AF37
    )
    embed.set_footer(text=f"{date_display} • Winter Arc • Standings Archived")
    return embed


def build_recap_embed(
    user: discord.Member,
    stats: Dict[str, Any],
    is_overall: bool = False
) -> discord.Embed:
    """Builds the comprehensive recap card for a single phase or overall campaign."""
    if is_overall:
        rank_str = f"**#{stats.get('all_time_rank', 1)}** of {stats.get('total_warriors', 1)}"
        pts = stats.get("lifetime_points", 0)
        streak = stats.get("current_streak", 0)
        perfect = stats.get("perfect_days", 0)
        active = stats.get("active_days", 0)
        shields = stats.get("total_shields", 0)
        grind_count = stats.get("total_grinds", 0)
        grind_pts = stats.get("grind_points", 0)

        vol_lines = []
        for t in stats.get("task_totals", []):
            icon = TASK_ICONS.get(t["name"].lower(), "🎯")
            val = format_num(t["total_volume"])
            vol_lines.append(f"{icon} **{t['name']}**: `{val:,} {t['unit']}`")

        desc = (
            f"**{user.display_name}**\n\n"
            f"🏆 **All-Time Rank**: {rank_str}\n"
            f"💎 **Total Points**: **{pts:,} pts**\n"
            f"🔥 **Current Streak**: **{streak} days**\n"
            f"⭐ **Perfect Days**: **{perfect} days**\n"
            f"📅 **Active Days**: **{active} days**\n"
            f"🛡️ **Total Shields Consumed**: **{shields}**\n"
            f"⚔️ **Grind Sessions**: **{grind_count} sessions** *(+{grind_pts:,} pts)*\n\n"
            f"**Training Volume**\n"
            + ("\n".join(vol_lines) if vol_lines else "No exercise volume logged yet.")
        )

        embed = discord.Embed(
            title="Overall Campaign Recap",
            description=desc,
            color=0x2C3E50
        )
        embed.set_footer(text="Campaign Duration: Oct 1 – Jan 31 • Cumulative Arc Performance")
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        return embed

    # Phase-specific recap
    phase = stats.get("phase", {})
    p_name = phase.get("name", "Unknown Phase")
    p_short = phase.get("short_name", "Phase")
    p_badge = phase.get("badge", "❄️")
    p_sub = phase.get("subtitle", "")
    p_total_days = phase.get("total_days", 31)
    p_color = phase.get("color", 0x3498DB)

    rank_str = f"**#{stats.get('phase_rank', 1)}** of {stats.get('total_participants', 1)}"
    pts = stats.get("total_points", 0)
    perfect = stats.get("perfect_days", 0)
    active = stats.get("active_days", 0)
    shields = stats.get("shields_used", 0)
    grind_count = stats.get("grind_count", 0)
    grind_pts = stats.get("grind_points", 0)

    vol_lines = []
    for t in stats.get("task_totals", []):
        icon = TASK_ICONS.get(t["name"].lower(), "🎯")
        val = format_num(t["total_volume"])
        vol_lines.append(f"{icon} **{t['name']}**: `{val:,} {t['unit']}`")

    desc = (
        f"**{user.display_name}**\n"
        f"{p_sub}\n\n"
        f"🏆 **Phase Rank**: {rank_str}\n"
        f"💎 **Phase Points**: **{pts:,} pts**\n"
        f"⭐ **Perfect Days**: **{perfect} days**\n"
        f"📅 **Active Days**: **{active} / {p_total_days} days**\n"
        f"🛡️ **Streak Shields Used**: **{shields}**\n"
        f"⚔️ **Grind Sessions**: **{grind_count} logs** *(+{grind_pts:,} pts)*\n\n"
        f"**Training Volume**\n"
        + ("\n".join(vol_lines) if vol_lines else "No exercise volume logged in this phase.")
    )

    embed = discord.Embed(
        title=f"{p_short}: {p_name} Recap",
        description=desc,
        color=p_color
    )
    embed.set_footer(text=f"Phase Window: {phase.get('start_date')} to {phase.get('end_date')} • Historical Phase Snapshot")
    if user.avatar:
        embed.set_thumbnail(url=user.avatar.url)
    return embed


def build_phase_podium_embed(
    phase: Dict[str, Any],
    leaderboard: List[Dict[str, Any]]
) -> discord.Embed:
    """Builds the end-of-phase unified podium and standings embed."""
    p_name = phase.get("name", "PHASE")
    p_badge = phase.get("badge", "❄️")
    p_color = phase.get("color", 0x3498DB)

    leaderboard_lines = []
    medals = ["🥇", "🥈", "🥉"]
    for idx, u in enumerate(leaderboard[:10]):
        rank_badge = medals[idx] if idx < 3 else f"{idx+1}."
        perfect_str = f" ⭐ {u.get('perfect_days', 0)} perfect" if u.get("perfect_days") else ""
        leaderboard_lines.append(f"{rank_badge} **{u['username']}** — **{u['total_points']:,} pts**{perfect_str}")

    desc = (
        f"⚔️ **The trial of {p_name} has officially concluded.**\n"
        f"{phase.get('subtitle', '')}\n\n"
        "🏆 **Phase Standings**\n"
        + ("\n".join(leaderboard_lines) if leaderboard_lines else "No qualifiers.")
    )

    embed = discord.Embed(
        title=f"{p_badge} Winter Arc — {phase.get('short_name', '')}: {p_name} Concluded!",
        description=desc,
        color=p_color
    )
    embed.set_footer(text="Data frozen in phase snapshot • Streaks continue into the next phase")
    return embed


def build_phase_conclusion_message(
    phase_dict: Dict[str, Any],
    phase_lb: List[Dict[str, Any]],
    ceremony_speech: Optional[str] = None,
    next_phase_dict: Optional[Dict[str, Any]] = None,
    role_ping: str = ""
) -> str:
    """Builds native Discord broadcast for the monthly Phase Conclusion ceremony."""
    p_name = phase_dict.get("name", "Phase")
    p_num = phase_dict.get("id", 1)

    header = f"### Winter Arc | Phase {p_num} Concluded • {p_name}"

    quote_section = ""
    if ceremony_speech:
        clean_speech = ceremony_speech.strip()
        quote_section = clean_speech if clean_speech.startswith(">") else f"> {clean_speech}"

    top_lines = []
    badges = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    top_5 = phase_lb[:5]
    for idx, u in enumerate(top_5):
        badge = badges[idx] if idx < len(badges) else f"#{idx+1}"
        username = u.get("username", "Warrior")
        streak = u.get("streak", 0)
        streak_str = f" *({streak}-day streak)*"
        pts = u.get("total_points", u.get("points", 0))
        top_lines.append(f"{badge} **{username}** — **{pts:,} pts**{streak_str}")

    standings_block = f"**Phase {p_num} Top Standings**\n" + ("\n".join(top_lines) if top_lines else "_No participants recorded._")

    # Stats without the word Community
    total_pts = sum(u.get("total_points", u.get("points", 0)) for u in phase_lb)
    active_count = len(phase_lb)
    max_streak = max((u.get("streak", 0) for u in phase_lb), default=0)
    avg_pts = round(total_pts / active_count) if active_count > 0 else 0

    totals_block = (
        f"**Winter Arc Phase {p_num} Stats:**\n"
        f"• Active Warriors: `{active_count}`\n"
        f"• Total Points Logged: `{total_pts:,} pts`\n"
        f"• Longest Active Streak: `{max_streak} days`\n"
        f"• Average Pack Output: `{avg_pts:,} pts / warrior`"
    )

    next_block = ""
    if next_phase_dict:
        next_id = next_phase_dict.get("id", p_num + 1)
        next_name = next_phase_dict.get("name", "THE HUNT")
        if next_id == 2:
            phase_quote = "First Frost was about becoming the person capable of facing winter. The Hunt is about becoming the person who refuses to leave empty-handed. Whatever you chose to pursue this winter, pursue it completely."
        elif next_id == 3:
            phase_quote = "The Hunt forged your discipline into instinct. The Endgame is where champions are made—while the rest of the world celebrates early, we finish what we started."
        elif next_id == 4:
            phase_quote = "The war with yourself has been fought and won. Aftermath is not a return to comfort, but the integration of who you have permanently become."
        else:
            phase_quote = "A new trial begins. Carry your momentum forward and execute without compromise."

        next_block = (
            f"**Next Phase:**\n"
            f"⚔️ **Phase {next_id}: {next_name}** officially begins today.\n"
            f"> \"{phase_quote}\""
        )

    clean_ping = role_ping.strip()
    ping_section = clean_ping if clean_ping else ""

    subtext = f"-# Phase {p_num} archived • Discipline compounds • Winter Arc"

    sections = [header]
    if quote_section:
        sections.append(quote_section)
    sections.append(standings_block)
    sections.append(totals_block)
    if next_block:
        sections.append(next_block)
    if ping_section:
        sections.append(ping_section)
    sections.append(subtext)

    return "\n\n".join(sections)


def build_server_records_embed(records: Dict[str, Any], phase_id: Optional[int] = None) -> discord.Embed:
    """Builds the Server Records & Benchmarks embed for Phase 1-3 or Overall."""
    phase = records.get("phase")
    is_overall = phase is None

    # Title & Header
    if not is_overall:
        p_name = phase.get("name", "PHASE")
        p_short = phase.get("short_name", f"Phase {phase_id}")
        p_color = phase.get("color", 0x3498DB)
        title = f"{p_short}: {p_name} — Server Records"
        subtitle = f"*Top community benchmarks and combined volume for {p_name}*\n\n"
        footer_text = f"Phase Window: {phase.get('start_date')} to {phase.get('end_date')} • Live Server Benchmarks"
    else:
        title = "Winter Arc — All-Time Server Records"
        subtitle = "*Cumulative campaign benchmarks across all phases*\n\n"
        p_color = 0x2C3E50
        footer_text = "Oct 1 – Jan 31 • Cumulative Arc Performance"

    # 1. Achievements & Records
    achievements_lines = ["👑 **Achievements & Records**"]

    # Longest Streak
    ls = records.get("longest_streak")
    if ls and ls.get("streak", 0) > 0:
        u_str = f"<@{ls['discord_id']}>" if ls.get("discord_id") else f"**{ls.get('username', 'Nobody')}**"
        achievements_lines.append(f"🔥 **Longest Streak**: **{ls['streak']} days** — {u_str}")
    else:
        achievements_lines.append("🔥 **Longest Streak**: _None recorded yet_")

    # Daily Maxers
    dm = records.get("daily_maxers", {})
    max_score = dm.get("max_score", 0)
    users = dm.get("users", [])
    if max_score > 0 and users:
        u_list = [f"<@{u['discord_id']}>" if u.get("discord_id") else f"**{u.get('username')}**" for u in users[:3]]
        u_str = ", ".join(u_list)
        if len(users) > 3:
            u_str += f" *(+{len(users) - 3} more)*"
        achievements_lines.append(f"⚡ **Daily Maxers**: **{max_score} pts** — {u_str}")
    else:
        achievements_lines.append("⚡ **Daily Maxers**: _None yet_")

    # Most Perfect Days
    mp = records.get("most_perfect_days")
    if mp and mp.get("count", 0) > 0:
        u_str = f"<@{mp['discord_id']}>" if mp.get("discord_id") else f"**{mp.get('username')}**"
        achievements_lines.append(f"⭐ **Most Perfect Days**: **{mp['count']} days** — {u_str}")
    else:
        achievements_lines.append("⭐ **Most Perfect Days**: _None yet_")

    # Most Grinded Member
    mg = records.get("most_grinded")
    if mg and mg.get("sessions", 0) > 0:
        u_str = f"<@{mg['discord_id']}>" if mg.get("discord_id") else f"**{mg.get('username')}**"
        achievements_lines.append(f"⚔️ **Most Grinded Member**: **{mg['sessions']} sessions** *(+{mg['points']:,} pts)* — {u_str}")
    else:
        achievements_lines.append("⚔️ **Most Grinded Member**: _None yet_")

    # Single Day Peaks
    peak_lines = []
    for p in records.get("single_day_peaks", []):
        name = p["task_name"]
        icon = TASK_ICONS.get(name.lower(), "🎯")
        unit = p["unit"]
        amt = format_num(p["amount"])
        if p.get("amount", 0) > 0 and p.get("discord_id"):
            u_str = f"<@{p['discord_id']}>"
            peak_lines.append(f"• {icon} **{name}**: `{amt:,} {unit}` — {u_str}")
        else:
            peak_lines.append(f"• {icon} **{name}**: `0 {unit}`")

    single_day_peaks_block = "\n\n**Single Day Peaks**\n" + "\n".join(peak_lines)

    # 2. Server Totals
    st = records.get("server_totals", {})
    totals_lines = [
        "────────────────────────────────────────\n",
        "🌐 **Server Totals**",
        f"💎 **Total Points**: **{st.get('total_points', 0):,} pts**",
        f"👥 **Active Contributors**: **{st.get('active_contributors', 0)} members**",
        f"⭐ **Total Perfect Days**: **{st.get('total_perfect_days', 0)} perfect days**",
        f"⚔️ **Grind Sessions**: **{st.get('deep_work_sessions', 0)} logs** *(+{st.get('deep_work_points', 0):,} pts)*",
    ]

    vol_lines = []
    for t in st.get("task_totals", []):
        icon = TASK_ICONS.get(t["name"].lower(), "🎯")
        val = format_num(t["total_volume"])
        vol_lines.append(f"• {icon} **{t['name']}**: `{val:,} {t['unit']}`")

    volume_block = "\n\n**Total Volume**\n" + ("\n".join(vol_lines) if vol_lines else "_No exercise volume logged yet._")

    desc = (
        subtitle
        + "\n".join(achievements_lines)
        + single_day_peaks_block
        + "\n\n"
        + "\n".join(totals_lines)
        + volume_block
    )

    embed = discord.Embed(
        title=title,
        description=desc,
        color=p_color
    )
    embed.set_footer(text=footer_text)
    return embed


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


STREAK_LEGEND_FOOTER = "🟩 Streaked • ⭐ Perfect Day (100%) • ❤️ ARD • 🛡️ Shield Used • 🟥 Missed • ▫️ Upcoming"
STREAK_LEGEND_SUBTEXT = STREAK_LEGEND_FOOTER


def build_streak_consistency_embed(user: Any, data: Dict[str, Any]) -> discord.Embed:
    """Builds the monthly habit calendar, streak matrix, and consistency highlights embed."""
    title = "📅 Winter Arc — Streak and Consistency"

    name = user.display_name.upper()
    month_str = data.get("month_name", "Month").upper()
    year_str = str(data.get("year", 2026))
    rank_title = data.get("rank_title", "Initiate").upper()
    sub_header = f"**{name}** | **{month_str} {year_str}** | **{rank_title}**"

    grid_block = f"```text\n{data.get('calendar_grid', '')}\n```"

    h = data.get("highlights", {})
    highest_streak = h.get("highest_streak", 0)
    current_streak = h.get("current_streak", 0)
    active_days = h.get("active_days", 0)
    elapsed_days = h.get("elapsed_days", 0)
    consistency_pct = h.get("consistency_pct", 0)
    total_points = h.get("total_points", 0)
    avg_points = h.get("avg_points", 0)
    perfect_days = h.get("perfect_days", 0)
    shields_used = h.get("shields_used", 0)
    shields_left = h.get("shields_left", 0)

    highlights_block = (
        "──────────────────────────────────────────────\n"
        "🏆 **Month Highlights:**\n"
        f"• Highest Streak: 🏔️ **{highest_streak} Days**\n"
        f"• Current Streak: 🔥 **{current_streak} days**\n"
        f"• Consistency: 📅 **{active_days}/{elapsed_days} days active ({consistency_pct}%)**\n"
        f"• Volume: ⚡ **{total_points:,} total pts (Avg: {avg_points:,} pts/day)**\n"
        f"• Perfect Days: ⭐ **{perfect_days} (Per day 100% completion)**\n"
        f"• Streak Shields Used: 🛡️ **{shields_used}x ({shields_left} Left)**"
    )

    desc = f"{sub_header}\n\n{grid_block}\n{highlights_block}"

    embed = discord.Embed(
        title=title,
        description=desc,
        color=0xE67E22 if current_streak > 0 else 0x95A5A6
    )
    embed.set_footer(text=STREAK_LEGEND_FOOTER)
    return embed


def build_full_calendar_embed(user: Any, data: Dict[str, Any]) -> discord.Embed:
    """Builds the 3-phase full Winter Arc campaign calendar (Oct 1 - Dec 31)."""
    title = "📅 Winter Arc — Full Calendar"

    name = user.display_name.upper()
    rank_title = data.get("rank_title", "Initiate").upper()
    sub_header = f"**{name}** | **OCT 1 – DEC 31** | **{rank_title}**"

    grid_block = f"```text\n{data.get('calendar_text', '')}\n```"

    h = data.get("highlights", {})
    longest_streak = h.get("longest_streak", 0)
    active_days = h.get("active_days", 0)
    total_days = h.get("total_days", 92)
    consistency_pct = h.get("overall_consistency_pct", 0)
    total_points = h.get("total_points", 0)
    avg_points = h.get("avg_points", 0)
    perfect_days = h.get("perfect_days", 0)
    shields_used = h.get("shields_used", 0)
    shields_left = h.get("shields_left", 0)

    highlights_block = (
        "──────────────────────────────────────────────\n"
        "🏆 **Overall Highlights:**\n"
        f"• Overall Consistency: 📅 **{active_days}/{total_days} days active ({consistency_pct}%)**\n"
        f"• All-Time Longest Streak: 🏔️ **{longest_streak} Days**\n"
        f"• Campaign Volume: ⚡ **{total_points:,} total pts (Avg: {avg_points:,} pts/day)**\n"
        f"• Total Perfect Days: ⭐ **{perfect_days} (Per day 100% completion)**\n"
        f"• Total Shields Used: 🛡️ **{shields_used}x ({shields_left} Left)**"
    )

    desc = f"{sub_header}\n\n{grid_block}\n{highlights_block}"

    embed = discord.Embed(
        title=title,
        description=desc,
        color=0xE67E22 if longest_streak > 0 else 0x95A5A6
    )
    embed.set_footer(text=STREAK_LEGEND_FOOTER)
    return embed


def build_quick_streak_embed(user: Any, streak: int, shield_status: Dict[str, Any], stats: Dict[str, Any]) -> discord.Embed:
    """Builds the compact quick streak status card."""
    next_milestone = ((streak // 7) + 1) * 7
    days_to_milestone = next_milestone - streak

    shields_count = shield_status.get("frost_shields", shield_status.get("inventory", 0))
    is_shielded = shield_status.get("is_today_shielded", shield_status.get("is_shielded_today", False))

    desc = (
        f"**{user.display_name}** • Streak Status\n\n"
        f"🔥 **Current Streak**: **{streak} days**\n"
        f"⭐ **Perfect Days (100%)**: **{stats.get('perfect_days', 0)}**\n"
        f"🛡️ **Streak Shields**: **{shields_count}/2 available**\n"
        f"⏳ **Next Shield Milestone**: **{days_to_milestone} day(s)** (at Day {next_milestone})\n\n"
        + ("🛡️ *Protected by Streak Shield today!*" if is_shielded else "⚡ *Log at least 30 points today to maintain your streak.*")
    )
    embed = discord.Embed(
        title="🔥 Winter Arc — Streak Status",
        description=desc,
        color=0xE67E22 if streak > 0 else 0x95A5A6
    )
    embed.set_footer(text="Requires 30+ pts/day to preserve streak • Max 2 Streak Shields")
    return embed


def build_launch_invite_embed(username: str, channel_id: int = 1554843200814845952) -> discord.Embed:
    """Builds the personalized, stylized launch invitation DM embed for Winter Arc."""
    ch_mention = f"<#{channel_id}>" if channel_id else "the dedicated Winter Arc channel"

    embed = discord.Embed(
        title="❄️ Winter Arc 2026 // Kicking Off Tomorrow (Oct 1)",
        color=0x3498DB
    )

    desc = (
        f"Hi **{username}**,\n\n"
        "Winter Arc officially kicks off tomorrow, **October 1st**.\n\n"
        "Before we get started, here is a quick breakdown of what’s changing, how this year works, and why it is structured differently.\n\n"
        "**What We Learned From Last Year**\n\n"
        "Last year, Winter Arc fell flat for a simple reason: **it was too broad and completely manual.** People tried to manage 10 different goals across study, habits, and work, tracked everything manually on sheets, and naturally burned out within a couple of weeks.\n\n"
        "This year, we’ve stripped away all the noise. We are narrowing the focus down to **one core pillar: physical health and daily consistency.**\n\n"
        "Everything is tracked automatically by our Discord bot so you never have to deal with spreadsheets or manual logs.\n\n"
        "**The Daily Goal (Yes, It Looks Absurd)**\n\n"
        "When you look at the daily tasks, the numbers look intense:\n\n"
        "• **100 Push-ups**\n"
        "• **100 Squats**\n"
        "• **100 Pull-ups**\n"
        "• **100 Sit-ups**\n"
        "• **10 km Run**\n\n"
        "**Do not stress about maxing these out.** The targets are deliberately set high so there is always room to grow. Nobody expects anyone to hit 100% on day one.\n\n"
        "The real rule is simple: **Do whatever you can each day, but show up consistently.**\n\n"
        "Logging just **30 points** (e.g. 30 pushups, or 3 km running, or a mix of reps) is all it takes to complete your daily requirement and keep your streak alive."
    )
    embed.description = desc

    embed.add_field(
        name="🗺️ The 4-Phase Roadmap",
        value=(
            "• ❄️ **Phase 1: First Frost (October)**\n"
            "_The Foundation:_ Focus on setting the habit, logging daily, and shaking off the rust. Just get into the groove.\n\n"
            "• 🐺 **Phase 2: The Hunt (November)**\n"
            "_The Mid-Stretch:_ The initial excitement has worn off. This month is about staying consistent when motivation dips.\n\n"
            "• ⚔️ **Phase 3: The Endgame (December)**\n"
            "_The True Test:_ Most people slack off during December and wait for New Year's resolutions. This phase is about staying disciplined while the rest of the world checks out.\n\n"
            "• 🌅 **Phase 4: Aftermath (January)**\n"
            "_The Integration:_ Cementing the gains you built over the winter into a permanent lifestyle, rather than starting from zero like everyone else."
        ),
        inline=False
    )

    embed.add_field(
        name="🛡️ Built-in Safety Net: Streak Shields",
        value=(
            "We know life happens—exams, travel, or sick days:\n\n"
            "• Every 7-day streak milestone earns you a **Streak Shield** (capped at 2).\n"
            "• You do not have to activate anything manually. If you miss a day, the bot automatically consumes a shield at midnight (**00:00 IST**) to protect your streak."
        ),
        inline=False
    )

    embed.add_field(
        name="⚡ How to Get Started",
        value=(
            f"1. All challenge activity happens exclusively in {ch_mention}. Head there and type **`/enroll`** to join the roster and claim your role.\n\n"
            "2. Whenever you finish a workout, use **`/log`** or **`/quicklog`** to log your reps or kilometers in seconds.\n\n"
            "3. Use **`/today`** or **`/streak`** anytime to see your daily progress, points, and your live streak.\n\n"
            "4. Check out **`/leaderboard`** to see server standings, or **`/grind`** if you pushed through a tough session and want AI feedback.\n\n"
            "5. Type **`/help`** anytime to see the full list of commands and complete details on how everything works."
        ),
        inline=False
    )

    embed.add_field(
        name="🔔 Channel Notifications",
        value=(
            f"Right-click (or tap and hold on mobile) {ch_mention}, go to **Notification Settings**, and set it to **\"Only @mentions\"**.\n\n"
            "This way, you won't get buzzed every time someone logs a workout, but you will still get pinged for the daily morning kickoff, afternoon check-in, and midnight podium!"
        ),
        inline=False
    )

    embed.set_footer(text="Winter Arc 2026 • Consistency Over Everything • Tomorrow is Day 1")
    return embed

