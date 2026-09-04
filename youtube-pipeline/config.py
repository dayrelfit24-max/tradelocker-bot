"""Load pipeline configuration from config.env."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / "config.env")


def _bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).lower() in ("1", "true", "yes", "on")


def _path(key: str, default: str) -> Path:
    raw = os.getenv(key, default)
    p = Path(raw)
    return p if p.is_absolute() else ROOT / p


CHANNEL_NAME = os.getenv("CHANNEL_NAME", "Your Gaming Channel")
CHANNEL_URL = os.getenv("CHANNEL_URL", "")
DISCORD_URL = os.getenv("DISCORD_URL", "")
TWITTER_URL = os.getenv("TWITTER_URL", "")
TWITCH_URL = os.getenv("TWITCH_URL", "")
DEFAULT_GAME = os.getenv("DEFAULT_GAME", "Gaming")
DEFAULT_PRIVACY = os.getenv("DEFAULT_PRIVACY", "unlisted")
REQUIRE_REVIEW = _bool("REQUIRE_REVIEW", True)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
AI_PROVIDER = os.getenv("AI_PROVIDER", "auto")  # auto | claude | openai
THUMBNAIL_STYLE = os.getenv("THUMBNAIL_STYLE", "neon")
DEFAULT_HASHTAGS = os.getenv("DEFAULT_HASHTAGS", "#gaming #gameplay")
DEFAULT_PLAYLIST_ID = os.getenv("DEFAULT_PLAYLIST_ID", "")
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "en")
YOUTUBE_CLIENT_SECRETS = _path("YOUTUBE_CLIENT_SECRETS", "client_secrets.json")
TOKEN_PATH = ROOT / "tokens" / "youtube_token.json"

INCOMING_DIR = ROOT / "incoming"
PROCESSED_DIR = ROOT / "processed"
THUMBNAILS_DIR = ROOT / "thumbnails"
GENERATED_DIR = ROOT / "generated"

# TTS: edge (free) or openai (tts-1-hd, most natural — set OPENAI_API_KEY + TTS_PROVIDER=openai)
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "edge")
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-AndrewMultilingualNeural")
TTS_RATE = os.getenv("TTS_RATE", "+5%")
TTS_PITCH = os.getenv("TTS_PITCH", "+0Hz")
TTS_VOLUME = os.getenv("TTS_VOLUME", "+0%")
TTS_OPENAI_MODEL = os.getenv("TTS_OPENAI_MODEL", "tts-1-hd")
TTS_OPENAI_SPEED = float(os.getenv("TTS_OPENAI_SPEED", "1.08"))
TTS_CHUNK_SENTENCES = _bool("TTS_CHUNK_SENTENCES", True)
TTS_AUDIO_POLISH = _bool("TTS_AUDIO_POLISH", True)
AUTO_PROCESS_AFTER_CREATE = _bool("AUTO_PROCESS_AFTER_CREATE", True)
DAILY_LONG_VIDEOS = int(os.getenv("DAILY_LONG_VIDEOS", "3"))
DAILY_SHORTS = int(os.getenv("DAILY_SHORTS", "4"))
CHANNEL_FOCUS_ENABLED = _bool("CHANNEL_FOCUS_ENABLED", False)
CHANNEL_FOCUS_PLATFORM = os.getenv("CHANNEL_FOCUS_PLATFORM", "PC").strip()
CHANNEL_FOCUS_GAMES = [
    g.strip() for g in os.getenv("CHANNEL_FOCUS_GAMES", "").split(",") if g.strip()
]
CHANNEL_PRIMARY_GAME = os.getenv("CHANNEL_PRIMARY_GAME", "").strip()
TITLE_HISTORY_DAYS = int(os.getenv("TITLE_HISTORY_DAYS", "30"))
# Growth test week — Fortnite Shorts Mon–Fri, no longs (see growth_test.py)
GROWTH_TEST_ENABLED = _bool("GROWTH_TEST_ENABLED", False)
GROWTH_TEST_UNTIL = os.getenv("GROWTH_TEST_UNTIL", "").strip()
GROWTH_TEST_SHORTS_ONLY = _bool("GROWTH_TEST_SHORTS_ONLY", False)
GROWTH_TEST_SHORT_WEEKDAYS = os.getenv("GROWTH_TEST_SHORT_WEEKDAYS", "0,1,2,3,4").strip()
AUTO_UPLOAD_DAILY = _bool("AUTO_UPLOAD_DAILY", False)
AUTO_CLEANUP_AFTER_UPLOAD = _bool("AUTO_CLEANUP_AFTER_UPLOAD", True)
UPLOAD_DELAY_SEC = int(os.getenv("UPLOAD_DELAY_SEC", "45"))
TREND_HISTORY_DAYS = int(os.getenv("TREND_HISTORY_DAYS", "14"))
TREND_TRACK_HISTORY = _bool("TREND_TRACK_HISTORY", True)

# Visual enhancement: Pexels B-roll + OpenAI scene images
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
COVERR_API_KEY = os.getenv("COVERR_API_KEY", "")
RAWG_API_KEY = os.getenv("RAWG_API_KEY", "")
USE_TRAILER_CLIPS = _bool("USE_TRAILER_CLIPS", True)
# gameplay = real in-game footage (default) | mix = alternate cinematic | cinematic = trailers only
TRAILER_FOOTAGE_STYLE = os.getenv("TRAILER_FOOTAGE_STYLE", "gameplay").lower()
GAMEPLAY_POOL_SIZE = max(1, min(int(os.getenv("GAMEPLAY_POOL_SIZE", "2")), 4))
YT_DLP_COOKIES_FROM_BROWSER = os.getenv("YT_DLP_COOKIES_FROM_BROWSER", "").strip()
_yt_cookies = os.getenv("YT_DLP_COOKIES_FILE", "").strip()
YT_DLP_COOKIES_FILE = Path(_yt_cookies) if _yt_cookies else None
if YT_DLP_COOKIES_FILE and not YT_DLP_COOKIES_FILE.is_absolute():
    YT_DLP_COOKIES_FILE = ROOT / YT_DLP_COOKIES_FILE
YT_DLP_EXTRA_ARGS = os.getenv("YT_DLP_EXTRA_ARGS", "").strip()
GAME_FOOTAGE_FALLBACK = _bool("GAME_FOOTAGE_FALLBACK", True)
VIDEO_ENCODE_QUALITY = os.getenv("VIDEO_ENCODE_QUALITY", "high").lower()
YT_MAX_HEIGHT = int(os.getenv("YT_MAX_HEIGHT", "1080"))
YT_MAX_FILESIZE = os.getenv("YT_MAX_FILESIZE", "400M")
# Long-form only — Shorts stay 1080×1920
VIDEO_LONG_HEIGHT = int(os.getenv("VIDEO_LONG_HEIGHT", "1440"))
YT_MAX_HEIGHT_LONG = int(os.getenv("YT_MAX_HEIGHT_LONG", str(VIDEO_LONG_HEIGHT)))
YT_MAX_FILESIZE_LONG = os.getenv("YT_MAX_FILESIZE_LONG", "800M")
SHORTS_VIDEO_ONLY = _bool("SHORTS_VIDEO_ONLY", True)
# fit = full frame + blurred sides (not zoomed). fill = center-crop zoom
SHORTS_ASPECT_MODE = os.getenv("SHORTS_ASPECT_MODE", "fit")
USE_STOCK_FOOTAGE = _bool("USE_STOCK_FOOTAGE", False)
USE_AI_IMAGES = _bool("USE_AI_IMAGES", True)
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "dall-e-3")
OPENAI_IMAGE_SIZE_SHORT = os.getenv("OPENAI_IMAGE_SIZE_SHORT", "1024x1792")
OPENAI_IMAGE_SIZE_LONG = os.getenv("OPENAI_IMAGE_SIZE_LONG", "1792x1024")

# YouTube category: Gaming
YOUTUBE_CATEGORY_ID = "20"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]