# Spotify playlist → MP3

Reads a Spotify playlist through the Spotify API, finds each song on YouTube with `yt-dlp`, and converts it to MP3 with `ffmpeg`.

## Requirements

- Python 3.9+
- `ffmpeg`
  - macOS: `brew install ffmpeg`
  - Windows: `winget install ffmpeg`
  - Linux: `sudo apt install ffmpeg`
- A free Spotify account

## Setup (once)

1. **Create your own Spotify app** at https://developer.spotify.com/dashboard → *Create app*.
   - Redirect URI: `http://127.0.0.1:8888/callback` (must match exactly)
   - Copy the **Client ID** and **Client Secret** from the app's Settings page.
   - Each person should create their own app. Don't share credentials.
2. **Install dependencies:**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Add your credentials:**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and paste in your Client ID and Client Secret. `.env` is git-ignored, so it won't be committed. Never share or upload it.

## Usage

Activate the venv first if it isn't already (`source .venv/bin/activate`), then:

```bash
python spotify_to_mp3.py "https://open.spotify.com/playlist/XXXX" -o downloads
```

- The first run opens a browser for Spotify login and consent. After that, the login is cached in `.cache`.
- MP3s are saved as `downloads/Artist - Title.mp3`.
- Re-running skips files that already exist, so an interrupted run can simply be started again.
- Failed tracks are listed at the end.

## Troubleshooting

| Problem | Fix |
|---|---|
| `INVALID_CLIENT: Invalid redirect URI` | The redirect URI in the dashboard must be exactly `http://127.0.0.1:8888/callback`. |
| `403` or no tracks returned | Spotify limits what new developer apps can read. Make sure you're logged in as the app owner and the playlist is yours (or public/collaborative). Otherwise, copy the playlist into your own account first. |
| `ffmpeg not found` | Install ffmpeg (see Requirements). |
| YouTube errors or `Sign in to confirm you're not a bot` | Update yt-dlp: `pip install -U yt-dlp`. YouTube changes often. |
| Wrong song or live version downloaded | The script takes the first YouTube search result. Delete the file and replace it manually. |
| Stale or wrong Spotify login | Delete the `.cache` file and run again. |

## Limitations

- Audio quality is limited by YouTube (about 128–160 kbps), so it's not lossless.
- Matching is automatic, so spot-check the results.

## Legal

For personal use with music you're entitled to copy. Downloading from YouTube may violate its terms of service, and copyright law varies by country. You are responsible for how you use this.
