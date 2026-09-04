"""One-week growth experiment — Fortnite Shorts only (channel audit Jul 2026)."""

from __future__ import annotations

import json
from datetime import datetime

import config

# Winning title shapes from channel audit (125-view Fortnite Short)
FORTNITE_WINNING_TITLES = (
    "5 Fortnite Tips That INSTANTLY Make You Better",
    "The Building Trick Pro Players Won't Tell You",
    "This PC Setting Is Killing Your Aim in Fortnite",
    "5 Edit Speed Tips That Fix Your Box Fights",
    "The Piece Control Habit Ranked Players Use",
    "Stop Taking This Fight — Rotate Earlier",
    "One Sensitivity Tweak for Better Shotgun Flicks",
)

# Mon=0 … Fri=4
DEFAULT_SHORT_WEEKDAYS = (0, 1, 2, 3, 4)


def _parse_date(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def is_active() -> bool:
    if not getattr(config, "GROWTH_TEST_ENABLED", False):
        return False
    until = _parse_date(getattr(config, "GROWTH_TEST_UNTIL", ""))
    if until and datetime.now() > until.replace(hour=23, minute=59, second=59):
        return False
    return True


def shorts_only() -> bool:
    return is_active() and getattr(config, "GROWTH_TEST_SHORTS_ONLY", False)


def short_weekdays() -> tuple[int, ...]:
    raw = getattr(config, "GROWTH_TEST_SHORT_WEEKDAYS", "")
    if not raw:
        return DEFAULT_SHORT_WEEKDAYS
    days: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            days.append(int(part))
    return tuple(days) if days else DEFAULT_SHORT_WEEKDAYS


def short_uploaded_today(day: datetime | None = None) -> bool:
    """True if today's 6 PM short slot already ran successfully."""
    day = day or datetime.now()
    log_path = config.GENERATED_DIR / f"daily_log_{day:%Y%m%d}_short.json"
    if not log_path.is_file():
        return False
    try:
        data = json.loads(log_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return False
        return any(not entry.get("error") and entry.get("bundle") for entry in data)
    except (json.JSONDecodeError, OSError):
        return False


def is_short_upload_day(day: datetime | None = None) -> bool:
    day = day or datetime.now()
    if not is_active():
        return True
    return day.weekday() in short_weekdays()


def should_run_slot(slot: str | None) -> bool:
    """Return False when this launchd slot should no-op."""
    if not is_active():
        return True
    if slot == "long" and shorts_only():
        return False
    if slot == "short" and not is_short_upload_day():
        return False
    if slot == "short" and short_uploaded_today():
        return False
    return True


def status_line() -> str:
    if not is_active():
        return ""
    game = getattr(config, "CHANNEL_PRIMARY_GAME", "Fortnite")
    until = getattr(config, "GROWTH_TEST_UNTIL", "?")
    days = "Mon–Fri" if short_weekdays() == DEFAULT_SHORT_WEEKDAYS else ",".join(str(d) for d in short_weekdays())
    mode = "Shorts only" if shorts_only() else "long + short"
    return f"🧪 GROWTH TEST until {until}: {game} | {mode} | Shorts {days} @ 6 PM"