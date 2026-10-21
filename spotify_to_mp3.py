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
import logging
import shutil
import subprocess
import html
import json
import unicodedata
import webbrowser

import imageio_ffmpeg
import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from yt_dlp import YoutubeDL

logging.getLogger("spotipy").setLevel(logging.CRITICAL)  # we show friendlier messages ourselves
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


# --- YouTube matching -------------------------------------------------------
# Each search result gets a score; the best-scoring one wins. Edit these to tune.
SEARCH_SUFFIXES = ("official audio", "HQ", "")
BAD_WORDS = (  # results containing these are skipped (unless the song's own name has them)
    "live", "cover", "remix", "karaoke", "reaction", "instrumental", "slowed", "sped up", "8d",
    "nightcore", "mashup", "compilation", "full album", "album stream", "bass boosted", "bassboost",
    "reverb", "tutorial", "1 hour", "tiktok", "tik tok", "traducao", "traduccion", "legendado",
    "subtitulado", "לייב", "pitch corrected", "pitched", "no speech", "no monologue", "outtakes", "demo",
    "transposed", "acapella", "a cappella", "vocals only",
)
TITLE_POINTS = (  # (words in the video title, points)
    (("official audio",), 20),
    (("audio",), 10),
    (("hq", "hd"), 8),
    (("lyrics", "lyric"), 6),
)
OFFICIAL_CHANNEL_WORDS = ("vevo", "הרשמי")  # trusted on their own; plain "official" also needs the artist's name
GOOD_ENOUGH = 55  # stop searching once a result scores at least this
MAX_ATTEMPTS = 8  # if a download fails (age-restricted, blocked...), try up to this many ranked results


def norm(s):
    """Lowercase, strip accents/punctuation so titles compare fairly ('H.Q.' -> 'hq')."""
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"h\.\s?q\.?", "hq", s)
    s = re.sub(r"['\u2019`]", "", s)
    return re.sub(r"[\W_]+", " ", s).strip()


def has_phrase(text, phrase):
    return f" {phrase} " in f" {text} "


def base_title(title):
    """Drop Spotify extras like ' - Remastered 2011', ' - From "Movie"' and '(feat. X)'."""
    t = re.sub(r"\s+-\s+.*$", "", title)
    t = re.sub(r"\s*[\(\[](feat|ft|with|from)\b[^\)\]]*[\)\]]", "", t, flags=re.I)
    return t.strip() or title


def score_result(entry, artist, title, duration, pos):
    """Return (score, reasons). score is None when the result should be rejected."""
    vt, ch = norm(entry.get("title")), norm(entry.get("channel"))
    vwords = set(vt.split())
    ttoks = norm(base_title(title)).split()
    if ttoks and sum(t in vwords for t in ttoks) / len(ttoks) < 0.8:
        return None, "wrong song (title words missing)"
    own = norm(f"{artist} {title}")
    bad = next((w for w in BAD_WORDS if has_phrase(vt, norm(w)) and not has_phrase(own, norm(w))), None)
    if bad:
        return None, f"skip: has '{bad}'"

    score, why = 0, []
    atoks = norm(artist).split()
    acompact = "".join(atoks)
    trusted = True
    if ch.endswith("topic"):
        score += 35; why.append("+35 Topic channel")
    elif any(w in ch for w in OFFICIAL_CHANNEL_WORDS) or (atoks and all(t in ch.split() for t in atoks)):
        score += 25; why.append("+25 official/artist channel")  # channel named after the artist
    elif acompact and acompact in ch.replace(" ", ""):
        score += 20; why.append("+20 channel contains artist name")  # e.g. "boburnham", "EminemMusic"
    else:
        trusted = False
        if atoks and all(t in vwords for t in atoks):
            score += 10; why.append("+10 artist in title")
    for words, pts in TITLE_POINTS:
        hit = next((w for w in words if has_phrase(vt, w)), None)
        if hit:
            if not trusted:
                pts //= 2  # anyone can write "Official Audio" in a title
            score += pts; why.append(f"+{pts} '{hit}'")
            break  # only the strongest title keyword counts
    dur = entry.get("duration")
    if duration and dur:
        diff = abs(dur - duration)
        pts = 30 if diff <= 4 else 15 if diff <= 10 else 0 if diff <= 20 else -40
        score += pts; why.append(f"{pts:+d} length off by {diff}s")
    score -= pos
    return score, ", ".join(why) or "no signals"


