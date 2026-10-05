# Hosting & Deployment Guide: Winter Arc Bot & Showcase

This guide covers deployment instructions for:
1. **The Showcase & Documentation Website** (GitHub Pages or Vercel)
2. **The 24/7 Discord Bot Process** (Wispbyte / Pterodactyl, Linux VPS with Systemd, Docker / Compose, or Render / Railway)

---

## Part 1: Discord Developer Portal Setup (Required)

Before deploying to any host:
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and click **New Application**.
2. Go to the **Bot** tab:
   - Click **Reset Token** and save your `DISCORD_TOKEN`.
   - Under **Privileged Gateway Intents**, enable:
     - **Server Members Intent** (Required for tracking enrolled members)
     - **Message Content Intent** (Required for processing commands)
   - Click **Save Changes**.
3. Under **OAuth2 -> URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Embed Links`, `Attach Files`, `Read Message History`, `Add Reactions`, `Manage Roles`
   - Use the generated invite URL to add the bot to your Discord server.

---

## Part 2: Hosting the 24/7 Discord Bot Process

### Option A: Wispbyte / Pterodactyl Panel (Free/Low-cost 24/7)

Wispbyte provides low-cost 24/7 Discord bot server containers running Python with automatic restart on crash and web console monitoring. You can deploy using either the **New GitHub Auto-Pull Integration** (recommended) or the **Classic ZIP Bundle Upload**.

#### Method 1: Direct GitHub Integration & Auto-Pull (New & Recommended)
1. **Create Python Server**: In the **Wispbyte Game/Bot Panel**, select **Create Server** and pick the **Python / Generic Discord Bot** egg (Python 3.11+).
2. **Configure GitHub Integration**:
   - In your server sidebar, open the **GitHub Integration** tab.
   - **Repository URL**: `https://github.com/vishnunandan555/winter-arc-discord-bot`
   - **Branch**: `main`
   - **Authentication**: Leave blank if the repository is public. *(If private, enter your GitHub Username and a Personal Access Token with repo read scope)*.
   - **Auto Update on Startup**: Toggle **ON** so restarting your server automatically pulls the latest code.
3. **Clone the Repo**: Click the **Clone / Pull** button at the top to sync files to your server container.
4. **Configure Secrets (`.env`)**:
   - Since `.gitignore` intentionally excludes `.env` and `*.db` for security, open **File Manager** in the panel.
   - Create a `.env` file with your `DISCORD_TOKEN`, `APPLICATION_ID`, etc.
   - *Note: Live SQLite databases (`winter_arc.db`) are ignored by Git, so pulling updates will never overwrite user progress or streaks.*
5. **Verify Startup & Start**:
   - In the **Startup** tab, ensure **Startup Command** is `python bot.py`.
   - Click **Start** on the console. Dependencies install automatically from `requirements.txt` and the bot launches.

#### Method 2: Manual ZIP Archive Deployment (`bot_deploy.zip`) (Classic)
1. **Create Python Server**: In the **Wispbyte Game/Bot Panel**, select **Create Server** and choose the **Python / Generic Discord Bot** egg (Python 3.11+).
2. **Package Locally**:
   - Run the bundler script on your local machine:
     ```bash
     python create_deploy_zip.py
     ```
   - This builds an ultra-lean `bot_deploy.zip` (~130 KB) containing all code, cogs, AI services, and your `.env`, while stripping local databases and caches.
3. **Upload & Extract**:
   - Under **File Manager** on Wispbyte, upload `bot_deploy.zip`.
   - Click the options menu on `bot_deploy.zip` and select **Unarchive / Extract**.
4. **Install Dependencies**:
   - In the web terminal console, run:
     ```bash
     pip install -r requirements.txt
     ```
5. **Verify Startup & Start**:
   - In **Startup**, set **Startup Command** to `python bot.py`.
   - Click **Start** on the console. The bot initializes `winter_arc.db` automatically and goes online.

---

### Option B: Linux VPS / Ubuntu Server (Systemd Service)
For dedicated control on Ubuntu/Debian (DigitalOcean, Hetzner, AWS EC2, Linode):

1. **Clone and setup virtual environment**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/winter-arc-discord-bot.git
   cd winter-arc-discord-bot
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure `.env`**:
   ```bash
   cp .env.example .env
   nano .env
   # Add your DISCORD_TOKEN, NUKE_SECURITY_HASH, GROQ_API_KEY, GEMINI_API_KEY
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
   EnvironmentFile=/home/ubuntu/winter-arc-discord-bot/.env

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

### Option C: Docker & Docker Compose (Containerized)
1. Ensure Docker and Docker Compose are installed on your server.
2. Clone repository and set up environment:
   ```bash
   git clone https://github.com/YOUR_USERNAME/winter-arc-discord-bot.git
   cd winter-arc-discord-bot
   cp .env.example .env
   nano .env
   ```
3. Build and launch with persistent volume:
   ```bash
   docker compose up -d --build
   docker compose logs -f
   ```

---

### Option D: Cloud Background Worker (Render / Railway)
1. In Render or Railway, create a new **Background Worker** (not a Web Service).
2. Connect your GitHub repository.
3. Configure settings:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
4. Add environment variables:
   - `DISCORD_TOKEN`
   - `NUKE_SECURITY_HASH`
   - `WINTER_ARC_ROLE_ID` (optional)
   - `WINTER_ARC_CHANNEL_ID` (optional)
   - `GROQ_API_KEY` (optional)
   - `GEMINI_API_KEY` (optional)
5. Deploy the worker.

---

## Part 3: Hosting the Showcase Website

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

## Part 4: Initial Server Onboarding Checklist

Once your bot process is running:
1. In your Discord server, assign the dedicated broadcast channel:
   ```
   /admin set_channel channel:#winter-arc
   ```
2. Assign the ping role:
   ```
   /admin set_role role:@Winter Arc
   ```
3. Have your members join:
   ```
   /enroll
   ```
4. Test the scheduled layouts:
   ```
   /test_reminder type:morning
   ```
