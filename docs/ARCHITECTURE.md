# 🏗️ Winter Arc Bot & Dashboard Architecture

Technical design specification, component separation, database schema, and scoring logic for the **Winter Arc** ecosystem.

---

## 1. System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                    Discord Gateway API                      │
└──────────────────────────────┬──────────────────────────────┘
                               │ WebSocket / Slash Commands
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    WinterArcBot (bot.py)                    │
│   • Gateway lifecycle                                       │
│   • Cog discovery & extension loading                       │
│   • Global slash command tree synchronization               │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────────────┐┌─────────────────────────────┐
│      cogs.warrior            ││        cogs.admin           │
│  • /enroll, /leave_arc       ││  • /admin overview         │
│  • /today, /log, /set        ││  • /admin set_channel, role │
│  • /streak, /calendar        ││  • /admin dm, /admin tasks  │
│  • /profile, /ranks          ││  • /admin grind (probation) │
│  • /leaderboard, /stats      ││  • /nuke (Owner 2FA Purge)  │
│  • /history, /recap, /quick  ││  • /test_reminder           │
│  • /grind, /reminders, /tips ││                             │
│  • /accuse (Council trial)   ││                             │
└──────────────┬───────────────┘└─────────────┬───────────────┘
               │                              │
               ▼                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Presentation Layer (ui/)                  │
│   • ui.formatters: Progress bars, rank badges, icons        │
│   • ui.embeds: Single-card Discord embeds & Amarok voice    │
│   • ui.views: CouncilVotingView, AccuseConfirmView, tabs    │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────────────┐┌─────────────────────────────┐
│       levels.py              ││      helpers.py             │
│  • 12-level pack hierarchy   ││  • require_enrolled guard   │
│  • Tier progress & thresholds││  • task_autocomplete        │
│  • check_level_up triggers   ││  • get_or_create_arc_role   │
└──────────────┬───────────────┘└─────────────┬───────────────┘
               │                              │
               ▼                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Database Layer (database.py)              │
│   • SQLite WAL mode with foreign keys                       │
│   • Dual logging (additive /log, absolute /set)             │
│   • Daily 500 pt ceiling capping & streak calculus          │
│   • Live stats aggregation & midnight finalization          │
│   • grind_logs, shield_logs, and disciplinary probation     │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│                 WinterArcScheduler (scheduler.py)           │
│   • 05:00 IST: Morning Kickoff (silent) + AI Briefing DMs   │
│   • 16:30 IST: Midday Progress (silent) + Progress DMs      │
│   • 21:00 IST: Evening Warning (silent) + Streak Alert DMs  │
│   • Sun 10:00 IST: Weekly Community Recap                   │
│   • 00:00 IST: Midnight finalization & podium broadcast     │
│   • Month-end 00:00 IST: Phase Conclusion Ceremony         │
│   • Real-time web export hook (export_web_stats.py)         │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│               Static Web Dashboard (docs/)                  │
│   • index.html + style.css + app.js                         │
│   • stats.json data store                                   │
│   • Hosted via GitHub Pages / Vercel                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Directory Structure

