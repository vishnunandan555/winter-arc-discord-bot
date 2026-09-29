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

# Realistic single-go / single-set limits to reject fake or unrealistic volume
MAX_SINGLE_SET_LIMITS = {
    "push-ups": 50.0,
    "pull-ups": 20.0,
    "squats": 50.0,
    "sit-ups": 50.0,
    "running": 10.0,
}

# AI Configuration
# Gemini API: Judgemental & reasoning commands (/grind evaluation, Toast & Roast, Sunday address)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

# Groq API: Ultra-fast inference for rapid NLP workout parsing & reactive command nudges
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

import sys
from logging.handlers import RotatingFileHandler

LOG_DIR = os.getenv("LOG_DIR", "logs")
LOG_FILE_PATH = os.path.join(LOG_DIR, "winter_arc.log")
LOG_LEVEL_NAME = os.getenv("LOG_LEVEL", "INFO").upper()


class VoiceWarningFilter(logging.Filter):
    """Filters out irrelevant voice-related warnings since Winter Arc does not use voice channels."""
    def filter(self, record):
        return "voice will NOT be supported" not in record.getMessage()


class NoisyLibraryFilter(logging.Filter):
    """Filters out repetitive third-party diagnostic warnings."""
    def filter(self, record):
        msg = record.getMessage()
        if "Direct use of automatic function calling (AFC)" in msg:
            return False
        return True


def setup_logging():
    log_level = getattr(logging, LOG_LEVEL_NAME, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers to avoid duplicates on reloads
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(log_format, date_format)

    # 1. Console / Stdout Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 2. Rotating File Handler (max 5MB, 3 backups)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_FILE_PATH,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8"
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        sys.stderr.write(f"Warning: Could not configure rotating log file at '{LOG_FILE_PATH}': {e}\n")

    # Suppress verbose / noisy libraries
    logging.getLogger("discord.ext.commands.bot").setLevel(logging.ERROR)
    if log_level > logging.DEBUG:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Apply filters
    logging.getLogger("discord.client").addFilter(VoiceWarningFilter())
    logging.getLogger("google_genai.models").addFilter(NoisyLibraryFilter())

    app_logger = logging.getLogger("winter_arc")
    app_logger.setLevel(log_level)
    return app_logger


def setup_global_exception_handlers(app_logger: logging.Logger):
    """Hooks into sys.excepthook to ensure uncaught exceptions are formatted and logged."""
    def handle_uncaught_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        app_logger.critical("Uncaught fatal exception at top-level:", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_uncaught_exception


logger = setup_logging()
