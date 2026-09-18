# ❄️ Winter Arc Discord Bot

A streamlined, robust fitness and accountability Discord bot built with **Python 3.14**, **discord.py 2.x**, and **SQLite**. Designed for friend groups to track daily workouts, earn capped points, maintain streaks, and celebrate daily and overall podium finishes.
*(Mascot: Amarok the Arctic Wolf)*

Pinned to **Asia/Kolkata (IST)** with scheduled morning motivation (05:00), afternoon check-ins (16:30), and midnight finalization (00:00).


---

## 🎨 Bot Assets & Discord Branding

The following assets are formatted and ready to upload to the [Discord Developer Portal](https://discord.com/developers/applications):

| Asset | File | Dimensions | Purpose |
| :--- | :--- | :--- | :--- |
| **Profile Banner (Recommended)** | [`winter_arc_banner.png`](file:///home/vishnunandan555/Projects/winter-arc-bot/winter_arc_banner.png) | **680x240** (17:6) | Cinematic dark gym & mountain wolf banner |
| **Vector Banner (Alternative)** | [`winter_arc_banner_vector_680x240.png`](file:///home/vishnunandan555/Projects/winter-arc-bot/winter_arc_banner_vector_680x240.png) | **680x240** (17:6) | Sharp geometric ice crystal & wolf banner |
| **Retina 2x Banners** | `winter_arc_banner_*_1360x480.png` | **1360x480** (17:6) | Ultra high-res retina versions |
| **Avatar — Pitch Black (Clean)** | [`winter_arc_wolf_black_bg.png`](file:///home/vishnunandan555/Projects/winter-arc-bot/winter_arc_wolf_black_bg.png) | **1024x1024** (1:1) | Pure black background, neon cyan glow vector wolf |
| **Avatar — Minimal Snow Dust** | [`winter_arc_wolf_snow_bg.png`](file:///home/vishnunandan555/Projects/winter-arc-bot/winter_arc_wolf_snow_bg.png) | **1024x1024** (1:1) | Black background, subtle frost dust aura, no weights |
| **Avatar — Obsidian Shield Badge** | [`winter_arc_wolf_crest_badge.png`](file:///home/vishnunandan555/Projects/winter-arc-bot/winter_arc_wolf_crest_badge.png) | **1024x1024** (1:1) | Pitch black background with glowing circular neon crest |

---

## 🛡️ Core Rules & Architecture

1. **The 5 Winter Arc Disciplines (500 Points Daily Max)**:
   - 💪 **100 Push-ups** — 1 point per rep (100 pts max)
   - 🧗 **100 Pull-ups** — 1 point per rep (100 pts max)
   - 🦵 **100 Squats** — 1 point per rep (100 pts max)
   - 🧘 **100 Sit-ups** — 1 point per rep (100 pts max)
   - 🏃 **10 km Running** — 1 point per 100m = 10 pts / km (100 pts max)
   - **Daily Total**: **500 points**. 100% completion = ⭐ **Perfect Day** + 🔥 **Streak Counter +1**.

2. **Enrollment Gate**: Commands (`/today`, `/log`, `/stats`, etc.) only respond to enrolled warriors. Anyone else is prompted to run `/enroll`.
3. **Dedicated Channel Only**: The bot only auto-broadcasts (05:00, 16:30, 00:00 IST) in the server's dedicated channel configured by `/admin set_channel`. Everywhere else, the bot stays completely quiet unless directly prompted.
4. **Role Pings (No Private DMs)**: Daily automated announcements mention the server's Winter Arc role (`/admin set_role`). Users can mute the role/channel in Discord if they want quiet, while remaining enrolled.
5. **Admin Dashboard**: `/admin overview` gives server admins a single-command overview of all enrolled members, today's scores, streaks, and settings.

---

## 🚀 Quick Setup for Server Admins

Once you invite the bot into your server:

1. **Set the Dedicated Channel**:
   ```
   /admin set_channel channel:#winter-arc
   ```
2. **Set the Ping Role**:
   ```
   /admin set_role role:@Winter Arc
   ```
3. **Enroll in the Challenge**:
   ```
   /enroll
   ```
4. **Inspect Server Dashboard**:
   ```
   /admin overview
   ```

---

## 🎮 Slash Command Reference

### Warrior Commands
| Command | Description |
| :--- | :--- |
| `/help` | View the complete command manual, daily schedule, and rules. |
| `/enroll` | Enroll in the Winter Arc challenge and receive the warrior role. |
| `/leave_arc` | Step away and unenroll from the challenge. |
| `/ping` | Health check & gateway latency in milliseconds. |
| `/today [member]` | View visual progress bars (`🟩🟩🟩⬜⬜`), earned points, completion %, and current streak. *(Enrolled only)* |
| `/log [task] [amount]` | Add completed reps or km throughout the day with instant autocomplete. *(Enrolled only)* |
| `/set [task] [amount]` | Directly set or override today's total (or set to `0` to fix typos/reset). *(Enrolled only)* |
| `/leaderboard` | Interactive leaderboard with **Daily** and **Overall** sub-buttons to toggle views in-place. |
| `/stats [member]` | View lifetime points, perfect days, active days, and all-time volume per task. *(Enrolled only)* |
| `/history` | View points and completion rates over the past 7 days. *(Enrolled only)* |
| `/profile` | View member card, rank tier progress, streak, and enrolled date. *(Enrolled only)* |
| `/ranks` | View the 12-level Winter Pack hierarchy and point thresholds. |

---

## 🐺 12-Level Winter Pack Progression

Calibrated around a 90-day Winter Arc with **Apex** achieved at **12,000 Lifetime Points** (~133 pts/day average):

| Level | Title | Badge | Point Range | Tier Target |
| :---: | :--- | :---: | :--- | :--- |
| **1** | **Lone Stray** | 🐾 | `0 – 499 pts` | Getting started |
| **2** | **Stray** | 🐺 | `500 – 1,199 pts` | Habit forming |
| **3** | **Scout** | 🧭 | `1,200 – 1,999 pts` | Building momentum |
| **4** | **Prowler** | 🐾 | `2,000 – 2,999 pts` | Routine locked |
| **5** | **Tracker** | 🏹 | `3,000 – 4,199 pts` | Reliable volume |
| **6** | **Hunter** | 🗡️ | `4,200 – 5,499 pts` | Halfway milestone |
| **7** | **Savage** | ⚔️ | `5,500 – 6,999 pts` | High endurance |
| **8** | **Vanguard** | 🛡️ | `7,000 – 8,499 pts` | Elite discipline |
| **9** | **Frostborn** | ❄️ | `8,500 – 9,799 pts` | Winter-hardened |
| **10** | **Predator** | ⚡ | `9,800 – 10,799 pts` | Relentless output |
| **11** | **Alpha** | 🔥 | `10,800 – 11,999 pts` | Final ascent |
| **12** | **Apex** | 👑 | `12,000+ pts` | **Peak Mastery (Max Rank)** |

---

### Admin Commands (`/admin`, requires Administrator)
| Command | Description |
| :--- | :--- |
| `/admin overview` | Server dashboard: inspect channel, role, enrolled members, and tasks. |
| `/admin set_channel [channel]` | Set the dedicated channel where daily scheduled messages are broadcast. |
| `/admin set_role [role]` | Set the role to ping during daily scheduled announcements. |
| `/admin task_add` | Dynamically add a new exercise discipline (e.g. Plank 5 minutes). |
| `/admin task_toggle` | Turn an existing task on or off without code changes. |
| `/admin tasks_list` | Inspect all tasks in the database. |
| `/test_reminder [type]` | Test or preview morning kickoff, afternoon check-in, or midnight finalization in the dedicated channel. |

---

## 💻 Running Locally

```bash
# In your terminal inside /home/vishnunandan555/Projects/winter-arc-bot:
source .venv/bin/activate

# Run automated test suite:
python test_engine.py

# Launch the bot:
python bot.py
```