```text
winter-arc-bot/
├── config.py                 # Centralized environment variables, TZ, role ID, logger
├── database.py               # SQLite data access layer and scoring math
├── levels.py                 # 12-level Winter Pack progression engine
├── phases.py                 # 4-phase calendar & recap definitions
├── helpers.py                # Reusable guards, role resolver, safe reactions
├── tips.py                   # Contextual tips engine & rate limits
├── ai/                       # Modular AI reasoning and NLP services
│   ├── models.py             # Pydantic schemas, payload structures & error types
│   ├── fallbacks.py          # Curated authentic Stoic & active recovery quotes
│   ├── prompts.py            # Structured system rubrics & anti-slop prompt engineering
│   ├── reasoning_service.py  # Tier 1 OpenRouter client & multi-tier reasoning failover
│   └── groq_service.py       # Tier 2 Lightning-fast NLP workout parser & failover
├── ui/
│   ├── __init__.py
│   ├── formatters.py         # Visual progress bar & rank badge formatters
│   ├── embeds.py             # Backward-compatible embed facade re-exporting all builders
│   ├── embed_builders/       # Modular domain-specific embed builders
│   │   ├── common.py         # Theme colors, progress bars, text sanitizer, formatters
│   │   ├── warrior.py        # Individual workout progress, ranks, profiles, streaks
│   │   ├── leaderboards.py   # Daily, weekly, monthly, overall, podiums & server records
│   │   ├── broadcasts.py     # Scheduled kickoff, checkin, recap & ceremony broadcasts
│   │   └── system.py         # Help directory, streak shields, tips & settings
│   ├── views.py              # Interactive views (CouncilVotingView, AccuseConfirmView, etc.)
│   └── todo_views.py         # Interactive 15-item Todo views, alerts, and assignment cards
├── cogs/
│   ├── __init__.py
│   ├── warrior.py            # User-facing slash commands, /accuse, /reminders, and /tips
│   ├── admin.py              # Administrator commands, /admin grind, /admin backup, /nuke
│   └── todo.py               # Standalone /todo command group implementation
├── todo_db.py                # Dedicated SQLite engine for Todo addon (todo.db)
├── todo_parser.py            # Natural language schedule & recurrence parser
├── todo_reminders.py         # Background reminder dispatcher & maintenance ticker
├── dm_templates.py           # Centralized DM announcement & invitation templates
├── tests/                    # Modular domain test suite (158 tests across 13 modules)
├── scheduler.py              # Automated background APScheduler loop with silent broadcasts
├── export_web_stats.py       # Exporter utility syncing DB to web JSON
├── bot.py                    # Lightweight bot client and gateway runner
├── test_engine.py            # Automated test discovery runner (158 tests)
├── create_deploy_zip.py      # Production deployment packager (bot_deploy.zip)
├── Dockerfile                # Production container specification
├── docker-compose.yml        # Multi-platform container configuration
├── vercel.json               # 1-click Vercel deployment configuration
├── docs/                     # Web dashboard & documentation (GitHub Pages / Vercel root)
│   ├── index.html            # Web dashboard structure
│   ├── style.css             # Dark obsidian glassmorphism design system
│   ├── app.js                # Client logic, live countdown, search filter
│   ├── stats.json            # Database snapshot JSON
│   ├── HOSTING.md            # Hosting & deployment documentation
│   └── ARCHITECTURE.md       # Architecture specification (this file)
└── README.md                 # Project summary and quickstart
```

---

## 3. Database Schema

SQLite schema definition (`PRAGMA foreign_keys = ON;`):

### `users`

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | INTEGER PRIMARY KEY | Internal user ID |
| `discord_id` | INTEGER UNIQUE | User's 64-bit Discord snowflake ID |
| `username` | TEXT | Discord display username |
| `joined_at` | DATETIME | Timestamp when user enrolled |
| `enrolled` | BOOLEAN | `1` if active, `0` if unenrolled via `/leave_arc` |
| `frost_shields` | INTEGER DEFAULT 0 | Current inventory of Streak Shields (cap: 2) |
| `last_shield_milestone` | INTEGER DEFAULT 0 | Highest 7-day streak milestone awarded |
| `dm_reminders` | BOOLEAN DEFAULT 0 | Legacy DM toggle |
| `dm_morning` | BOOLEAN DEFAULT 1 | 05:00 IST Morning Kickoff DM preference |
| `dm_afternoon` | BOOLEAN DEFAULT 1 | 16:30 IST Afternoon Standings DM preference |
| `dm_evening` | BOOLEAN DEFAULT 1 | 21:00 IST Evening Streak Alert DM preference |
| `tips_enabled` | BOOLEAN DEFAULT 1 | Periodic bot tips preference (`/tips [on/off]`) |

### `tasks`

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | INTEGER PRIMARY KEY | Discipline ID |
| `name` | TEXT UNIQUE | e.g. "Push-ups", "Running" |
| `description` | TEXT | Brief description |
| `target` | REAL | Daily target amount (e.g. 100.0 reps, 10.0 km) |
| `unit` | TEXT | e.g. "reps", "km", "minutes" |
| `max_points` | INTEGER | Maximum points obtainable for this task (100) |
| `active` | BOOLEAN | `1` if active in daily calculations |

