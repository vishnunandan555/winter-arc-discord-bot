<div align="center">

  <img src="docs/assets/winter_arc_banner_vector_clean_1360x480.png" alt="Winter Arc Discord Bot Banner" width="100%" style="border-radius: 12px; margin-bottom: 1rem;">

  # Winter Arc Discord Bot
  
  **An open-source, self-hosted fitness accountability ecosystem for private Discord communities.**  
  *Track volume, defend streaks, conquer the cold, and ascend through a 12-tier discipline hierarchy.*

  [![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
  [![discord.py](https://img.shields.io/badge/discord.py-v2.x-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
  [![Tests](https://img.shields.io/badge/Tests-52%20Passed%20(100%25)-00E5FF?style=for-the-badge&logo=pytest&logoColor=black)](test_engine.py)
  [![Database](https://img.shields.io/badge/Database-SQLite%20Zero--Config-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](database.py)
  [![License](https://img.shields.io/badge/License-MIT-F39C12?style=for-the-badge)](LICENSE)

  <br>

  <h3>
    🌐 <a href="https://vishnunandan555.github.io/winter-arc-discord-bot/"><strong>Explore Live Showcase & Documentation Website »</strong></a>
  </h3>
  <p>Interactive Command Directory • 12-Tier Ranks • Season Roadmap • Live Calendar Preview</p>

</div>

---

## ⚡ Why Winter Arc?

Most fitness and habit trackers fail because working out in isolation provides no tribal pressure, while commercial apps are plagued by paywalls, subscriptions, and bloat.

**Winter Arc moves the accountability loop directly into Discord:**
- **Shared Pack Accountability**: Volume, streaks, and missed days are transparently celebrated or challenged in your server.
- **Anti-Cheat 500-Point Daily Ceiling**: Prevents erratic binge workouts and vanity scores. 90-day consistency beats single-day ego lifting.
- **Dual AI Workout Logging**: Log workouts with standard slash commands or natural language with Groq and Gemini AI.
- **Data Sovereignty**: 100% self-hosted with local SQLite. Your members' workout data remains completely private.

---

## 🏔️ Core Pillars

| Feature | Description |
| :--- | :--- |
| **5 Disciplines (Saitama Protocol)** | Push-ups (100), Pull-ups (100), Squats (100), Sit-ups (100), and Running (10 km). 1 rep / 100m = 1 pt (500 pts max/day). |
| **Monospace Habit Calendar** | `/streak` renders an aligned, monospace monthly matrix and full 92-day campaign view with status highlights. |
| **Streak Shield Defense** | Earn Streak Shields every 7-day milestone. Deploy `/shield use` to protect your streak on rest or recovery days. |
| **Dual AI Parsing** | `/quick` parses unstructured workout text via Groq (Qwen 2.5); `/grind` evaluates deep work & academic friction via Gemini. |
| **12-Tier Progression** | Climb from **Initiate (Level 1, 0 pts)** to **Apex (Level 12, 12,000 pts)** over the course of the 90-day challenge. |
| **Automated Cadence** | Morning kickoff (07:00 IST), afternoon pulse (16:30 IST), evening warning (21:00 IST), and midnight finalization (00:00 IST). |

> 📖 **Want the deep dive?**  
> Explore the full [12-Tier Hierarchy](https://vishnunandan555.github.io/winter-arc-discord-bot/#ranks) and [Seasonal Phase Roadmap](https://vishnunandan555.github.io/winter-arc-discord-bot/#phases) on the showcase site.

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

# Timezone for scheduled daily announcements (Default: Asia/Kolkata)
BOT_TIMEZONE=Asia/Kolkata

# Optional: Server role ID to ping during broadcasts
WINTER_ARC_ROLE_ID=

# Optional: AI capabilities for /quick and /grind commands
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
```

### 3. Launch the Bot
```bash
python bot.py
```
*The bot will connect to Discord, initialize `winter_arc.db`, and sync all 21 slash commands automatically.*

---

## 🧪 Automated Test Suite

The test suite contains **52 comprehensive test cases** organized into domain modules inside the [`tests/`](tests/) directory.

```bash
# Run the complete test suite via discovery runner
python test_engine.py

# Or run standard unittest discovery
python -m unittest discover tests

# Or run individual domain test modules
python -m unittest tests/test_streaks_shields.py
python -m unittest tests/test_scoring_logging.py
python -m unittest tests/test_ui_embeds_views.py
python -m unittest tests/test_ai_services.py
python -m unittest tests/test_cogs_bot.py
```

---

## 📋 Slash Command Overview

The bot registers **21 native slash commands** designed with Discord autocomplete and button pagination:

| Category | Commands | Description |
| :--- | :--- | :--- |
| **Workout Logging** | `/log`, `/set`, `/quick`, `/grind` | Add volume, set direct overrides, or parse workout text with AI. |
| **Habits & Streaks** | `/streak`, `/today`, `/tasks`, `/history` | Monospace habit calendar, daily progress card, task guide, and past logs. |
| **Pack Standings** | `/leaderboard`, `/profile`, `/ranks`, `/stats`, `/recap` | Daily/weekly/monthly leaderboards, rank cards, server records, and phase summaries. |
| **Recovery & Settings**| `/shield`, `/settings`, `/enroll`, `/leave_arc`, `/help`, `/ping`| Streak shield defense, morning/evening DM preferences, manual, and latency check. |
| **Server Admin** | `/admin` (`overview`, `set_channel`, `set_role`, `task_add`, `task_toggle`, `tasks_list`, `sync`) | Dedicated announcement channel binding, role configuration, and discipline customization. |

👉 **[Search & Filter All Commands Interactively on the Website »](https://vishnunandan555.github.io/winter-arc-discord-bot/#commands)**

---

## 🛠️ Self-Hosting & Deployment

Winter Arc is engineered for 24/7 reliability with minimal resource consumption (<50 MB RAM on idle).

| Deployment Method | Guide & Reference |
| :--- | :--- |
| **Linux VPS (Systemd)** | Ubuntu/Debian production service configuration with auto-restart: [docs/HOSTING.md »](docs/HOSTING.md#option-b-linux-vps--ubuntu-server-systemd-service) |
| **Docker & Docker Compose** | One-command deployment via `docker compose up -d`: [Dockerfile](Dockerfile) • [docker-compose.yml](docker-compose.yml) |
| **Wispbyte / Pterodactyl** | Low-cost 24/7 bot hosting panel setup: [docs/HOSTING.md »](docs/HOSTING.md#option-a-wispbyte--pterodactyl-panel-freelow-cost-247) |
| **Cloud (Render / Railway)** | Persistent background worker setup: [docs/HOSTING.md »](docs/HOSTING.md#option-c-hosting-on-cloud-render--railway) |

For complete step-by-step instructions, see the **[Full Hosting Guide (docs/HOSTING.md)](docs/HOSTING.md)**.

### 📦 One-Click Deployment Bundle
If you are deploying to **Wispbyte**, a Pterodactyl panel, or uploading via a file manager, generate a production archive with a single command:
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

```
winter-arc-discord-bot/
├── ai/                      # Groq & Gemini AI service integrations
├── cogs/                    # Discord command extensions (warrior & admin cogs)
├── ui/                      # Discord embeds, formatters, and interactive views
├── tests/                   # Modular test suite (52 test cases)
├── docs/                    # Static showcase website (GitHub Pages / Vercel)
│   ├── assets/              # Banners, badges, and branding graphics
│   ├── index.html           # Interactive showcase site
│   ├── HOSTING.md           # Deployment documentation
│   └── ARCHITECTURE.md      # Deep technical architecture breakdown
├── bot.py                   # Discord bot client & lifecycle events
├── config.py                # Environment variables & constants
├── database.py              # SQLite database schema, migrations & queries
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
