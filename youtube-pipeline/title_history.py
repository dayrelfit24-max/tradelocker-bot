"""Recent upload titles — avoid repeating hooks the algorithm already ignored."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import config

# Phrases that dominated uploads and likely hurt CTR (Jun 2026 audit)
BANNED_PHRASES = (
    "costing you kills",
    "quietly killing your ranked",
    "ranked players quietly",
    "settings most players get wrong",
    "mistake is costing you",
    "holding you back in ranked",
)

OVERUSED_PATTERNS = (
    r"this \w+ mistake is costing",
    r"settings most .* get wrong",
    r"quietly (fixed|killing|changed)",
)


def recent_titles(days: int | None = None) -> list[str]:
    days = days or int(getattr(config, "TITLE_HISTORY_DAYS", 30))
    cutoff = datetime.now() - timedelta(days=days)
    titles: list[str] = []
    processed = getattr(config, "PROCESSED_DIR", Path("processed"))
    if not processed.is_dir():
        return titles
    for path in sorted(processed.glob("*_upload.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            ts = data.get("generated_at") or data.get("uploaded_at")
            if ts:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00")[:26])
                if dt.replace(tzinfo=None) < cutoff.replace(tzinfo=None):
                    continue
            title = (data.get("metadata") or {}).get("title", "")
            if title:
                titles.append(title)
        except (json.JSONDecodeError, ValueError, OSError):
            continue
    return titles[:40]


def title_is_too_similar(candidate: str, history: list[str] | None = None) -> bool:
    history = history or recent_titles()
    c = candidate.lower().strip()
    for banned in BANNED_PHRASES:
        if banned in c:
            return True
    for pattern in OVERUSED_PATTERNS:
        if re.search(pattern, c, re.I):
            return True
    for old in history:
        o = old.lower().strip()
        if c == o:
            return True
        # Same first 6 words = near-duplicate
        if " ".join(c.split()[:6]) == " ".join(o.split()[:6]):
            return True
    return False


def seo_guardrails(game: str, is_short: bool) -> str:
    """Extra rules injected into SEO/script prompts."""
    history = recent_titles(14)
    recent_block = "\n".join(f"- {t}" for t in history[:12]) if history else "(none)"
    g = game.lower()
    game_rules = ""
    if g == "gta":
        game_rules = (
            "GTA has NO ranked mode. NEVER say 'ranked' for GTA — use Online, PvP, gunfights, "
            "heists, freeroam fights, KD."
        )
    elif g == "cs2":
        game_rules = "CS2: use Premier, Matchmaking, aim, crosshair, peek, utility — be specific."
    elif g == "fortnite":
        from growth_test import FORTNITE_WINNING_TITLES, is_active

        winners = "\n".join(f"- {t}" for t in FORTNITE_WINNING_TITLES[:5])
        game_rules = (
            "Fortnite Short: COPY the structure of these winners (not exact words):\n"
            f"{winners}\n"
            "Use numbered tips (5 Fortnite Tips…), building/edit tricks, or one PC setting fix. "
            "NEVER 'costing you kills' or vague settings videos."
        )
        if is_active():
            game_rules += " GROWTH TEST: Fortnite Shorts only — max curiosity in first 40 chars."

    slot = "Short" if is_short else "Long"
    return f"""
{slot} for {game}. {game_rules}
Do NOT reuse these recent titles or their hook patterns:
{recent_block}
Banned phrases: {", ".join(BANNED_PHRASES)}
Write a NEW angle — different problem, different promise, different first 5 words.
"""