### `daily_logs`

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | INTEGER PRIMARY KEY | Log entry ID |
| `user_id` | INTEGER FK | Foreign key $\rightarrow$ `users(id)` |
| `task_id` | INTEGER FK | Foreign key $\rightarrow$ `tasks(id)` |
| `amount` | REAL | Total logged for the given date |
| `points_earned` | INTEGER | Capped points earned for this task on date |
| `date` | TEXT | ISO format date (`YYYY-MM-DD`) |

### `daily_summaries`

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | INTEGER PRIMARY KEY | Summary entry ID |
| `user_id` | INTEGER FK | Foreign key $\rightarrow$ `users(id)` |
| `date` | TEXT | ISO format date (`YYYY-MM-DD`) |
| `points` | INTEGER | Sum of points earned across all tasks (max 500) |
| `completion_rate` | REAL | Ratio achieved (0.0 to 1.0) |
| `perfect_day` | BOOLEAN | `1` if user achieved 100% completion |
| `is_rest_day` | BOOLEAN DEFAULT 0 | `1` if designated Active Recovery Day (Sunday) |

### `server_settings`

| Column | Type | Description |
| :--- | :--- | :--- |
| `guild_id` | INTEGER PRIMARY KEY | Discord Guild ID |
| `channel_id` | INTEGER | Channel for automated announcements |
| `role_id` | INTEGER | Role pinged during announcements |

### `grind_logs`

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | INTEGER PRIMARY KEY | Grind entry ID |
| `user_id` | INTEGER FK | Foreign key $\rightarrow$ `users(id)` |
| `date` | TEXT | ISO format date (`YYYY-MM-DD`, 1 per day limit) |
| `raw_input` | TEXT | Raw submitted custom workout / study log |
| `verdict` | TEXT | `ACCEPTED`, `ROASTED`, `CAPPED`, or `REVOKED` |
| `points_awarded` | INTEGER | Points earned (+5 to +50, or 0 if capped) |
| `key_learning` | TEXT | Extracted custom workout summary or deep work focus |
| `commentary` | TEXT | Amarok's gritty evaluation / roast |

### `shield_logs`

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | INTEGER PRIMARY KEY | Shield consumption ID |
| `user_id` | INTEGER FK | Foreign key $\rightarrow$ `users(id)` |
| `date` | TEXT | Timestamp of consumption (`YYYY-MM-DD`) |
| `target_date` | TEXT | Date protected by the shield |
| `reason` | TEXT | Rest or recovery explanation |

### `bot_state`

| Column | Type | Description |
| :--- | :--- | :--- |
| `key` | TEXT PRIMARY KEY | State identifier (e.g. `grind_ban_{discord_id}`) |
| `value` | TEXT | State payload (e.g. ISO expiration date or `INDEFINITE`) |
| `updated_at` | DATETIME | Timestamp of last modification |

---

## 4. 12-Level Progression Mathematical Model

Calculated over a **90-day arc** targeting **Apex at 12,000 Lifetime Points** (~133 pts/day average):

$$\text{Points in Tier} = \text{Lifetime Points} - \text{Tier Min Points}$$

$$\text{Tier Progress \%} = \min\left(100, \frac{\text{Points in Tier}}{\text{Tier Max} - \text{Tier Min} + 1} \times 100\right)$$

$$\text{Arc Progress \%} = \min\left(100.0, \frac{\text{Lifetime Points}}{12000} \times 100\right)$$

---

## 5. Streak Defense & Active Recovery Day (ARD) Engine

1. **Streak Calculus & Shields**:
   - Maintaining an active streak requires $\ge 30\text{ points}$ on standard weekdays and Saturdays (or achieving Perfect Day with 500 pts).
   - Warriors earn **+1 Streak Shield** for every 7 consecutive days completed (inventory capped at 2 shields).
   - If a warrior logs $< 30\text{ points}$ on a standard day, an available Streak Shield is consumed automatically at midnight (00:00 IST) without shame or manual intervention.

