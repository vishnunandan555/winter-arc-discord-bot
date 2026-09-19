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
        ),
        color=0xF1C40F
    )
    footer_text = "Updated live • Resets daily at 00:00 IST"
    if len(data) > 10:
        footer_text = f"Showing top 10 of {len(data)} warriors • {footer_text}"
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
            clean_str = f" • ⭐ {clean} clean" if clean > 0 else ""
            lines.append(f"{badge} **{entry['username']}** — **{pts:,} pts**{clean_str}")

    embed = discord.Embed(
        title="🏆 Winter Arc — Weekly Standings",
        description=(
            f"📅 **Week of {date_display}**\n\n"
            + "\n".join(lines)
        ),
        color=0x2ECC71
    )
    footer_text = "Updated live • Ranked by weekly points (Mon–Sun)"
    if len(data) > 10:
        footer_text = f"Showing top 10 of {len(data)} warriors • {footer_text}"
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
            extras.append(f"⭐ {entry['perfect_days']} clean")
        extra_str = f" • {' '.join(extras)}" if extras else ""

        lines.append(f"{badge} **{entry['username']}** — **{pts:,} pts** *(Lvl {lvl_info['level']} {lvl_info['title']})*{extra_str}")

    if not lines:
        lines.append("_No enrolled warriors found._")

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
        footer_text = f"Showing top 10 of {len(data)} warriors • {footer_text}"
    embed.set_footer(text=footer_text)
    return embed


def build_monthly_leaderboard_embed(year: Optional[int] = None, month: Optional[int] = None) -> discord.Embed:
    """Builds the monthly standings leaderboard (max top 10)."""
    now = datetime.now(BOT_TZ)
    y = year or now.year
    m = month or now.month
    month_name = datetime(y, m, 1).strftime("%B %Y")
    data = db.get_monthly_leaderboard(y, m)
    top_10 = data[:10]

    any_points = any(entry["total_points"] > 0 for entry in top_10)
    lines = []
    if not any_points:
        lines.append(f"_No activity recorded for {month_name} yet._")
    else:
        for idx, entry in enumerate(top_10):
            pts = entry["total_points"]
            badge = format_rank_badge(idx, pts=pts)
            clean = entry.get("perfect_days", 0)
            clean_str = f" • ⭐ {clean} clean" if clean > 0 else ""
            lines.append(f"{badge} **{entry['username']}** — **{pts:,} pts**{clean_str}")

    embed = discord.Embed(
        title=f"📆 Winter Arc — {month_name} Standings",
        description=(
            f"🏆 **Monthly Leaderboard • {month_name}**\n\n"
            + "\n".join(lines)
        ),
        color=0x9B59B6
    )
    footer_text = "Updated live • Ranked by monthly points"
    if len(data) > 10:
        footer_text = f"Showing top 10 of {len(data)} warriors • {footer_text}"
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
        cur = int(t["current_amount"]) if float(t["current_amount"]).is_integer() else t["current_amount"]
        tgt = int(t["target"]) if float(t["target"]).is_integer() else t["target"]
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
        grind_section = f"\n\n**🧠 Mental / Academic Friction**\n• **Grind Bonus**: +{grind_pts} pts *({learning})*"
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
    embed.set_footer(text=f"Log with /log • {MIN_STREAK_POINTS} pts/day minimum for streak • 500 pts for Perfect Day")
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
        cur = int(t["current_amount"]) if float(t["current_amount"]).is_integer() else t["current_amount"]
        tgt = int(t["target"]) if float(t["target"]).is_integer() else t["target"]
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
        grind_section = f"\n\n**🧠 Mental / Academic Friction**\n• **Grind Bonus**: +{grind_pts} pts *({learning})*"
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


