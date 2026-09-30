"""
dm_templates.py - Centralized Custom DM Templates for Winter Arc

This file contains pre-configured message templates that administrators
can select from when using `/admin dm`.

You can freely add new templates, modify existing text, or customize titles and descriptions below.
"""

from typing import Dict, Any, Optional
import discord


def build_launch_invitation(username: str, channel_id: int) -> discord.Embed:
    """Builds the full official Winter Arc launch invitation embed."""
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


# Registry of templates available in `/admin dm`
DM_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "launch_invite": {
        "name": "❄️ Winter Arc Launch Invitation (Oct 1)",
        "description": "The official invitation explaining last year's lessons, 4 phases, 30pt streaks, and notifications.",
        "type": "embed_builder",
        "builder": build_launch_invitation,
    },
    "custom_message_1": {
        "name": "📝 Custom Message 1 (General Announcement)",
        "title": "❄️ Winter Arc Announcement",
        "description": (
            "Hi **{username}**,\n\n"
            "This is a direct message regarding Winter Arc 2026.\n\n"
            "Stay locked in, stay consistent, and remember to log your progress daily in {channel}.\n\n"
            "Consistency beats motivation."
        ),
        "color": 0x3498DB,
        "footer": "Winter Arc 2026 • Official Announcement"
    },
    "custom_message_2": {
        "name": "📝 Custom Message 2 (Mid-Week Check-in)",
        "title": "⚡ Winter Arc Check-in",
        "description": (
            "Hi **{username}**,\n\n"
            "Just checking in on your Winter Arc journey.\n\n"
            "How are your daily goals looking? Remember, even reaching 30 points keeps your streak intact!\n\n"
            "Keep pushing forward in {channel}."
        ),
        "color": 0x2ECC71,
        "footer": "Winter Arc 2026 • Accountability Check"
    },
    "custom_message_3": {
        "name": "📝 Custom Message 3 (Discipline Motivation)",
        "title": "⚔️ Discipline Over Motivation",
        "description": (
            "Hi **{username}**,\n\n"
            "Motivation is fleeting. Discipline is permanent.\n\n"
            "When the cold sets in and you don't feel like showing up, that's when the real progress is made.\n\n"
            "Show up today and claim your streak."
        ),
        "color": 0xE74C3C,
        "footer": "Winter Arc 2026 • The Standard"
    }
}


def get_template(key: str) -> Optional[Dict[str, Any]]:
    """Retrieves template configuration by key."""
    return DM_TEMPLATES.get(key)


def build_message_from_template(
    template_key: str,
    username: str,
    channel_id: int,
    extra_text: Optional[str] = None
) -> discord.Embed:
    """Builds a formatted discord.Embed for the given template key and recipient."""
    ch_mention = f"<#{channel_id}>" if channel_id else "the dedicated Winter Arc channel"
    tmpl = DM_TEMPLATES.get(template_key)

    if not tmpl:
        # Fallback if raw text was passed instead of template key
        embed = discord.Embed(
            title="📩 Message from Winter Arc Staff",
            description=template_key,
            color=0x3498DB
        )
        if extra_text:
            embed.description += f"\n\n{extra_text}"
        embed.set_footer(text="Winter Arc 2026")
        return embed

    if tmpl.get("type") == "embed_builder" and "builder" in tmpl:
        embed = tmpl["builder"](username, channel_id)
        if extra_text:
            embed.add_field(name="📌 Additional Note", value=extra_text, inline=False)
        return embed

    # Standard dictionary template
    title = tmpl.get("title", "❄️ Winter Arc Notification")
    desc_template = tmpl.get("description", "")
    rendered_desc = desc_template.format(username=username, channel=ch_mention)

    if extra_text:
        rendered_desc += f"\n\n**Note**: {extra_text}"

    embed = discord.Embed(
        title=title,
        description=rendered_desc,
        color=tmpl.get("color", 0x3498DB)
    )
    if "footer" in tmpl:
        embed.set_footer(text=tmpl["footer"])
    return embed
