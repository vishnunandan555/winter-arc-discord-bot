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

# Minimum points required in a day to maintain or advance an active streak (default: 30)
MIN_STREAK_POINTS = int(os.getenv("MIN_STREAK_POINTS", "30"))

# AI Configuration
# Gemini API: Judgemental & reasoning commands (/grind evaluation, Toast & Roast, Sunday address)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

# Groq API: Ultra-fast inference for rapid NLP workout parsing & reactive command nudges
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

class VoiceWarningFilter(logging.Filter):
    """Filters out irrelevant voice-related warnings since Winter Arc does not use voice channels."""
    def filter(self, record):
        return "voice will NOT be supported" not in record.getMessage()

# Setup logger
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    # Suppress prefix command intent warning since bot exclusively uses slash commands
    logging.getLogger("discord.ext.commands.bot").setLevel(logging.ERROR)
    # Filter voice warnings
    logging.getLogger("discord.client").addFilter(VoiceWarningFilter())
    return logging.getLogger("winter_arc")

logger = setup_logging()