def build_log_embed(result: Dict[str, Any], amount: float, level_up_info: Optional[Dict[str, Any]] = None) -> discord.Embed:
    """Builds the confirmation embed after logging sets, including level up promotion banners."""
    cur = int(result["new_total"]) if result["new_total"].is_integer() else result["new_total"]
    tgt = int(result["target"]) if result["target"].is_integer() else result["target"]
    amt = int(amount) if amount.is_integer() else amount

    bar = make_progress_bar(result["new_total"], result["target"], length=8)
    delta_str = f"+{result['points_earned_delta']} pts" if result['points_earned_delta'] > 0 else "Capped"

    promo_banner = ""
    if level_up_info:
        promo_banner = (
            f"\n\n🎉 **RANK PROMOTION!**\n"
            f"You reached **Level {level_up_info['level']} — {level_up_info['badge']} {level_up_info['title']}**!\n"
        )
    if result.get("shield_awarded"):
        promo_banner += "\n\n🛡️ **FROST SHIELD EARNED!** You hit a 7-day streak milestone (+1 Shield added to inventory)."

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
    cur = int(result["new_total"]) if result["new_total"].is_integer() else result["new_total"]
    tgt = int(result["target"]) if result["target"].is_integer() else result["target"]
    prev = int(result["previous_total"]) if result["previous_total"].is_integer() else result["previous_total"]

    bar = make_progress_bar(result["new_total"], result["target"], length=8)

    promo_banner = ""
    if level_up_info:
        promo_banner = (
            f"\n\n🎉 **RANK PROMOTION!**\n"
            f"You reached **Level {level_up_info['level']} — {level_up_info['badge']} {level_up_info['title']}**!\n"
        )
    if result.get("shield_awarded"):
        promo_banner += "\n\n🛡️ **FROST SHIELD EARNED!** You hit a 7-day streak milestone (+1 Shield added to inventory)."

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
        vol = int(t["total_volume"]) if t["total_volume"].is_integer() else t["total_volume"]
        volume_lines.append(f"• **{t['name']}**: {vol:,} {t['unit']}")

    desc = (
        f"**{target_user.display_name}** • {lvl['badge']} **Level {lvl['level']}: {lvl['title']}**\n\n"
        f"🔥 **Current Streak**: {streak} days\n"
        f"⭐ **Clean Days**: {clean}\n"
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
    embed.set_footer(text="Winter Arc • Consistency Beats Motivation")
    return embed


def build_history_embed(user: discord.Member, hist: List[Dict[str, Any]]) -> discord.Embed:
    """Builds the 7-day point history card."""
    lines = []
    for d in reversed(hist):
        pct = int(d["completion_rate"] * 100)
        star = " ⭐" if d["perfect_day"] else ""
        lines.append(f"• `{d['date']}` — **{d['points']} pts** ({pct}%){star}")

    embed = discord.Embed(
        title="📜 Winter Arc — 7-Day History",
        description=f"**{user.display_name}**\n\n" + ("\n\n".join(lines) if lines else "_No history recorded yet._"),
        color=0x34495E
    )
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

    desc = (
        f"**{user.display_name}**\n\n"
        f"🏆 **All-Time Rank**: {rank_str}\n"
        f"🐺 **Pack Level**: **Level {lvl['level']} — {lvl['title']}** {lvl['badge']}\n"
        f"*{lvl['description']}*\n\n"
        f"📈 **Level Progression**\n"
        f"{progress_block}\n\n"
        f"🎯 **Today's Daily Progress**\n"
        f"{daily_block}\n\n"
        f"🔥 **Current Streak**: **{streak} days** • 🛡️ **Frost Shields**: **{user_record.get('frost_shields', 0)}/2**\n"
        f"💎 **Lifetime Points**: **{pts:,} pts**\n"
        f"📅 **Enrolled**: `{joined_date_str}`{days_note}"
    )

    embed = discord.Embed(
        title="🐺 Winter Arc — Warrior Profile",
        description=desc,
        color=lvl["color"]
    )
    if user.avatar:
        embed.set_thumbnail(url=user.avatar.url)

    embed.set_footer(text="Winter Arc • Discipline is Destiny")
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
        "**The 12-Level Winter Pack Hierarchy**\n"
        "Earn lifetime points across the 90-day arc to advance your rank:\n\n"
        + "\n".join(lines)
        + f"\n\nYour Current Standing: {user_lvl['badge']} **Level {user_lvl['level']}: {user_lvl['title']}** ({user_lvl['lifetime_points']:,} pts)"
    )

    embed = discord.Embed(
        title="🐺 Winter Arc — Pack Progression Hierarchy",
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
            title="⚡ Workout & AI Logging Manual",
            description=(
                "Log your physical and mental friction every single day.\n"
                "Amarok supports natural language parsing, rigid slash commands, and dedicated channel logging."
            ),
            color=0x3498DB
        )
        embed.add_field(
            name="🤖 `/quick [text]` — AI Workout Parser (Ultra-Fast Groq)",
            value=(
                "Log workouts using natural English. Automatically extracts exercises, aggregates sets, and converts miles to km.\n"
                "• **Example**: `/quick text: did 50 pushups, 25 pullups, and ran 3.5 km`\n"
                "• **Example**: `/quick text: 40 squats, 30 situps then 20 more squats`\n"
                "🛡️ *Safeguard*: Unrealistic volume will be rejected by Amarok."
            ),
            inline=False
        )
        embed.add_field(
            name="💬 Dedicated `#quick-log` Channel",
            value=(
                "Type your workout directly in `#quick-log` or `#fast-log` without any slash command prefix!\n"
                "Amarok will automatically parse the message, award your points, and react with 🐺."
            ),
            inline=False
        )
        embed.add_field(
            name="📝 Traditional Logging (`/log` & `/set`)",
            value=(
                "• `/log [task] [amount]` — Adds reps or km to your current daily count.\n"
                "• `/set [task] [amount]` — Overrides today's count directly. Set to `0` to wipe accidental entries."
            ),
            inline=False
        )
        embed.add_field(
            name="🧠 `/grind [friction]` — Academic & Engineering Bonus (Gemini AI)",
            value=(
                "Submit heavy mental disciplines (LeetCode, systems programming, thesis research, deep reading).\n"
                "• **Reward**: Up to **+50 bonus points** awarded directly to today's tally (Limit: 1/day).\n"
                "• **Example**: `/grind friction: Solved 2 hard graph DP problems on LeetCode and debugged OS scheduler for 3 hours`\n"
                "⚠️ *Zero Slop Policy*: Generic or low-effort submissions will be roasted and awarded 0 points."
            ),
            inline=False
        )
        embed.add_field(
            name="🐺 Amarok's Reactive Observations",
            value=(
                "When you log workouts or check progress (`/today`, `/tasks`, `/log`, `/quick`, `/streak`, `/profile`), "
                "Amarok occasionally whispers a terse, razor-sharp stoic observation from the shadows. "
                "These run asynchronously in the background so commands never experience any lag."
            ),
            inline=False
        )
        embed.set_footer(text="Use the menu below to navigate categories • Day resets at 00:00 IST")
        return embed

    elif category == "progress":
        embed = discord.Embed(
            title="📊 Progression, Ranks & Leaderboards",
            description="Track your daily execution, climb the 12 pack ranks, and conquer the 90-day arc.",
            color=0x9B59B6
        )
        embed.add_field(
            name="🎯 Daily Accountability",
            value=(
                "• `/today [member]` — Clean daily progress card with individual emoji progress bars, points, and completion rate.\n"
                "• `/tasks [member]` — Extended disciplines overview with individual emoji progress bars, targets, and exercise descriptions.\n"
                "• `/streak [member]` — Quick check of active streak days, clean days (100%), and Frost Shield protection status."
            ),
            inline=False
        )
        embed.add_field(
            name="🐺 12-Tier Rank Hierarchy",
            value=(
                "• `/profile [member]` — Complete warrior dossier with All-Time Rank (#X of Y), Pack Level, Next Level progression, and separate Daily Progress.\n"
                "• `/ranks` — Inspect all 12 pack ranks from **Lone Stray (Level 1, 0 pts)** to **Apex (Level 12, 12,000+ pts)**."
            ),
            inline=False
        )
        embed.add_field(
            name="🏆 Standings & History",
            value=(
                "• `/leaderboard` — Interactive podium view featuring **📅 Daily**, **📆 Monthly**, and **🌐 All-Time** rankings (top 10).\n"
                "• `/stats [member]` — Lifetime repetitions per discipline, total kilometers logged, and milestone records.\n"
                "• `/history [days]` — View point breakdown over the past 7, 14, or 30 days."
            ),
            inline=False
        )
        embed.set_footer(text="Consistency beats motivation • Apex rank unlocks at 12,000 points")
        return embed

    elif category == "shields":
        embed = discord.Embed(
            title="🛡️ Frost Shield & Recovery System",
            description=(
                "The Winter Arc demands relentless discipline, but smart recovery prevents collapse.\n"
                "Frost Shields protect your unbroken streak during rest days, sickness, travel, or exams."
            ),
            color=0x00D2FF
        )
        embed.add_field(
            name="❄️ How Frost Shields Work & Streaks",
            value=(
                f"• **Daily Streak Threshold**: Earn at least **{MIN_STREAK_POINTS} points** per day (e.g. 5 push-ups, 5 sit-ups, 5 squats, 5 pull-ups, 1 km run) to maintain your streak.\n"
                "• **Earning Shields**: You earn **+1 Frost Shield for every 7-day streak milestone**.\n"
                "• **Inventory Cap**: You can hold a maximum of **2 Frost Shields** at any time.\n"
                f"• **Auto-Protection**: If you finish a day under {MIN_STREAK_POINTS} points, a shield is automatically consumed at midnight to preserve your streak."
            ),
            inline=False
        )
        embed.add_field(
            name="🎮 Shield Commands",
            value=(
                "• `/shield status` — View your current shield count (e.g. `1/2`) and countdown days to the next shield unlock.\n"
                "• `/shield use [target_date] [reason]` — Consume a shield to protect your streak.\n"
                "  — `target_date`: Choose `Today` (preemptive) or `Yesterday` (rescue a missed day).\n"
                "  — `reason`: Optional label (e.g. *Leg day recovery, Travel, Sick*)."
            ),
            inline=False
        )
        embed.set_footer(text="Shields preserve your streak, but true progress comes from the iron.")
        return embed

    elif category == "settings":
        embed = discord.Embed(
            title="⚙️ Accountability, Settings & Utilities",
            description="Manage your participation and customize automated direct messages.",
            color=0x2ECC71
        )
        embed.add_field(
            name="🔔 `/settings` — Personal Direct Messages",
            value=(
                "Configure automated private DM alerts sent directly to your inbox:\n"
                "• 🌅 **Morning Kickoff DM (05:00 IST)**: Daily discipline targets and motivation.\n"
                "• ⚠️ **Evening Streak Warning DM (21:00 IST)**: Urgent reminder if you have unlogged points.\n"
                "*(Requires Discord privacy settings to allow DMs from server members)*"
            ),
            inline=False
        )
        embed.add_field(
            name="⚔️ Enrollment & Utilities",
            value=(
                "• `/enroll` — Join the Winter Arc challenge and establish your warrior profile.\n"
                "• `/leave_arc` — Unenroll from active server rosters (lifetime stats preserved).\n"
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
                "**Welcome to the Winter Arc.**\n"
                "A 90-day crucible of physical and mental discipline governed by **Amarok**.\n"
                "Use the interactive menu below to deep-dive into each subsystem."
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
                "• 🏃 **Running**: 10 km *(1 pt / 100m)*\n"
                "• 🧠 **Grind Bonus**: Up to +50 pts daily (`/grind`)"
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
                "• 🏆 `Sunday 20:00` — Weekly Roast/Toast & State of the Pack"
            ),
            inline=False
        )
        embed.add_field(
            name="⚡ Command Directory Cheat Sheet",
            value=(
                "• **Logging**: `/quick` • `/log` • `/set` • `/grind` • `#quick-log`\n"
                "• **Progress**: `/today` • `/tasks` • `/streak` • `/profile` • `/stats` • `/history`\n"
                "• **Standings**: `/leaderboard` • `/ranks`\n"
                "• **Recovery**: `/shield status` • `/shield use`\n"
                "• **Accountability**: `/settings` • `/enroll` • `/leave_arc` • `/ping`\n"
                "• **Admin**: `/admin overview` • `/admin health` • `/test_reminder`"
            ),
            inline=False
        )
        embed.set_footer(text="Select a category from the dropdown menu below for complete details")
        return embed


