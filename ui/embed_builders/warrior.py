"""
ui/embed_builders/warrior.py - Embed builders and reply formatters for individual warrior commands, disciplines, progression, and streaks.
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Dict, Any, List, Optional
import discord

import database as db
from config import BOT_TZ, MIN_STREAK_POINTS
from levels import get_level_info, get_all_ranks
from ui.formatters import make_progress_bar, TASK_ICONS
from ui.embed_builders.common import (
    format_num,
    get_midnight_reset_timestamp,
    STREAK_LEGEND_FOOTER,
    is_recovery_day,
)


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

    rank_str = f"**#{all_time_rank}** of {total_warriors}" if all_time_rank > 0 else "Unranked"

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

    joined_date_str = user_record.get("joined_at", "")[:10]
    days_note = ""
    if joined_date_str:
        try:
            j_date = datetime.fromisoformat(joined_date_str).date()
            diff_days = (datetime.now(BOT_TZ).date() - j_date).days + 1
            days_note = f" *(Day {diff_days} in Arc)*"
        except Exception:
            pass

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
    embed.set_footer(text="Evaluated by AI • 1 grind submission allowed per day (max 50 pts)")
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
