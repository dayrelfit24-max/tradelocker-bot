"""Video format templates for faceless gaming content."""

from __future__ import annotations

import re
from dataclasses import dataclass

FORMAT_CHOICES = (
    "tips", "top5", "news", "facts", "versus",
    "gameplay", "bestgames", "upcoming", "industry",
)


@dataclass
class FormatSpec:
    name: str
    label: str
    scene_count_short: int
    scene_count_long: int
    seconds_per_scene_short: float
    seconds_per_scene_long: float


FORMATS: dict[str, FormatSpec] = {
    "tips": FormatSpec(
        name="tips",
        label="Pro Tips You Need",
        scene_count_short=7,
        scene_count_long=8,
        seconds_per_scene_short=4.5,
        seconds_per_scene_long=8.0,
    ),
    "top5": FormatSpec(
        name="top5",
        label="Top 5 Countdown",
        scene_count_short=6,
        scene_count_long=10,
        seconds_per_scene_short=4.0,
        seconds_per_scene_long=7.0,
    ),
    "news": FormatSpec(
        name="news",
        label="Gaming News Update",
        scene_count_short=4,
        scene_count_long=7,
        seconds_per_scene_short=5.0,
        seconds_per_scene_long=9.0,
    ),
    "facts": FormatSpec(
        name="facts",
        label="Insane Facts",
        scene_count_short=5,
        scene_count_long=8,
        seconds_per_scene_short=4.5,
        seconds_per_scene_long=8.0,
    ),
    "versus": FormatSpec(
        name="versus",
        label="Which Is Better",
        scene_count_short=5,
        scene_count_long=8,
        seconds_per_scene_short=4.5,
        seconds_per_scene_long=8.0,
    ),
    "gameplay": FormatSpec(
        name="gameplay",
        label="Gameplay Highlights",
        scene_count_short=6,
        scene_count_long=12,
        seconds_per_scene_short=5.0,
        seconds_per_scene_long=10.0,
    ),
    "bestgames": FormatSpec(
        name="bestgames",
        label="Best Games To Play",
        scene_count_short=5,
        scene_count_long=9,
        seconds_per_scene_short=4.5,
        seconds_per_scene_long=8.5,
    ),
    "upcoming": FormatSpec(
        name="upcoming",
        label="Upcoming Games",
        scene_count_short=5,
        scene_count_long=8,
        seconds_per_scene_short=4.5,
        seconds_per_scene_long=9.0,
    ),
    "industry": FormatSpec(
        name="industry",
        label="Gaming Industry News",
        scene_count_short=4,
        scene_count_long=8,
        seconds_per_scene_short=5.0,
        seconds_per_scene_long=9.0,
    ),
}


def uses_gameplay_footage(format_name: str) -> bool:
    """Deprecated — we no longer fake personal gameplay footage."""
    return False


def is_generic_format(format_name: str) -> bool:
    """Formats that use generic gaming B-roll instead of a single game."""
    return format_name in ("industry", "news", "bestgames")


def uses_tip_numbering(format_name: str) -> bool:
    """Only true tips videos should show TIP #1 / tip-style narration."""
    return format_name == "tips"


def scene_overlay_badge(format_name: str, scene_index: int, headline: str) -> str | None:
    """Shorts on-screen badge above headline — tips only by default."""
    if headline.upper() in ("SUBSCRIBE", "FOLLOW", "FOLLOW FOR MORE"):
        return None
    if scene_index == 0:
        return None
    if uses_tip_numbering(format_name):
        return f"TIP #{scene_index}"
    if format_name in ("top5", "bestgames"):
        m = re.search(r"#\s*(\d+)", headline)
        if m:
            return f"#{m.group(1)}"
    if format_name == "facts":
        return f"FACT #{scene_index}"
    return None


def is_short_format(duration: str) -> bool:
    return duration.lower() in ("short", "shorts", "60", "60s")