def build_morning_kickoff_embed(active_tasks: List[Dict[str, Any]], date_display: str, quote: Optional[str] = None) -> discord.Embed:
    """Builds the 05:00 morning kickoff broadcast embed."""
    task_lines = []
    for t in active_tasks:
        target_display = int(t["target"]) if t["target"].is_integer() else t["target"]
        task_lines.append(f"• **{t['name']}**: `{target_display} {t['unit']}` *(max {t['max_points']} pts)*")

    disciplines_block = "\n".join(task_lines) if task_lines else "_No active disciplines._"
    quote_section = f"\n\n🐺 **Amarok's Edict**:\n> *\"{quote}\"*" if quote else ""

    embed = discord.Embed(
        title=f"🌅 Winter Arc — Daily Kickoff • {date_display}",
        description=(
            "A new day has begun. 500 points available across 5 disciplines.\n\n"
            "**Daily Targets**\n"
            f"{disciplines_block}"
            f"{quote_section}\n\n"
            "Log your sets with `/log` or check progress with `/today`."
        ),
        color=0x3498DB
    )
    embed.set_footer(text="Consistency beats motivation • Day resets at 00:00 IST")
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

    quote_section = f"\n\n🐺 **Amarok**:\n> *\"{quote}\"*" if quote else ""

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

    quote_section = f"\n\n🐺 **Amarok's Final Call**:\n> *\"{quote}\"*" if quote else ""

    embed = discord.Embed(
        title="🌙 Winter Arc — Evening Streak Alert",
        description=desc.strip() + quote_section,
        color=0xE67E22
    )
    embed.set_footer(text=f"Log sets with /log • {MIN_STREAK_POINTS} pts/day minimum for streak • Rollover at 00:00 IST")
    return embed


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

    perfect_info = f"\n\n🔥 **Clean Sweeps**: **{perfect_count}** member(s) completed 100%." if perfect_count > 0 else ""

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
    shield_icons = "🛡️ " * shields + "⚪ " * (status["max_shields"] - shields)
    shield_icons = shield_icons.strip()

    active_tag = "🟢 **Active Today** (Rest day declared)" if status["is_today_shielded"] else "⚪ **Inactive** (Regular training day)"
    next_tag = f"**{status['days_until_next_shield']} day(s)** of clean streak until next shield" if shields < status["max_shields"] else "💎 **MAX SHIELDS STORED (2/2)**"

    history_lines = []
    for h in status.get("recent_uses", []):
        history_lines.append(f"• `{h['date']}` — {h['reason']}")

    desc = (
        f"**{user.display_name}** • Streak Protection\n\n"
        f"**Shield Inventory**: {shield_icons} `({shields}/{status['max_shields']})`\n"
        f"**Today's Status**: {active_tag}\n"
        f"🔥 **Current Streak**: **{status['current_streak']} days**\n"
        f"⏳ **Next Unlock**: {next_tag}\n\n"
        "**How Frost Shields Work**\n"
        "• **Earn**: +1 Shield earned every **7 consecutive streak days** *(cap 2)*.\n"
        "• **Manual Rest Day**: `/shield use` consumes 1 shield to protect your streak today.\n"
        "• **Midnight Safety Net**: If you miss your targets with an active streak, 1 shield is automatically consumed at 00:00 IST."
    )

    if history_lines:
        desc += "\n\n**Recent Recovery Days**\n" + "\n".join(history_lines)

    embed = discord.Embed(
        title="🛡️ Winter Arc — Frost Shield Status",
        description=desc,
        color=0x00D2FF
    )
    embed.set_footer(text="Consistency beats burnout • Rest with purpose")
    return embed


