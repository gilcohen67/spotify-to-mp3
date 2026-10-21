# Spotify playlist → MP3

Reads a Spotify playlist through the Spotify API, finds each song on YouTube with `yt-dlp`, and converts it to MP3 with `ffmpeg`.

## Quick start (no terminal needed)

1. Install Python 3 from https://www.python.org/downloads/ (on Windows, tick **Add python.exe to PATH**).
2. Double-click **`Start (Mac).command`** or **`Start (Windows).bat`**.
   - Mac: if it's blocked, right-click it → *Open* → *Open*.
3. **First run only:** the window walks you through connecting your own Spotify account. It opens the Spotify Developer Dashboard, tells you what to click, and asks you to paste your Client ID and Client Secret. They are checked and saved to a private `.env` file in this folder.
4. Spotify opens in your browser to log in and approve access.
5. Paste your playlist link when asked. MP3s appear in the `downloads` folder.

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

- The first run opens a browser for Spotify login and consent. After that, the login is cached in `.cache`.
- MP3s are saved as `downloads/001 - Artist - Title.mp3` (001 = most recently added to the playlist).
- Re-running skips songs you already have and renumbers them if the playlist order changed.
- Failed tracks are listed at the end.

## Troubleshooting

| Problem | Fix |
|---|---|
| `INVALID_CLIENT: Invalid redirect URI` | The redirect URI in the dashboard must be exactly `http://127.0.0.1:8888/callback`. |
| `403` or no tracks returned | Spotify limits what new developer apps can read. Make sure you're logged in as the app owner and the playlist is yours (or public/collaborative). Otherwise, copy the playlist into your own account first. |
| YouTube errors or `Sign in to confirm you're not a bot` | Update yt-dlp: `pip install -U yt-dlp`. YouTube changes often. |
| Wrong song or live version downloaded | The script takes the first YouTube search result. Delete the file and replace it manually. |
| Stale or wrong Spotify login | Delete the `.cache` file and run again. |

## Limitations

- Audio quality is limited by YouTube (about 128–160 kbps), so it's not lossless.
- Matching is automatic, so spot-check the results.

## Legal

For personal use with music you're entitled to copy. Downloading from YouTube may violate its terms of service, and copyright law varies by country. You are responsible for how you use this.
