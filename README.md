# Winter Arc Discord Bot & Showcase

An open-source, self-hosted fitness accountability and discipline ecosystem built with Python 3.14, discord.py 2.x, and SQLite.

Engineered for private Discord communities and friend circles to track daily calisthenics and running, enforce anti-cheat capped volume, maintain unbroken streaks, climb a 12-level pack hierarchy, and celebrate daily podium finishes.

---

## Why Winter Arc Was Built

Most fitness trackers and habit apps fail for two reasons:
1. **Solitary Isolation**: Working out alone in a closed app provides no collective pressure or shared pride.
2. **Subscription Bloat & Complexity**: Modern fitness apps are crowded with paywalls, social feeds, and intrusive tracking.

Winter Arc takes inspiration from the 90-day Winter Arc self-improvement protocol and moves the entire accountability loop directly into Discord:
- **Tribal Peer Accountability**: Progress, missed days, and streaks are visible to your pack in your private server.
- **Anti-Cheat 500 Daily Point Ceiling**: To eliminate erratic binging and impossible vanity scores, daily points are capped at 500. Consistency over 90 days is rewarded over single erratic bursts.
- **Zero-Friction Logging**: Members log volume with clean slash commands or natural language AI parsing in seconds.
- **Data Sovereignty**: The bot is 100% self-hosted. All user volume, streak states, and logs reside inside a local SQLite database that your server controls.

---

## The 5 Seasonal Phases

The Winter Arc journey follows a structured 5-phase seasonal cadence:

| Phase | Timeframe | Designation | Focus |
| :---: | :--- | :--- | :--- |
| **Phase 0** | **September** | **Warmup & Trial** | Test-drive the 5 disciplines, establish routines, setup the bot, and eliminate logistical friction before October 1. |
| **Phase 1** | **October** | **The Shock & Ignition** | Official kickoff of the 90-day arc. Overcome DOMS, cut distractions, lock in morning discipline, and build streak momentum. |
| **Phase 2** | **November** | **The Dark Tunnel** | Motivation fades; pure mechanical discipline takes over. Cold mornings, dark evenings, volume stacked in absolute silence. |
| **Phase 3** | **December** | **The Real Winter Arc** | The apex trial. Freezing weather, end-of-year fatigue, and holiday temptations. The pack locks shields and ascends to Apex rank. |
| **Phase 4** | **January** | **Cooldown & Standard** | While others scramble to make New Year resolutions, you emerge transformed. The 90-day arc concludes; the lifestyle remains. |

---

## Core Capabilities & Features

### 1. The Five Foundation Disciplines (Saitama Protocol)
Modelled after the legendary **Saitama training challenge** (100 push-ups, 100 sit-ups, 100 squats, and a 10 km run), amplified with 100 pull-ups to forge complete calisthenic upper-body dominance:

- **Push-ups**: 100 reps ceiling (1 point per rep, 100 pts max)
- **Pull-ups**: 100 reps ceiling (1 point per rep, 100 pts max)
- **Squats**: 100 reps ceiling (1 point per rep, 100 pts max)
- **Sit-ups**: 100 reps ceiling (1 point per rep, 100 pts max)
- **Running**: 10 km ceiling (1 point per 100m / 10 pts per km, 100 pts max)

> **High Ceiling. Zero Barrier. Every Rep Counts**:  
> 500 points a day is a brutal mountain &mdash; and that is the point. You are not expected to hit peak volume on day one. Whether you can only grind out 10 push-ups, 2 pull-ups, or jog a single kilometer today, **log it**. Every single repetition earns points toward your pack rank. The Winter Arc is about locking in, embracing the cold, and stacking volume in silence until you become undeniable.
> 
> Maxing out all 500 daily points earns **Clean Day** status and fuels your active streak.

### 2. Dual Logging Engine
- `/log [task] [amount]`: Progressively adds completed reps or kilometers throughout the day.
- `/set [task] [amount]`: Directly sets or overrides today's count, allowing immediate correction of typos or resetting to 0.

### 3. AI Workout Intelligence
- **Natural Language Parsing (Groq)**: `/quick [text]` allows warriors to log complex workouts in plain text (e.g., `/quick "did 45 pushups and ran 3.2km"`).
- **Friction & Academic Grind (Google Gemini)**: `/grind [text]` allows warriors to submit daily deep work, studying, or engineering friction to receive verified bonus points (1x per day, +10 to +60 pts).

