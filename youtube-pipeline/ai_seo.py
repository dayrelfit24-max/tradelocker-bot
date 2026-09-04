"""Optional LLM enhancement for titles, descriptions, and tags (Claude or OpenAI)."""

from __future__ import annotations

from pathlib import Path

import config
from llm_client import active_provider, chat_json
from seo_generator import VideoMetadata, generate_metadata
from youtube_upload import sanitize_youtube_tags


def _safe_tags(tags) -> list[str]:
    return sanitize_youtube_tags([str(t) for t in tags])


def enhance_metadata(
    video_path: Path,
    base: VideoMetadata,
    duration_sec: float | None = None,
) -> VideoMetadata:
    if not active_provider():
        return base

    from title_history import seo_guardrails, title_is_too_similar

    guardrails = seo_guardrails(base.game, base.is_short)
    prompt = f"""You are a YouTube gaming growth expert. Optimize this upload for CTR and search.

Game: {base.game}
Current title: {base.title}
Topic from filename: {video_path.stem}
Is Short: {base.is_short}
Duration seconds: {duration_sec or 'unknown'}
Channel: {config.CHANNEL_NAME} ({config.CHANNEL_URL})

{guardrails}

TITLE RULES — specific, searchable, NOT repetitive:
- BAD: generic "tips that rank you up", "costing you kills", "settings most players get wrong"
- BAD: repeating the same hook structure as recent uploads (see list above)
- GOOD: one concrete mechanic — "Stop wide-swinging A long on Dust2", "Bind edit like this"
- GOOD: surprise or specificity — numbers, map names, weapon names, one fix
Sound like one creator who plays {base.game}, not a template bot.

Return JSON only:
{{
  "title": "max 70 chars, curiosity hook first, game name, no clickbait lies",
  "description": "full YouTube description with timestamps section, CTA, hashtags at end",
  "tags": ["array", "of", "10-15", "short", "tags", "max", "25", "chars", "each", "no", "years"],
  "hook": "short hook phrase for thumbnail"
}}"""
    data = chat_json("You output valid JSON only.", prompt, temperature=0.7)
    if not data:
        return base

    title = str(data.get("title", base.title))[:100]
    if title_is_too_similar(title):
        retry = chat_json(
            "You output valid JSON only.",
            prompt + "\n\nREJECTED: title too similar to recent uploads. Try a completely different angle.",
            temperature=0.85,
        )
        if retry and retry.get("title"):
            title = str(retry["title"])[:100]

    return VideoMetadata(
        title=title,
        description=str(data.get("description", base.description)),
        tags=_safe_tags(data.get("tags", base.tags)),
        game=base.game,
        hook=str(data.get("hook", base.hook)),
        is_short=base.is_short,
        hashtags=base.hashtags,
        chapters_placeholder=base.chapters_placeholder,
    )


def build_metadata(video_path: Path, **kwargs) -> VideoMetadata:
    base = generate_metadata(video_path, **kwargs)
    enhanced = enhance_metadata(video_path, base, kwargs.get("duration_sec"))
    if active_provider() and enhanced.title != base.title:
        print(f"   SEO: AI ({active_provider()})")
    return enhanced