def find_videos(search, artist, title, duration=None, debug=False):
    """Search YouTube; return candidate videos ({url, title, channel}) ranked best first, or [] if none.

    Rejected results are left out, unless nothing else exists: then the first result is the last resort.
    """
    scored, first, seen = [], None, set()
    lines = []  # debug output, printed at the end so the winner can be marked
    for suffix in SEARCH_SUFFIXES:
        query = f"{artist} {base_title(title)} {suffix}".strip()
        try:
            info = search.extract_info(f"ytsearch5:{query}", download=False)
        except Exception as e:
            lines.append((None, f"   search '{query}' failed: {e}"))
            continue
        lines.append((None, f"   search: {query}"))
        for pos, e in enumerate(info.get("entries") or []):
            url = e.get("url") or e.get("webpage_url")
            if not url or url in seen:
                continue
            seen.add(url)
            video = {"url": url, "title": e.get("title"), "channel": e.get("channel")}
            first = first or video
            sc, why = score_result(e, artist, title, duration, pos)
            if sc is not None:
                scored.append((sc, video))
            d = int(e.get("duration") or 0)
            label = f"score {sc}" if sc is not None else "rejected"
            lines.append((url, f"{e.get('title')} [{e.get('channel')}, {d // 60}:{d % 60:02d}]  {label}: {why}"))
        if scored and max(sc for sc, _ in scored) >= GOOD_ENOUGH:
            break
    scored.sort(key=lambda x: -x[0])  # stable: ties keep search order
    ranked = [v for _, v in scored[:MAX_ATTEMPTS]] or ([first] if first else [])
    if debug:
        chosen = ranked[0]["url"] if ranked else None
        for url, text in lines:
            print(text if url is None else f"   {'->' if url == chosen else '  '} {text}")
        if not scored and first:
            print("   nothing scored well; falling back to first result")
    return ranked


def get_tracks(sp, playlist):
    """Return [(artist, title), ...] for every track, most recently added first."""
    tracks = []
    page = sp.playlist_items(playlist, additional_types=("track",))
    while page:
        for item in page["items"]:
            t = item.get("track") or item.get("item")
            if t and t.get("name"):
                secs = (t.get("duration_ms") or 0) // 1000 or None
                tracks.append((item.get("added_at") or "", t["artists"][0]["name"], t["name"], secs))
        page = sp.next(page) if page.get("next") else None
    tracks.sort(key=lambda x: x[0], reverse=True)  # ISO timestamps sort as text
    return [(artist, title, secs) for _, artist, title, secs in tracks]


def explain_playlist_error(sp, playlist, err):
    """Print a friendly explanation for a playlist Spotify wouldn't let us read."""
    status = getattr(err, "http_status", None)
    print(f"\nCouldn't read that playlist (Spotify error {status}).")
    owner = None
    try:
        owner = sp.playlist(playlist, fields="owner(display_name)")["owner"]["display_name"]
    except Exception:
        pass
    if status == 403:
        who = f"someone else ({owner})" if owner else "someone else"
        print(
            f"\nThis playlist belongs to {who}. Spotify only lets this app read playlists you own or\n"
            "collaborate on, even when the playlist is public.\n\n"
            "Workaround: copy the songs into a playlist of your own, then use that link.\n"
            "  1. Open the playlist in the Spotify app and click any song.\n"
            "  2. Select all songs (Cmd+A on Mac, Ctrl+A on Windows).\n"
            "  3. Right-click -> Add to playlist -> New playlist. (Songs keep their order, but all\n     get today's date, so numbering follows the playlist order instead of when each was added.)\n"
            "  4. Share your new playlist's link and run this again."
        )
    elif status == 404:
        print("\nThe playlist wasn't found. Check the link, and that the playlist isn't deleted or private.")
    else:
        print(f"\n{err}")


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|]', "_", s)


SETTINGS = os.path.join(HERE, ".settings.json")