def build_shield_activated_embed(user: discord.Member, result: Dict[str, Any]) -> discord.Embed:
    """Builds confirmation embed after manually activating a Frost Shield."""
    embed = discord.Embed(
        title="🛡️ Frost Shield Activated",
        description=(
            f"**{user.display_name}**, your streak is protected for **{result['target_date']}**.\n\n"
            f"• **Remaining Shields**: `🛡️ {result['remaining_shields']} / 2`\n"
            f"• **Reason**: _{result['reason']}_\n\n"
            "Take today for intentional active recovery, hydration, and mental reset.\n"
            "Your streak will not break at midnight."
        ),
        color=0x2ECC71
    )
    embed.set_footer(text="Winter Arc • Rest Smart, Strike Harder Tomorrow")
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
        f"• **{t['name']}**: `{int(t['target']) if t['target'].is_integer() else t['target']} {t['unit']}` *(max {t['max_points']} pts)*"
        for t in tasks
    ]

    quote_section = f"\n\n🐺 **Amarok**:\n> *\"{quote}\"*" if quote else ""

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
    embed.set_footer(text="Winter Arc • Consistency Beats Motivation")
    return embed


def build_dm_evening_embed(user: discord.User, progress: Dict[str, Any], streak: int, shield_status: Dict[str, Any], quote: Optional[str] = None) -> discord.Embed:
    """Builds private evening streak warning DM sent at 21:00 IST (3h before midnight)."""
    pts = progress["total_points"]
    max_pts = progress["max_possible_points"]
    pct = int(progress["overall_completion_rate"] * 100)
    quote_section = f"\n\n🐺 **Amarok**:\n> *\"{quote}\"*" if quote else ""

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
            f"\n\n🛡️ **Safety Net**: You have **{shield_status['frost_shields']} Frost Shield(s)**. "
            "If you cannot finish today, an auto-shield will protect your streak at midnight."
            if shield_status["frost_shields"] > 0
            else f"\n\n⚠️ **No Frost Shields available!** Log {needed} more points before midnight to prevent your streak from resetting."
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
    embed.set_footer(text="Winter Arc • Discipline is Destiny")
    return embed


