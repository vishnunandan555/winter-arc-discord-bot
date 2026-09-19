"""
ui/embeds.py - Reusable Discord Embed Builders for Winter Arc Bot

Centralizes all presentation styling, layout spacing, color palettes,
and progression information across user commands, admin tools, and scheduled announcements.
"""

from datetime import datetime, date
from typing import Dict, Any, List, Optional
import discord

import database as db
from config import BOT_TZ
from levels import get_level_info, get_all_ranks, APEX_THRESHOLD
from ui.formatters import make_progress_bar, format_rank_badge, TASK_ICONS


def build_daily_leaderboard_embed() -> discord.Embed:
    """Builds the spacious daily standing leaderboard embed."""
    now = datetime.now(BOT_TZ)
    today_str = now.strftime("%Y-%m-%d")
    date_display = now.strftime("%A, %B %d, %Y")
    data = db.get_daily_leaderboard(today_str)

    lines = []
    for idx, entry in enumerate(data):
        rank = format_rank_badge(idx)
        pct = int(entry["completion_rate"] * 100)
        pts = entry["points"]
        star = " ⭐" if entry["perfect_day"] else ""
        lines.append(f"{rank}  **{entry['username']}** — **{pts} pts** ({pct}%){star}")

    if not lines:
        lines.append("_No activity logged today yet. Use `/enroll` and `/log` to start._")

    embed = discord.Embed(
        title="🏆 Winter Arc — Daily Standings",
        description=(
            f"📅 **{date_display}**\n\n"
            + "\n\n".join(lines)
        ),
        color=0xF1C40F
    )
    embed.set_footer(text="Updated live • Resets daily at 00:00 IST")
    return embed


def build_overall_leaderboard_embed() -> discord.Embed:
    """Builds the all-time standings leaderboard with Winter Pack ranks."""
    data = db.get_overall_leaderboard()

    lines = []
    for idx, entry in enumerate(data):
        rank = format_rank_badge(idx)
        lvl_info = get_level_info(entry["total_points"])
        rank_tag = f"[{lvl_info['badge']} {lvl_info['title']}]"

        extras = []
        if entry.get("streak", 0) > 0:
            extras.append(f"🔥 {entry['streak']}d")
        if entry.get("perfect_days", 0) > 0:
            extras.append(f"⭐ {entry['perfect_days']} clean")
        extra_str = f"  •  {' • '.join(extras)}" if extras else ""
        lines.append(f"{rank}  **{entry['username']}** `{rank_tag}` — **{entry['total_points']:,} pts**{extra_str}")

    if not lines:
        lines.append("_No enrolled participants found._")

    embed = discord.Embed(
        title="🏆 Winter Arc — Overall Standings",
        description=(
            "🌐 **All-Time Standings**\n\n"
            + "\n\n".join(lines)
        ),
        color=0x3498DB
    )
    embed.set_footer(text="Updated live • Ranked by lifetime points")
    return embed


def build_monthly_leaderboard_embed(year: Optional[int] = None, month: Optional[int] = None) -> discord.Embed:
    """Builds the monthly standings leaderboard."""
    now = datetime.now(BOT_TZ)
    y = year or now.year
    m = month or now.month
    month_name = datetime(y, m, 1).strftime("%B %Y")
    data = db.get_monthly_leaderboard(y, m)

    lines = []
    for idx, entry in enumerate(data):
        rank = format_rank_badge(idx)
        pts = entry["total_points"]
        clean = entry.get("perfect_days", 0)
        clean_str = f" • ⭐ {clean} clean" if clean > 0 else ""
        lines.append(f"{rank}  **{entry['username']}** — **{pts:,} pts**{clean_str}")

    if not lines:
        lines.append(f"_No activity recorded for {month_name} yet._")

    embed = discord.Embed(
        title=f"📆 Winter Arc — {month_name} Standings",
        description=(
            f"🏆 **Monthly Leaderboard • {month_name}**\n\n"
            + "\n\n".join(lines)
        ),
        color=0x9B59B6
    )
    embed.set_footer(text="Updated live • Ranked by total points this month")
    return embed