class QuietLogger:
    """Swallow yt-dlp's own messages; we print short ones ourselves."""

    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def load_settings():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def pick_folder(start):
    """Open the system's folder chooser (Finder on Mac). Returns a path, or None if cancelled."""
    msg = "Choose where to save your MP3 files"
    start = start if os.path.isdir(start) else os.path.expanduser("~")
    try:
        if sys.platform == "darwin":
            script = (
                f'POSIX path of (choose folder with prompt "{msg}" '
                f'default location POSIX file "{start.replace(chr(34), "")}")'
            )
            r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        elif sys.platform == "win32":
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
                f"$f.Description = '{msg}'; $f.SelectedPath = '{start}'; "
                "if ($f.ShowDialog() -eq 'OK') { $f.SelectedPath }"
            )
            r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps], capture_output=True, text=True)
        elif shutil.which("zenity"):
            r = subprocess.run(
                ["zenity", "--file-selection", "--directory", "--title", msg], capture_output=True, text=True
            )
        else:
            return input("Type the full folder path (or press Enter to cancel): ").strip() or None
        return r.stdout.strip() or None
    except OSError:
        return input("Type the full folder path (or press Enter to cancel): ").strip() or None


def read_key():
    """Read one keypress without waiting for Enter (falls back to a typed line)."""
    try:
        if sys.platform == "win32":
            import msvcrt
            ch = msvcrt.getwch()
        else:
            import termios
            import tty
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setcbreak(fd)
                ch = sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except (ImportError, OSError, ValueError, AttributeError):
        return (input() or "\r")[:1]
    if ch == "\x03":
        raise KeyboardInterrupt
    return ch


def choose_output_folder(default):
    """Ask where to save, offering a folder chooser. Remembers the last choice."""
    settings = load_settings()
    current = settings.get("out") or default
    if sys.stdin.isatty():
        print(f"\nMP3s will be saved to:\n  {current}")
        print("Press Enter to use this folder, or C to choose a different one.")
        key = read_key().lower()
        while key not in ("\r", "\n", "c"):
            key = read_key().lower()
        if key == "c":
            picked = pick_folder(current)
            if picked:
                current = picked
            else:
                print("No folder chosen, keeping the one above.")
    current = os.path.abspath(os.path.expanduser(current))
    try:
        with open(SETTINGS, "w", encoding="utf-8") as f:
            json.dump({**settings, "out": current}, f)
    except OSError:
        pass
    return current


def open_folder(path):
    """Show the folder in Finder / Explorer."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", path])
        elif sys.platform == "win32":
            os.startfile(path)
        elif shutil.which("xdg-open"):
            subprocess.run(["xdg-open", path])
    except OSError:
        pass


REPORT_JSON = "selected_videos.json"
REPORT_HTML = "selected_videos.html"


def write_report(out, rows, known):
    """Write selected_videos.html (clickable list) and remember choices in selected_videos.json."""
    with open(os.path.join(out, REPORT_JSON), "w", encoding="utf-8") as f:
        json.dump(known, f, ensure_ascii=False, indent=1)
    trs = []
    for num, name, video, status in rows:
        if video:
            link = f'<a href="{html.escape(video["url"])}" target="_blank">{html.escape(video["title"] or video["url"])}</a>'
            channel = html.escape(video.get("channel") or "")
        else:
            link, channel = "&mdash;", ""
        trs.append(
            f"<tr><td>{num}</td><td>{html.escape(name)}</td><td>{link}</td><td>{channel}</td><td>{html.escape(status)}</td></tr>"
        )
    page = (
        "<!doctype html><meta charset='utf-8'><title>Selected videos</title>"
        "<style>body{font:15px system-ui;margin:2em}table{border-collapse:collapse}"
        "td,th{border:1px solid #ccc;padding:6px 10px;text-align:left}th{background:#f3f3f3}</style>"
        "<h1>Selected YouTube videos</h1>"
        "<p>Open a link to check that the right video was used. Replace any MP3 that is wrong.</p>"
        "<table><tr><th>#</th><th>Spotify song</th><th>YouTube video</th><th>Channel</th><th>Status</th></tr>"
        + "".join(trs)
        + "</table>"
    )
    with open(os.path.join(out, REPORT_HTML), "w", encoding="utf-8") as f:
        f.write(page)


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def is_age_error(e):
    text = ANSI.sub("", str(e))
    return "confirm your age" in text or "age-restricted" in text


def js_runtimes():
    """A JavaScript runtime for yt-dlp's YouTube challenge solving: deno (installed via pip) or node."""
    path = os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "")
    for name in ("deno", "node"):
        exe = shutil.which(name, path=path)
        if exe:
            return {name: {"path": exe}}
    return {}