def build_grind_embed(user: discord.Member, result: Dict[str, Any], total_daily_points: int) -> discord.Embed:
    """Builds the confirmation embed for /grind evaluation."""
    verdict = result["verdict"]
    pts = result["points"]

    if verdict == "ACCEPTED":
        title = f"⚔️ Grind Accepted: +{pts} Points"
        color = 0x00D2FF
        icon = "🧠"
    elif verdict == "ROASTED":
        title = "🔥 Submission Roasted: 0 Points"
        color = 0xE67E22
        icon = "💀"
    else:
        title = "❌ Submission Rejected: 0 Points"
        color = 0x95A5A6
        icon = "⚪"

    learning_line = f"• **Key Focus**: `{result['key_learning']}`\n" if result.get("key_learning") and result["key_learning"] != "None" else ""

    desc = (
        f"**{user.display_name}** • Daily Intellectual Friction\n\n"
        f"{icon} **Verdict**: **{verdict}** (+{pts} bonus pts)\n"
        f"{learning_line}"
        f"📊 **Today's Total**: **{total_daily_points} pts**\n\n"
        f"🐺 **Amarok's Assessment**:\n"
        f"> *\"{result['commentary']}\"*"
    )

    embed = discord.Embed(
        title=title,
        description=desc,
        color=color
    )
    embed.set_footer(text="Winter Arc • Only real friction counts • Returns tomorrow at 00:00 IST")
    return embed


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
        cur = int(r["new_total"]) if float(r["new_total"]).is_integer() else r["new_total"]
        tgt = int(raw_tgt) if float(raw_tgt).is_integer() else raw_tgt
        amt = int(r["amount_logged"]) if float(r["amount_logged"]).is_integer() else r["amount_logged"]
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
        promo_banner += "\n\n🛡️ **FROST SHIELD EARNED!** You hit a 7-day streak milestone (+1 Shield added to inventory)."

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
    embed.set_footer(text="Winter Arc • Consistency Beats Motivation")
    return embed


