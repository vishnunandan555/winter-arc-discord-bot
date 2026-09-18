# Winter Arc Discord Bot — Implementation Plan & Specification

A robust, lightweight Discord bot designed for accountability, fitness challenges, and daily progress tracking for a friend group (5–10 members). Built with Python, `discord.py`, and SQLite, hosted 24/7 on Wispbyte.

---

## 1. System Architecture & Tech Stack

```
                     DISCORD CLIENTS
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
    Slash Commands      Interactive UI      Reminders
   (/today, /log...)   (Buttons, Toggles)  (05:00, 16:30)
         │                 │                 │
         └─────────────────┼─────────────────┘
                           ▼
                 ┌───────────────────┐
                 │   WinterArcBot    │
                 │   (discord.py)    │
                 └─────────┬─────────┘
                           │
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
Command Router      Async Scheduler       Scoring Engine
(discord.tree)      (Asia/Kolkata)       (Capped Formula)
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
                 ┌───────────────────┐
                 │  database.py (DAO)│
                 └─────────┬─────────┘
                           ▼
                    SQLite Database
                   (winter_arc.db)
```

### Core Technologies
- **Runtime**: Python 3.10+
- **Bot Framework**: `discord.py` 2.x (with modern Application Commands / CommandTree)
- **Database**: SQLite 3 (Standard library `sqlite3` with connection management)
- **Scheduling**: `discord.ext.tasks` or `apscheduler` locked explicitly to `Asia/Kolkata`
- **Environment Management**: `python-dotenv`
- **Hosting**: Wispbyte (Free 24/7 Python Discord Bot container)
- **VCS**: GitHub (Public or Private repository)

---

## 2. Database Design (SQLite)

The database abstracts all SQL operations away from Discord presentation code via a dedicated Data Access Object (`database.py`).

### Schema Definition

```sql
-- Users and reminder preferences
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id INTEGER UNIQUE NOT NULL,
    username TEXT NOT NULL,
    timezone TEXT DEFAULT 'Asia/Kolkata',
    morning_reminder BOOLEAN DEFAULT 1,
    afternoon_reminder BOOLEAN DEFAULT 1,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Challenge tasks configuration (dynamic, not hardcoded)
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    target REAL NOT NULL,
    unit TEXT NOT NULL,
    max_points INTEGER NOT NULL,
    active BOOLEAN DEFAULT 1
);

-- Granular activity entries (preserves raw logs for historical recalculations)
CREATE TABLE IF NOT EXISTS daily_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    task_id INTEGER NOT NULL,
    date DATE NOT NULL,              -- Format: YYYY-MM-DD
    amount REAL NOT NULL,
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

-- Finalized day summaries (generated at midnight 00:00)
CREATE TABLE IF NOT EXISTS daily_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date DATE NOT NULL,              -- Format: YYYY-MM-DD
    points INTEGER NOT NULL,
    completion_rate REAL NOT NULL,   -- e.g. 0.85 for 85%
    perfect_day BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, date),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_logs_user_date ON daily_logs (user_id, date);
CREATE INDEX IF NOT EXISTS idx_summaries_user_date ON daily_summaries (user_id, date);
```

### Initial Seed Data (`tasks`)
| Task | Target | Unit | Max Points |
| :--- | :--- | :--- | :--- |
| **Push-ups** | 100 | reps | 100 |
| **Pull-ups** | 20 | reps | 100 |
| **Squats** | 100 | reps | 100 |
| **Running** | 5 | km | 100 |

---

## 3. Core Gameplay & Calculation Engine

### 3.1 Scoring Formula
To prevent abuse (e.g., `/log push-ups 999999`), points are capped at the task's `max_points`. Over-achieving target is encouraged for vanity/progress metrics, but scoring does not inflate past 100%:

$$\text{completion} = \min\left(\frac{\text{total\_amount}}{\text{target}}, 1.0\right)$$
$$\text{task\_points} = \lfloor \text{completion} \times \text{max\_points} \rfloor$$
$$\text{daily\_points} = \sum \text{task\_points}$$