2. **❤️ Active Recovery Day (ARD — Sundays)**:
   - **Calendar Schedule**: Every Sunday throughout the 90-day campaign is designated as an **Active Recovery Day (ARD)**:
     - **Phase 1**: Oct 11, Oct 18, Oct 25
     - **Phase 2**: Nov 1, Nov 8, Nov 15, Nov 22
     - **Phase 3**: Nov 29, Dec 6, Dec 13, Dec 20, Dec 27
   - **Point Threshold**: Daily target is set to **0 points** (`is_active_recovery_day(date) == True`).
   - **Streak Auto-Protection**: No warrior loses their streak on an ARD, and **zero Streak Shields are consumed**.
   - **Database Schema**: Tracks recovery state via `daily_summaries.is_rest_day` (`BOOLEAN DEFAULT 0`), persisted automatically across daily logs and finalizations.
   - **Monospace Calendar & Hidden ARD Mechanics**:
     - In `/calendar` and `/streak`, upcoming days are intentionally rendered with neutral `▫️` (hidden ARD dates) to prevent warriors from slacking off ahead of time.
     - Upon arrival and for past dates, ARDs reveal as `❤️` (Active Recovery Day) if rest was taken, or `🟩` if the warrior logged full volume.
   - **Dynamic Broadcast Cadence on ARDs**:
     - **Morning Kickoff (05:00 IST)**: Role pinged `@Warrior [WinterArc]` (deliberate ARD exception to notify the pack). Short, feel-good, dynamic AI message reflecting pack history (top performers urged to rest and recover; low-activity members encouraged to move lightly), paired with authentic rest quotes (no generic cliché quotes).
     - **Afternoon Check-in (14:30 IST)**: Unpinged message featuring dynamic AI health and human physiology fun facts, hydration tips, and gentle mobility reminders.
     - **Evening Wind-down (21:00 IST)**: Short dynamic message focused on quality sleep, winding down, and mental readiness for tomorrow's resumption.
   - **Direct Message (DM) Personalization on ARDs**:
     - Personalized morning ARD DM evaluates the warrior's individual 7-day volume. Reassures them that their streak is protected, offering tailored recovery, nutrition, and walking suggestions.
   - **Reactive AI Nudge Adaptation on ARDs**:
     - Reactive nudges never scold or chastise a warrior for having 0 reps on an ARD. Prompts dynamically instruct Amarok to motivate light mobility, stretching, and mental reset.

---

## 5.1 Contextual Tips Engine (`tips.py`)

A non-intrusive habit intelligence system providing actionable micro-tips:
- **Command Control**:
  - `/tips [category]` — Query immediate tips across categories (`pushups`, `pullups`, `squats`, `running`, `recovery`, `nutrition`, `mindset`).
  - `/tips toggle` — Individual warrior toggle to enable or disable tip footers across bot responses.
- **Server & User Settings**:
  - Persisted via `users.tips_enabled` and `server_settings.tips_enabled` (`BOOLEAN DEFAULT 1`).
  - Admins can manage server-wide tip broadcasting via `/settings`.
- **Dynamic Rotation & Anti-Spam**:
  - Tips rotate dynamically in embed footers of workout logs (`/log`, `/quick`, `/set`), `/today`, and `/streak` without inflating message size.

---

## 6. Tribal Governance & Anti-Cheat Council Engine

The Winter Arc governance system enforces authenticity through a dual-trigger architecture:

1. **Automated AI Sentinel**: When OpenRouter flags vague buzzword bingo or ungrounded claims (`verdict == 'ROASTED'`), Amarok credits token effort points (+10 pts) and immediately auto-summons the Council in the designated announcements channel.
2. **Community Challenge (`/accuse @member`)**: Any enrolled brother can challenge a dishonest log. To prevent petty rivalry or jealousy, the challenger must pass an ephemeral **Honor Code Verification Modal** before the public trial is summoned.
3. **Democratic Resolution (`CouncilVotingView`)**:
   - 10-minute public voting session with real-time button counts: `[ 🔨 Guilty ]` vs `[ 🛡️ Innocent ]`.
   - The accused is blocked from self-voting; only enrolled pack members may cast votes.
   - Concludes with thematic animated courtroom GIFs (Phoenix Wright, Higuruma court, cat council).
   - If Guilty: Points are stripped (`cap_user_grind`). If Innocent or Tied: Points stand.