def build_today_embed(target_user: discord.Member, progress: Dict[str, Any], streak: int, date_display: str) -> discord.Embed:
    """Builds the spacious daily progress card with physical disciplines and grind bonus."""
    task_lines = []
    for t in progress["tasks"]:
        icon = TASK_ICONS.get(t["name"].lower(), "🎯")
        cur = int(t["current_amount"]) if t["current_amount"].is_integer() else t["current_amount"]
        tgt = int(t["target"]) if t["target"].is_integer() else t["target"]
        check = " ✅" if t["completed"] else ""
        task_lines.append(f"{icon}  **{t['name']}** — {cur} / {tgt} {t['unit']} *({t['points_earned']} pts)*{check}")

    pct = int(progress["overall_completion_rate"] * 100)
    bar = make_progress_bar(progress["total_points"], progress["max_possible_points"], length=10)

    grind_pts = progress.get("grind_points", 0)
    grind_section = ""
    points_breakdown = ""
    if grind_pts > 0 or progress.get("grind_entry"):
        entry = progress.get("grind_entry") or {}
        learning = entry.get("key_learning", "Deep Work") if isinstance(entry, dict) else "Deep Work"
        grind_section = f"\n\n**🧠 Mental / Academic Friction**\n• **Grind Bonus**: +{grind_pts} pts *({learning})*"
        phys_pts = progress.get("physical_points", progress["total_points"] - grind_pts)
        points_breakdown = f"  *(Physical: {phys_pts} + Grind: {grind_pts})*"

    desc = (
        f"**{target_user.display_name}** • {date_display}\n\n"
        f"`{bar}`  **{progress['total_points']} / {progress['max_possible_points']} pts** ({pct}%){points_breakdown}\n"
        f"🔥 Current Streak: **{streak} days**\n\n"
        "**Daily Disciplines**\n"
        + "\n".join(task_lines)
        + grind_section
    )

    embed = discord.Embed(
        title="❄️ Winter Arc — Today",
        description=desc,
        color=0x1ABC9C if progress["perfect_day"] else 0x3498DB
    )
    embed.set_footer(text="Log with /log • Set with /set • Standings with /leaderboard")
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


