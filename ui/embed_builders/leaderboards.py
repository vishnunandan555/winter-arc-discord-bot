"""
ui/embed_builders/leaderboards.py - Embed builders for daily, weekly, monthly, overall leaderboards, podiums, and records.
"""

from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
import discord

import database as db
from config import BOT_TZ
from phases import get_current_phase, get_phase_progress
from levels import get_level_info
from ui.formatters import format_rank_badge, TASK_ICONS
from ui.embed_builders.common import (
    AUTHENTIC_REST_QUOTES,
    format_num,
    sanitize_display_text,
    is_recovery_day,
)


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
