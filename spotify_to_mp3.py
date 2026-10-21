#!/usr/bin/env python3
"""Download a Spotify playlist as MP3s.

Spotify API -> track list; yt-dlp -> best YouTube match -> MP3 via ffmpeg.

Usage:
    export SPOTIPY_CLIENT_ID=...
    export SPOTIPY_CLIENT_SECRET=...
    python spotify_to_mp3.py <playlist URL or ID> [-o output_dir]
"""
import argparse
import os
import re
import sys

import getpass
import webbrowser

import imageio_ffmpeg
import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from yt_dlp import YoutubeDL

HERE = os.path.dirname(os.path.abspath(__file__))
SCOPE = "playlist-read-private playlist-read-collaborative"


def load_env(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
    """Load KEY=VALUE lines from .env into os.environ (existing vars win)."""
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


DASHBOARD = "https://developer.spotify.com/dashboard"
REDIRECT = "http://127.0.0.1:8888/callback"


def has_credentials():
    cid = os.environ.get("SPOTIPY_CLIENT_ID", "")
    secret = os.environ.get("SPOTIPY_CLIENT_SECRET", "")
    return bool(cid and secret) and not cid.startswith("your_") and not secret.startswith("your_")


def credentials_valid(cid, secret):
    """Check the pair against Spotify's token endpoint."""
    try:
        r = requests.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials"},
            auth=(cid, secret),
            timeout=15,
        )
        return r.status_code == 200
    except requests.RequestException:
        return False


def setup_credentials():
    """Walk a first-time user through creating a Spotify app and save it to .env."""
    print(
        f"""
=== First-time setup: connect your own Spotify account ===
Spotify requires each person to make a free "developer app" (takes ~2 minutes).
Your browser will open the Spotify Developer Dashboard.

  1. Log in with your normal Spotify account and accept the terms.
  2. Click "Create app".
  3. App name: anything (e.g. My MP3 Tool). Description: anything.
  4. Redirect URI: copy this EXACTLY, then click "Add":
         {REDIRECT}
  5. Under "Which API/SDKs are you planning to use?" tick "Web API".
  6. Accept the terms and click "Save".
  7. Open the app, click "Settings", and copy the "Client ID".
     Then click "View client secret" and copy the secret.
"""
    )
    input("Press Enter to open the dashboard...")
    webbrowser.open(DASHBOARD)

    while True:
        cid = input("\nPaste your Client ID: ").strip()
        secret = getpass.getpass("Paste your Client Secret (hidden as you type): ").strip()
        if credentials_valid(cid, secret):
            break
        print("Spotify rejected those credentials. Check for extra spaces and try again.")

    path = os.path.join(HERE, ".env")
    with open(path, "w") as f:
        f.write(
            f"SPOTIPY_CLIENT_ID={cid}\nSPOTIPY_CLIENT_SECRET={secret}\nSPOTIPY_REDIRECT_URI={REDIRECT}\n"
        )
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    os.environ.update(SPOTIPY_CLIENT_ID=cid, SPOTIPY_CLIENT_SECRET=secret, SPOTIPY_REDIRECT_URI=REDIRECT)
    print("\nSaved to .env. You won't be asked again.\n")


def get_tracks(sp, playlist):
    """Return [(artist, title), ...] for every track, most recently added first."""
    tracks = []
    page = sp.playlist_items(playlist, additional_types=("track",))
    while page:
        for item in page["items"]:
            t = item.get("track") or item.get("item")
            if t and t.get("name"):
                tracks.append((item.get("added_at") or "", t["artists"][0]["name"], t["name"]))
        page = sp.next(page) if page.get("next") else None
    tracks.sort(key=lambda x: x[0], reverse=True)  # ISO timestamps sort as text
    return [(artist, title) for _, artist, title in tracks]


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|]', "_", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("playlist", nargs="?", help="Spotify playlist URL, URI or ID (asked for if omitted)")
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "downloads"))
    args = ap.parse_args()
    load_env()

    if not has_credentials():
        setup_credentials()
    playlist = (args.playlist or input("Paste the Spotify playlist link and press Enter: ")).strip().strip("'\"")
    redirect = os.environ.get("SPOTIPY_REDIRECT_URI", REDIRECT)
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=SCOPE, redirect_uri=redirect))
    tracks = get_tracks(sp, playlist)
    print(f"Found {len(tracks)} tracks")
    os.makedirs(args.out, exist_ok=True)

    ydl_opts = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
            {"key": "FFmpegMetadata"},
        ],
    }
    failed = []
    width = max(3, len(str(len(tracks))))
    # existing files by name without the "NNN - " prefix, so a re-run renumbers them
    existing = {
        re.sub(r"^\d+ - ", "", f[:-4]): f for f in os.listdir(args.out) if f.endswith(".mp3")
    }
    with YoutubeDL(ydl_opts) as ydl:
        for i, (artist, title) in enumerate(tracks, 1):
            name = safe_name(f"{artist} - {title}")
            numbered = f"{i:0{width}d} - {name}"
            target = os.path.join(args.out, numbered)
            if name in existing:
                old = existing[name]
                if old != numbered + ".mp3":
                    os.rename(os.path.join(args.out, old), target + ".mp3")
                print(f"[{i}/{len(tracks)}] skip (exists): {name}")
                continue
            print(f"[{i}/{len(tracks)}] {name}")
            ydl.params["outtmpl"] = {"default": target + ".%(ext)s"}
            try:
                ydl.download([f"ytsearch1:{artist} - {title} audio"])
            except Exception as e:
                print(f"   failed: {e}", file=sys.stderr)
                failed.append(name)

    if failed:
        print("\nFailed:\n  " + "\n  ".join(failed))


if __name__ == "__main__":
    main()
