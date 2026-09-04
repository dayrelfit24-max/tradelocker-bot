"""Fetch fresh gaming trends (Reddit hot/rising/new) and avoid repeating recent topics."""

from __future__ import annotations

import json
import random
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import requests

import config
from popular_games import detect_game_from_text

PULLPUSH_API = "https://api.pullpush.io/reddit/search/submission/"
REDDIT_SUBREDDITS = [
    "gaming",
    "Games",
    "pcgaming",
    "GlobalOffensive",
    "FortNiteBR",
    "GTA6",
    "PS5",
    "xbox",
    "NintendoSwitch",
    "GamingLeaksAndRumours",
]
GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search?q=video+games+gaming&hl=en-US&gl=US&ceid=US:en"
)
_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

CURATED_TOPICS = [
    "Best games to play on PC right now",
    "Best PS5 exclusives you need in 2026",
    "Best Xbox Game Pass games this month",
    "Upcoming AAA games releasing soon",
    "Nintendo Switch games worth buying",
    "Free games you should download today",
    "Gaming industry news and acquisitions",
    "Steam Deck vs handheld PC gaming",
    "VR gaming comeback in 2026",
    "Indie games blowing up on Steam",
    "Battle royale meta shifts in 2026",
    "Co-op games to play with friends",
    "Horror games trending this week",
    "RPG releases everyone is talking about",
    "Esports highlights and roster moves",
    "Game pass day-one releases worth it",
    "Crossplay games dominating lobbies",
    "Speedrun records broken this month",
]

_SKIP_TITLE = re.compile(
    r"megathread|weekly|daily thread|rant thread|meme monday|simple questions|"
    r"free talk|self.?promotion|giveaway thread|community highlights",
    re.I,
)


@dataclass
class TrendingTopic:
    title: str
    source: str
    subreddit: str = ""
    score: int = 0
    created_utc: float = 0.0
    feed: str = "hot"

    @property
    def sort_key(self) -> float:
        """Higher = prefer for today's videos."""
        age_hours = max(0.0, (time.time() - self.created_utc) / 3600) if self.created_utc else 48.0
        recency = max(0.0, 400.0 - age_hours * 12.0)
        feed_boost = {"rising": 350.0, "new": 280.0, "hot": 120.0}.get(self.feed, 0.0)
        src_boost = 80.0 if self.source == "reddit" else 20.0
        return float(self.score) + recency + feed_boost + src_boost


def _history_path() -> Path:
    return config.GENERATED_DIR / "trend_history.json"


def _normalize_title(title: str) -> str:
    t = re.sub(r"\[.*?\]", "", title.lower())
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:80]


def _clean_title(title: str) -> str:
    t = re.sub(r"\[.*?\]", "", title)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:120]


def load_trend_history() -> list[dict]:
    path = _history_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("used", []) if isinstance(data, dict) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_trend_history(entries: list[dict]) -> None:
    path = _history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"used": entries}, indent=2), encoding="utf-8")


def _recently_used_titles(days: int | None = None) -> set[str]:
    days = days or int(getattr(config, "TREND_HISTORY_DAYS", 14))
    cutoff = datetime.now() - timedelta(days=days)
    used: set[str] = set()
    for row in load_trend_history():
        title = row.get("title", "")
        if not title:
            continue
        try:
            when = datetime.fromisoformat(row.get("date", ""))
        except ValueError:
            when = cutoff
        if when >= cutoff:
            used.add(_normalize_title(title))
    return used


def record_trends_from_plan(plan: list) -> None:
    """Persist topics used today so future runs pick fresh headlines."""
    history = load_trend_history()
    today = datetime.now().isoformat(timespec="seconds")
    seen_norm: set[str] = set()
    for item in plan:
        title = getattr(item, "trend_title", None) or getattr(item, "topic", "")
        if not title:
            continue
        norm = _normalize_title(title)
        if norm in seen_norm:
            continue
        seen_norm.add(norm)
        history.append({
            "title": title,
            "date": today,
            "slot": getattr(item, "slot", ""),
            "source": getattr(item, "trend_source", ""),
            "game": getattr(item, "game", ""),
        })
    # Keep last ~200 entries
    save_trend_history(history[-200:])


