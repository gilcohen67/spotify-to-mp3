#!/bin/bash
# Double-click to run. First run installs what it needs (takes a minute).
cd "$(dirname "$0")"

if ! python3 -c "import venv" >/dev/null 2>&1; then
  echo "Python 3 is required. Opening the download page..."
  open "https://www.python.org/downloads/"
  read -p "Install Python, then double-click this file again. Press Enter to close."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "First-time setup, please wait..."
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt || {
    read -p "Setup failed. Press Enter to close."; exit 1; }
fi
# pick up any new requirements, and keep yt-dlp current (YouTube changes often)
.venv/bin/pip install -q -r requirements.txt >/dev/null 2>&1
.venv/bin/pip install -q -U yt-dlp >/dev/null 2>&1

.venv/bin/python spotify_to_mp3.py
read -p "Done. Press Enter to close."