### 3.2 Abuse Prevention & Input Validation
- Reject negative logs: `amount > 0`
- Reject unrealistic values per log entry (e.g., `amount <= 500` reps or `amount <= 50` km)
- Tasks are matched via case-insensitive lookup or autocomplete parameter.

### 3.3 Streak Calculation
Streaks are dynamically computed from `daily_summaries` by scanning backwards from yesterday (or today if already completed):
- A day counts as successful if $\text{completion\_rate} \ge 1.0$ (or custom threshold e.g. $\ge 80\%$).
- Scan backwards consecutively until a break in days is encountered.
- Eliminates stale counter desyncs.

---

## 4. Timezone & Automated Schedules

All scheduler routines are pinned to **`Asia/Kolkata`** (IST, UTC+5:30) regardless of the host server location.

### Schedule Timeline

| Time (IST) | Event | Target | Description |
| :--- | :--- | :--- | :--- |
| **05:00** | **Morning Kickoff** | Opted-in DMs or `#daily-challenge` | Daily motivation, list of active tasks, and targets. |
| **16:30** | **Afternoon Check-in** | Opted-in Users | Personalized progress report showing remaining amounts needed. |
| **00:00** | **Midnight Day Finalization** | Background Job + `#daily-results` | Finalize points, compute summaries, publish daily podium leaderboard, rollover to new date. |

### Midnight Roll-over Mechanics
1. Lock previous date: `target_date = (now_ist - 1 day).date()`
2. For each registered user:
   - Sum `daily_logs` for `target_date`.
   - Calculate total points and overall completion %.
   - Insert record into `daily_summaries`.
3. Format daily podium embed:
   - 🥇 First place
   - 🥈 Second place
   - 🥉 Third place
   - List users with perfect days (100% completion).
4. Send embed to `#daily-results`.
5. Next day queries automatically start fresh at `0 / target` since queries filter by `date = today()`.

---

## 5. Command Specifications

### User Commands

| Command | Parameters | Description |
| :--- | :--- | :--- |
| `/ping` | *None* | Health check; responds with latency. |
| `/today` | *None* | Displays rich embed of user's current day progress, targets, percentage, total points, and current streak. |
| `/log` | `task: str`, `amount: float` | Logs completed units for an active task. Updates total and shows earned points. |
| `/stats` | `user: Optional[User]` | Displays lifetime totals, perfect days count, and average completion. |
| `/history` | `days: Optional[int]` | Displays past week/month timeline of scores. |
| `/leaderboard` | `period: [day, week, month]` | Displays ranking table sorted by cumulative points. |
| `/reminders` | *None* | Interactive Discord UI with toggle buttons for Morning (05:00) and Afternoon (16:30). |
| `/profile` | *None* | User card showing joined date, reminder status, streak, and tier badge. |

### Administrative Commands (Restricted to Server Admins)

| Command | Parameters | Description |
| :--- | :--- | :--- |
| `/admin task add` | `name`, `target`, `unit`, `max_points` | Dynamically registers a new challenge task without restarting. |
| `/admin task edit` | `name`, `target`, `unit`, `max_points` | Updates requirements or points for an existing task. |
| `/admin task toggle` | `name`, `active: bool` | Enables/disables a task for future daily cycles. |
| `/admin set_results_channel` | `channel: TextChannel` | Sets destination channel for the 00:00 midnight leaderboard. |

---

## 6. Directory Structure

```
winter-arc-bot/
├── .env                  # Bot token & channel IDs (NEVER commit to git)
├── .env.example          # Template for required environment variables
├── .gitignore            # Excludes venv, sqlite db, cache, secrets
├── README.md             # Project overview & local setup guide
├── requirements.txt      # Python dependencies
├── bot.py                # Main bot client, event handlers & slash commands
├── database.py           # SQLite connection, migrations, query functions
├── scheduler.py          # Cron jobs (05:00, 16:30, 00:00) in Asia/Kolkata
└── PLAN.md               # Detailed architecture & milestone tracker
```

