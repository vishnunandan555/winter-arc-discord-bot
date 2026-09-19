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

# Default Winter Arc Role ID (0 means disabled until explicitly configured)
DEFAULT_ROLE_ID = int(os.getenv("WINTER_ARC_ROLE_ID", "0"))

# Database path
DB_PATH = os.getenv("WINTER_ARC_DB", "winter_arc.db")

# AI Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Setup logger
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    return logging.getLogger("winter_arc")

logger = setup_logging()