### 4. Streak System & Frost Shield Defense
- Daily streaks advance with consecutive Clean Days.
- To prevent injury or demoralization from illness, warriors earn **Frost Shields** by achieving streak milestones. Activating a shield with `/shield use` protects an active streak across a necessary recovery day.

### 5. Automated Cadence
Scheduled automated checkpoints broadcast into the designated channel:
- **05:00**: Morning Wakeup & Daily Challenge Announcement
- **16:30**: Midday Accountability Pulse
- **00:00**: Midnight Podium Finalization, Streak Calculation, and Rollover

### 6. Single Dedicated Channel Architecture
The bot broadcasts solely inside the text channel designated by `/admin set_channel`. No clutter or unsolicited bot spam occurs across other server channels.

---

## The 12-Level Pack Hierarchy

Calibrated around a 90-day arc, culminating at Apex (12,000 Lifetime Points / ~133 pts daily average):

| Level | Rank Title | Point Range | Target Timeline | Focus |
| :---: | :--- | :--- | :--- | :--- |
| **01** | **Lone Stray** | 0 - 499 pts | Days 1 - 3 | Initiation |
| **02** | **Stray** | 500 - 1,199 pts | Days 4 - 8 | Habit Forming |
| **03** | **Scout** | 1,200 - 1,999 pts | Days 9 - 15 | Momentum |
| **04** | **Prowler** | 2,000 - 2,999 pts | Days 16 - 22 | Routine Locked |
| **05** | **Tracker** | 3,000 - 4,199 pts | Days 23 - 31 | Reliable Volume |
| **06** | **Hunter** | 4,200 - 5,499 pts | Days 32 - 41 | Halfway Milestone |
| **07** | **Savage** | 5,500 - 6,999 pts | Days 42 - 52 | High Endurance |
| **08** | **Vanguard** | 7,000 - 8,499 pts | Days 53 - 63 | Elite Discipline |
| **09** | **Frostborn** | 8,500 - 9,799 pts | Days 64 - 73 | Winter Hardened |
| **10** | **Predator** | 9,800 - 10,799 pts | Days 74 - 81 | Relentless Output |
| **11** | **Alpha** | 10,800 - 11,999 pts | Days 82 - 89 | Final Ascent |
| **12** | **Apex** | 12,000+ pts | Day 90+ | Peak Mastery |

---

## Slash Command Directory

### Member Commands
| Command | Purpose |
| :--- | :--- |
| `/today [member]` | Inspect daily volume, earned points, completion rate, and streak. |
| `/log [task] [amount]` | Increment today's workout reps or kilometers with autocomplete. |
| `/set [task] [amount]` | Directly set or correct today's count (or 0 to reset). |
| `/profile` | View rank card, progress towards next tier, lifetime points, and streak. |
| `/ranks` | Display the 12-tier pack hierarchy, point targets, and requirements. |
| `/leaderboard` | Interactive leaderboard with Daily and All-Time overall standings. |
| `/quick [text]` | Log natural language workout descriptions via Groq LLM parsing. |
| `/grind [text]` | Log academic/engineering friction evaluated by Gemini (+10 to +60 pts). |
| `/shield status` | Check Frost Shield inventory and active protection state. |
| `/shield use [reason]` | Activate a Frost Shield on a rest day to defend streak integrity. |
| `/enroll` | Join the Winter Arc challenge and receive the server role. |
| `/leave_arc` | Step away and unenroll from the challenge. |
| `/help` | View command manual, daily schedule, and rules. |
| `/ping` | Health check and gateway latency in milliseconds. |

### Administrator Commands (`/admin`, requires Administrator permissions)
| Command | Purpose |
| :--- | :--- |
| `/admin overview` | Inspect broadcast channel, ping role, and enrolled warrior count. |
| `/admin set_channel [channel]` | Assign dedicated text channel for automated scheduled announcements. |
| `/admin set_role [role]` | Assign role mentioned during morning and evening announcements. |
| `/admin task_add [name] [goal] [pts]` | Dynamically add custom disciplines (e.g. Plank 5 min). |
| `/admin task_toggle [task_id]` | Enable or disable an existing discipline without code modifications. |
| `/admin tasks_list` | Inspect all disciplines in the database. |
| `/test_reminder [type]` | Preview morning kickoff, afternoon pulse, or midnight broadcast layouts. |