### Git Configuration (`.gitignore`)
```gitignore
.env
.venv/
__pycache__/
*.db
*.sqlite
*.sqlite3
*.log
```

---

## 7. Implementation Milestones

### [ ] Milestone 1: Discord Connection & Foundation
- [ ] Initialize git repository and virtual environment.
- [ ] Create `.env` and `.env.example`.
- [ ] Register application & bot on Discord Developer Portal.
- [ ] Generate invite link with scopes `bot`, `applications.commands` and permissions (Send Messages, Embed Links, Read Message History).
- [ ] Build minimal `bot.py` with `CommandTree` and `/ping` slash command.
- [ ] Verify `/ping` responds in Discord.

### [ ] Milestone 2: SQLite Database Layer
- [ ] Create `database.py` with schema initialization:
  - `users`
  - `tasks`
  - `daily_logs`
  - `daily_summaries`
- [ ] Implement seed function for default tasks (Push-ups, Pull-ups, Squats, Running).
- [ ] Add CRUD functions:
  - `get_or_create_user(discord_id, username)`
  - `get_active_tasks()`
  - `log_activity(user_id, task_id, date, amount)`
  - `get_daily_progress(user_id, date)`
  - `calculate_daily_points(user_id, date)`

### [ ] Milestone 3: Core Gameplay Commands
- [ ] Implement `/log [task] [amount]`:
  - Input validation (`amount > 0`, upper bounds).
  - Autocomplete choices for task names.
  - Formatted response showing `previous -> updated / target (+points)`.
- [ ] Implement `/today`:
  - Calculate completion percentage and current daily points.
  - Render rich embed with emoji progress bars and current streak.

### [ ] Milestone 4: Statistics & Leaderboards
- [ ] Implement dynamic streak calculation engine.
- [ ] Implement `/leaderboard [daily | monthly]`:
  - Daily podium query from `daily_logs` / `daily_summaries`.
  - Monthly aggregation query (`SUM(points)` across active calendar month).
- [ ] Implement `/stats` and `/history`.

### [ ] Milestone 5: Reminders & Scheduler
- [ ] Build `scheduler.py` configured with `zoneinfo.ZoneInfo("Asia/Kolkata")`.
- [ ] Implement 05:00 IST Morning Kickoff job.
- [ ] Implement 16:30 IST Afternoon Check-in job (progress summary).
- [ ] Implement 00:00 IST Midnight Finalization job (summary persistence & `#daily-results` announcement).
- [ ] Implement `/reminders` command with interactive Discord UI buttons (`discord.ui.View`) to toggle preferences.

### [ ] Milestone 6: Admin Management
- [ ] Implement `/admin task add`, `/admin task edit`, `/admin task toggle`.
- [ ] Enforce Discord `administrator` permission check on admin group.
- [ ] Implement `/admin set_results_channel`.

### [ ] Milestone 7: Polish & Robustness
- [ ] Global error handler for slash commands (handling invalid inputs, cooldowns, missing permissions).
- [ ] Polished Discord embed styling with consistent colors, emojis, and layouts.
- [ ] Comprehensive documentation in `README.md`.

### [ ] Milestone 8: Deployment & 24/7 Operations (Wispbyte)
- [ ] Commit codebase to GitHub (excluding `.env` and `*.db`).
- [ ] Setup server on Wispbyte (Python runtime).
- [ ] Configure environment variable `DISCORD_TOKEN` in Wispbyte console.
- [ ] Configure startup command: `python bot.py`.
- [ ] Start bot and verify persistence across server restarts.
- [ ] Test scheduler trigger offset to verify timezone accuracy.
- [ ] Document database backup procedure (periodic download of `winter_arc.db`).

---

## 8. Operational & Maintenance Playbook

### Wispbyte Free Tier Rule
- Log in to the Wispbyte panel at least once every 14 days to keep the container active.

### Backup Strategy
- Download `winter_arc.db` weekly or before performing system updates.
- If scaling beyond 10–20 members in the future, migrate `database.py` connection to a hosted PostgreSQL instance (e.g., Supabase / Neon free tiers).
