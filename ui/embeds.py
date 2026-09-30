"""
ui/embeds.py - Reusable Discord Embed Builders for Winter Arc Bot

Centralizes all presentation styling, layout spacing, color palettes,
and progression information across user commands, admin tools, and scheduled announcements.
"""

from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
import discord

import database as db
from config import BOT_TZ, MIN_STREAK_POINTS
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


LEADERBOARD_NAV_GUIDE = (
    "\n\n**🔘 Standings Sections** *(Use buttons below or `/leaderboard [timeframe]`)*\n"
    "• **📅 Daily** — Today's live sprint (resets at 00:00 IST)\n"
    "• **📆 Weekly** — Monday to Sunday weekly standings\n"
    "• **🗓️ Monthly** — Active Phase / Monthly cumulative points\n"
    "• **🌐 All-Time** — Master leaderboard across the entire campaign"
)


def build_daily_leaderboard_embed() -> discord.Embed:
    """Builds the clean daily standing leaderboard embed (max top 10)."""
    now = datetime.now(BOT_TZ)
    today_str = now.strftime("%Y-%m-%d")
    date_display = now.strftime("%A, %B %d, %Y")
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
            + LEADERBOARD_NAV_GUIDE
        ),
        color=0xF1C40F
    )
    footer_text = "Updated live • Resets daily at 00:00 IST"
    if len(data) > 10:
        footer_text = f"Showing top 10 of {len(data)} participants • {footer_text}"
    embed.set_footer(text=footer_text)
    return embed