def _fetch_pullpush_subreddit(sub: str, feed: str, limit: int = 12) -> list[TrendingTopic]:
    """Reddit mirror API (reddit.com JSON often returns 403 from servers)."""
    params: dict = {"subreddit": sub, "sort": "desc", "size": limit}
    if feed == "new":
        params["sort_type"] = "created_utc"
    else:
        params["sort_type"] = "score"
    if feed == "rising":
        params["after"] = int(time.time()) - 36 * 3600
    topics: list[TrendingTopic] = []
    try:
        r = requests.get(PULLPUSH_API, params=params, headers=_HTTP_HEADERS, timeout=20)
        r.raise_for_status()
        for post in r.json().get("data", []):
            title = _clean_title(post.get("title", ""))
            if len(title) < 12 or post.get("over_18"):
                continue
            if _SKIP_TITLE.search(title):
                continue
            topics.append(
                TrendingTopic(
                    title=title,
                    source="reddit",
                    subreddit=sub,
                    score=int(post.get("score", 0)),
                    created_utc=float(post.get("created_utc", 0)),
                    feed=feed,
                )
            )
    except (requests.RequestException, ValueError, KeyError):
        pass
    return topics


def fetch_google_news_trends() -> list[TrendingTopic]:
    topics: list[TrendingTopic] = []
    try:
        r = requests.get(GOOGLE_NEWS_RSS, headers=_HTTP_HEADERS, timeout=20)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        for item in root.findall(".//item"):
            title_el = item.find("title")
            if title_el is None or not title_el.text:
                continue
            title = _clean_title(title_el.text.split(" - ")[0])
            if len(title) < 15 or _SKIP_TITLE.search(title):
                continue
            topics.append(
                TrendingTopic(
                    title=title,
                    source="google_news",
                    feed="news",
                    score=400,
                    created_utc=time.time(),
                )
            )
    except (requests.RequestException, ET.ParseError):
        pass
    return topics[:20]


def fetch_reddit_trends() -> list[TrendingTopic]:
    topics: list[TrendingTopic] = []
    for sub in REDDIT_SUBREDDITS:
        topics.extend(_fetch_pullpush_subreddit(sub, "hot", limit=10))
        if sub in ("gaming", "Games", "pcgaming"):
            topics.extend(_fetch_pullpush_subreddit(sub, "rising", limit=6))
            topics.extend(_fetch_pullpush_subreddit(sub, "new", limit=5))

    topics.sort(key=lambda t: t.sort_key, reverse=True)
    seen: set[str] = set()
    out: list[TrendingTopic] = []
    for t in topics:
        key = _normalize_title(t.title)
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out[:40]


def fetch_curated_trends() -> list[TrendingTopic]:
    """Rotate curated list by day so fallback topics still feel fresh."""
    day = datetime.now().timetuple().tm_yday
    n = len(CURATED_TOPICS)
    rotated = CURATED_TOPICS[day % n :] + CURATED_TOPICS[: day % n]
    return [
        TrendingTopic(title=t, source="curated", feed="curated")
        for t in rotated
    ]


def fetch_rawg_trending() -> list[TrendingTopic]:
    key = getattr(config, "RAWG_API_KEY", "")
    if not key:
        return []
    try:
        r = requests.get(
            "https://api.rawg.io/api/games/trending",
            params={"key": key},
            timeout=15,
        )
        r.raise_for_status()
        out: list[TrendingTopic] = []
        for item in r.json().get("results", [])[:12]:
            name = item.get("name", "")
            if not name:
                continue
            out.append(
                TrendingTopic(
                    title=f"{name} is trending right now",
                    source="rawg",
                    score=500,
                    feed="trending",
                )
            )
        return out
    except requests.RequestException:
        return []


def get_all_trends() -> list[TrendingTopic]:
    reddit = fetch_reddit_trends()
    news = fetch_google_news_trends()
    rawg = fetch_rawg_trending()
    curated = fetch_curated_trends()
    pool = reddit + news + rawg + curated
    pool.sort(key=lambda t: t.sort_key, reverse=True)
    seen: set[str] = set()
    out: list[TrendingTopic] = []
    for t in pool:
        key = _normalize_title(t.title)
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out


