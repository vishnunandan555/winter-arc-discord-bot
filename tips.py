"""
tips.py - Winter Arc Bot Feature Tips & Community Guidance

Contains the comprehensive pool of bot usage tips, user-specific 10-minute timers,
and the 75% probability background dispatcher.
"""

import time
import random
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger("winter_arc.tips")

BOT_USAGE_TIPS: List[str] = [
    # 🏋️ /log — Incremental Workout Logging
    "💡 **Tip (`/log`)**: How to use: Type `/log [task] [amount]` to record completed reps or kilometers. Tab-autocomplete lets you select exercises and units in a fraction of a second!",
    "💡 **Tip (`/log`)**: Why `/log`? It is built for progressive tracking throughout your day—log 30 push-ups in the morning, 40 at lunch, and 30 at night without ever having to calculate your daily sum.",
    "💡 **Tip (`/log`)**: Pro Tip: Every single rep logged counts toward your 12-tier discipline rank, even if you don't hit the full 100-rep daily cap.",

    # ✏️ /set — Direct Count Overrides & Reset
    "💡 **Tip (`/set`)**: How to use: Made an error or logged the wrong exercise? Directly correct today's exact count using `/set [task] [amount]`.",
    "💡 **Tip (`/set`)**: Why `/set`? It provides an instant self-serve fix for honest mistakes—entering `0` wipes an accidental entry clean without needing server admin help.",
    "💡 **Tip (`/set`)**: Pro Tip: While `/log` adds reps to your current count, `/set` replaces today's total and immediately recalculates your daily score.",

    # ⚡ /quick — Natural Language AI Logging
    "💡 **Tip (`/quick`)**: How to use: Type `/quick 40 pushups, 20 squats, 5km run` to parse and record multiple exercises in a single message via Groq AI.",
    "💡 **Tip (`/quick`)**: Why `/quick`? Post-workout friction kills consistency. `/quick` extracts reps, sets, and distances from everyday shorthand in under a second.",
    "💡 **Tip (`/quick`)**: Pro Tip: `/quick` understands natural abbreviations and mixed formatting like `45 push ups, 20 pull-ups, 5.5k run` all in a single command!",

    # ⚔️ /grind — Custom Workouts & Deep Work
    "💡 **Tip (`/grind`)**: How to use: Submit custom workouts (Surya Namaskar, gym, skipping, yoga) or deep work with `/grind [text]` to earn **+5 to +50 bonus points** toward today's score!",
    "💡 **Tip (`/grind`)**: Why `/grind`? Winter Arc rewards body and mind—earning points for custom workouts outside the 5 core tasks and tough intellectual focus.",
    "💡 **Tip (`/grind`)**: Pro Tip: Core checklist tasks (pushups, squats, pullups, situps, running) are excluded from `/grind` to prevent double-counting. Log those with `/quick` or `/log`!",

    # 📅 /streak — Habit Calendar Matrix & Consistency
    "💡 **Tip (`/streak`)**: How to use: Run `/streak` to view your personal habit grid, current streak count, peak streak record, and shield inventory.",
    "💡 **Tip (`/streak`)**: Why `/streak`? Inspired by GitHub contribution graphs, visual streak squares create psychological momentum that makes breaking the chain painful.",
    "💡 **Tip (`/streak`)**: Pro Tip: Click the **Calendar** button below your `/streak` embed to inspect the entire 92-day 3-phase campaign calendar (Oct 1 – Dec 31)!",

    # 🗓️ /calendar — Full 3-Phase Campaign Habit Calendar
    "💡 **Tip (`/calendar`)**: How to use: Run `/calendar` to directly view your full 92-day 3-phase habit calendar matrix (Oct 1 – Dec 31) with an interactive button to switch back to `/streak`!",

    # 📊 /today — Daily Progress Dashboard
    "💡 **Tip (`/today`)**: How to use: Run `/today` to inspect your live daily checklist, individual exercise progress bars, daily points total, and streak status.",
    "💡 **Tip (`/today`)**: Why `/today`? It gives you instant clarity on how close you are to today's 500-point ceiling and whether your streak is already locked in.",
    "💡 **Tip (`/today`)**: Pro Tip: Accountability partner check! You can inspect any teammate's live daily progress card with `/today [member]`.",

    # 📋 /tasks — Daily Disciplines & Target Guide
    "💡 **Tip (`/tasks`)**: How to use: Run `/tasks` to see full discipline targets, point values, muscle groups targeted, and current completion bars.",
    "💡 **Tip (`/tasks`)**: Why `/tasks`? It defines the campaign standard: Push-ups (100), Pull-ups (100), Squats (100), Sit-ups (100), and Running (10 km) for complete physical balance.",
    "💡 **Tip (`/tasks`)**: Pro Tip: Notice the muscle group tags! Balancing upper body, core, legs, and cardio ensures you build durable functional fitness without overtraining.",

    # 📜 /history — Reverse-Chronological Workout Logs
    "💡 **Tip (`/history`)**: How to use: Review your past performance and completion rates over the last 7, 14, or 30 days with `/history [days]`.",
    "💡 **Tip (`/history`)**: Why `/history`? Reviewing past weeks reveals patterns in your discipline, highlights recovery needs, and archives past AI grind notes.",
    "💡 **Tip (`/history`)**: Pro Tip: You can also audit an accountability partner's log with `/history [member]` to see their daily point consistency over time.",

    # 🛡️ /shield status & /shield use — Streak Preservation
    "💡 **Tip (`/shield status`)**: How to use: Check your current Streak Shield inventory, safety net state, and countdown to your next shield with `/shield status`.",
    "💡 **Tip (`/shield status`)**: Why `/shield status`? It lets you check your protection cushion, ensuring you know your streak is safe if a busy day prevents training.",
    "💡 **Tip (`/shield use`)**: How to use: Streak Shields are 100% automated! If you miss a day (< 30 pts), an available shield is automatically used at midnight (00:00 IST) to preserve your streak.",
    "💡 **Tip (`/shield use`)**: Why Streak Shields? A day is only missed if you run out of shields! Consistency is about longevity, not breaking momentum over an unexpected emergency.",
    "💡 **Tip (`/shield`)**: Pro Tip: You earn **+1 Streak Shield** for every 7 consecutive days of active streak (hold up to 2 maximum).",
    "💡 **Tip (`/shield`)**: Pro Tip: Safety net! If you miss a day with an active streak, an available Streak Shield is automatically deployed at midnight rollover!",

    # 🎖️ /profile — Personal Warrior Card
    "💡 **Tip (`/profile`)**: How to use: Inspect your personal warrior card with `/profile`—view your current discipline tier badge, all-time standing (#X of Y), and lifetime points.",
    "💡 **Tip (`/profile`)**: Why `/profile`? It tracks your macro journey over the entire 90-day arc, celebrating sustained dedication beyond single days.",
    "💡 **Tip (`/profile`)**: Pro Tip: You can inspect any member's profile card with `/profile [member]` to see their rank badge and lifetime volume.",

    # 🗺️ /ranks — 12-Tier Discipline Hierarchy
    "💡 **Tip (`/ranks`)**: How to use: Run `/ranks` to inspect the full 12-tier discipline roadmap from **Initiate (0 pts)** all the way to **Apex (12,000+ pts)**.",
    "💡 **Tip (`/ranks`)**: Why `/ranks`? Calibrated for the 90-day challenge (~133 pts/day average to reach Apex), giving you achievable milestones every single week.",
    "💡 **Tip (`/ranks`)**: Pro Tip: Each rank tier has its own signature icon and prestige color. Reaching Titan or Apex cements your legacy on the server wall of fame!",

    # 🏆 /leaderboard — Weekly, Monthly & All-Time Podiums
    "💡 **Tip (`/leaderboard`)**: How to use: See who's leading the pack with `/leaderboard`! Use the interactive buttons to switch between Weekly, Monthly, and All-Time standings.",
    "💡 **Tip (`/leaderboard`)**: Why `/leaderboard`? Friendly tribal competition pushes everyone to eliminate excuses and hit higher standards.",
    "💡 **Tip (`/leaderboard`)**: Pro Tip: The Weekly podium runs Sun–Sat and resets every Sunday, giving every member a fresh shot at glory no matter when they enrolled!",

    # ⚖️ /accuse — Community Governance & Council Trials
    "💡 **Tip (`/accuse`)**: How to use: Suspect an exaggerated or illegitimate workout log? Run `/accuse [member]` to confirm your challenge and summon the Council to vote on stripping the points!",

    # 📈 /stats — Server Records & Community Volume
    "💡 **Tip (`/stats`)**: How to use: Explore server-wide records, all-time longest streaks, single-day peak maxers, and community volume across all phases with `/stats`.",
    "💡 **Tip (`/stats`)**: Why `/stats`? It honors peak individual performances while showcasing the collective strength of the entire server.",
    "💡 **Tip (`/stats`)**: Pro Tip: Check the 'Single-Day Peak' record—can you beat the server record for the highest points logged in a single 24-hour cycle?",

    # 🗂️ /recap — Phase Performance Snapshots
    "💡 **Tip (`/recap`)**: How to use: Explore detailed phase-by-phase performance summaries and exercise volume breakdowns with `/recap [member]`.",
    "💡 **Tip (`/recap`)**: Why `/recap`? Each official Winter Arc phase has distinct psychological challenges; `/recap` permanently archives your achievements across each phase.",
    "💡 **Tip (`/recap`)**: Pro Tip: Run `/recap` at the end of Phase 1 (Foundation) or Phase 2 (Intensity) to see your total reps accumulated across the month!",

    # 🔔 /reminders & /settings — Personal DM Reminders
    "💡 **Tip (`/reminders`)**: How to use: Never miss a streak deadline! Toggle private morning kickoff (05:00 IST), afternoon check-in (16:30 IST), and evening streak alert (21:00 IST) DMs with `/reminders` or `/settings`.",
    "💡 **Tip (`/reminders`)**: Why `/reminders`? Direct message alerts keep you accountable with personalized AI briefings and reminders without public server noise.",
    "💡 **Tip (`/reminders`)**: Pro Tip: The 21:00 IST evening alert fires only if your streak is in jeopardy, giving you 3 hours and showing your Streak Shield status before midnight rollover.",

    # ⚔️ /enroll & /leave_arc — Challenge Membership
    "💡 **Tip (`/enroll`)**: How to use: New to the challenge? Run `/enroll` to join the pack, receive your server challenge role, and start tracking points on the leaderboard.",
    "💡 **Tip (`/enroll`)**: Why `/enroll`? Enrolling is your formal commitment contract with the server—it unlocks live tracking, streak protection, and automated DM check-ins.",
    "💡 **Tip (`/leave_arc`)**: How to use: Need to step away from the challenge? Use `/leave_arc` to unenroll peacefully—your past logs remain securely archived if you return.",
    "💡 **Tip (`/leave_arc`)**: Why `/leave_arc`? Life happens. It gives you full control over your participation without deleting your historical workout accomplishments.",

    # 📖 /help — Master Interactive Manual
    "💡 **Tip (`/help`)**: How to use: Got questions about rules, scoring, or schedules? Run `/help` to open the interactive command directory and master manual.",
    "💡 **Tip (`/help`)**: Why `/help`? Instead of static walls of text, `/help` features a categorized interactive dropdown for fast reference during training.",
    "💡 **Tip (`/help`)**: Pro Tip: Check the 'AI Logging Guide' category in `/help` to learn all the natural language formatting tricks for `/quick`.",

    # 🏓 /ping — Health & Latency Check
    "💡 **Tip (`/ping`)**: How to use: Check the bot's live gateway WebSocket latency and API response time with `/ping`.",
    "💡 **Tip (`/ping`)**: Why `/ping`? A quick way to verify that the bot is responsive and connected before logging important workout sets.",
    "💡 **Tip (`/ping`)**: Pro Tip: Shows gateway ping in milliseconds—low ping ensures your instant AI evaluations and streak calculations execute in real time.",

    # ⏰ Daily Rules & Streak Threshold
    "💡 **Tip (Streak Threshold)**: Why 30 points? It represents the non-negotiable minimum—even on your busiest or most exhausting days, doing 5 reps of each discipline keeps the habit alive.",
    "💡 **Tip (Daily Reset)**: The board finalizes at **00:00 IST** every night. Max out your 500 points before midnight to claim a **Perfect Day (⭐)**!",
]

