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

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from yt_dlp import YoutubeDL


def load_env(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
    """Load KEY=VALUE lines from .env into os.environ (existing vars win)."""
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def get_tracks(sp, playlist):
    """Return [(artist, title), ...] for every track in the playlist."""
    tracks = []
    page = sp.playlist_items(playlist, additional_types=("track",))
    while page:
        for item in page["items"]:
            t = item.get("track") or item.get("item")
            if t and t.get("name"):
                tracks.append((t["artists"][0]["name"], t["name"]))
        page = sp.next(page) if page.get("next") else None
    return tracks


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|]', "_", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("playlist", help="Spotify playlist URL, URI or ID")
    ap.add_argument("-o", "--out", default="downloads")
    args = ap.parse_args()
    load_env()

    sp = spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            scope="playlist-read-private playlist-read-collaborative",
            redirect_uri=os.environ.get("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback"),
        )
    )
    tracks = get_tracks(sp, args.playlist)
    print(f"Found {len(tracks)} tracks")
    os.makedirs(args.out, exist_ok=True)

    ydl_opts = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
            {"key": "FFmpegMetadata"},
        ],
    }
    failed = []
    with YoutubeDL(ydl_opts) as ydl:
        for i, (artist, title) in enumerate(tracks, 1):
            name = safe_name(f"{artist} - {title}")
            target = os.path.join(args.out, name)
            if os.path.exists(target + ".mp3"):
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