def pick_fresh_trends(
    count: int,
    exclude: set[str] | None = None,
) -> list[TrendingTopic]:
    """Pick `count` unique trends not used recently (always fetches live Reddit)."""
    exclude_norm = {_normalize_title(x) for x in (exclude or set())}
    exclude_norm |= _recently_used_titles()
    pool = get_all_trends()

    fresh: list[TrendingTopic] = []
    for t in pool:
        if _normalize_title(t.title) in exclude_norm:
            continue
        fresh.append(t)
        exclude_norm.add(_normalize_title(t.title))
        if len(fresh) >= count:
            return fresh

    # Not enough new topics — allow older repeats, still shuffled
    random.shuffle(pool)
    for t in pool:
        key = _normalize_title(t.title)
        if key in {_normalize_title(x.title) for x in fresh}:
            continue
        fresh.append(t)
        if len(fresh) >= count:
            break
    return fresh


def pick_trend(used: set[str] | None = None) -> TrendingTopic:
    used_norm = {_normalize_title(u) for u in (used or set())}
    picks = pick_fresh_trends(1, exclude=used_norm)
    if picks:
        return picks[0]
    return TrendingTopic(title=random.choice(CURATED_TOPICS), source="fallback")


def game_from_trend(topic: TrendingTopic) -> str | None:
    """Map a trend headline to a known game when possible."""
    game = detect_game_from_text(topic.title)
    return None if game == "Gaming" else game


def platform_for_day() -> str:
    if getattr(config, "CHANNEL_FOCUS_ENABLED", False):
        return getattr(config, "CHANNEL_FOCUS_PLATFORM", "PC") or "PC"
    platforms = ["PC", "PS5", "Xbox", "Nintendo Switch"]
    return platforms[datetime.now().day % len(platforms)]


def focus_game_for_day() -> str:
    """Primary game for the day — sticky niche beats daily rotation."""
    primary = getattr(config, "CHANNEL_PRIMARY_GAME", "").strip()
    if primary:
        return primary
    games = getattr(config, "CHANNEL_FOCUS_GAMES", None) or []
    if not games:
        return "Fortnite"
    # Weekly rotation (not daily) when no primary set — build audience per game
    week = datetime.now().isocalendar()[1]
    return games[week % len(games)]


def _matches_focus(trend: TrendingTopic) -> bool:
    if not getattr(config, "CHANNEL_FOCUS_ENABLED", False):
        return True
    games = getattr(config, "CHANNEL_FOCUS_GAMES", None) or []
    if not games:
        return True
    text = f"{trend.title} {trend.subreddit}".lower()
    platform = (getattr(config, "CHANNEL_FOCUS_PLATFORM", "") or "").lower()
    if platform and platform in text:
        return True
    for game in games:
        if game.lower() in text:
            return True
    detected = detect_game_from_text(trend.title)
    return detected in games


def pick_focused_trend(used: set[str] | None = None) -> TrendingTopic:
    """Trend about a focus game/platform, or a curated fallback."""
    used_norm = {_normalize_title(u) for u in (used or set())}
    pool = [t for t in get_all_trends() if _matches_focus(t)]
    random.shuffle(pool)
    for t in pool:
        if _normalize_title(t.title) not in used_norm:
            return t
    game = focus_game_for_day()
    platform = platform_for_day()
    if game.lower() == "gta":
        fallbacks = [
            f"What changed in GTA Online this week on {platform}",
            f"GTA Online PvP habits most PC players skip",
            f"GTA PC settings hurting your gunfights",
        ]
    elif game.lower() == "fortnite":
        fallbacks = [
            "5 Fortnite box fight habits ranked players use on PC",
            "Fortnite edit speed tips that instantly help piece control",
            "The building trick Fortnite pros won't tell you",
            "One PC sensitivity tweak for better shotgun flicks in Fortnite",
            "Stop taking this height fight in Fortnite ranked",
        ]
    else:
        fallbacks = [
            f"What changed in {game} this week on {platform}",
            f"{game} habits most {platform} players skip",
            f"{game} PC settings hurting your consistency",
        ]
    return TrendingTopic(title=random.choice(fallbacks), source="focus_curated")