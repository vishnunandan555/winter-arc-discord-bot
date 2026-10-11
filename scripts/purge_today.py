#!/usr/bin/env python3
"""
scripts/purge_today.py - Safe CLI Utility to Purge Accidental Logs on Active Recovery Days

Usage:
    python scripts/purge_today.py                 # Purges today's logs (defaults to today in IST)
    python scripts/purge_today.py 2026-10-11      # Purges specific date
    python scripts/purge_today.py 2026-10-11 -y   # Non-interactive / skip confirmation

Features:
- Validates date format.
- Automatically creates a timestamped safety backup in backups/ before deletion.
- Atomic SQLite transaction: deletes daily_logs, grind_logs, and daily_summaries for the date.
- Recalculates and displays summary of cleaned data.
"""

import sys
import os
import argparse
from datetime import datetime

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import BOT_TZ, DB_PATH
import database as db
from phases import is_recovery_day


def main():
    parser = argparse.ArgumentParser(description="Safely purge accidental workout logs recorded on an Active Recovery Day.")
    parser.add_argument("date", nargs="?", default=None, help="Target date in YYYY-MM-DD format (defaults to today in IST).")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt and execute immediately.")
    parser.add_argument("--db", default=DB_PATH, help=f"Path to SQLite database (default: {DB_PATH}).")
    parser.add_argument("--force", action="store_true", help="Force purge even if target date is not a designated recovery day.")

    args = parser.parse_args()

    target_date = args.date or datetime.now(BOT_TZ).strftime("%Y-%m-%d")

    # Validate format
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        print(f"❌ Error: '{target_date}' is not a valid date. Please use YYYY-MM-DD format.")
        sys.exit(1)

    recovery = is_recovery_day(target_date)
    if not recovery and not args.force:
        print(f"⚠️ Warning: {target_date} is NOT listed as an official Active Recovery Day in phases.py.")
        print("To purge this date anyway, use the --force flag.")
        sys.exit(1)

    # Check current row counts in database
    with db.get_connection(args.db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS cnt FROM daily_logs WHERE date = ?;", (target_date,))
        count_logs = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) AS cnt FROM grind_logs WHERE date = ?;", (target_date,))
        count_grind = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) AS cnt FROM daily_summaries WHERE date = ?;", (target_date,))
        count_summaries = cursor.fetchone()["cnt"]

    print("=" * 65)
    print(f"  WINTER ARC — SAFE REST DAY LOG PURGE")
    print("=" * 65)
    print(f"Target Date         : {target_date} ({'Active Recovery Day 🌿' if recovery else 'Training Day ⚠️'})")
    print(f"Database            : {args.db}")
    print(f"Daily Logs Found    : {count_logs}")
    print(f"Grind Logs Found    : {count_grind}")
    print(f"Daily Summaries     : {count_summaries}")
    print("=" * 65)

    if count_logs == 0 and count_grind == 0 and count_summaries == 0:
        print(f"✅ The database is already completely clean for {target_date}. No records to purge.")
        return

    if not args.yes:
        confirm = input(f"Proceed with purging all {count_logs + count_grind + count_summaries} records for {target_date}? (yes/no): ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Purge aborted by user.")
            sys.exit(0)

    try:
        result = db.purge_recovery_day_logs(target_date, db_path=args.db)
        print("\n✅ PURGE SUCCESSFUL!")
        print(f"• Automated Backup Created : {result['backup_path']}")
        print(f"• Deleted Daily Logs       : {result['deleted_daily_logs']}")
        print(f"• Deleted Grind Logs       : {result['deleted_grind_logs']}")
        print(f"• Deleted Daily Summaries  : {result['deleted_daily_summaries']}")
        print("\nAll user points, ranks, and streaks have been restored to their pre-rest-day state.")
    except Exception as e:
        print(f"\n❌ Error during purge: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