def build_weekly_leaderboard_embed(start_date: Optional[str] = None, end_date: Optional[str] = None) -> discord.Embed:
    """Builds the weekly standings leaderboard for a specific calendar week (max top 10)."""
    now = datetime.now(BOT_TZ)
    today = now.date()
    start_of_week = today - timedelta(days=today.weekday())
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
            + LEADERBOARD_NAV_GUIDE
        ),
        color=0x2ECC71
    )
    footer_text = "Updated live • Ranked by weekly points (Mon–Sun)"
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
            + LEADERBOARD_NAV_GUIDE
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
        title_text = f"{curr_phase['badge']} Winter Arc — {curr_phase['name']} ({month_name})"

    embed = discord.Embed(
        title=title_text,
        description=f"{phase_header}\n\n" + "\n".join(lines) + LEADERBOARD_NAV_GUIDE,
        color=embed_color
    )
    footer_text = "Updated live • Ranked by monthly points"
    if len(data) > 10:
        footer_text = f"Showing top 10 of {len(data)} participants • {footer_text}"
    embed.set_footer(text=footer_text)
    return embed


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
        learning = entry.get("key_learning", "Deep Work") if isinstance(entry, dict) else "Deep Work"
        grind_section = f"\n\n**🧠 Grind Bonus**: +{grind_pts} pts *({learning})*"
        phys_pts = progress.get("physical_points", total_pts - grind_pts)
        points_breakdown = f"  *(Physical: {phys_pts} + Grind: {grind_pts})*"

    total_line = f"\n\n📊 **Total Daily Progress**: **{total_pts} / {max_pts} pts** (**{pct}%**){points_breakdown}"

    streak_status = " *(Streak Secured ✅)*" if (total_pts >= MIN_STREAK_POINTS or progress["perfect_day"]) else f" *({MIN_STREAK_POINTS - total_pts} pts to secure streak)*"

    desc = (
        f"**{target_user.display_name}** • {date_display}\n"
        f"🔥 Current Streak: **{streak} days**{streak_status}\n\n"
        "**Daily Disciplines**\n"
        + "\n\n".join(task_lines)
        + grind_section
        + total_line
    )

    embed = discord.Embed(
        title="❄️ Winter Arc — Today",
        description=desc,
        color=0x1ABC9C if progress["perfect_day"] else (0x2ECC71 if total_pts >= MIN_STREAK_POINTS else 0x3498DB)
    )
    embed.set_footer(text=f"Log with /log • {MIN_STREAK_POINTS} pts/day minimum for streak")
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
        learning = entry.get("key_learning", "Deep Work") if isinstance(entry, dict) else "Deep Work"
        grind_section = f"\n\n**🧠 Grind Bonus**: +{grind_pts} pts *({learning})*"
        phys_pts = progress.get("physical_points", total_pts - grind_pts)
        points_breakdown = f"  *(Physical: {phys_pts} + Grind: {grind_pts})*"

    total_line = f"\n\n📊 **Total Daily Progress**: **{total_pts} / {max_pts} pts** (**{pct}%**){points_breakdown}"
    streak_status = " *(Streak Secured ✅)*" if (total_pts >= MIN_STREAK_POINTS or progress["perfect_day"]) else f" *({MIN_STREAK_POINTS - total_pts} pts to secure streak)*"

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
        color=0x1ABC9C if progress["perfect_day"] else (0x2ECC71 if total_pts >= MIN_STREAK_POINTS else 0x3498DB)
    )
    embed.set_footer(text=f"Log with /log • Set with /set • {MIN_STREAK_POINTS} pts/day minimum for streak")
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
    lines = []
    for d in reversed(hist):
        pct = int(round(d["completion_rate"] * 100))
        star = " ⭐" if d["perfect_day"] else ""

        raw_date = d["date"]
        try:
            d_obj = date.fromisoformat(raw_date)
            date_display = d_obj.strftime("%a, %b %d")
        except Exception:
            date_display = raw_date

        grind_note = ""
        g = d.get("grind_entry")
        if g and g.get("points_awarded", 0) > 0:
            tag = g.get("key_learning") or "Deep Focus"
            grind_note = f"\n  ↳ 🧠 *+{g['points_awarded']} pts grind ({tag})*"

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
                "Log your physical and mental friction every single day.\n"
                "Supports natural language AI parsing, rapid set increments, count overrides, and verified deep work."
            ),
            color=0x3498DB
        )
        embed.add_field(
            name="🤖 `/quick [text]` — AI Workout Parser (Ultra-Fast Groq)",
            value=(
                "Log workouts using natural English. Automatically extracts exercises, aggregates sets, and converts miles to km.\n"
                "• **Example**: `/quick text: did 50 pushups, 25 pullups, and ran 3.5 km`\n"
                "• **Example**: `/quick text: 40 squats, 30 situps then 20 more squats`\n"
                "🛡️ *Safeguard*: Unrealistic single-set volume (>50 reps / >10 km) is rejected automatically to preserve integrity."
            ),
            inline=False
        )
        embed.add_field(
            name="⚡ Shorthand & Multi-Discipline Logging",
            value=(
                "Combine multiple exercises in a single `/quick` command: e.g. `/quick 40 pushups, 20 squats, 5km run`.\n"
                "Groq AI automatically extracts reps, sets, and distances in under a second."
            ),
            inline=False
        )
        embed.add_field(
            name="📝 Traditional Set Logging (`/log` & `/set`)",
            value=(
                "• `/log [task] [amount]` — Adds reps or km to your current daily count. Realistic single-set limits apply.\n"
                "• `/set [task] [amount]` — Direct count override. Set to `0` to wipe accidental entries or reset."
            ),
            inline=False
        )
        embed.add_field(
            name="🧠 `/grind [text]` — Academic & Engineering Deep Work (Gemini AI)",
            value=(
                "Submit heavy mental disciplines (LeetCode, systems programming, thesis research, deep technical study).\n"
                "• **Reward**: Up to **+60 bonus points** awarded directly to today's score (Limit: 1 entry per day).\n"
                "• **Example**: `/grind text: Solved 2 hard graph DP problems on LeetCode and debugged OS scheduler for 3 hours`\n"
                "🛡️ *Strict Evaluation*: Evaluated by Gemini AI. Casual reading or passive browsing gets roasted."
            ),
            inline=False
        )
        embed.add_field(
            name="⚡ Reactive AI Coach & Bot Tips",
            value=(
                "When you run commands or log volume (`/today`, `/tasks`, `/log`, `/quick`, `/profile`, `/ranks`, "
                "`/leaderboard`, `/stats`, `/history`, `/recap`, `/streak`, `/shield status`, `/shield use`, `/grind`), "
                "the AI coach Amarok analyzes your results and speaks with sharp accountability (strictly excludes `/set`).\n"
                "Helpful bot usage tips are also shared periodically across non-admin commands on a 10-minute timer."
            ),
            inline=False
        )
        embed.set_footer(text="Use the dropdown menu below to navigate categories • Day resets at 00:00 IST")
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
                "• `/today [member]` — Live daily progress card with individual emoji progress bars, points breakdown, and live streak status.\n"
                "• `/tasks [member]` — Extended disciplines overview with targets, units, muscle groups, and live progress bars.\n"
                "• `/streak [member]` — Habit consistency calendar & streak dashboard! Monday–Sunday weekly matrix with status tags (🟩 30+ pts, ⭐ Perfect Days (100%), 🛡️ Streak Shield, 🟥 Missed, ▫️ Upcoming) and interactive buttons for **Current Month** and the **Full 3-Phase Campaign Calendar** (Oct 1 – Dec 31, 92 days)."
            ),
            inline=False
        )
        embed.add_field(
            name="🎖️ 12-Tier Discipline Hierarchy",
            value=(
                "• `/profile [member]` — Complete member profile with All-Time Standing (#X of Y), Discipline Tier badge, XP to next rank, and daily status.\n"
                "• `/ranks` — Inspect the full 12-tier discipline roadmap from **Initiate (Level 1, 0 pts)** to **Apex (Level 12, 12,000+ pts)**."
            ),
            inline=False
        )
        embed.add_field(
            name="🏆 Standings, Benchmarks & Analytics",
            value=(
                "• `/leaderboard` — Interactive podium view featuring **📅 Daily**, **📆 Monthly (Phase Standings)**, and **🌐 All-Time** rankings (top 10).\n"
                "• `/stats [phase]` — **Server Records & Benchmarks**! Explore server-wide PRs, longest streaks, single-day peak maxers, most Perfect Days, and community volume with interactive buttons for Overall, Phase 1, Phase 2, and Phase 3.\n"
                "• `/recap [member]` — Interactive Phase Explorer with dynamic buttons for active phases and overall campaign with training volume breakdown.\n"
                "• `/history [days]` — View point breakdown and completion rates over the past 7, 14, or 30 days."
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
                "Streak Shields protect your unbroken streak automatically during missed days or emergencies."
            ),
            color=0x00D2FF
        )
        embed.add_field(
            name="❄️ How Streak Shields Work & Streaks",
            value=(
                f"• **Daily Streak Threshold**: Earn at least **{MIN_STREAK_POINTS} points** per day (e.g. 5 push-ups, 5 sit-ups, 5 squats, 5 pull-ups, 1 km run) to maintain your streak.\n"
                "• **Earning Shields**: You earn **+1 Streak Shield for every 7-day streak milestone** (cap of 2 shields max).\n"
                "• **Inventory Cap**: You can hold a maximum of **2 Streak Shields** at any time.\n"
                "• **Automatic Midnight Usage**: If you miss a day (< 30 pts), an available shield is automatically used at midnight (00:00 IST).\n"
                "• **Safety Rule**: A day is missed only if you run out of Streak Shields!"
            ),
            inline=False
        )
        embed.add_field(
            name="🎮 Shield Commands",
            value=(
                "• `/shield status` — View your current shield count (e.g. `1/2`), auto-protection status, and countdown to next shield.\n"
                "• `/shield use` — Learn how automated streak protection keeps your streak alive without manual intervention."
            ),
            inline=False
        )
        embed.set_footer(text="Max 2 shields stored • 1 shield awarded every 7-day streak milestone")
        return embed

    elif category == "settings":
        embed = discord.Embed(
            title="⚙️ Accountability, Settings & Utilities",
            description="Manage personal reminder alerts and challenge lifecycle commands.",
            color=0x2ECC71
        )
        embed.add_field(
            name="🔔 `/settings` — Personal Direct Messages",
            value=(
                "Configure automated private DM alerts sent directly to your inbox:\n"
                "• 🌅 **Morning Kickoff DM (05:00 IST)**: Daily discipline targets, motivation quote, and clean slate.\n"
                "• ⚠️ **Evening Streak Warning DM (21:00 IST)**: Urgent reminder if you are below 30 points.\n"
                "*(Requires Discord privacy settings to allow DMs from server members)*"
            ),
            inline=False
        )
        embed.add_field(
            name="⚔️ Enrollment & Utilities",
            value=(
                "• `/enroll` — Join the Winter Arc challenge and establish your warrior profile.\n"
                "• `/leave_arc` — Unenroll from active server rosters (lifetime stats and points preserved).\n"
                "• `/ping` — Check bot response time, gateway latency, and timezone synchronization."
            ),
            inline=False
        )
        embed.set_footer(text="Automated broadcasts run on Asia/Kolkata (IST) time.")
        return embed

    elif category == "admin":
        embed = discord.Embed(
            title="👑 Server Administration & Maintenance",
            description="Server controls for administrators to configure broadcast channels, roles, disciplines, and monitor system health.",
            color=0xE67E22
        )
        embed.add_field(
            name="📢 Broadcast Configuration",
            value=(
                "• `/admin set_channel [channel]` — Set the server channel for automated 05:00, 16:30, 21:00, and 00:00 broadcasts.\n"
                "• `/admin set_role [role]` — Set the role to mention during scheduled announcements.\n"
                "• `/admin overview` — View server channel, role ping, active disciplines, and enrolled roster."
            ),
            inline=False
        )
        embed.add_field(
            name="🏋️ Discipline Management",
            value=(
                "• `/admin tasks_list` — List all challenge disciplines in the database.\n"
                "• `/admin task_add` — Add a new discipline with custom targets, units, and point limits.\n"
                "• `/admin task_toggle` — Temporarily enable or disable an existing discipline."
            ),
            inline=False
        )
        embed.add_field(
            name="🖥️ System Diagnostics & Testing",
            value=(
                "• `/admin health` — Live RSS RAM monitor, SQLite file sizes, uptime, and one-click **🧹 Collect GC & Free RAM** button.\n"
                "• `/admin finalize_day` — Manually trigger midnight point locks, streak rolls, and daily summaries.\n"
                "• `/test_reminder [type]` — Preview morning, afternoon, evening, midnight, Sunday, DM briefings, or reactive Groq observations (`groq_nudge`)."
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
                "A 4-phase challenge of daily physical and mental discipline.\n"
                "Daily Standard: **500 points (Perfect Day)** • **30 pts/day minimum** to keep your streak alive.\n"
                "Use the interactive dropdown menu below to deep-dive into each subsystem."
            ),
            color=0x2B2D31
        )
        embed.add_field(
            name="🎯 Daily Disciplines (500 pts max)",
            value=(
                "• 💪 **Push-ups**: 100 reps *(1 pt / rep)*\n"
                "• 🧗 **Pull-ups**: 100 reps *(1 pt / rep)*\n"
                "• 🦵 **Squats**: 100 reps *(1 pt / rep)*\n"
                "• 🧘 **Sit-ups**: 100 reps *(1 pt / rep)*\n"
                "• 🏃 **Running**: 10 km *(1 pt / 100m / 10 pts per km)*\n"
                "• 🧠 **Grind Bonus**: Up to +60 pts daily (`/grind`)"
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
                "• 🏆 `Sunday 20:00` — Weekly Community Recap & State of the Pack"
            ),
            inline=False
        )
        embed.add_field(
            name="⚡ Command Directory Cheat Sheet",
            value=(
                "• **Logging**: `/quick` • `/log` • `/set` • `/grind`\n"
                "• **Progress & Tiers**: `/today` • `/tasks` • `/streak` • `/profile` • `/ranks`\n"
                "• **Standings & Benchmarks**: `/leaderboard` • `/stats` • `/history` • `/recap`\n"
                "• **Recovery**: `/shield status` • `/shield use`\n"
                "• **Accountability**: `/settings` • `/enroll` • `/leave_arc` • `/ping`\n"
                "• **Admin**: `/admin set_channel` • `/admin set_role` • `/admin overview` • `/admin health` • `/test_reminder`"
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
    role_ping: str = ""
) -> str:
    """Builds native Discord broadcast for the 07:00 IST morning kickoff."""
    clean_ping = role_ping.strip()
    prefix = f"{clean_ping} " if clean_ping else ""

    if curr_phase and phase_progress:
        phase_header = f"Day {phase_progress['day_num']} of {curr_phase['name']} ({curr_phase['short_name']}) 🌅"
    else:
        phase_header = f"{date_display} 🌅"

    header = (
        f"{prefix}[WinterArc] {phase_header}\n"
        "A new day is on the board. 500 points available across today's disciplines."
    )

    task_lines = []
    for t in active_tasks:
        tgt = format_num(t["target"])
        task_lines.append(f"• **{t['name']}**: `{tgt} {t['unit']}` *({t.get('max_points', 100)} pts)*")
    tasks_section = "\n".join(task_lines) if task_lines else "_No active disciplines configured._"

    quote_text = (quote or '"When you arise in the morning think of what a privilege it is to be alive: to think, to enjoy, to love." — Marcus Aurelius').strip()
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
        member_lines.append(f"- <@{m['discord_id']}> — **{m['points']} / {m['max_points']} pts** ({m['pct']}%){star}")

    members_section = "\n".join(member_lines) if member_lines else "- _No enrolled members yet._"

    quote_text = (quote or '"First say to yourself what you would be; and then do what you have to do." — Epictetus').strip()
    quote_section = quote_text if quote_text.startswith(">") else f"> {quote_text}"

    subtext = "-# Log with /log • 30 pts/day minimum for streak • Rollover at midnight"

    return f"{header}\n\n{members_section}\n\n{quote_section}\n\n{subtext}"


def build_morning_kickoff_embed(active_tasks: List[Dict[str, Any]], date_display: str, quote: Optional[str] = None) -> discord.Embed:
    """Builds the 05:00 morning kickoff broadcast embed with active phase context."""
    from phases import get_current_phase, get_phase_progress
    curr_phase = get_current_phase()
    title_text = f"🌅 Winter Arc — Daily Kickoff • {date_display}"
    embed_color = 0x3498DB
    phase_header = ""
    if curr_phase:
        prog = get_phase_progress(curr_phase)
        title_text = f"{curr_phase['badge']} {curr_phase['short_name']}: {curr_phase['name']} • Daily Kickoff"
        embed_color = curr_phase["color"]
        phase_header = f"**{curr_phase['badge']} {curr_phase['name']}** — *Day {prog['day_num']} of {prog['total_days']} ({prog['days_remaining']} days left in phase)*\n\n"

    task_lines = []
    for t in active_tasks:
        target_display = format_num(t["target"])
        task_lines.append(f"• **{t['name']}**: `{target_display} {t['unit']}` *(max {t['max_points']} pts)*")

    disciplines_block = "\n".join(task_lines) if task_lines else "_No active disciplines._"
    quote_section = f"\n\n**Daily Focus**:\n> {quote}" if quote else ""

    embed = discord.Embed(
        title=title_text,
        description=(
            f"{phase_header}"
            "A new day has begun. 500 points available across 5 disciplines.\n\n"
            "**Daily Targets**\n"
            f"{disciplines_block}"
            f"{quote_section}\n\n"
            "Log your sets with `/log` or check progress with `/today`."
        ),
        color=embed_color
    )
    embed.set_footer(text="Day resets at 00:00 IST • Log early to secure your standing")
    return embed


def build_afternoon_checkin_embed(enrolled_users: List[Dict[str, Any]], today_str: str, quote: Optional[str] = None) -> discord.Embed:
    """Builds the 16:30 afternoon check-in broadcast embed."""
    warrior_lines = []
    for u in enrolled_users:
        prog = db.get_user_daily_progress(u["discord_id"], today_str)
        pct = int(prog["overall_completion_rate"] * 100)
        star = " ⭐" if prog["perfect_day"] else ""
        warrior_lines.append(
            f"• **{u['username']}** — **{prog['total_points']} / {prog['max_possible_points']} pts** ({pct}%){star}"
        )

    quote_section = f"\n\n**Midday Note**:\n> {quote}" if quote else ""

    embed = discord.Embed(
        title="⏰ Winter Arc — Afternoon Check-in",
        description=(
            "Midday check-in. Complete your remaining disciplines before midnight.\n\n"
            "**Today's Progress**\n"
            + ("\n\n".join(warrior_lines) if warrior_lines else "_No enrolled participants yet. Use `/enroll` to join!_")
            + quote_section
        ),
        color=0xE67E22
    )
    embed.set_footer(text="Log sets with /log • Finalizes at 00:00 IST")
    return embed


def build_evening_checkin_message(
    warriors_data: List[Dict[str, Any]],
    callouts: Optional[Dict[int, str]] = None,
    stoic_quote: Optional[str] = None,
    role_ping: str = ""
) -> str:
    """
    Builds the native Discord text broadcast for the 21:00 IST evening streak alert (3h before midnight).
    Formatted with raw pings, per-warrior accountability callouts, authentic stoic quote, and subtext.

    Format:
    @Role [WinterArc] 3 hours left until midnight rollover. ⏳
    If you haven't hit your 30 points yet, get your reps or run logged before midnight to keep your streak alive.

    - <@USER_ID> — {callout}

    > "{stoic_quote}" — Author

    -# Log with /log • 30 pts/day minimum for streak • Rollover at midnight
    """
    clean_ping = role_ping.strip()
    header_ping = f"{clean_ping} " if clean_ping else ""

    header = (
        f"{header_ping}[WinterArc] 3 hours left until midnight rollover. ⏳\n"
        "If you haven't hit your 30 points yet, get your reps or run logged before midnight to keep your streak alive."
    )

    if not warriors_data:
        warriors_section = "- _No enrolled warriors yet._"
    else:
        # Sort ascending by points so warriors who need urgency (0 pts, <30 pts) are at the top
        sorted_warriors = sorted(
            warriors_data,
            key=lambda w: (w.get("points", 0), w.get("streak", 0))
        )
        lines = []
        for w in sorted_warriors:
            d_id = int(w["discord_id"])
            pts = w.get("points", 0)
            callout = (callouts or {}).get(d_id)
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
            lines.append(f"- <@{d_id}> — {callout}")
        warriors_section = "\n".join(lines)

    quote = (stoic_quote or '"Waste no more time arguing what a good man should be. Be one." — Marcus Aurelius').strip()
    if quote.startswith(">"):
        quote_section = quote
    else:
        quote_section = f"> {quote}"

    subtext = "-# Log with /log • 30 pts/day minimum for streak • Rollover at midnight"

    return f"{header}\n\n{warriors_section}\n\n{quote_section}\n\n{subtext}"


def build_evening_checkin_embed(enrolled_users: List[Dict[str, Any]], today_str: str, quote: Optional[str] = None) -> discord.Embed:
    """Builds the 21:00 IST evening streak alert channel broadcast embed (3 hours before midnight)."""
    completed_lines = []
    pending_lines = []

    for u in enrolled_users:
        prog = db.get_user_daily_progress(u["discord_id"], today_str)
        pct = int(round(prog["overall_completion_rate"] * 100))
        pts = prog["total_points"]
        max_pts = prog["max_possible_points"]
        streak = db.calculate_streak(u["discord_id"], today_str)

        if prog["perfect_day"]:
            completed_lines.append(f"• **{u['username']}** — **{pts} / {max_pts} pts** (⭐ 100% Perfect Day • 🔥 {streak}d)")
        elif pts >= MIN_STREAK_POINTS:
            completed_lines.append(f"• **{u['username']}** — **{pts} / {max_pts} pts** (Streak Secured ✅ • 🔥 {streak}d)")
        else:
            needed = MIN_STREAK_POINTS - pts
            pending_lines.append(f"• **{u['username']}** — **{pts} / {max_pts} pts** (⚠️ {needed} pts needed for streak)")

    desc = (
        "⏳ **3 Hours Remaining Until Midnight Rollover!**\n"
        f"Scores lock in at 00:00 IST. Earn at least **{MIN_STREAK_POINTS} pts** to defend your streak.\n\n"
    )

    if completed_lines:
        desc += "**🔥 Streak Secured**\n" + "\n".join(completed_lines) + "\n\n"

    if pending_lines:
        desc += "**⚠️ Streak at Risk (< 30 pts)**\n" + "\n".join(pending_lines) + "\n\n"

    if not completed_lines and not pending_lines:
        desc += "_No enrolled warriors yet. Use `/enroll` to join!_\n\n"

    quote_section = f"\n\n**Evening Note**:\n> {quote}" if quote else ""

    embed = discord.Embed(
        title="🌙 Winter Arc — Evening Streak Alert",
        description=desc.strip() + quote_section,
        color=0xE67E22
    )
    embed.set_footer(text=f"Log sets with /log • {MIN_STREAK_POINTS} pts/day minimum for streak • Rollover at 00:00 IST")
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
    if ai_recap:
        clean_recap = ai_recap.strip()
        recap_section = clean_recap if clean_recap.startswith(">") else f"> {clean_recap}"

    podium_lines = []
    perfect_count = 0
    for idx, entry in enumerate(leaderboard):
        pts = entry["points"]
        rank_badge = ["🥇", "🥈", "🥉"][idx] if idx < 3 else f"`#{idx+1}`"
        perfect_star = " ⭐" if entry["perfect_day"] else ""
        if entry["perfect_day"]:
            perfect_count += 1
        pct = int(round(entry.get("completion_rate", 0) * 100))
        d_id = entry.get("discord_id")
        user_mention = f"<@{d_id}>" if d_id else f"**{entry['username']}**"
        podium_lines.append(f"{rank_badge} {user_mention} — **{pts} pts** ({pct}%){perfect_star}")

    board_section = "\n".join(podium_lines) if podium_lines else "_No activity logged for this day._"
    clean_sweeps = f"\n\n🔥 **Perfect Days**: **{perfect_count}** member(s) hit 100%." if perfect_count > 0 else ""

    subtext = "-# Fresh slate is open • Check your board with /today • Rollover at midnight"

    sections = [header]
    if recap_section:
        sections.append(recap_section)
    sections.append(board_section + clean_sweeps)
    sections.append(subtext)

    return "\n\n".join(sections)


def build_podium_embed(date_str: str, leaderboard: List[Dict[str, Any]]) -> discord.Embed:
    """Builds the 00:00 midnight finalization podium embed."""
    try:
        d_obj = date.fromisoformat(date_str)
        title_date = d_obj.strftime("%A, %B %d, %Y")
    except Exception:
        title_date = date_str

    podium_lines = []
    perfect_count = 0

    for idx, entry in enumerate(leaderboard):
        pts = entry["points"]
        rank = format_rank_badge(idx, pts=pts)
        perfect_star = " ⭐" if entry["perfect_day"] else ""
        if entry["perfect_day"]:
            perfect_count += 1
        pct = int(entry["completion_rate"] * 100)
        podium_lines.append(f"{rank}  **{entry['username']}** — **{pts} pts** ({pct}%){perfect_star}")

    if not podium_lines:
        podium_lines.append("_No activity logged for this day._")

    perfect_info = f"\n\n🔥 **Perfect Days**: **{perfect_count}** member(s) completed 100%." if perfect_count > 0 else ""

    embed = discord.Embed(
        title=f"🌙 Winter Arc — Daily Finalization • {title_date}",
        description=(
            "Scores are locked in for the day. Final standings:\n\n"
            + "\n\n".join(podium_lines)
            + perfect_info
        ),
        color=0x9B59B6
    )
    embed.set_footer(text="A new day has begun • Check your fresh slate with /today")
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


def build_settings_embed(user: discord.Member, settings: Dict[str, Any]) -> discord.Embed:
    """Builds the interactive private DM notification settings embed."""
    master_icon = "🟢 Enabled" if settings["dm_reminders"] else "🔴 Disabled"
    morning_icon = "🟢 On" if settings["dm_morning"] else "⚪ Off"
    evening_icon = "🟢 On" if settings["dm_evening"] else "⚪ Off"

    desc = (
        f"**{user.display_name}** • Notification Preferences\n\n"
        f"**Master DM Notifications**: {master_icon}\n"
        f"• 🌅 **Morning Kickoff (05:00 IST)**: {morning_icon}\n"
        f"• 🌙 **Evening Streak Alert (21:00 IST)**: {evening_icon}\n\n"
        "_Toggle settings using the interactive buttons below._\n"
        "_Note: Ensure your Discord privacy settings allow DMs from server members._"
    )

    embed = discord.Embed(
        title="⚙️ Winter Arc — Private Accountability Settings",
        description=desc,
        color=0x5865F2
    )
    embed.set_footer(text="Zero spam • Only high-leverage discipline alerts")
    return embed


def build_dm_morning_embed(tasks: List[Dict[str, Any]], streak: int, date_display: str, quote: Optional[str] = None) -> discord.Embed:
    """Builds private morning briefing DM sent at 05:00 IST."""
    task_lines = [
        f"• **{t['name']}**: `{format_num(t['target'])} {t['unit']}` *(max {t['max_points']} pts)*"
        for t in tasks
    ]

    quote_section = f"\n\n**Focus**:\n> {quote}" if quote else ""

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
    embed.set_footer(text="Log reps in server with /log • Day resets at 00:00 IST")
    return embed


def build_dm_evening_embed(user: discord.User, progress: Dict[str, Any], streak: int, shield_status: Dict[str, Any], quote: Optional[str] = None) -> discord.Embed:
    """Builds private evening streak warning DM sent at 21:00 IST (3h before midnight)."""
    pts = progress["total_points"]
    max_pts = progress["max_possible_points"]
    pct = int(progress["overall_completion_rate"] * 100)
    quote_section = f"\n\n**Evening Note**:\n> {quote}" if quote else ""

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
        desc = (
            f"**{user.display_name}**, only **3 hours remain** before midnight (00:00 IST).\n\n"
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
    embed.set_footer(text="Midnight rollover occurs at 00:00 IST")
    return embed


def build_grind_embed(user: discord.Member, result: Dict[str, Any], total_daily_points: int) -> discord.Embed:
    """Builds a clean, human confirmation card for /grind deep work entries."""
    verdict = result.get("verdict", "REJECTED")
    pts = result.get("points", 0)
    learning = result.get("key_learning")
    has_focus = learning and learning != "None"

    if pts > 0:
        if verdict == "ROASTED":
            title = f"🔥 Effort Logged (+{pts} pts)"
            color = 0xE67E22
            header_tag = f"• `{learning}`" if has_focus else "• Effort Points"
        else:
            title = f"🧠 Deep Work Logged (+{pts} pts)"
            color = 0x00D2FF
            header_tag = f"• `{learning}`" if has_focus else "• Deep Work"
        pts_line = f"**+{pts} pts earned** • Today's Board: **{total_daily_points} pts**"
    else:
        title = "⚪ Deep Work Log (0 pts)"
        color = 0xE67E22 if verdict == "ROASTED" else 0x95A5A6
        header_tag = "• Deep Work"
        pts_line = f"**0 pts earned** • Today's Board: **{total_daily_points} pts**"

    commentary = result.get("commentary", "Session logged.")

    desc = (
        f"**{user.display_name}** {header_tag}\n"
        f"{pts_line}\n\n"
        f"> {commentary}"
    )

    embed = discord.Embed(
        title=title,
        description=desc,
        color=color
    )
    embed.set_footer(text="Evaluated by Gemini AI • 1 deep work submission allowed per day")
    return embed


def format_grind_reply(result: Dict[str, Any]) -> str:
    """Formats /grind evaluation as a casual conversational Discord message reply."""
    commentary = (result.get("commentary") or "Session logged.").strip()
    pts = int(result.get("points", 0))
    learning = result.get("key_learning")
    verdict = str(result.get("verdict", "")).upper()

    if pts > 0:
        if learning and learning.lower() != "none":
            task_label = learning
        elif verdict == "ROASTED":
            task_label = "Effort / Grind Attempt"
        else:
            task_label = "Deep Work"
        return f"{commentary}\n\n**Points Earned**: {pts} pts\n**Logged**: {task_label}"
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


def build_weekly_recap_message(
    weekly_stats: Dict[str, Any],
    top_warriors: List[Dict[str, Any]],
    ai_speech: Optional[str] = None,
    role_ping: str = ""
) -> str:
    """Builds native Discord broadcast for Sunday 20:00 weekly recap."""
    clean_ping = role_ping.strip()
    prefix = f"{clean_ping} " if clean_ping else ""

    header = (
        f"{prefix}[WinterArc] Weekly Community Recap 📊\n"
        "The week is officially in the books."
    )

    ai_section = ""
    if ai_speech:
        clean_ai = ai_speech.strip()
        ai_section = clean_ai if clean_ai.startswith(">") else f"> {clean_ai}"

    podium_lines = []
    for idx, w in enumerate(top_warriors[:3]):
        badge = ["🥇", "🥈", "🥉"][idx] if idx < 3 else f"#{idx+1}"
        d_id = w.get("discord_id")
        user_mention = f"<@{d_id}>" if d_id else f"**{w['username']}**"
        podium_lines.append(f"{badge} {user_mention} — **{w['points']} pts**")

    podium_block = "**🏆 Week's Top 3**\n" + ("\n".join(podium_lines) if podium_lines else "_No scores logged this week._")

    vol_lines = [
        f"• 💪 Push-ups: `{weekly_stats.get('total_pushups', 0):,}`",
        f"• 🧗 Pull-ups: `{weekly_stats.get('total_pullups', 0):,}`",
        f"• 🦵 Squats: `{weekly_stats.get('total_squats', 0):,}`",
        f"• 🧘 Sit-ups: `{weekly_stats.get('total_situps', 0):,}`",
        f"• 🏃 Running: `{weekly_stats.get('total_km', 0):,.1f} km`",
    ]
    vol_block = "**🌐 Community Workout Volume**\n" + "\n".join(vol_lines)

    subtext = "-# New weekly leaderboard begins tomorrow at 00:00 IST"

    sections = [header]
    if ai_section:
        sections.append(ai_section)
    sections.append(f"{podium_block}\n\n{vol_block}")
    sections.append(subtext)

    return "\n\n".join(sections)


def build_weekly_state_of_the_pack_embed(
    weekly_stats: Dict[str, Any],
    top_warriors: List[Dict[str, Any]],
    ai_speech: str
) -> discord.Embed:
    """Builds the Sunday 20:00 IST community broadcast embed."""
    podium_lines = []
    for idx, w in enumerate(top_warriors[:3]):
        badge = ["👑", "⚔️", "🛡️"][idx] if idx < 3 else f"#{idx+1}"
        podium_lines.append(f"{badge} **{w['username']}** — **{w['points']} pts**")

    ai_block = f"> {ai_speech}\n\n" if ai_speech else ""
    desc = (
        ai_block
        + "**🏆 Week's Podium**\n"
        + ("\n".join(podium_lines) if podium_lines else "_No scores logged this week._")
        + "\n\n**🌐 Community Total Volume**\n"
        f"• 💪 **Push-ups**: `{weekly_stats.get('total_pushups', 0):,}`\n"
        f"• 🧗 **Pull-ups**: `{weekly_stats.get('total_pullups', 0):,}`\n"
        f"• 🦵 **Squats**: `{weekly_stats.get('total_squats', 0):,}`\n"
        f"• 🧘 **Sit-ups**: `{weekly_stats.get('total_situps', 0):,}`\n"
        f"• 🏃 **Running**: `{weekly_stats.get('total_km', 0):,.1f} km`"
    )

    embed = discord.Embed(
        title="📊 Winter Arc — Weekly Community Recap",
        description=desc,
        color=0xF1C40F
    )
    embed.set_footer(text="New weekly leaderboard begins tomorrow at 00:00 IST")
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
            f"🧠 **Deep Work Grinds**: **{grind_count} sessions** *(+{grind_pts:,} pts)*\n\n"
            f"**Training Volume**\n"
            + ("\n".join(vol_lines) if vol_lines else "_No exercise volume logged yet._")
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
        f"*{p_sub}*\n\n"
        f"🏆 **Phase Rank**: {rank_str}\n"
        f"💎 **Phase Points**: **{pts:,} pts**\n"
        f"⭐ **Perfect Days**: **{perfect} days**\n"
        f"📅 **Active Days**: **{active} / {p_total_days} days**\n"
        f"🛡️ **Streak Shields Used**: **{shields}**\n"
        f"🧠 **Deep Work Sessions**: **{grind_count} logs** *(+{grind_pts:,} pts)*\n\n"
        f"**Training Volume**\n"
        + ("\n".join(vol_lines) if vol_lines else "_No exercise volume logged in this phase._")
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
    """Builds the end-of-phase podium and final standings embed."""
    p_name = phase.get("name", "PHASE")
    p_badge = phase.get("badge", "❄️")
    p_color = phase.get("color", 0x3498DB)

    top_3 = leaderboard[:3]
    podium_lines = []
    for idx, u in enumerate(top_3):
        crown = ["🥇", "🥈", "🥉"][idx]
        podium_lines.append(f"{crown} **{u['username']}** — **{u['total_points']:,} pts** ⭐ {u.get('perfect_days', 0)} perfect")

    other_lines = []
    for idx, u in enumerate(leaderboard[3:10], start=4):
        other_lines.append(f"`#{idx:02d}` **{u['username']}** — **{u['total_points']:,} pts**")

    desc = (
        f"⚔️ **The trial of {p_name} has officially concluded.**\n"
        f"*{phase.get('subtitle', '')}*\n\n"
        "👑 **THE PHASE PODIUM**\n"
        + ("\n".join(podium_lines) if podium_lines else "_No qualifiers._")
    )
    if other_lines:
        desc += "\n\n**Top Warriors**\n" + "\n".join(other_lines)

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
    clean_ping = role_ping.strip()
    prefix = f"{clean_ping} " if clean_ping else ""
    p_name = phase_dict.get("name", "Phase")
    p_num = phase_dict.get("id", 1)
    p_days = phase_dict.get("total_days", 31)

    header = (
        f"{prefix}[WinterArc] Phase {p_num} Concluded • {p_name} 🏆\n"
        f"{p_days} days of baseline execution locked in. Scores are now archived."
    )

    quote_section = ""
    if ceremony_speech:
        clean_speech = ceremony_speech.strip()
        quote_section = clean_speech if clean_speech.startswith(">") else f"> {clean_speech}"

    top_lines = []
    top_3 = phase_lb[:3]
    for idx, u in enumerate(top_3):
        badge = ["🥇", "🥈", "🥉"][idx]
        d_id = u.get("discord_id")
        user_mention = f"<@{d_id}>" if d_id else f"**{u['username']}**"
        clean = u.get("perfect_days", 0)
        clean_str = f" *({clean} perfect days)*" if clean > 0 else ""
        top_lines.append(f"{badge} {user_mention} — **{u['total_points']:,} pts**{clean_str}")

    runners_up = []
    for idx, u in enumerate(phase_lb[3:6], start=4):
        d_id = u.get("discord_id")
        user_mention = f"<@{d_id}>" if d_id else f"**{u['username']}**"
        runners_up.append(f"{idx}th: {user_mention} — **{u['total_points']:,} pts**")

    if runners_up:
        top_lines.append(" • ".join(runners_up))

    standings_block = f"**🏆 Phase {p_num} Top Standings**\n" + ("\n".join(top_lines) if top_lines else "_No participants recorded._")

    # Community stats
    total_pts = sum(u.get("total_points", 0) for u in phase_lb)
    total_clean = sum(u.get("perfect_days", 0) for u in phase_lb)
    active_count = len(phase_lb)

    totals_block = (
        f"**🌐 Community Phase {p_num} Totals**\n"
        f"• Active Participants: `{active_count}`\n"
        f"• Perfect Days Logged: `{total_clean}`\n"
        f"• Total Volume: `{total_pts:,} pts`"
    )

    next_block = ""
    if next_phase_dict:
        next_block = f"⚡ **{next_phase_dict['short_name']} ({next_phase_dict['name']})** begins tomorrow at 00:00 IST."

    subtext = "-# Phase snapshot archived • Streaks carry over uninterrupted"

    sections = [header]
    if quote_section:
        sections.append(quote_section)
    sections.append(standings_block)
    sections.append(totals_block)
    if next_block:
        sections.append(next_block)
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
        achievements_lines.append(f"🧠 **Most Grinded Member**: **{mg['sessions']} sessions** *(+{mg['points']:,} pts)* — {u_str}")
    else:
        achievements_lines.append("🧠 **Most Grinded Member**: _None yet_")

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
        f"🧠 **Deep Work Sessions**: **{st.get('deep_work_sessions', 0)} logs** *(+{st.get('deep_work_points', 0):,} pts)*",
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


STREAK_LEGEND_FOOTER = "🟩 Streaked • ⭐ Perfect Day (100%) • 🛡️ Shield Used • 🟥 Missed • ▫️ Upcoming"
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