def build_profile_embed(user: discord.Member, user_record: Dict[str, Any], streak: int, stats_data: Dict[str, Any]) -> discord.Embed:
    """Builds the comprehensive Member Profile card showcasing 12-level progression."""
    pts = stats_data.get("lifetime_points", 0)
    lvl = get_level_info(pts)

    tier_bar = make_progress_bar(lvl["points_in_tier"], lvl["tier_size"] if not lvl["is_apex"] else 1, length=10)
    arc_bar = make_progress_bar(pts, APEX_THRESHOLD, length=10)

    next_info = (
        f"Next: **{lvl['pts_to_next']:,} pts** to Level {lvl['level']+1} ({lvl['next_rank']['title']})"
        if not lvl["is_apex"] else "👑 **MAX LEVEL ACHIEVED (APEX)**"
    )

    desc = (
        f"**{user.display_name}**\n\n"
        f"🛡️ **Rank**: {lvl['badge']} **Level {lvl['level']} — {lvl['title']}**\n"
        f"`{tier_bar}` {lvl['tier_pct']}%\n"
        f"{next_info}\n\n"
        f"🔥 **Current Streak**: **{streak} days** • 🛡️ **Frost Shields**: **{user_record.get('frost_shields', 0)}/2**\n"
        f"💎 **Lifetime Points**: **{pts:,} pts**\n"
        f"🌐 **90-Day Arc Progress**: `{arc_bar}` {lvl['arc_pct']}%\n"
        f"📅 **Enrolled**: `{user_record['joined_at'][:10]}`"
    )

    embed = discord.Embed(
        title="🛡️ Winter Arc — Member Profile",
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


def build_help_embed() -> discord.Embed:
    """Builds the command manual and rules overview."""
    desc = (
        "**Daily Targets (500 pts max)**\n"
        "• 💪 **Push-ups**: 100 reps *(1 pt / rep)*\n"
        "• 🧗 **Pull-ups**: 100 reps *(1 pt / rep)*\n"
        "• 🦵 **Squats**: 100 reps *(1 pt / rep)*\n"
        "• 🧘 **Sit-ups**: 100 reps *(1 pt / rep)*\n"
        "• 🏃 **Running**: 10 km *(1 pt / 100m)*\n\n"
        "**Core Commands**\n"
        "• `/today` — Check your daily progress & streak\n"
        "• `/log [task] [amount]` — Add completed reps or km\n"
        "• `/set [task] [amount]` — Override count or reset to 0\n"
        "• `/profile` — Member card, level & rank progress\n"
        "• `/ranks` — View 12-level pack hierarchy\n"
        "• `/leaderboard` — Daily & all-time standings\n"
        "• `/stats` — Lifetime volume & records\n"
        "• `/history` — 7-day point history\n"
        "• `/enroll` • `/leave_arc` • `/ping`"
    )

    embed = discord.Embed(
        title="❄️ Winter Arc — Commands & Rules",
        description=desc,
        color=0x2B2D31
    )
    embed.set_footer(text="05:00 Kickoff • 16:30 Check-in • 00:00 Finalization (IST)")
    return embed


def build_morning_kickoff_embed(active_tasks: List[Dict[str, Any]], date_display: str) -> discord.Embed:
    """Builds the 05:00 morning kickoff broadcast embed."""
    task_lines = []
    for t in active_tasks:
        target_display = int(t["target"]) if t["target"].is_integer() else t["target"]
        task_lines.append(f"• **{t['name']}**: `{target_display} {t['unit']}` *(max {t['max_points']} pts)*")

    disciplines_block = "\n".join(task_lines) if task_lines else "_No active disciplines._"

    embed = discord.Embed(
        title=f"🌅 Winter Arc — Daily Kickoff • {date_display}",
        description=(
            "A new day has begun. 500 points available across 5 disciplines.\n\n"
            "**Daily Targets**\n"
            f"{disciplines_block}\n\n"
            "Log your sets with `/log` or check progress with `/today`."
        ),
        color=0x3498DB
    )
    embed.set_footer(text="Consistency beats motivation • Day resets at 00:00 IST")
    return embed


def build_afternoon_checkin_embed(enrolled_users: List[Dict[str, Any]], today_str: str) -> discord.Embed:
    """Builds the 16:30 afternoon check-in broadcast embed."""
    warrior_lines = []
    for u in enrolled_users:
        prog = db.get_user_daily_progress(u["discord_id"], today_str)
        pct = int(prog["overall_completion_rate"] * 100)
        star = " ⭐" if prog["perfect_day"] else ""
        warrior_lines.append(
            f"• **{u['username']}** — **{prog['total_points']} / {prog['max_possible_points']} pts** ({pct}%){star}"
        )

    embed = discord.Embed(
        title="⏰ Winter Arc — Afternoon Check-in",
        description=(
            "Midday check-in. Complete your remaining disciplines before midnight.\n\n"
            "**Today's Progress**\n"
            + ("\n\n".join(warrior_lines) if warrior_lines else "_No enrolled participants yet. Use `/enroll` to join!_")
        ),
        color=0xE67E22
    )
    embed.set_footer(text="Log sets with /log • Finalizes at 00:00 IST")
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
        rank = format_rank_badge(idx)
        perfect_star = " ⭐" if entry["perfect_day"] else ""
        if entry["perfect_day"]:
            perfect_count += 1
        pct = int(entry["completion_rate"] * 100)
        pts = entry["points"]
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


def build_dm_morning_embed(tasks: List[Dict[str, Any]], streak: int, date_display: str) -> discord.Embed:
    """Builds private morning briefing DM sent at 05:00 IST."""
    task_lines = [
        f"• **{t['name']}**: `{int(t['target']) if t['target'].is_integer() else t['target']} {t['unit']}` *(max {t['max_points']} pts)*"
        for t in tasks
    ]

    desc = (
        f"📅 **{date_display}**\n\n"
        f"🔥 **Your Streak**: **{streak} days**\n\n"
        "**Today's Challenge (500 pts ceiling)**\n"
        + "\n".join(task_lines)
        + "\n\n_Rise early. Move your body. Log your reps in the server with `/log`._"
    )

    embed = discord.Embed(
        title="🌅 Winter Arc — Morning Briefing",
        description=desc,
        color=0x00D2FF
    )
    embed.set_footer(text="Winter Arc • Consistency Beats Motivation")
    return embed


def build_dm_evening_embed(user: discord.User, progress: Dict[str, Any], streak: int, shield_status: Dict[str, Any]) -> discord.Embed:
    """Builds private evening streak warning DM sent at 21:00 IST (3h before midnight)."""
    pts = progress["total_points"]
    max_pts = progress["max_possible_points"]
    pct = int(progress["overall_completion_rate"] * 100)

    if progress["perfect_day"]:
        title = "⭐ Winter Arc — Perfect Day Secured!"
        color = 0x2ECC71
        desc = (
            f"Outstanding work, **{user.display_name}**.\n\n"
            f"You have reached **{pts} / {max_pts} pts** (100%) today.\n"
            f"Your **{streak}‑day streak** is fully protected at midnight.\n\n"
            "_Rest up and recover for tomorrow's grind._"
        )
    else:
        title = "⚠️ Winter Arc — Evening Streak Warning"
        color = 0xE74C3C
        shield_info = (
            f"\n\n🛡️ **Safety Net**: You have **{shield_status['frost_shields']} Frost Shield(s)**. "
            "If you cannot finish today, run `/shield use` in the server to protect your streak."
            if shield_status["frost_shields"] > 0
            else "\n\n⚠️ **No Frost Shields available!** Complete your disciplines to prevent your streak from resetting."
        )
        desc = (
            f"**{user.display_name}**, only **3 hours remain** before midnight (00:00 IST).\n\n"
            f"📊 **Today's Score**: **{pts} / {max_pts} pts** ({pct}%)\n"
            f"🔥 **Streak in Danger**: **{streak} days**"
            f"{shield_info}\n\n"
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
        cur = int(r["new_total"]) if r["new_total"].is_integer() else r["new_total"]
        tgt = int(r["target"]) if r["target"].is_integer() else r["target"]
        amt = int(r["amount_logged"]) if r["amount_logged"].is_integer() else r["amount_logged"]
        bar = make_progress_bar(r["new_total"], r["target"], length=8)
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
        + f"\n\n🐺 **Amarok**:\n> *\"{commentary}\"*"
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


