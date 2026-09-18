# ❄️ Winter Arc Discord Bot

A streamlined, robust fitness and accountability Discord bot built with **Python 3.14**, **discord.py 2.x**, and **SQLite**. Designed for friend groups to track daily workouts, earn capped points, maintain streaks, and celebrate daily and monthly podium finishes.

Pinned to **Asia/Kolkata (IST)** with scheduled morning motivation (05:00), afternoon check-ins (16:30), and midnight finalization (00:00).


---

## 🎨 Bot Assets & Discord Branding

The following assets are formatted and ready to upload to the [Discord Developer Portal](https://discord.com/developers/applications):

| Asset | File | Dimensions | Purpose |
| :--- | :--- | :--- | :--- |
| **Profile Banner (Recommended)** | [`winter_arc_banner.png`](file:///home/vishnunandan555/Projects/winter-arc-bot/winter_arc_banner.png) | **680x240** (17:6) | Cinematic dark gym & mountain wolf banner |
| **Vector Banner (Alternative)** | [`winter_arc_banner_vector_680x240.png`](file:///home/vishnunandan555/Projects/winter-arc-bot/winter_arc_banner_vector_680x240.png) | **680x240** (17:6) | Sharp geometric ice crystal & wolf banner |
| **Retina 2x Banners** | `winter_arc_banner_*_1360x480.png` | **1360x480** (17:6) | Ultra high-res retina versions |
| **App Icon / Avatar** | [`winter_arc_avatar.jpg`](file:///home/vishnunandan555/Projects/winter-arc-bot/winter_arc_avatar.jpg) | **1024x1024** (1:1) | Bot profile picture |

---

## 🛡️ Core Rules & Architecture

1. **The Saitama One-Punch Man Routine**:
   - 💪 **100 Push-ups** — Chest, shoulders, triceps (100 pts)
   - 🧘 **100 Sit-ups** — Core & hip flexors (100 pts)
   - 🦵 **100 Squats** — Quads, glutes, lower body (100 pts)
   - 🏃 **10 km Running** — Cardiovascular endurance (100 pts)
   - **Daily Total**: 400 pts. 100% completion = ⭐ **Perfect Day** + 🔥 **Streak Counter +1**.

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
| `/log [task] [amount]` | Log completed reps or km with instant autocomplete and capped points calculation. *(Enrolled only)* |
| `/leaderboard [day \| month]` | View podium rankings for today or the entire calendar month. |
| `/stats [member]` | View lifetime points, perfect days, active days, and all-time volume per task. *(Enrolled only)* |
| `/history` | View points and completion rates over the past 7 days. *(Enrolled only)* |
| `/profile` | View your warrior card, streak, and enrolled date. *(Enrolled only)* |

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