def browser_profile(browser):
    """Name of a Chromium browser's last-used profile (e.g. 'Profile 2'); yt-dlp assumes 'Default' otherwise."""
    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA", "")
    dirs = {
        "chrome": [
            f"{home}/Library/Application Support/Google/Chrome",
            f"{local}/Google/Chrome/User Data",
            f"{home}/.config/google-chrome",
        ],
        "edge": [
            f"{home}/Library/Application Support/Microsoft Edge",
            f"{local}/Microsoft/Edge/User Data",
            f"{home}/.config/microsoft-edge",
        ],
        "brave": [
            f"{home}/Library/Application Support/BraveSoftware/Brave-Browser",
            f"{local}/BraveSoftware/Brave-Browser/User Data",
            f"{home}/.config/BraveSoftware/Brave-Browser",
        ],
    }.get(browser, [])
    for d in dirs:
        try:
            with open(os.path.join(d, "Local State"), encoding="utf-8") as f:
                last = json.load(f)["profile"].get("last_used")
            if last and os.path.isdir(os.path.join(d, last)):
                return last
        except (OSError, ValueError, KeyError):
            continue
    return None


def ask_cookie_browser():
    """Offer to use the browser's YouTube login for age-restricted (often explicit) songs. '' = declined."""
    if not sys.stdin.isatty():
        return ""
    print(
        "\nThis song is age-restricted on YouTube (common for explicit songs).\n"
        "To download it, the script can use the YouTube login from your web browser.\n"
        "You must be signed in to YouTube there, with an account that is old enough to view it.\n"
        "The login stays on your computer. (macOS may ask for permission to read the browser's data.)\n"
        "Which browser are you signed in to YouTube with?\n"
        "  C = Chrome   F = Firefox   S = Safari   E = Edge   B = Brave   N = don't sign in; use another upload instead"
    )
    names = {"c": "chrome", "f": "firefox", "s": "safari", "e": "edge", "b": "brave"}
    while True:
        key = read_key().lower()
        if key == "n":
            print("OK, not signing in. For age-restricted songs the next best upload will be used instead.\n")
            return ""
        if key in names:
            choice = names[key]
            settings = load_settings()
            try:
                with open(SETTINGS, "w", encoding="utf-8") as f:
                    json.dump({**settings, "cookies_browser": choice}, f)
            except OSError:
                pass
            print(f"Using {choice}. To change this later, delete the file .settings.json.\n")
            return choice


def short_error(e):
    """One readable line from a yt-dlp error."""
    text = ANSI.sub("", str(e)).strip()
    if is_age_error(e):
        return "age-restricted video"
    msg = re.sub(r"^ERROR:\s*(\[\w+\]\s*\S+:\s*)?", "", text).splitlines()[0] if text else "unknown error"
    return msg[:100]


