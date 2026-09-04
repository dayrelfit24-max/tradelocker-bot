# YouTube Gaming Upload Pipeline — **ProGamer**

Channel: [@ProGamer-ys7hu](https://youtube.com/@ProGamer-ys7hu)

**Fully automated faceless gaming channel** — no gameplay recording required.

AI writes the script → voiceover → animated slides → SEO + thumbnail → YouTube upload. Supports **68 trending games**.

## What it does

| Step | Automation |
|------|------------|
| **AI script** | Tips, Top 5, news, facts, vs formats per game |
| **AI voice** | Free neural TTS (edge-tts) |
| **AI visuals** | ProGamer-branded motion slides (vertical Shorts or horizontal) |
| **AI edit** | ffmpeg assembly, captions `.srt`, Ken Burns zoom |
| SEO + thumbnail | Titles, tags, descriptions, ProGamer thumb |
| Upload | YouTube Data API v3 |

Optional API keys in `config.env` (more cinematic videos):

| Key | Get it | Adds |
|-----|--------|------|
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) | Smarter scripts + **AI scene images** per line |
| `PEXELS_API_KEY` | [pexels.com/api](https://www.pexels.com/api/) (free) | **Stock gaming B-roll** under your text overlays |

Without keys → styled slides still work.

## Daily automation (3 long + 4 Shorts)

Every day the pipeline pulls **trending topics** from Reddit (r/gaming, r/Games, r/pcgaming, r/PS5, r/xbox) and builds:

| # | Type | Content |
|---|------|---------|
| 3× | **Long** | Industry news, best games (PC/PS5/Xbox rotation), gameplay highlights |
| 4× | **Short** | Trending news, pro tips, best games pick, upcoming releases |

**Gameplay-style videos** use real Pexels action B-roll (monitors, esports, controllers) + Claude narration — no capture needed.

```bash
# Preview today's plan
python pipeline.py daily --plan-only

# Create all 7 videos (SEO + thumbnails)
python pipeline.py daily

# Create + upload all 7 to YouTube
python pipeline.py daily --upload --public

# Or use the shell script
./run_daily.sh
./run_daily.sh --upload
```

**Auto-run every morning at 8am (Mac):**
```bash
cp com.progamer.daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.progamer.daily.plist
```

See trending topics: `python pipeline.py trends`

Config in `config.env`: `DAILY_LONG_VIDEOS=3`, `DAILY_SHORTS=4`

---

## Create videos (no recording)

```bash
source .venv/bin/activate
brew install ffmpeg   # required once

# One vertical Short (best for fast growth)
python pipeline.py create --game "Fortnite" --format tips --duration short

# Random trending game (omit --game)
python pipeline.py create --format facts --duration short

# Long-form horizontal video
python pipeline.py create --game "Valorant" --format top5 --duration long

# Batch 5 Shorts (different games)
python pipeline.py batch --count 5 --auto --format tips --duration short

# Daily automation
./create_daily.sh 3
```

Formats: `tips` | `top5` | `news` | `facts` | `versus`

Output: `generated/*.mp4` + `processed/*_upload.json` + thumbnails.

Upload after review:
```bash
python pipeline.py upload processed/your_video_upload.json --public
```

## One-time setup (≈15 min)

### 1. Google Cloud / YouTube API

1. Open [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → **APIs & Services** → enable **YouTube Data API v3**
3. **Credentials** → **Create credentials** → **OAuth client ID** → **Desktop app**
4. Download JSON → save as `youtube-pipeline/client_secrets.json`

### 2. Install dependencies

```bash
cd youtube-pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Required:** [ffmpeg](https://ffmpeg.org/) (`brew install ffmpeg` on Mac) for video creation.

### 3. Configure channel

```bash
cp config.example.env config.env
# Edit CHANNEL_NAME, CHANNEL_URL, social links, DEFAULT_GAME, etc.
```

### 4. Authorize your channel

```bash
python pipeline.py auth
```

Browser opens → sign in with the Google account that owns your gaming channel.

## Daily workflow

### Option A — Single video

```bash
python pipeline.py process ~/Videos/fortnite_clutch.mp4 --game Fortnite --hook "INSANE CLUTCH"
# Review processed/fortnite_clutch_upload.json
python pipeline.py upload processed/fortnite_clutch_upload.json --public
```

### Option B — Drop folder (watch mode)

```bash
python pipeline.py watch
# Copy .mp4 files into youtube-pipeline/incoming/
# Pipeline generates SEO + thumbnail in processed/
# Then upload each bundle when ready
```

### Check monetization progress

```bash
python pipeline.py stats
```

### List all supported games

```bash
python pipeline.py games
```

## Files

```
youtube-pipeline/
├── incoming/          # Drop videos here (watch mode)
├── processed/         # upload.json bundles
├── thumbnails/        # Generated thumbs
├── tokens/            # OAuth token (gitignored)
├── config.env         # Your secrets (gitignored)
└── client_secrets.json
```

## Monetization targets (YouTube Partner Program)

- **1,000** subscribers
- **4,000** watch hours (12 months) *or* **10M** Shorts views (90 days)

This pipeline helps you ship consistently (the main lever). Use `stats` to track subs; watch hours are in YouTube Studio → Analytics.

## Tips for fastest growth

1. **Niche down** — one game or genre in `DEFAULT_GAME`
2. **Shorts + long** — process Shorts (&lt;60s) for `#shorts` auto-tagging
3. **Batch record, batch upload** — 3 Shorts + 1 long per week minimum
4. **Edit bundle JSON** before upload if you want a custom title
5. **Playlist ID** — set `DEFAULT_PLAYLIST_ID` for series binge-watching

## Privacy defaults

New uploads default to **unlisted** so you can preview on YouTube before going public. Change `DEFAULT_PRIVACY=public` in `config.env` when ready.