---

## Self-Hosting & Deployment Guide

This repository is designed to be forked and self-hosted on your own infrastructure.

### Step 1: Fork and Clone the Repository
1. Click **Fork** on the top right of the GitHub repository.
2. Clone your fork locally or onto your server:
   ```bash
   git clone https://github.com/your-username/winter-arc-discord-bot.git
   cd winter-arc-discord-bot
   ```

### Step 2: Discord Developer Portal Setup
1. Navigate to the [Discord Developer Portal](https://discord.com/developers/applications) and create a **New Application**.
2. Go to the **Bot** tab:
   - Click **Reset Token** and copy your token securely.
   - Under **Privileged Gateway Intents**, enable:
     - **Server Members Intent**
     - **Message Content Intent**
   - Click **Save Changes**.

### Step 3: Configure Environment Variables
Create a `.env` file from the provided `.env.example`:
```bash
cp .env.example .env
```
Fill in your credentials:
```env
# Required: Discord Bot Token from Developer Portal
DISCORD_TOKEN=your_bot_token_here

# Timezone for scheduled daily announcements (Default: Asia/Kolkata)
BOT_TIMEZONE=Asia/Kolkata

# Optional: Server role ID to ping on announcements
WINTER_ARC_ROLE_ID=

# Optional: AI capabilities for /quick and /grind commands
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
```

---

### Step 4: Choose Your Hosting Method

#### Option A: Hosting on Wispbyte (or any Pterodactyl-based host)
1. In the **Wispbyte Game/Bot Panel**, click **Create Server**.
2. Select the **Python / Generic Bot** egg (Python 3.11+ recommended).
3. In **File Manager**, upload the repository files or pull them directly via the Git repository settings.
4. Ensure `pip install -r requirements.txt` is run on installation or execute it in the panel terminal.
5. In the **Startup** tab:
   - Set **Startup Command**: `python bot.py`
6. In **File Manager**, create `.env` and paste your environment variables.
7. Click **Start** on the console. The bot will connect to Discord, register slash commands, and initialize the SQLite database automatically.

#### Option B: Hosting on a Linux VPS (Ubuntu / Debian Systemd)
For running on a VPS (DigitalOcean, Hetzner, AWS EC2, Linode):

1. **Setup environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Create a Systemd Service**:
   ```bash
   sudo nano /etc/systemd/system/winter-arc.service
   ```
   Paste the following service configuration:
   ```ini
   [Unit]
   Description=Winter Arc Discord Bot
   After=network.target

   [Service]
   Type=simple
   User=ubuntu
   WorkingDirectory=/home/ubuntu/winter-arc-discord-bot
   ExecStart=/home/ubuntu/winter-arc-discord-bot/.venv/bin/python bot.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

3. **Enable and start the service**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable winter-arc
   sudo systemctl start winter-arc
   ```

4. **Monitor live logs**:
   ```bash
   journalctl -u winter-arc -f
   ```

#### Option C: Hosting on Cloud (Render / Railway)
Discord bots require a persistent background process maintaining a live WebSocket connection:
1. Create a **Background Worker** service (not a Web Service).
2. Connect your GitHub repository.
3. Configure:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
4. Add `DISCORD_TOKEN` and `BOT_TIMEZONE` in the service Environment Variables tab.

---

### Step 5: Initial Discord Server Configuration
Once your bot is running and connected to your server:
1. Assign the broadcast channel:
   ```
   /admin set_channel channel:#winter-arc
   ```
2. Assign the announcement role:
   ```
   /admin set_role role:@Winter Arc
   ```
3. Have members join the challenge:
   ```
   /enroll
   ```

---

## Showcase Website

A static showcase and self-hosting documentation site is included in the `docs/` folder.
To preview the website locally:
```bash
python -m http.server 8000 --directory docs
```
The site is pre-configured for deployment via GitHub Pages (serving `/docs`) or Vercel (via included `vercel.json`).

---

## Local Development & Testing

```bash
# Activate virtual environment
source .venv/bin/activate

# Run automated test suite
python test_engine.py -v

# Run the bot in development mode
python bot.py
```
