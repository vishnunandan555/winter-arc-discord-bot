<div align="center">

  <img src="docs/assets/winter_arc_banner_vector_clean_1360x480.png" alt="Winter Arc Discord Bot Banner" width="100%" style="border-radius: 12px; margin-bottom: 1rem;">

  <h1 align="center">Winter Arc Discord Bot</h1>

  **An open-source, self-hosted fitness accountability ecosystem for private Discord communities.**  
  *Track volume, defend streaks, conquer the cold, and ascend through a 12-tier discipline hierarchy.*

  [![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
  [![discord.py](https://img.shields.io/badge/discord.py-v2.x-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
  [![Tests](https://img.shields.io/badge/Tests-77%20Passed%20(100%25)-00E5FF?style=for-the-badge&logo=pytest&logoColor=black)](tests/)
  [![Database](https://img.shields.io/badge/Database-SQLite%20Zero--Config-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](database.py)
  [![License](https://img.shields.io/badge/License-MIT-F39C12?style=for-the-badge)](LICENSE)

  <br>

  <h3>
    <a href="https://winter-arc-discord-bot.vercel.app/"><strong>Visit Website</strong></a>
  </h3>
</div>

---

## ⚡ Why Winter Arc?

Most fitness and habit trackers fail because working out in isolation provides no tribal pressure, while commercial apps are plagued by paywalls, subscriptions, and bloat.

**Winter Arc moves the accountability loop directly into Discord:**

- **Shared Pack Accountability**: Volume, streaks, and missed days are transparently celebrated or challenged in your server.
- **Anti-Cheat 500-Point Daily Ceiling**: Prevents erratic binge workouts and vanity scores. 90-day consistency beats single-day ego lifting.
- **Dual AI Workout Logging**: Log workouts with standard slash commands or natural language with Groq and Gemini AI.
- **Tribal Governance & Council Trials**: Anti-buzzword AI audits and democratic Council trials (`/accuse`) protect server integrity from vanity claims.
- **Data Sovereignty**: 100% self-hosted with local SQLite. Your members' workout data remains completely private.

---

## 🏔️ Core Pillars

| Feature | Description |
| :--- | :--- |
| **5 Disciplines (Saitama Protocol)** | Push-ups (100), Pull-ups (100), Squats (100), Sit-ups (100), and Running (10 km). 1 rep / 100m = 1 pt (500 pts max/day). |
| **Monospace Habit Calendar** | `/streak` & `/calendar` render an aligned, monospace monthly matrix and full 92-day campaign view with interactive bidirectional switching and status highlights. |
| **Streak Shield Defense** | Earn Streak Shields every 7-day milestone. Deploy `/shield use` to protect your streak on rest or recovery days. |
| **Dual AI Parsing** | `/quick` parses unstructured workout text via Groq (Qwen 2.5); `/grind` evaluates deep work & cognitive friction via Gemini (+5 to +60 pts, 1x/day). |
| **Tribal Council Governance** | Real-time integrity verification: `/accuse` challenges suspect logs with an Honor Code verification modal, 10-minute democratic voting, and courtroom GIF verdicts. |
| **12-Tier Progression** | Climb from **Initiate (Level 1, 0 pts)** to **Apex (Level 12, 12,000 pts)** over the course of the 90-day challenge. |
| **Automated Cadence** | Morning kickoff (05:00 IST), afternoon pulse (16:30 IST), evening warning (21:00 IST), Sunday weekly recap (10:00 IST), midnight podium (00:00 IST), and month-end phase ceremonies. |

> 📖 **Want the deep dive?**  
> Explore the full [12-Tier Hierarchy](https://winter-arc-discord-bot.vercel.app/#ranks) and [Seasonal Phase Roadmap](https://winter-arc-discord-bot.vercel.app/#phases) on the website.

---

## 🚀 Quickstart Guide

### 1. Clone & Setup Virtual Environment

```bash
# Clone the repository
git clone https://github.com/vishnunandan555/winter-arc-discord-bot.git
cd winter-arc-discord-bot

# Create and activate virtual environment (Python 3.11+)
python3 -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your Discord credentials:

```bash
cp .env.example .env
```

```env
# Required: Discord Bot Token from Discord Developer Portal
DISCORD_TOKEN=your_bot_token_here

# Required for /nuke: SHA-256 hash of owner's 2FA secret answer
NUKE_SECURITY_HASH=ae50ad81a2d4006e372c0bd3220f24c377345455d0e980c3f0d94f0e5faf2561

# Optional: Default role & channel IDs (can also be configured in-server via /admin)
WINTER_ARC_ROLE_ID=
WINTER_ARC_CHANNEL_ID=

# Optional: AI capabilities for /quick and /grind commands
GEMINI_API_KEY=your_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here
```

### 3. Launch the Bot

```bash
python bot.py
```

*The bot will connect to Discord, initialize `winter_arc.db`, and sync all 25 slash commands automatically.*

---

## 🧪 Automated Test Suite

The test suite contains **88 comprehensive test cases** organized into 10 domain modules inside the [`tests/`](tests/) directory.

```bash
# Run the complete test suite via discovery runner
python test_engine.py

# Or run standard unittest discovery
python -m unittest discover tests

# Or run individual domain test modules
python -m unittest tests/test_reminders_and_dms.py
python -m unittest tests/test_call_cap_and_governance.py
python -m unittest tests/test_streaks_shields.py
python -m unittest tests/test_scoring_logging.py
python -m unittest tests/test_ui_embeds_views.py
python -m unittest tests/test_ai_services.py
python -m unittest tests/test_cogs_bot.py
```

---

## 📋 Slash Command Overview

The bot registers **25 native slash commands** designed with Discord autocomplete and button pagination:

| Category | Commands | Description |
| :--- | :--- | :--- |
| **Workout Logging** | `/log`, `/set`, `/quick`, `/grind` | Add volume, set direct overrides, or parse workout text with AI. |
| **Habits & Streaks** | `/streak`, `/calendar`, `/today`, `/tasks`, `/history` | Monospace habit consistency dashboard, 3-phase full habit calendar, daily progress card, task guide, and past logs. |
| **Pack Standings** | `/leaderboard`, `/profile`, `/ranks`, `/stats`, `/recap` | Daily/weekly/monthly leaderboards, rank cards, server records, and phase summaries. |
| **Tribal Governance** | `/accuse` | Challenge suspect grind logs to summon a 10-min Council verification vote. |
| **Recovery & Settings** | `/shield`, `/settings`, `/reminders`, `/enroll`, `/leave_arc`, `/help`, `/ping` | Streak shield defense, private morning/afternoon/evening DM preferences, manual, and latency check. |
| **Server Admin** | `/admin` (`overview`, `set_channel`, `set_role`, `dm`, `task_add`, `task_toggle`, `tasks_list`, `grind`, `sync`), `/test_reminder`, `/nuke` | Channel binding, role ping, multi-target DMs, discipline customization, broadcast preview, and factory reset. |
| **Security & Safety** | `/nuke` | Server Owner emergency channel purge with 2FA modal verification and rotated nuclear explosion GIFs. |

👉 **[Search & Filter All Commands Interactively on the Website »](https://winter-arc-discord-bot.vercel.app/#commands)**

---

## 🛠️ Self-Hosting & Deployment

Winter Arc is engineered for 24/7 reliability with minimal resource consumption (<50 MB RAM on idle).

| Deployment Method | Guide & Reference |
| :--- | :--- |
| **Linux VPS (Systemd)** | Ubuntu/Debian production service configuration with auto-restart: [docs/HOSTING.md »](docs/HOSTING.md#option-b-linux-vps--ubuntu-server-systemd-service) |
| **Docker & Docker Compose** | One-command deployment via `docker compose up -d`: [Dockerfile](Dockerfile) • [docker-compose.yml](docker-compose.yml) |
| **Wispbyte / Pterodactyl** | Low-cost 24/7 bot hosting (GitHub Auto-Pull & ZIP Bundle): [docs/HOSTING.md »](docs/HOSTING.md#option-a-wispbyte--pterodactyl-panel-freelow-cost-247) |
| **Cloud (Render / Railway)** | Persistent background worker setup: [docs/HOSTING.md »](docs/HOSTING.md#option-c-hosting-on-cloud-render--railway) |

For complete step-by-step instructions, see the **[Full Hosting Guide (docs/HOSTING.md)](docs/HOSTING.md)**.

### 🚀 Wispbyte Deployment Options

- **Method 1 (Recommended): GitHub Auto-Pull** — Configure your repo in Wispbyte's **GitHub Integration** tab with `Auto Update on Startup` enabled. Bot reboots automatically pull the latest commits without manual file transfers.
- **Method 2 (Classic): One-Click ZIP Bundle** — Generate an ultra-lean production archive with a single command:

```bash
python create_deploy_zip.py
```

> **What this does:**
> - Automatically bundles all bot code, cogs, AI services, test suites, and Docker configs.
> - **Includes your `.env` file** so your credentials and token work instantly upon unzipping.
> - Excludes all local databases (`*.db`), virtual environments (`.venv`), caches, and website assets to keep the upload ultra-lean (~130 KB).
> - Produces a fresh `bot_deploy.zip` ready to upload and extract in your server's file manager.

---

## 📂 Project Architecture

```text
winter-arc-discord-bot/
├── ai/                      # Groq & Gemini AI service integrations
├── cogs/                    # Discord command extensions (warrior & admin cogs)
├── ui/                      # Discord embeds, formatters, and interactive views
├── tests/                   # Modular domain test suite (77 test cases across 9 modules)
├── docs/                    # Static showcase website (GitHub Pages / Vercel)
│   ├── assets/              # Banners, badges, and branding graphics
│   ├── index.html           # Interactive showcase site
│   ├── HOSTING.md           # Deployment documentation
│   └── ARCHITECTURE.md      # Deep technical architecture breakdown
├── bot.py                   # Discord bot client & lifecycle events
├── config.py                # Environment variables & constants
├── database.py              # SQLite database schema, migrations & queries
├── dm_templates.py          # Centralized private DM announcement & invitation templates
├── helpers.py               # Autocomplete providers & date helpers
├── levels.py                # 12-tier discipline calculation & thresholds
├── phases.py                # 4-phase calendar & recap definitions
├── tips.py                  # Contextual tips engine & rate limits
└── test_engine.py           # Test discovery runner (backward compatible)
```

For complete technical specifications, database schema diagrams, and memory management details, refer to **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

---

## 📄 License & Attribution

Distributed under the **MIT License**. Created by [Vishnu Nandan](https://github.com/vishnunandan555).  
Contributions, issues, and feature requests are welcome!