def build_weekly_state_of_the_pack_embed(
    weekly_stats: Dict[str, Any],
    top_warriors: List[Dict[str, Any]],
    ai_speech: str
) -> discord.Embed:
    """Builds the Sunday 20:00 IST State of the Pack broadcast embed."""
    apex = top_warriors[0] if top_warriors else {"username": "Nobody", "points": 0}
    podium_lines = []
    for idx, w in enumerate(top_warriors[:3]):
        badge = ["👑", "⚔️", "🛡️"][idx] if idx < 3 else f"#{idx+1}"
        podium_lines.append(f"{badge} **{w['username']}** — **{w['points']} pts**")

    desc = (
        f"🐺 **Amarok's Weekly Address**:\n"
        f"> *\"{ai_speech}\"*\n\n"
        "**🏆 Week's Podium**\n"
        + ("\n".join(podium_lines) if podium_lines else "_No scores logged this week._")
        + "\n\n**🌐 Pack Cumulative Volume**\n"
        f"• 💪 **Push-ups**: `{weekly_stats.get('total_pushups', 0):,}`\n"
        f"• 🧗 **Pull-ups**: `{weekly_stats.get('total_pullups', 0):,}`\n"
        f"• 🦵 **Squats**: `{weekly_stats.get('total_squats', 0):,}`\n"
        f"• 🧘 **Sit-ups**: `{weekly_stats.get('total_situps', 0):,}`\n"
        f"• 🏃 **Running**: `{weekly_stats.get('total_km', 0):,.1f} km`"
    )

    embed = discord.Embed(
        title="🐺 Winter Arc — Sunday State of the Pack",
        description=desc,
        color=0xF1C40F
    )
    embed.set_footer(text="A new week dawns tomorrow at 05:00 IST • Rest and steel your resolve")
    return embed


