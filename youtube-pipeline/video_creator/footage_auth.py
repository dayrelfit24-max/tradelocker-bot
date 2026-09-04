"""YouTube gameplay download auth status for pipeline logs."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import config


def youtube_cookies_path() -> Path | None:
    path = getattr(config, "YT_DLP_COOKIES_FILE", None)
    if path and Path(path).is_file() and Path(path).stat().st_size > 50:
        return Path(path)
    return None


def youtube_footage_auth_label() -> str:
    """Human-readable status for create/daily logs."""
    path = youtube_cookies_path()
    if path:
        days = int((time.time() - path.stat().st_mtime) / 86400)
        stale = " ⚠️ re-export soon" if days >= 21 else ""
        return f"READY (cookies file, {days}d old){stale}"

    browser = getattr(config, "YT_DLP_COOKIES_FROM_BROWSER", "").strip()
    if browser:
        return f"browser ({browser}) — may prompt keychain at 8 AM"

    return "NOT SET — run ./export_youtube_cookies.sh (Pexels fallback until then)"


def verify_youtube_download(timeout: int = 25) -> bool:
    """Quick probe: can we download a short YouTube clip with current auth?"""
    path = youtube_cookies_path()
    if not path:
        return False
    try:
        out = subprocess.run(
            [
                "yt-dlp", "--no-warnings", "--no-update",
                "--cookies", str(path),
                "--simulate", "--no-playlist",
                "https://www.youtube.com/watch?v=jNQXAC9IVRw",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        err = (out.stderr or out.stdout or "").lower()
        if "sign in" in err or "not a bot" in err:
            return False
        return out.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False