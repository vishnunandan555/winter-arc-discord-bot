# ❄️ Winter Arc Discord Bot

A streamlined, robust fitness and accountability Discord bot built with **Python 3.14**, **discord.py 2.x**, and **SQLite**. Designed for friend groups to track daily workouts, earn capped points, maintain streaks, and celebrate daily and monthly podium finishes.

Pinned to **Asia/Kolkata (IST)** with scheduled morning motivation (05:00), afternoon check-ins (16:30), and midnight finalization (00:00).

---

## 🎨 Bot Profile & Avatar

A custom high-resolution avatar has been created for your bot at:
`winter_arc_avatar.jpg` (in this project root).

### Suggested Bot Profile Description (About Me)
```
❄️ Winter Arc — Discipline, Fitness & Daily Accountability
Tracking daily workouts, points, and streaks for our crew.
Rise at 05:00 | Check in at 16:30 | Finalize at 00:00 IST.
Type /today to view your daily progress or /log to record sets.
```

---

## 🚀 Setup Guide: Connecting Bot to Discord

### Step 1: Create the Discord Application
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application** (top right).
3. Name it: **`Winter Arc`**.
4. In **General Information**:
   - **App Icon**: Click and upload `winter_arc_avatar.jpg` from this folder.
   - **Description**: Paste the suggested description above.
   - Click **Save Changes**.

### Step 2: Configure Bot User & Get Token
1. In the left sidebar, click **Bot**.
2. Customize the bot username if desired (e.g. `Winter Arc`).
3. Under **Build-A-Bot**, click **Reset Token** (authenticate with 2FA if prompted).
4. Click **Copy** to copy your bot token.
5. **Privileged Gateway Intents**:
   - Scroll down to *Privileged Gateway Intents*.
   - Toggle **ON**:
     - ✅ **Server Members Intent**
     - ✅ **Message Content Intent**
   - Click **Save Changes**.

### Step 3: Invite the Bot to Your Server
1. In the left sidebar, click **OAuth2** ➔ **URL Generator**.
2. Under **Scopes**, select:
   - ✅ `bot`
   - ✅ `applications.commands`
3. Under **Bot Permissions**, select:
   - ✅ **View Channels**
   - ✅ **Send Messages**
   - ✅ **Embed Links**
   - ✅ **Attach Files**
   - ✅ **Read Message History**
   - ✅ **Use Slash Commands**
4. Copy the generated URL at the bottom of the page.
5. Paste it into your browser, choose your Discord server, and click **Authorize**.

---

## 💻 Running Locally

### 1. Configure Environment Variables
Open the `.env` file in this directory and paste your token:
```ini
DISCORD_TOKEN=your_token_copied_from_step_2

# Optional but HIGHLY recommended for local testing:
# Enables instantaneous slash command updates without waiting for Discord's 1-hour global cache.
# (In Discord: User Settings -> Advanced -> Turn on Developer Mode. Right-click your server -> Copy Server ID)
TEST_GUILD_ID=your_server_id_here

# Optional: Channel ID where 00:00 midnight daily results will be posted
DAILY_RESULTS_CHANNEL_ID=
```

### 2. Activate Virtual Environment & Launch
```bash
# In your terminal inside /home/vishnunandan555/Projects/winter-arc-bot:
source .venv/bin/activate

# Run automated tests to verify database and calculations:
python test_engine.py

# Launch the bot:
python bot.py
```

When successful, your console will output:
```
2026-09-18 ... [INFO] winter_arc.bot: SQLite database initialized and seed tasks confirmed.
2026-09-18 ... [INFO] winter_arc.scheduler: Winter Arc Scheduler started in timezone Asia/Kolkata.
2026-09-18 ... [INFO] winter_arc.bot: Slash commands synchronized instantaneously to Test Guild: ...
2026-09-18 ... [INFO] winter_arc.bot: Logged in successfully as Winter Arc#...
```

---

## 🎮 Slash Command Reference

### User Commands
| Command | Description |
| :--- | :--- |
| `/ping` | Health check & gateway latency in milliseconds. |
| `/today [member]` | View visual progress bars (`🟩🟩🟩⬜⬜`), earned points, completion %, and current streak. |
| `/log [task] [amount]` | Log completed reps or km with instant autocomplete and capped points calculation. |
| `/leaderboard [day \| month]` | View podium rankings for today or the entire calendar month. |
| `/stats [member]` | View lifetime points, perfect days, active days, and all-time volume per task. |
| `/history` | View points and completion rates over the past 7 days. |
| `/profile` | View your warrior card, streak, joined date, and active reminder toggles. |
| `/reminders` | Interactive UI with buttons (`[🌅 Morning ON/OFF]`, `[⏰ Afternoon ON/OFF]`). |
| `/test_reminder [type]` | Test or preview morning kickoff, afternoon check-in, or midnight finalization DMs instantly. |

### Admin Commands (`/admin`, requires Administrator)
| Command | Description |
| :--- | :--- |
| `/admin task_add` | Dynamically add a new exercise challenge (e.g. Plank 5 minutes). |
| `/admin task_toggle` | Turn an existing task on or off without code changes. |
| `/admin tasks_list` | Inspect all tasks in the database. |
| `/admin set_results_channel` | Select the channel where midnight podium results are posted. |

---

## 🧪 Testing Reminders On Demand
Don't wait until 05:00 or 16:30 IST to test reminders!
Type in Discord:
- `/test_reminder reminder_type:Morning Kickoff` ➔ Sends you a DM of the 05:00 morning message.
- `/test_reminder reminder_type:Afternoon Check-in` ➔ Sends you a DM of the 16:30 check-in message.
- `/test_reminder reminder_type:Midnight Finalization` ➔ Runs the rollover calculation and displays the podium embed.

---

## ☁️ Next Step: Moving to 24/7 Hosting (Wispbyte)
Once you have tested locally and verified the bot:
1. Initialize git and push to a private GitHub repository:
   ```bash
   git init
   git add .
   git commit -m "feat: complete winter arc discord bot"
   ```
2. On Wispbyte:
   - Create a Python bot server.
   - Set environment variable `DISCORD_TOKEN`.
   - Set startup command: `python bot.py`.
   - Upload project files (excluding `.venv` and `.env`).
