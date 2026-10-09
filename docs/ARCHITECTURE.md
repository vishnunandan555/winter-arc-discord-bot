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
│  • /grind, /reminders        ││                             │
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
├── ai/                       # Groq & Gemini AI service integrations
├── ui/
│   ├── __init__.py
│   ├── formatters.py         # Visual progress bar & rank badge formatters
│   ├── embeds.py             # Single-card spacious Discord embeds & Amarok voice
│   └── views.py              # Interactive views (CouncilVotingView, AccuseConfirmView, etc.)
├── cogs/
│   ├── __init__.py
│   ├── warrior.py            # User-facing slash commands, /accuse, and /reminders
│   └── admin.py              # Administrator commands, /admin grind, /nuke
├── dm_templates.py           # Centralized DM announcement & invitation templates
├── tests/                    # Modular domain test suite (90 tests across 10 modules)
├── scheduler.py              # Automated background APScheduler loop with silent broadcasts
├── export_web_stats.py       # Exporter utility syncing DB to web JSON
├── bot.py                    # Lightweight bot client and gateway runner
├── test_engine.py            # Automated test discovery runner (90 tests)
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
| `raw_input` | TEXT | Raw submitted reflection / study log |
| `verdict` | TEXT | `ACCEPTED`, `ROASTED`, `CAPPED`, or `REVOKED` |
| `points_awarded` | INTEGER | Points earned (+5 to +60, or 0 if capped) |
| `key_learning` | TEXT | Extracted technical focus / tag |
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

## 5. Tribal Governance & Anti-Cheat Council Engine

The Winter Arc governance system enforces authenticity through a dual-trigger architecture:

1. **Automated AI Sentinel**: When Gemini flags vague buzzword bingo or ungrounded claims (`verdict == 'ROASTED'`), Amarok credits token effort points (+10 pts) and immediately auto-summons the Council in the designated announcements channel.
2. **Community Challenge (`/accuse @member`)**: Any enrolled brother can challenge a dishonest log. To prevent petty rivalry or jealousy, the challenger must pass an ephemeral **Honor Code Verification Modal** before the public trial is summoned.
3. **Democratic Resolution (`CouncilVotingView`)**:
   - 10-minute public voting session with real-time button counts: `[ 🔨 Guilty ]` vs `[ 🛡️ Innocent ]`.
   - The accused is blocked from self-voting; only enrolled pack members may cast votes.
   - Concludes with thematic animated courtroom GIFs (Phoenix Wright, Higuruma court, cat council).
   - If Guilty: Points are stripped (`cap_user_grind`). If Innocent or Tied: Points stand.
4. **Administrative Probation (`/admin grind`)**: Server administrators can suspend `/grind` access (`block` with custom duration & reason) or restore it (`unlock`).
