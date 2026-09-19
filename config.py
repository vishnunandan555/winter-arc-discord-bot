"""
config.py - Centralized Configuration for Winter Arc Bot

Manages environment variables, timezone settings, logging configuration,
and default role IDs.
"""

import os
import logging
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

# Discord Application Token
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")

# Default Timezone for all calculations & schedules (Asia/Kolkata / IST)
TIMEZONE_NAME = os.getenv("BOT_TIMEZONE", "Asia/Kolkata")
BOT_TZ = ZoneInfo(TIMEZONE_NAME)

# Default Winter Arc Role ID (Fallback when server has not explicitly configured another)
DEFAULT_ROLE_ID = int(os.getenv("WINTER_ARC_ROLE_ID", "1550511682344845352"))

# Database path
DB_PATH = os.getenv("WINTER_ARC_DB", "winter_arc.db")

# AI API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Setup logger
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    return logging.getLogger("winter_arc")

logger = setup_logging()