4. **Administrative Probation (`/admin grind`)**: Server administrators can suspend `/grind` access (`block` with custom duration & reason) or restore it (`unlock`).

---

## 7. Multi-Tier AI Architecture & Cascade Failover Engine

The bot employs a fault-tolerant, 3-tier cascade architecture to guarantee zero-downtime execution and eliminate regional datacenter IP restrictions:

```text
User Request (/grind, recaps, announcements, briefings)
                    │
                    ▼
          Is OpenRouter Configured?
              /              \
            Yes               No
            /                  \
           ▼                    ▼
    OpenRouter API        Groq Cloud API
 (openrouter/free cascade) (openai/gpt-oss-20b)
           │                    │
     All Models Fail?           │
           │                    ▼
           ├──► Fallback ───────┤
           │                    ▼
           ▼              Groq Fails?
     Curated Reserves     /         \
     (Authentic Stoic)   No         Yes
                         │           │
                         ▼           ▼
                      Result   Curated Reserves
```

1. **Tier 1 — OpenRouter API (`openrouter/free` with model cascade)**:
   - Primary high-reasoning engine for `/grind` evaluations, midnight toasts/roasts, Sunday State of the Pack recaps, morning personalized briefings, and end-of-phase ceremonies.
   - Bypasses European VPS datacenter IP restrictions (Google edge proxy HTTP 403 Forbidden) by routing requests through OpenRouter's distributed global proxy.
   - Multi-model fallback cascade automatically recovers across free candidate models (`openrouter/free`, `nvidia/nemotron-3.5-lightning:free`, `google/gemma-4-31b-it:free`, `google/gemma-4-26b-a4b-it:free`) upon 429 rate limits or upstream 500 errors.
2. **Tier 2 — Groq Cloud (`openai/gpt-oss-20b`)**:
   - Primary engine for ultra-fast `/quick` natural language workout parsing and reactive coach Amarok nudges (~300ms latency).
   - Real-time reasoning failover fallback for `/grind`, daily toasts/roasts, weekly recaps, and morning DM briefings if OpenRouter candidate models fail.
3. **Tier 3 — Curated Stoic Safety Net**:
   - Zero-downtime safety net guaranteeing grounded, authentic Stoic edicts (Marcus Aurelius, Seneca, Epictetus) and deterministic announcements even during network partitions.

### 7.1 Standardized AI Logging & Observability Pipeline

All AI requests, background evaluators, and probabilistic rolls output uniform structured log tags to `sys.stdout` and `winter_arc.log` for real-time observability:

| Tag | Level | Context | Description & Output Example |
| :--- | :--- | :--- | :--- |
| `[Nudge-Roll]` | `INFO` | Reactive nudge probability | `[Nudge-Roll] User 123456: TRIGGERED (rolled 0.11 <= threshold 0.35) -> Invoking Groq reactive nudge.` |
| `[Nudge-Cooldown]` | `INFO` | 30-min per-user cooldown suppression | `[Nudge-Cooldown] User 123456: SKIPPED (on active cooldown, 28m remaining).` |
| `[AI-Call]` | `INFO` | Outbound request initiation | `Calling OpenRouter API (openrouter/free) for afternoon_recovery reminder quote...` |
| `[AI-Success]` | `INFO` | Model latency & generation confirmation | `OpenRouter afternoon_recovery quote generated in 0.42s: '...'` |
| `[AI-Fallback]` | `WARNING` | Multi-tier failover transition | `OpenRouter morning briefing failed for warrior (429). Falling back to Groq...` |

---

## 8. Modular Productivity Addon: Todo & Smart Reminders (`todo.db`)

To keep productivity distraction-free and protect the fitness progression integrity, the **Todo & Smart Reminders Addon** is architected with strict decoupling from the core Winter Arc framework.

