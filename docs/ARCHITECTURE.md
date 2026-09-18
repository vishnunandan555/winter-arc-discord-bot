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
│  • /today, /log, /set        ││  • /admin set_channel       │
│  • /profile, /ranks          ││  • /admin set_role          │
│  • /leaderboard, /stats      ││  • /admin task_*            │
│  • /history, /ping, /help    ││  • /test_reminder           │
└──────────────┬───────────────┘└─────────────┬───────────────┘
               │                              │
               ▼                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Presentation Layer (ui/)                  │
│   • ui.formatters: Progress bars, rank badges, icons        │
│   • ui.embeds: Reusable, uncrowded Discord embed cards      │
│   • ui.views: Interactive components (LeaderboardView)      │
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
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│                 WinterArcScheduler (scheduler.py)           │
│   • 05:00 IST: Morning Kickoff announcement                 │
│   • 16:30 IST: Midday Progress check-in                     │
│   • 00:00 IST: Midnight finalization & podium broadcast     │
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
├── helpers.py                # Reusable guards, role resolver, safe reactions
├── ui/
│   ├── __init__.py
│   ├── formatters.py         # Visual progress bar & rank badge formatters
│   ├── embeds.py             # Single-card spacious Discord embeds
│   └── views.py              # Interactive discord.ui.View components
├── cogs/
│   ├── __init__.py
│   ├── warrior.py            # User-facing slash commands
│   └── admin.py              # Administrator commands and diagnostic tools
├── scheduler.py              # Automated background APScheduler loop
├── export_web_stats.py       # Exporter utility syncing DB to web JSON
├── bot.py                    # Lightweight bot client and gateway runner
├── test_engine.py            # Automated test suite (10 unit tests)
├── vercel.json               # 1-click Vercel deployment configuration
├── docs/                     # Web dashboard (GitHub Pages / Vercel root)
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

---

## 4. 12-Level Progression Mathematical Model

Calculated over a **90-day arc** targeting **Apex at 12,000 Lifetime Points** (~133 pts/day average):

$$\text{Points in Tier} = \text{Lifetime Points} - \text{Tier Min Points}$$

$$\text{Tier Progress \%} = \min\left(100, \frac{\text{Points in Tier}}{\text{Tier Max} - \text{Tier Min} + 1} \times 100\right)$$

$$\text{Arc Progress \%} = \min\left(100.0, \frac{\text{Lifetime Points}}{12000} \times 100\right)$$
