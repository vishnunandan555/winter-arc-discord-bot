# Hosting & Deployment Guide: Winter Arc Bot & Showcase

This guide covers deployment instructions for:
1. **The Showcase & Documentation Website** (GitHub Pages or Vercel)
2. **The 24/7 Discord Bot Process** (Wispbyte / Pterodactyl, Linux VPS with Systemd, or Render / Railway)

---

## Part 1: Hosting the Showcase Website

The website is a static, responsive web application located in the `docs/` directory.

### Option A: GitHub Pages (Free, Zero Configuration)
1. Push your repository to GitHub:
   ```bash
   git push origin main
   ```
2. In your GitHub repository:
   - Go to **Settings** > **Pages**
   - Under **Build and deployment** > **Branch**, select `main` and folder `/docs`
   - Click **Save**
3. Your site will be live at:
   ```
   https://<your-username>.github.io/<your-repo-name>/
   ```

### Option B: Vercel (1-Click Deployment)
The repository includes a pre-configured `vercel.json` pointing to `docs`:
1. In [vercel.com](https://vercel.com), import your forked repository.
2. Vercel detects `outputDirectory: "docs"`.
3. Click **Deploy**.

---

## Part 2: Hosting the Discord Bot Process (24/7)

Discord bots require a continuous Python process maintaining an active WebSocket gateway connection to Discord.

### Option A: Wispbyte / Pterodactyl Panel
1. In the **Wispbyte Game/Bot Panel**, select **Create Server**.
2. Choose the **Python / Generic Discord Bot** egg (Python 3.11+).
3. Under **File Manager** or **Git Integration**, upload or clone your repository.
4. Run dependency installation:
   ```bash
   pip install -r requirements.txt
   ```
5. Configure startup and environment:
   - **Startup Command**: `python bot.py`
   - In **File Manager**, create `.env` and set `DISCORD_TOKEN`, `BOT_TIMEZONE`, etc.
6. Click **Start** on the console. The bot will automatically connect to Discord, synchronize slash commands, and initialize `winter_arc.db`.

---

### Option B: Linux VPS / Ubuntu Server (Systemd Service)
For dedicated control on Ubuntu/Debian (DigitalOcean, Hetzner, AWS EC2, Linode):

1. **Clone and setup virtual environment**:
   ```bash
   git clone https://github.com/your-username/winter-arc-discord-bot.git
   cd winter-arc-discord-bot
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure `.env`**:
   ```bash
   cp .env.example .env
   nano .env
   # Add your DISCORD_TOKEN and BOT_TIMEZONE
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

### Option C: Cloud Background Worker (Render / Railway)
1. In Render or Railway, create a new **Background Worker** (not a Web Service).
2. Connect your GitHub repository.
3. Configure settings:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
4. Add environment variables:
   - `DISCORD_TOKEN`
   - `BOT_TIMEZONE` (e.g. `Asia/Kolkata`)
5. Deploy the worker.
