@echo off
rem Double-click to run. First run installs what it needs (takes a minute).
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python 3 is required. Opening the download page...
  start https://www.python.org/downloads/
  echo Install Python (tick "Add python.exe to PATH"), then double-click this file again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo First-time setup, please wait...
  py -3 -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
  if errorlevel 1 (
    echo Setup failed.
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -m pip install -q -U yt-dlp >nul 2>nul

".venv\Scripts\python.exe" spotify_to_mp3.py
if exist downloads start "" downloads
echo Done.
pause
