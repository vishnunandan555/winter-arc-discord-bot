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
    # ⚡ Fast & Multi-Logging
    "💡 **Tip**: Log multiple exercises at once with `/quick` (e.g. `/quick 40 pushups, 20 squats, 5km run`).",
    "💡 **Tip**: You can log directly in the `#quick-log` channel just by typing numbers and exercises without any slash command!",
    "💡 **Tip**: Made a typo? Override your count directly with `/set [task] [amount]` (or set 0 to reset).",

    # 🛡️ Streaks & Streak Shields
    "💡 **Tip**: You only need **30 points a day** (e.g. 5 pushups, 5 pullups, 5 squats, 5 situps, 1km run) to keep your streak alive.",
    "💡 **Tip**: You earn **+1 Streak Shield** for every 7-day streak milestone you achieve (hold up to 2 shields).",
    "💡 **Tip**: Sick, traveling, or need recovery? Use `/shield use` to activate a Streak Shield and protect your streak without penalty.",
    "💡 **Tip**: Check your active streak days, shield inventory, and next milestone unlock anytime with `/streak` or `/shield status`.",
    "💡 **Tip**: If you miss a day with an active streak, a Streak Shield is automatically consumed at midnight as a safety net.",

    # 🧠 Deep Work & Academics
    "💡 **Tip**: Boost your daily score with `/grind`! Earn **+10 to +60 bonus points** daily for verified technical study or engineering work.",
    "💡 **Tip**: `/grind` is strictly evaluated by Gemini AI—passive videos and casual reading get roasted; only focused deep work gets rewarded.",

    # 📊 Dashboards & Analytics
    "💡 **Tip**: Use `/today` to inspect your daily checklist, points breakdown, and live streak status.",
    "💡 **Tip**: Use `/tasks` to view exercise descriptions, muscle groups targeted, and individual progress bars.",
    "💡 **Tip**: Check server-wide records, single-day PRs, and community volume across all phases with `/stats`.",
    "💡 **Tip**: Explore your past phase breakdowns and cumulative performance snapshots anytime with `/recap`.",
    "💡 **Tip**: Inspect your daily point history and completion rates over the past 7, 14, or 30 days with `/history`.",

    # 🎖️ Ranks, Leaderboards & Settings
    "💡 **Tip**: Climb the 12-tier discipline hierarchy from **Initiate (0 pts)** to **Apex (12,000+ pts)**. View the roadmap with `/ranks`.",
    "💡 **Tip**: Check your current rank badge, all-time standing, and XP needed for your next level with `/profile`.",
    "💡 **Tip**: See who's leading the server today, this week, this month, and all-time with `/leaderboard`.",
    "💡 **Tip**: Never forget to log! Enable private morning and evening DM reminders with `/settings`.",
    "💡 **Tip**: The board resets at **00:00 IST** every night. Lock in your volume before midnight to claim a Perfect Day!",
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