```text
┌─────────────────────────────────────────────────────────────┐
│               Slash Command Group: /todo                    │
│   • /todo add [task] [when] [remind_me] [until] [dm] [prio] │
│   • /todo list [filter: active | trash]                     │
│   • /todo done [id]      • /todo silence [id]               │
│   • /todo delete [id]    • /todo restore [id]               │
│   • /todo edit [id]      • /todo assign [member] [task]     │
│   • /todo incognito [mode: on|off|check] [user]             │
│   • /todo dnd [start] [end] [enable]                        │
│   • /todo clear [which: active | trash | all]               │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────────────┐┌─────────────────────────────┐
│   Schedule Parser            ││   Interactive Components    │
│   (todo_parser.py)           ││   (ui/todo_views.py)        │
│ • One-time timestamps        ││ • 15-item Paginated View    │
│ • "every 2 hours" intervals  ││ • Dynamic Quick Actions     │
│ • Windowed recurrence        ││ • Assignment Accept/Decline │
│ • "3 times a day" cadence    ││ • Incognito Privacy View    │
└──────────────┬───────────────┘└─────────────┬───────────────┘
               │                              │
               ▼                              ▼
┌─────────────────────────────────────────────────────────────┐
│               Background Ticker (todo_reminders.py)         │
│   • Runs every 30 seconds                                   │
│   • Cross-midnight DND quiet hours suppression              │
│   • Advances interval recurrences & daily windows           │
│   • Auto-purges trashed tasks older than 7 days             │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│             Dedicated Database Layer (todo_db.py)           │
│   • Completely isolated SQLite database: todo.db            │
│   • Zero coupling with winter_arc.db                        │
│   • Relative user task numbering (#1..#N)                   │
│   • user_settings table: DND hours & Incognito privacy mode │
│   • 7-day trash archive (T1..TN) with automatic purging     │
└─────────────────────────────────────────────────────────────┘
```

### Key Design Tenets
1. **Zero Contamination**:
   - `todo.db` is completely physically separate from `winter_arc.db`. No tables, foreign keys, or queries overlap.
   - Neutral aesthetic: Clean, distraction-free embeds without wolves, rankings, or frost metaphors.
2. **Relative User-Facing Task Numbering**:
   - Users interact exclusively with relative sequential numbers (`#1, #2, #3...`). Internal database autoincrement primary keys are abstracted away.
   - Trashed items use relative trash codes (`T1, T2...`).
3. **Smart Natural-Language Schedules**:
   - Handles one-time dates & times, interval recurrence (`every 2 hours`), windowed recurrence (`every hour after 6 PM`), and multi-daily cadences (`3 times a day`, `5 times a day`).
   - The `until` boundary parameter is strictly optional, allowing indefinite recurring habits until explicitly checked off.
4. **Quiet Hours (DND)**:
   - Users can configure daily quiet hours (e.g., `22:00` to `06:00`).
   - Reminders triggered during quiet hours are quietly postponed by 30 minutes without spamming or waking the user.
5. **Interactive Lifecycle**:
   - Direct inline buttons (`[ ✅ Mark Done ]`, `[ 🔕 Silence ]`, `[ ⏰ Snooze 30m ]`) on reminder alerts.
   - Delegated task assignment (`/todo assign`) with bilateral accept/decline confirmations.
6. **Incognito Privacy Mode**:
   - Users can toggle the channel visibility of their `/todo` operations between `OFF (Public)` (default) and `ON (Private)` using `/todo incognito`.
   - **OFF (Public)**: All actions (`/todo list`, `/todo done`, `/todo delete`, etc.) post publicly to the server channel so teams stay accountable together.
   - **ON (Private)**: Personal to-do actions respond ephemerally (visible only to the user), keeping channels quiet, while shared operations (`/todo add`, `/todo assign`) remain public.
   - **Interactive View (`TodoIncognitoView`)**: Running `/todo incognito` posts a public status card with `[ Turn On ]` and `[ Turn Off ]` buttons protected with user-only authorization checks. Users can also inspect peer privacy modes with `/todo incognito mode: check user: @member`.


