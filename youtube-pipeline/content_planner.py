"""Daily content plan — focused niche (VidIQ) or legacy multi-topic schedule."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import config
from content_angles import long_topic, short_topic, winning_short_angle
from growth_test import is_active as growth_test_active, shorts_only
from popular_games import list_popular_games
from trending_topics import (
    focus_game_for_day,
    game_from_trend,
    pick_focused_trend,
    pick_fresh_trends,
    platform_for_day,
    record_trends_from_plan,
)


@dataclass
class PlannedVideo:
    slot: str
    duration: str  # short | long
    format: str
    game: str | None
    topic: str
    trend_title: str
    trend_source: str = ""
    platform: str | None = None
    use_gameplay_footage: bool = False

    def label(self) -> str:
        src = f" [{self.trend_source}]" if self.trend_source else ""
        return f"{self.duration.upper()} | {self.format} | {self.topic[:48]}{src}"


def _format_for_day(game: str) -> tuple[str, str]:
    """Rotate formats within niche — tips dominate but news breaks repetition."""
    if growth_test_active():
        return "tips", f"{game} pro tips Short (winning title format)"
    # Mon/Wed/Fri/Sat/Sun tips | Tue industry patch | Thu upcoming
    weekday = datetime.now().weekday()
    if weekday == 1:
        return "industry", f"{game} update or meta shift players are missing"
    if weekday == 3:
        return "upcoming", f"What's next for {game} on PC"
    return "tips", "tips"


def _build_focused_plan(long_n: int, short_n: int) -> list[PlannedVideo]:
    """
    One niche game, varied angles, long + short different topics same day.
    """
    platform = platform_for_day()
    game = focus_game_for_day()
    plan: list[PlannedVideo] = []
    used_topics: set[str] = set()
    long_fmt, long_fmt_hint = _format_for_day(game)

    long_topic_text = ""
    if long_n >= 1:
        tr = pick_focused_trend(used_topics)
        used_topics.add(tr.title)
        if long_fmt == "tips":
            long_topic_text = long_topic(game, platform)
        else:
            long_topic_text = f"{game}: {long_fmt_hint} — {tr.title[:60]}"
        plan.append(
            PlannedVideo(
                f"long_{long_fmt}",
                "long",
                long_fmt,
                game,
                long_topic_text,
                tr.title,
                tr.source,
                platform,
                False,
            )
        )

    if short_n >= 1:
        tr = pick_focused_trend(used_topics)
        if growth_test_active():
            short_topic_text = winning_short_angle(game, platform)
        else:
            short_topic_text = short_topic(game, platform, long_topic_text)
        plan.append(
            PlannedVideo(
                "short_tips",
                "short",
                "tips",
                game,
                short_topic_text,
                tr.title,
                tr.source,
                platform,
                False,
            )
        )

    return plan


def build_daily_plan(
    long_count: int | None = None,
    short_count: int | None = None,
) -> list[PlannedVideo]:
    if shorts_only():
        long_n = 0
        short_n = short_count or getattr(config, "DAILY_SHORTS", 1)
    else:
        long_n = long_count if long_count is not None else getattr(config, "DAILY_LONG_VIDEOS", 3)
        short_n = short_count if short_count is not None else getattr(config, "DAILY_SHORTS", 4)

    if getattr(config, "CHANNEL_FOCUS_ENABLED", False):
        plan = _build_focused_plan(long_n, short_n)
        if getattr(config, "TREND_TRACK_HISTORY", True):
            record_trends_from_plan(plan)
        return plan

    games = [g for g in list_popular_games() if g != "Gaming"]
    random.shuffle(games)

    trend_slots = long_n + short_n
    fresh = pick_fresh_trends(trend_slots + 2)
    trend_idx = 0

    def next_trend():
        nonlocal trend_idx
        if trend_idx < len(fresh):
            t = fresh[trend_idx]
            trend_idx += 1
            return t
        from trending_topics import pick_trend
        return pick_trend()

    plan: list[PlannedVideo] = []
    platform = platform_for_day()

    long_specs = [
        ("long_news", "industry", None, True),
        ("long_best", "bestgames", None, False),
        ("long_upcoming", "upcoming", None, True),
    ]
    for slot, fmt, game_hint, wants_trend in long_specs[:long_n]:
        if wants_trend:
            tr = next_trend()
            topic = tr.title
            game = game_from_trend(tr) or (games[0] if games else "Fortnite")
            src = tr.source
        elif fmt == "bestgames":
            topic = f"Best games on {platform} right now"
            game = None
            src = "curated"
        else:
            tr = next_trend()
            topic = tr.title
            game = game_hint
            src = tr.source
        plan.append(
            PlannedVideo(slot, "long", fmt, game, topic, topic, src, platform, False)
        )

    short_specs = [
        ("short_trend", "news", None, True),
        ("short_tips", "tips", None, True),
        ("short_best", "bestgames", None, False),
        ("short_upcoming", "upcoming", None, True),
    ]
    g_i = 1
    for slot, fmt, game_hint, wants_trend in short_specs[:short_n]:
        if fmt == "bestgames":
            topic = f"Top {platform} picks this week"
            game = None
            src = "curated"
        elif wants_trend:
            tr = next_trend()
            topic = tr.title
            src = tr.source
            detected = game_from_trend(tr)
            if fmt == "tips":
                game = detected or (games[g_i % len(games)] if games else "Valorant")
                g_i += 1
            elif fmt == "upcoming":
                game = detected or (games[g_i % len(games)] if games else "Gaming")
                g_i += 1
            else:
                game = game_hint
        else:
            tr = next_trend()
            topic = tr.title
            game = game_hint
            src = tr.source
        plan.append(
            PlannedVideo(slot, "short", fmt, game, topic, topic, src, platform, False)
        )

    if getattr(config, "TREND_TRACK_HISTORY", True):
        record_trends_from_plan(plan)

    return plan


def load_daily_plan(day: datetime | None = None) -> list[PlannedVideo] | None:
    """Load today's saved plan (written by the 8 AM long run)."""
    day = day or datetime.now()
    path = config.GENERATED_DIR / f"daily_plan_{day:%Y%m%d}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [PlannedVideo(**v) for v in data.get("videos", [])]
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


def save_plan(plan: list[PlannedVideo], path: Path | None = None) -> Path:
    path = path or config.GENERATED_DIR / f"daily_plan_{datetime.now():%Y%m%d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    focus = getattr(config, "CHANNEL_FOCUS_ENABLED", False)
    data = {
        "date": datetime.now().isoformat(),
        "channel": config.CHANNEL_NAME,
        "mode": "growth_test" if growth_test_active() else ("focused" if focus else "scatter"),
        "focus_platform": getattr(config, "CHANNEL_FOCUS_PLATFORM", "") if focus else None,
        "focus_games": getattr(config, "CHANNEL_FOCUS_GAMES", []) if focus else None,
        "primary_game": getattr(config, "CHANNEL_PRIMARY_GAME", "") if focus else None,
        "total": len(plan),
        "longs": sum(1 for p in plan if p.duration == "long"),
        "shorts": sum(1 for p in plan if p.duration == "short"),
        "trending": "Reddit (PullPush) + Google News + optional RAWG",
        "videos": [asdict(p) for p in plan],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path