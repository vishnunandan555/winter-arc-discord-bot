# 🌐 Hosting & Deployment Guide: Winter Arc Bot & Web Dashboard

This guide covers deployment instructions for:
1. **The Web Statistics Dashboard** (GitHub Pages, Vercel, or Render)
2. **The 24/7 Discord Bot Process** (Render Background Worker, Railway, or VPS / Systemd)

---

## Part 1: Hosting the Web Dashboard

The web dashboard is a lightweight, responsive static web application located in the `docs/` folder.

### Option A: GitHub Pages (Recommended — 100% Free, Zero Config)
Since the web application is inside `docs/`, GitHub Pages can host it natively for free:

1. Push your code to your GitHub repository:
   ```bash
   git push origin main
   ```
2. Open your repository on GitHub:
   - Go to **Settings** > **Pages** (in the left sidebar).
3. Under **Build and deployment** > **Branch**:
   - Select branch: `main`
   - Select folder: `/docs`
   - Click **Save**.
4. Within 1–2 minutes, GitHub will publish your site at:
   ```
   https://<your-username>.github.io/<your-repo-name>/
   ```

---

### Option B: Vercel (1-Click Deployment)
The repository includes a pre-configured `vercel.json` pointing to `docs/`:

1. Go to [vercel.com](https://vercel.com) and click **Add New Project**.
2. Import `winter-arc-discord-bot` from your GitHub account.
3. Vercel will automatically detect `vercel.json` with output directory `docs`.
4. Click **Deploy**. Your dashboard will be live at `https://your-project.vercel.app`.

---

### Option C: Render (Static Site)
1. Go to [dashboard.render.com](https://dashboard.render.com) and click **New +** > **Static Site**.
2. Connect your GitHub repository.
3. Configure:
   - **Publish directory**: `docs`
   - **Build command**: `python export_web_stats.py` (optional, or leave blank)
4. Click **Create Static Site**.

---

## Part 2: Hosting the Discord Bot Process (24/7)

The Discord bot needs a continuous Python runtime to maintain a WebSocket gateway connection to Discord.

### Option A: Background Worker on Render (Free / Cheap)
1. Go to [dashboard.render.com](https://dashboard.render.com) and click **New +** > **Background Worker**.
2. Connect your GitHub repository.
3. Configure settings:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
4. Add **Environment Variables**:
   - `DISCORD_TOKEN`: Your Discord Bot Token from the Developer Portal
   - `BOT_TIMEZONE`: `Asia/Kolkata`
   - `WINTER_ARC_ROLE_ID`: `1550511682344845352`
5. Click **Create Background Worker**.

---

### Option B: Linux VPS / Ubuntu Server (Systemd Service)
For maximum control on a VPS (DigitalOcean, Hetzner, AWS EC2, Linode):

1. **Clone and setup virtual environment**:
   ```bash
   git clone git@github.com:vishnunandan555/winter-arc-discord-bot.git
   cd winter-arc-discord-bot
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Configure `.env`**:
   ```bash
   cp .env.example .env
   nano .env
   # Add your DISCORD_TOKEN
   ```
3. **Create a Systemd Service**:
   ```bash
   sudo nano /etc/systemd/system/winter-arc.service
   ```
   Paste the following service definition:
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
4. **Enable and start the service**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable winter-arc
   sudo systemctl start winter-arc
   sudo systemctl status winter-arc
   ```
5. **View live bot logs**:
   ```bash
   journalctl -u winter-arc -f
   ```

---

## Part 3: Synchronizing Web Stats

- **Automatic**: `scheduler.py` calls `export_stats_to_json()` every night at 00:00 IST during midnight finalization.
- **Manual**: You can manually update `docs/stats.json` at any time by running:
  ```bash
  python export_web_stats.py
  ```