_last_tip_timestamps: Dict[int, float] = {}
_user_seen_tips: Dict[int, List[int]] = {}

TIP_COOLDOWN_SECONDS: float = 600.0  # Exactly 10 minutes per user
TIP_ROLL_CHANCE: float = 0.75         # 75% probability after timer expires


def should_send_tip(user_id: int, force: bool = False, roll_chance: float = TIP_ROLL_CHANCE) -> bool:
    """
    Evaluates whether a tip should be dispatched:
    1. If within the 10-minute timer for this user, probability check is skipped entirely.
    2. Once 10 minutes have elapsed, executes the 75% probability roll.
    """
    if force:
        return True

    now = time.time()
    last_time = _last_tip_timestamps.get(user_id, 0.0)
    elapsed = now - last_time

    # User-specific 10-minute timer guard
    if elapsed < TIP_COOLDOWN_SECONDS:
        rem_min = int((TIP_COOLDOWN_SECONDS - elapsed) // 60)
        logger.debug(f"Tip check for user {user_id}: skipped (timer active for {rem_min}m).")
        return False

    # Execute 75% probability calculation
    roll = random.random()
    if roll <= roll_chance:
        logger.info(f"Tip check for user {user_id}: triggered (roll {roll:.2f} <= {roll_chance}).")
        return True

    logger.debug(f"Tip check for user {user_id}: skipped (roll {roll:.2f} > {roll_chance}).")
    return False


def get_tip_for_user(user_id: int) -> str:
    """
    Returns an unrepeated tip for the user and records the timestamp to start the 10-minute timer.
    """
    seen = _user_seen_tips.get(user_id, [])
    available_indices = [i for i in range(len(BOT_USAGE_TIPS)) if i not in seen]

    if not available_indices:
        seen = []
        available_indices = list(range(len(BOT_USAGE_TIPS)))

    chosen_idx = random.choice(available_indices)
    seen.append(chosen_idx)
    _user_seen_tips[user_id] = seen

    _last_tip_timestamps[user_id] = time.time()
    return BOT_USAGE_TIPS[chosen_idx]


async def dispatch_tip(
    interaction_or_channel: Any,
    user_id: int,
    user_name: str,
    force: bool = False,
    message: Optional[Any] = None
) -> None:
    """
    Non-blocking background dispatcher that sends a separate tip message
    if the user's 10-minute timer has expired and the 75% roll succeeds.
    """
    if not should_send_tip(user_id, force=force):
        return

    try:
        tip_text = get_tip_for_user(user_id)
        content = f"<@{user_id}> {tip_text}"

        channel = getattr(interaction_or_channel, "channel", None)
        if not channel and hasattr(interaction_or_channel, "client") and hasattr(interaction_or_channel, "channel_id"):
            channel = interaction_or_channel.client.get_channel(interaction_or_channel.channel_id)

        # If it's a direct TextChannel or message reply context
        if message and hasattr(message, "reply"):
            try:
                await message.reply(tip_text, mention_author=True)
                logger.info(f"Dispatched tip reply for {user_name}: '{tip_text[:40]}...'")
                return
            except Exception as reply_err:
                logger.debug(f"Could not reply tip to message: {reply_err}")

        sent = False
        if channel and hasattr(channel, "send"):
            try:
                await channel.send(content)
                sent = True
                logger.info(f"Dispatched tip to #{getattr(channel, 'name', 'chat')} for {user_name}: '{tip_text[:40]}...'")
            except Exception as send_err:
                logger.debug(f"Could not send tip via channel.send: {send_err}")

        if not sent and hasattr(interaction_or_channel, "followup"):
            try:
                await interaction_or_channel.followup.send(content)
                logger.info(f"Dispatched tip via followup for {user_name}: '{tip_text[:40]}...'")
            except Exception as followup_err:
                logger.debug(f"Could not send tip via followup: {followup_err}")
    except Exception as e:
        logger.debug(f"Could not dispatch tip for {user_name}: {e}")