def debug_search(tracks):
    """Print how each track's YouTube search plays out. Downloads and writes nothing."""
    print("DEBUG MODE: nothing will be downloaded. the line starting '->' shows the video that would be chosen.\n")
    with YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True}) as search:
        for i, (artist, title, secs) in enumerate(tracks, 1):
            print(f"[{i}/{len(tracks)}] {artist} - {title}")
            videos = find_videos(search, artist, title, secs, debug=True)
            print(f"   result: {videos[0]['url'] if videos else 'NOTHING FOUND'}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("playlist", nargs="?", help="Spotify playlist URL, URI or ID (asked for if omitted)")
    ap.add_argument("-o", "--out", help="folder to save MP3s in (asked for if omitted)")
    ap.add_argument("--debug", action="store_true", help="show the YouTube search results for each track; downloads nothing")
    ap.add_argument("--cookies-from-browser", metavar="BROWSER", help="use this browser's YouTube login for age-restricted videos (chrome, firefox, safari, edge, brave)")
    ap.add_argument("--limit", type=int, help="only process the first N tracks (handy with --debug)")
    args = ap.parse_args()
    load_env()

    if not has_credentials():
        setup_credentials()
    playlist = (args.playlist or input("Paste the Spotify playlist link and press Enter: ")).strip().strip("'\"")
    if not args.debug:
        args.out = args.out or choose_output_folder(os.path.join(HERE, "downloads"))
    redirect = os.environ.get("SPOTIPY_REDIRECT_URI", REDIRECT)
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=SCOPE, redirect_uri=redirect))
    try:
        tracks = get_tracks(sp, playlist)
    except spotipy.SpotifyException as e:
        explain_playlist_error(sp, playlist, e)
        sys.exit(1)
    if args.limit:
        tracks = tracks[: args.limit]
    print(f"Found {len(tracks)} tracks")
    if args.debug:
        debug_search(tracks)
        return
    os.makedirs(args.out, exist_ok=True)

    ydl_opts = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
        "quiet": True,
        "logger": QuietLogger(),
        "js_runtimes": js_runtimes(),
        "noprogress": True,
        "no_warnings": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
            {"key": "FFmpegMetadata"},
        ],
    }
    failed = []
    rows = []
    hinted = False
    browser = args.cookies_from_browser or load_settings().get("cookies_browser")  # None = not asked yet
    json_path = os.path.join(args.out, REPORT_JSON)
    try:
        known = json.load(open(json_path, encoding="utf-8"))  # videos chosen on earlier runs
    except (OSError, ValueError):
        known = {}
    width = max(3, len(str(len(tracks))))
    # existing files by name without the "NNN - " prefix, so a re-run renumbers them
    existing = {
        re.sub(r"^\d+ - ", "", f[:-4]): f for f in os.listdir(args.out) if f.endswith(".mp3")
    }
    search_opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
    with YoutubeDL(ydl_opts) as ydl, YoutubeDL(search_opts) as search:
        for i, (artist, title, secs) in enumerate(tracks, 1):
            name = safe_name(f"{artist} - {title}")
            numbered = f"{i:0{width}d} - {name}"
            target = os.path.join(args.out, numbered)
            if name in existing:
                old = existing[name]
                if old != numbered + ".mp3":
                    os.rename(os.path.join(args.out, old), target + ".mp3")
                print(f"[{i}/{len(tracks)}] skip (exists): {name}")
                rows.append((i, name, known.get(name), "already downloaded"))
                continue
            print(f"[{i}/{len(tracks)}] {name}")
            ydl.params["outtmpl"] = {"default": target + ".%(ext)s"}
            video, error = None, None
            try:
                candidates = find_videos(search, artist, title, secs)
            except Exception as e:
                candidates, error = [], e
            if not candidates and not error:
                error = "no YouTube results"
            for cand in candidates:  # next best result if one can't be downloaded
                try:
                    ydl.download([cand["url"]])
                    video = cand
                    break
                except Exception as e:
                    error = e
                    if is_age_error(e):
                        if browser is None:
                            browser = ask_cookie_browser()
                        if browser:
                            try:
                                opts = {**ydl_opts, "outtmpl": ydl.params["outtmpl"], "cookiesfrombrowser": (browser, browser_profile(browser))}
                                with YoutubeDL(opts) as signed_in:
                                    signed_in.download([cand["url"]])
                                video = cand
                                break
                            except Exception as e2:
                                error = e2
                                if is_age_error(e2) and not hinted:
                                    hinted = True
                                    print(
                                        f"   Still age-restricted with your {browser} login. Make sure you're signed in to\n"
                                        f"   YouTube in {browser} (your main profile) with an account Google has age-verified,\n"
                                        "   then run again. Using another upload for now."
                                    )
                    print(f"   couldn't use {cand['url']} ({short_error(error)}); trying the next one")
            if video:
                known[name] = video
                fallback = video is not candidates[0]
                if fallback:
                    print(f"   used a fallback upload: {video['title']}")
                rows.append((i, name, video, "downloaded (fallback upload)" if fallback else "downloaded"))
            else:
                print(f"   failed: {short_error(error)}", file=sys.stderr)
                failed.append(name)
                rows.append((i, name, None, "FAILED"))

    write_report(args.out, rows, known)
    print(f"\nSaved to: {args.out}")
    print(f"List of chosen videos: {os.path.join(args.out, REPORT_HTML)}")
    open_folder(args.out)

    if failed:
        print("\nFailed:\n  " + "\n  ".join(failed))


if __name__ == "__main__":
    main()
