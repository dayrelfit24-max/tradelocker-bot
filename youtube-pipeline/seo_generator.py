"""Gaming-focused YouTube SEO: titles, descriptions, tags."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import config
from popular_games import (
    GAME_DISPLAY,
    GAME_KEYWORDS,
    detect_game_from_text,
    list_popular_games,
    resolve_game_key,
)

TITLE_HOOKS = [
    "INSANE", "UNREAL", "They Did NOT Expect This", "Watch Till The End",
    "This Should NOT Be Legal", "I Can't Believe This Worked", "BROKEN",
    "CLUTCH", "GONE WRONG", "Peak Gameplay",
]

POWER_WORDS = ["BEST", "EPIC", "CRAZY", "ULTIMATE", "PRO", "RANKED", "HIGHLIGHTS"]


@dataclass
class VideoMetadata:
    title: str
    description: str
    tags: list[str]
    game: str
    hook: str
    is_short: bool
    hashtags: str
    chapters_placeholder: str

    def to_dict(self) -> dict:
        return asdict(self)

    def tag_string(self) -> str:
        """YouTube allows ~500 chars total for tags."""
        tags: list[str] = []
        total = 0
        for tag in self.tags:
            t = tag.strip()[:30]
            if not t or t in tags:
                continue
            add = len(t) + (1 if tags else 0)
            if total + add > 480:
                break
            tags.append(t)
            total += add
        return ",".join(tags)


def detect_game(text: str) -> str:
    found = detect_game_from_text(text)
    if found != "Gaming":
        return found
    return config.DEFAULT_GAME


def detect_short(duration_sec: float | None, path: Path) -> bool:
    if duration_sec is not None and duration_sec <= 60:
        return True
    name = path.stem.lower()
    return "short" in name or "shorts" in name or "#short" in name


def _slug_words(path: Path) -> str:
    """Turn filename into readable topic."""
    name = path.stem
    name = re.sub(r"[_\-\.]+", " ", name)
    name = re.sub(r"\b(20\d{2}|ep\d+|part\d+|v\d+)\b", "", name, flags=re.I)
    name = re.sub(r"\s+", " ", name).strip()
    return name.title() if name else "Epic Moment"


def build_title(game: str, topic: str, hook: str, is_short: bool) -> str:
    """CTR-focused title under 70 chars when possible."""
    game_up = game.upper() if len(game) <= 6 else game
    if is_short:
        base = f"{hook} {game_up} #shorts"
    else:
        base = f"{hook} {game_up} — {topic}"
    if len(base) > 95:
        base = f"{hook} {game_up} Gameplay"
    return base[:100]


def build_description(
    game: str,
    title: str,
    topic: str,
    is_short: bool,
    duration_sec: float | None,
) -> str:
    lines: list[str] = []
    lines.append(f"🔥 {title}")
    lines.append("")
    lines.append(
        f"Welcome back to {config.CHANNEL_NAME}! Today we're dropping "
        f"{'a Short' if is_short else 'full gameplay'} from {game} — {topic}."
    )
    lines.append("")
    lines.append("⏱️ TIMESTAMPS")
    if is_short:
        lines.append("0:00 — Watch till the end!")
    else:
        lines.append("0:00 — Intro")
        lines.append("0:30 — Highlights start")
        if duration_sec and duration_sec > 300:
            mid = int(duration_sec // 2)
            m, s = divmod(mid, 60)
            lines.append(f"{m}:{s:02d} — Best moment")
        lines.append("— Like & subscribe if you enjoyed!")
    lines.append("")
    lines.append("🎮 ABOUT THIS VIDEO")
    lines.append(
        f"In this {game} video we break down {topic.lower()}. "
        "Drop a comment with your rank / main and what you want next!"
    )
    lines.append("")
    lines.append(f"✅ SUBSCRIBE to {config.CHANNEL_NAME} for daily {game} & trending game content")
    if config.CHANNEL_URL:
        lines.append(f"👉 {config.CHANNEL_URL}")
    lines.append("🔔 Turn on notifications so you never miss a upload!")
    links = []
    if config.DISCORD_URL:
        links.append(f"Discord: {config.DISCORD_URL}")
    if config.TWITTER_URL:
        links.append(f"Twitter/X: {config.TWITTER_URL}")
    if config.TWITCH_URL:
        links.append(f"Twitch: {config.TWITCH_URL}")
    if links:
        lines.append("")
        lines.append("🔗 CONNECT")
        lines.extend(links)
    lines.append("")
    lines.append("🏷️ TAGS (for search)")
    game_key = resolve_game_key(game)
    kw = GAME_KEYWORDS.get(game_key, GAME_KEYWORDS["gaming"])
    lines.append(", ".join(kw[:12]))
    lines.append("")
    lines.append(config.DEFAULT_HASHTAGS)
    game_tag = "#" + re.sub(r"\W+", "", game.lower())
    if game_tag not in config.DEFAULT_HASHTAGS:
        lines.append(f"{game_tag} #gamingcommunity")
    lines.append("")
    lines.append(
        "#ad — Some links may be affiliate. "
        "All opinions are my own."
    )
    return "\n".join(lines)


def build_tags(game: str, topic: str, is_short: bool) -> list[str]:
    game_key = resolve_game_key(game)
    base = list(GAME_KEYWORDS.get(game_key, GAME_KEYWORDS["gaming"]))
    topic_words = [w.lower() for w in topic.split() if len(w) > 3]
    extra = [
        "progamer",
        "pro gamer",
        config.CHANNEL_NAME.lower(),
        f"{game_key} gameplay",
        f"{game_key} highlights",
        topic.lower(),
        "gaming channel",
        "youtube gaming",
        "best gaming moments",
        "trending games",
        "popular games 2026",
    ]
    if is_short:
        extra.extend(["youtube shorts", "gaming shorts", "shorts gaming", "shorts"])
    tags = base + extra + topic_words
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        t = re.sub(r"[^\w\s\-]", "", t).strip().lower()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out[:35]


def _clean_topic(topic: str, game: str) -> str:
    """Remove redundant game name from topic for titles."""
    g = game.lower()
    words = [w for w in topic.split() if w.lower() not in g.split() and w.lower() != g.replace(" ", "")]
    cleaned = " ".join(words).strip()
    return cleaned or topic


def generate_metadata(
    video_path: Path,
    game: str | None = None,
    hook: str | None = None,
    topic: str | None = None,
    duration_sec: float | None = None,
    custom_title: str | None = None,
) -> VideoMetadata:
    path = Path(video_path)
    if game:
        detected_game = GAME_DISPLAY.get(resolve_game_key(game), game)
    else:
        detected_game = detect_game(path.stem)
    topic_text = topic or _slug_words(path)
    topic_text = _clean_topic(topic_text, detected_game)
    hook_text = hook or TITLE_HOOKS[hash(path.name) % len(TITLE_HOOKS)]
    is_short = detect_short(duration_sec, path)
    title = custom_title or build_title(detected_game, topic_text, hook_text, is_short)
    description = build_description(
        detected_game, title, topic_text, is_short, duration_sec
    )
    tags = build_tags(detected_game, topic_text, is_short)
    hashtags = config.DEFAULT_HASHTAGS
    if is_short and "#shorts" not in hashtags.lower():
        hashtags += " #shorts"
    chapters = "Add chapters in YouTube Studio after upload (timestamps above)."
    return VideoMetadata(
        title=title,
        description=description,
        tags=tags,
        game=detected_game,
        hook=hook_text,
        is_short=is_short,
        hashtags=hashtags,
        chapters_placeholder=chapters,
    )


def save_metadata_bundle(
    video_path: Path,
    metadata: VideoMetadata,
    thumbnail_path: Path | None,
    out_dir: Path,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = {
        "video": str(video_path.resolve()),
        "thumbnail": str(thumbnail_path.resolve()) if thumbnail_path else None,
        "generated_at": datetime.now().isoformat(),
        "metadata": metadata.to_dict(),
        "youtube": {
            "category_id": config.YOUTUBE_CATEGORY_ID,
            "privacy": config.DEFAULT_PRIVACY,
            "language": config.DEFAULT_LANGUAGE,
            "playlist_id": config.DEFAULT_PLAYLIST_ID or None,
        },
        "growth_tips": [
            "Pin a comment asking a question within 1 hour",
            "Reply to every comment in the first 24h",
            "Share to Discord/Twitter within 30 min",
            "Add to a series playlist for binge sessions",
            "Use YouTube Analytics → Traffic sources after 48h",
        ],
    }
    out_path = out_dir / f"{video_path.stem}_upload.json"
    out_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return out_path