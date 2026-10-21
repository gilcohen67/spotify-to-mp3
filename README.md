# Spotify playlist → MP3

Reads a Spotify playlist through the Spotify API, finds each song on YouTube with `yt-dlp`, and converts it to MP3 with `ffmpeg`.

## Quick start (no terminal needed)

1. **Download the app from GitHub:**
   - On this page, click the green **Code** button → **Download ZIP**.
   - Open your Downloads folder and unzip it (double-click the ZIP). Move the unzipped folder somewhere easy, like your Desktop or Documents.
2. **Install Python 3 (one time).** Windows and Mac don't include a usable Python, so this is needed even if you've never installed it:
   - Download the installer from https://www.python.org/downloads/ and run it.
   - **Windows:** on the first screen, tick **Add python.exe to PATH** before clicking Install.
   - Already have Python 3? Skip this step. If you're not sure, just continue; the launcher will tell you if it's missing.
3. Open the unzipped folder and double-click **`Start (Mac).command`** or **`Start (Windows).bat`**.
   - Mac: if it's blocked, right-click it → *Open* → *Open*. If it says it can't be opened because of permissions, see Troubleshooting.
   - Windows: if you see "Windows protected your PC", click *More info* → *Run anyway*.
4. **First run only:** the window walks you through connecting your own Spotify account. It opens the Spotify Developer Dashboard, tells you what to click, and asks you to paste your Client ID and Client Secret. They are checked and saved to a private `.env` file in this folder.
5. Spotify opens in your browser to log in and approve access.
6. Paste your playlist link when asked. Then choose where to save: press Enter for the suggested folder, or press `C` to pick one in a Finder/Explorer window (your choice is remembered). The folder opens when it is done.

Everyone uses their **own** Spotify developer app, so never share your `.env` file or `.cache`.

### What the setup asks you to do (about 2 minutes)

1. Log in at https://developer.spotify.com/dashboard and accept the terms.
2. Click **Create app**. Name and description can be anything.
3. Add the redirect URI `http://127.0.0.1:8888/callback` exactly, and tick **Web API**.
4. Save, open the app's **Settings**, and copy the **Client ID** and **Client secret**.

## Terminal setup (optional)

Requires Python 3.9+ (ffmpeg is installed automatically).

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python spotify_to_mp3.py
```

If there's no `.env` yet, the same guided setup runs. You can also create it yourself with `cp .env.example .env` and fill it in. `.env` is git-ignored.


## Usage

Activate the venv first if it isn't already (`source .venv/bin/activate`), then:

```bash
python spotify_to_mp3.py "https://open.spotify.com/playlist/XXXX" -o downloads
```

Without `-o`, it asks where to save (see above).

- The first run opens a browser for Spotify login and consent. After that, the login is cached in `.cache`.
- MP3s are saved as `downloads/001 - Artist - Title.mp3` (001 = most recently added to the playlist).
- Re-running skips songs you already have and renumbers them if the playlist order changed.
- Failed tracks are listed at the end.
- `downloads/selected_videos.html` lists which YouTube video was used for each song, with clickable links. Open it in your browser to check for wrong matches. It's updated on every run and remembers videos chosen earlier.

## Debug mode (tune the YouTube matching)

Shows the YouTube results for each track with their score and the reasons behind it (or why they were rejected), and which one would be chosen (the `->` line). **Nothing is downloaded or renamed.**

```bash
python spotify_to_mp3.py "https://open.spotify.com/playlist/XXXX" --debug --limit 10
```

`--limit N` checks only the newest N tracks. To add keywords, edit `SEARCH_SUFFIXES`, `BAD_WORDS`, `TITLE_POINTS` and `GOOD_ENOUGH` at the top of the "YouTube matching" section in `spotify_to_mp3.py`.

## Age-restricted (explicit) songs

YouTube hides some songs, often explicit ones, behind an age check. When that happens the script uses the next best upload of the song instead (up to 8 candidates are tried, and the report marks these as "fallback upload"). If you want the exact age-restricted one, it asks once which browser you're signed in to YouTube with (Chrome, Firefox, Safari, Edge or Brave) and uses that login to download it. The login never leaves your computer, and your choice is remembered in `.settings.json`. You can also pass it directly:

```bash
python spotify_to_mp3.py "https://open.spotify.com/playlist/XXXX" --cookies-from-browser chrome
```

The script automatically uses your browser's most recently used profile. macOS may ask permission to read the browser's data (enter your Mac login password and choose *Allow*). Safari may require giving Terminal "Full Disk Access".

## Troubleshooting

| Problem | Fix |
|---|---|
| `INVALID_CLIENT: Invalid redirect URI` | The redirect URI in the dashboard must be exactly `http://127.0.0.1:8888/callback`. |
| `403` / "belongs to someone else" | Spotify only lets this app read playlists **you own or collaborate on**, even public ones. Copy the songs into your own playlist (open the playlist, select all songs, right-click → *Add to playlist* → *New playlist*) and use that link. |
| YouTube errors or `Sign in to confirm you're not a bot` | Update yt-dlp: `pip install -U yt-dlp`. YouTube changes often. |
| Wrong song or live version downloaded | The script prefers "official audio" / "HQ" uploads and skips live, cover and remix results, but matching is automatic. Delete the file and replace it manually. |
| Mac: `Start (Mac).command` won't open ("permission denied") | ZIP downloads can drop the executable flag. Open Terminal once and run `chmod +x ` followed by dragging the file into the window, then press Enter. After that, double-click works. |
| Stale or wrong Spotify login | Delete the `.cache` file and run again. |

## Limitations

- Audio quality is limited by YouTube (about 128–160 kbps), so it's not lossless.
- Matching: it searches YouTube ("official audio", then "HQ", then a plain search) and scores every result. Points for an official/artist or "- Topic" channel, a video length close to the Spotify track, and keywords like official audio/HQ. It rejects wrong songs and live/cover/remix/lyric-translation uploads. If nothing scores well, it uses the first result. Spot-check the results.

## Legal

For personal use with music you're entitled to copy. Downloading from YouTube may violate its terms of service, and copyright law varies by country. You are responsible for how you use this.
