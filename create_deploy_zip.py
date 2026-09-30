#!/usr/bin/env python3
"""
create_deploy_zip.py - Package Winter Arc Bot for Deployment

Generates a clean, production-ready 'bot_deploy.zip' bundle for uploading
to hosting services (Wispbyte, Pterodactyl, VPS, Docker, Railway, etc.).

Features:
- Includes .env for seamless one-click hosting configuration
- Excludes virtual environments, database files, and caches
- Excludes duplicate website assets and docs to keep the archive ultra-lean (~80 KB)
- Removes any previous zip first to prevent stale file ghosting
"""

import os
import sys
import zipfile
from pathlib import Path

# Project root directory
ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_ZIP = ROOT_DIR / "bot_deploy.zip"

# Core files to include if they exist
ROOT_FILES = [
    ".env",
    ".env.example",
    "bot.py",
    "config.py",
    "database.py",
    "helpers.py",
    "levels.py",
    "phases.py",
    "scheduler.py",
    "tips.py",
    "requirements.txt",
    "README.md",
    "test_engine.py",
    "Dockerfile",
    "docker-compose.yml",
]

# Directories to bundle recursively
INCLUDE_DIRS = [
    "ai",
    "cogs",
    "ui",
    "tests",
]

# Patterns and directories to strictly exclude
EXCLUDE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".db",
    ".db-wal",
    ".db-shm",
    ".sqlite",
    ".sqlite3",
    ".log",
}

EXCLUDE_DIRS = {
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".git",
    ".github",
    ".vscode",
    ".gemini",
    "logs",
    "scratch",
    "docs",     # Static website documentation (served via GitHub Pages)
    "assets",   # Website branding assets (avoids 8MB duplication)
}


def should_include_file(file_path: Path) -> bool:
    """Checks if a file should be included in the deployment package."""
    # Exclude zip itself
    if file_path.name == "bot_deploy.zip" or file_path.suffix == ".zip":
        return False

    # Check extension exclusions
    if file_path.suffix in EXCLUDE_EXTENSIONS:
        return False

    # Check directory exclusions in path parts
    for part in file_path.parts:
        if part in EXCLUDE_DIRS:
            return False

    return True


def create_package():
    """Builds the deployment archive."""
    print("=" * 60)
    print("🚀 Winter Arc Bot - Packaging Deployment Bundle")
    print("=" * 60)

    # 1. Remove previous zip to guarantee a fresh build
    if OUTPUT_ZIP.exists():
        try:
            OUTPUT_ZIP.unlink()
            print(f"🧹 Removed existing {OUTPUT_ZIP.name}")
        except OSError as e:
            print(f"⚠️ Warning: Could not remove old zip: {e}")

    added_files = []
    total_uncompressed_bytes = 0

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zipf:
        # Add root files
        for filename in ROOT_FILES:
            file_path = ROOT_DIR / filename
            if file_path.is_file():
                arcname = filename
                zipf.write(file_path, arcname=arcname)
                added_files.append(arcname)
                total_uncompressed_bytes += file_path.stat().st_size
                if filename == ".env":
                    print("  🔒 Included .env (with hosting secrets)")
                else:
                    print(f"  📄 Added {arcname}")

        # Add directory trees
        for dir_name in INCLUDE_DIRS:
            dir_path = ROOT_DIR / dir_name
            if not dir_path.is_dir():
                continue

            for root, dirs, files in os.walk(dir_path):
                # Filter out excluded directory names in-place
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

                for file in files:
                    file_path = Path(root) / file
                    if should_include_file(file_path):
                        arcname = file_path.relative_to(ROOT_DIR).as_posix()
                        zipf.write(file_path, arcname=arcname)
                        added_files.append(arcname)
                        total_uncompressed_bytes += file_path.stat().st_size
                        print(f"  📦 Added {arcname}")

    zip_size_bytes = OUTPUT_ZIP.stat().st_size
    zip_size_kb = zip_size_bytes / 1024

    print("=" * 60)
    print(f"✅ Deployment bundle created: {OUTPUT_ZIP.name}")
    print(f"📊 Total files packaged: {len(added_files)}")
    print(f"📦 Archive size: {zip_size_kb:.2f} KB ({zip_size_bytes:,} bytes)")
    print("🚫 Asset duplication: ZERO (assets/ & docs/ excluded)")
    print("🚫 Temporary/DB files: ZERO (.venv, *.db, __pycache__ excluded)")
    print("=" * 60)
    print(f"👉 Ready to upload: {OUTPUT_ZIP.name}")


if __name__ == "__main__":
    create_package()
