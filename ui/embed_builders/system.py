"""
ui/embed_builders/system.py - Help manual, streak shields, tips, user settings, and launch invite embeds.
"""

from __future__ import annotations

from typing import Dict, Any, Union
import discord

from config import MIN_STREAK_POINTS


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
