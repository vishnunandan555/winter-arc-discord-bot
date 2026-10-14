"""
ui/embed_builders/broadcasts.py - Embed builders and messages for scheduled morning, afternoon, evening, midnight broadcasts, weekly recaps, ceremonies, and private DMs.
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Dict, Any, List, Optional
import discord

import database as db
from config import BOT_TZ, MIN_STREAK_POINTS
from phases import get_current_phase, get_phase_progress
from ui.formatters import TASK_ICONS
from ui.embed_builders.common import (
    AUTHENTIC_REST_QUOTES,
    format_num,
    sanitize_display_text,
    get_midnight_reset_timestamp,
    _format_day_ordinal,
    is_recovery_day,
)


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


def build_morning_kickoff_embed(
    active_tasks: List[Dict[str, Any]],
    date_display: str,
    quote: Optional[str] = None,
    is_recovery: Optional[bool] = None,
) -> discord.Embed:
    """Builds the 05:00 morning kickoff broadcast embed with active phase context."""
    curr_phase = get_current_phase()
    today_recovery = is_recovery if is_recovery is not None else is_recovery_day(date_display)

    if today_recovery:
        import random
        rest_emoji = random.choice(["🌱", "🌿", "🍃", "🪴", "🧘"])
        embed = discord.Embed(
            title=f"❄️ Winter Arc — Rest & Recovery Day {rest_emoji}",
            color=0x27AE60
        )

        desc_lines = [
            f"📅 **{date_display}**",
            "The pack is on active recovery today. Movement is medicine — rebuild and adapt.",
        ]
        if curr_phase:
            prog = get_phase_progress(curr_phase)
            desc_lines.append(f"{curr_phase['badge']} **{curr_phase['name']}** — Day {prog['day_num']} of {prog['total_days']} ({prog['days_remaining']} days left in phase)")

        quote_text = sanitize_display_text(quote, random.choice(AUTHENTIC_REST_QUOTES)).strip()
        if quote_text:
            clean_q = quote_text.lstrip(">").strip()
            desc_lines.append(f"\n> {clean_q}")

        embed.description = "\n".join(desc_lines)

        protocol_lines = [
            "• **💧 Hydration**: Drink 3–4L of water; flush out metabolic fatigue",
            "• **🧘 Light Mobility**: 15–30 min casual walk or gentle full-body stretching",
            "• **🥗 Nutrition**: Nutrient-dense fuel and high-quality protein to repair muscle tissue",
            "• **😴 Restorative Sleep**: Aim for 8+ hours tonight; shut off screens early",
        ]
        embed.add_field(
            name="🌿 Active Recovery Protocol",
            value="\n".join(protocol_lines),
            inline=False
        )

        status_lines = [
            "• **Streaks Protected**: All warrior streaks remain locked in and preserved automatically ❤️",
            "• **Point Logging Paused**: No required disciplines or point ceilings for today",
            "• **Hunt Resumes Tomorrow**: Full challenge resumes tomorrow at 05:00 IST",
        ]
        embed.add_field(
            name="🛡️ Streak & Competition Status",
            value="\n".join(status_lines),
            inline=False
        )

        embed.set_footer(text="Winter Arc • Active Recovery Day (ARD) ❤️ • Streaks protected • Day resets at 00:00 IST")
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


def build_afternoon_checkin_embed(
    enrolled_users: List[Dict[str, Any]],
    today_str: str,
    quote: Optional[str] = None,
    is_recovery: Optional[bool] = None,
) -> discord.Embed:
    """Builds the 16:30 afternoon check-in broadcast embed."""
    today_recovery = is_recovery if is_recovery is not None else is_recovery_day(today_str)
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
    """Builds native Discord text broadcast for the 21:00 IST evening streak alert (3h before midnight)."""
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
    is_recovery: Optional[bool] = None,
) -> discord.Embed:
    """Builds the 21:00 IST evening streak alert channel broadcast embed (3 hours before midnight)."""
    today_recovery = is_recovery if is_recovery is not None else is_recovery_day(today_str)
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
