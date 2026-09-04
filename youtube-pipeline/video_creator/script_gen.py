"""Generate faceless gaming video scripts (templates + optional OpenAI)."""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass

import config
from popular_games import GAME_DISPLAY, list_popular_games, resolve_game_key
from video_creator.formats import FORMATS, FormatSpec


@dataclass
class Scene:
    narration: str
    headline: str
    subline: str = ""
    footage_game: str = ""  # exact game for this scene's video clip


def _subscribe_outro_scene(game: str) -> Scene:
    ch = config.CHANNEL_NAME
    return Scene(
        narration=(
            f"If this helped, smash subscribe on {ch}. "
            f"Hit the bell so you do not miss the next {game} drop."
        ),
        headline="SUBSCRIBE",
        subline=f"More {game} on {ch}",
    )


def _ensure_subscribe_outro(scenes: list[Scene], game: str, n: int) -> list[Scene]:
    """Last scene is always SUBSCRIBE; keep intro + tips before it."""
    outro = _subscribe_outro_scene(game)
    body = [s for s in scenes if "subscribe" not in s.narration.lower()]
    if len(body) >= n:
        body = body[: n - 1]
    body.append(outro)
    return body[:n]


@dataclass
class VideoScript:
    game: str
    format: str
    title: str
    hook: str
    topic: str
    scenes: list[Scene]
    is_short: bool

    @property
    def full_narration(self) -> str:
        return " ".join(s.narration for s in self.scenes)


def _template_tips(game: str, n: int) -> list[Scene]:
    tips = [
        ("Drop hot and rotate early", "Land Smart", "Map control wins lobbies"),
        ("Audio tells you everything", "Use Sound", "Footsteps = free intel"),
        ("Edit/build before you peek", "Pre-aim Cover", "Never wide-swing blind"),
        ("Third-party the fight, don't start it", "Play Timing", "Clean up after damage"),
        ("One sensitivity — stop switching", "Lock Settings", "Muscle memory > hype"),
        ("Warm up 10 min before ranked", "Warm Up", "Aim routine = consistency"),
        ("Review deaths, not wins", "VOD Mindset", "Fix one mistake per game"),
    ]
    random.shuffle(tips)
    scenes = [
        Scene(
            narration=f"Yo, {config.CHANNEL_NAME} here. {n} {game} tips that actually help you rank up.",
            headline=f"{n} {game.upper()} TIPS",
            subline=config.CHANNEL_NAME,
        )
    ]
    for i, (tip, head, sub) in enumerate(tips[: n - 1], 1):
        opener = "First up" if i == 1 else ("Next up" if i == 2 else f"Tip {i}")
        scenes.append(
            Scene(
                narration=f"{opener} — {tip}.",
                headline=f"#{i} {head}",
                subline=sub,
            )
        )
    outro = Scene(
        narration=f"Smash subscribe on {config.CHANNEL_NAME} for daily {game} content. Which tip helped you most?",
        headline="SUBSCRIBE",
        subline="@ProGamer",
    )
    body = scenes[1:]
    if n <= 2:
        return [scenes[0], outro][:n]
    return [scenes[0]] + body[: n - 2] + [outro]


def _template_top5(game: str, n: int) -> list[Scene]:
    items = [
        "Movement mechanics",
        "Loadout / agent pick",
        "Map knowledge",
        "Economy / resource control",
        "Team comms",
        "Clutch discipline",
        "Update meta awareness",
    ]
    random.shuffle(items)
    scenes = [
        Scene(
            narration=f"Top {n - 2} reasons players dominate {game} right now on {config.CHANNEL_NAME}.",
            headline=f"TOP {game.upper()}",
            subline="COUNTDOWN",
        )
    ]
    ranked = items[: n - 2]
    for i, item in enumerate(reversed(ranked), 1):
        rank = len(ranked) - i + 1
        scenes.append(
            Scene(
                narration=f"Number {rank}. {item}. This separates average from cracked.",
                headline=f"#{rank}",
                subline=item[:40],
            )
        )
    scenes.append(
        Scene(
            narration="Hit subscribe — we cover every trending game so you never fall behind meta.",
            headline="FOLLOW",
            subline="ProGamer",
        )
    )
    return scenes[:n]


def _template_news(game: str, n: int) -> list[Scene]:
    scenes = [
        Scene(
            narration=f"{game} update you need to know before your next session.",
            headline=f"{game.upper()} NEWS",
            subline="2026 META",
        ),
        Scene(
            narration="Balance changes are shifting the ranked ladder — adapt your main picks now.",
            headline="META SHIFT",
            subline="Ranked impact",
        ),
        Scene(
            narration="New content drops mean fresh strats — early players get free elo.",
            headline="NEW CONTENT",
            subline="First-mover advantage",
        ),
        Scene(
            narration="Community is split — test in unranked before committing your main.",
            headline="COMMUNITY",
            subline="Test before ranked",
        ),
        Scene(
            narration=f"{config.CHANNEL_NAME} tracks every patch. Subscribe for same-day breakdowns.",
            headline="SUBSCRIBE",
            subline=config.CHANNEL_NAME,
        ),
    ]
    return scenes[:n]


def _template_facts(game: str, n: int) -> list[Scene]:
    facts = [
        ("The average pro reaction time is under 200ms", "PRO STATS"),
        ("Most players lose from positioning, not aim", "POSITION > AIM"),
        ("Peak hours have harder lobbies — queue smart", "QUEUE TIMING"),
        ("One-trick mains climb faster until high rank", "ONE-TRICK"),
        ("Patch day is the best day to grind", "PATCH DAY"),
    ]
    random.shuffle(facts)
    scenes = [
        Scene(
            narration=f"{n - 1} wild {game} facts most players never heard.",
            headline=f"{game.upper()} FACTS",
            subline="Mind blown",
        )
    ]
    for i, (fact, head) in enumerate(facts[: n - 1], 1):
        scenes.append(Scene(narration=fact + ".", headline=head, subline=f"Fact #{i}"))
    scenes.append(
        Scene(
            narration="Like if one fact surprised you. Subscribe for more.",
            headline="MORE?",
            subline="ProGamer",
        )
    )
    return scenes[:n]


def _template_versus(game: str, n: int) -> list[Scene]:
    scenes = [
        Scene(
            narration=f"Hot take for {game} players — which playstyle wins in 2026?",
            headline="VS DEBATE",
            subline=game,
        ),
        Scene(narration="Aggressive pushers get clips but die to third parties.", headline="AGGRESSIVE", subline="High risk"),
        Scene(narration="Passive players survive but cap their rank ceiling.", headline="PASSIVE", subline="Safe but slow"),
        Scene(narration="The answer is situational — pivot mid-match.", headline="HYBRID", subline="Best rank"),
        Scene(
            narration=f"Comment your rank on {config.CHANNEL_NAME}. We post daily for every trending game.",
            headline="YOUR RANK?",
            subline="Comment below",
        ),
    ]
    return scenes[:n]


_TEMPLATES = {
    "tips": _template_tips,
    "top5": _template_top5,
    "news": _template_news,
    "facts": _template_facts,
    "versus": _template_versus,
}


def _structure_hint(fmt_name: str, n: int) -> str:
    body = n - 2
    hints = {
        "tips": (
            f"Structure: scene 1 = intro hook, scenes 2–{n - 1} = exactly {body} actionable "
            f"gameplay tips (narration: First up / Next up / Tip 3…), scene {n} = SUBSCRIBE only."
        ),
        "top5": (
            f"Structure: intro + {body}-item ranked countdown (#{body} down to #1) + SUBSCRIBE. "
            "Headlines use #5, #4… NEVER the word tip."
        ),
        "bestgames": (
            f"Structure: intro + ranked list of {body} specific real games (one game per scene) + SUBSCRIBE. "
            "Headlines name the game or rank (#5, #4…). NEVER the word tip."
        ),
        "upcoming": (
            f"Structure: intro + {body} story beats (announcement, features, release timing, hype) + SUBSCRIBE. "
            "News/documentary tone. NEVER tip, tip number, or how-to advice framing."
        ),
        "industry": (
            f"Structure: intro + {body} news beats (what happened, who, gamer impact, takeaway) + SUBSCRIBE. "
            "Journalism breakdown. NEVER tip or numbered tips."
        ),
        "news": (
            f"Structure: intro + {body} quick news hits (headline, context, why it matters) + SUBSCRIBE. "
            "Punchy news delivery. NEVER tip or tip number."
        ),
        "facts": (
            f"Structure: intro + {body} wild facts (one per scene) + SUBSCRIBE. Say fact, not tip."
        ),
        "versus": (
            f"Structure: intro + compare sides/approaches + verdict + CTA. NEVER tip."
        ),
        "gameplay": (
            f"Structure: intro + {body} trailer/feature highlights + SUBSCRIBE. NEVER tip."
        ),
    }
    return hints.get(
        fmt_name,
        f"Structure: intro + {body} content scenes + SUBSCRIBE. Do NOT use tip numbering unless teaching gameplay.",
    )


def _sanitize_script_for_format(script: VideoScript) -> VideoScript:
    """Strip accidental tip framing from non-tips formats (AI drift)."""
    if script.format == "tips":
        return script

    tip_headline = re.compile(r"^TIP\s*#?\s*\d+\s*[:\-]?\s*", re.I)
    tip_narration_open = re.compile(
        r"^(?:first up|next up|tip\s*#?\s*\d+|tip\s+number\s+\w+)\s*[,\-—:]\s*",
        re.I,
    )
    tip_inline = re.compile(r"\btip\s*#?\s*\d+\b", re.I)

    for scene in script.scenes:
        cleaned = tip_headline.sub("", scene.headline).strip()
        if cleaned:
            scene.headline = cleaned
        scene.narration = tip_narration_open.sub("", scene.narration).strip()
        scene.narration = tip_inline.sub("", scene.narration).strip()
        scene.narration = re.sub(r"\s+", " ", scene.narration).strip()
        if scene.subline:
            scene.subline = tip_inline.sub("", scene.subline).strip()

    return script


def _ai_script(
    game: str,
    fmt: FormatSpec,
    n: int,
    is_short: bool,
    topic: str | None = None,
    trend_context: str | None = None,
    platform: str | None = None,
) -> VideoScript | None:
    from llm_client import active_provider, chat_json

    if not active_provider():
        return None

    from title_history import seo_guardrails

    topic_line = f"\nTopic / headline to cover: {topic}" if topic else ""
    trend_line = f"\nTrending context (use for accuracy, paraphrase): {trend_context}" if trend_context else ""
    platform_line = f"\nTarget platform: {platform}" if platform else ""
    guardrails = seo_guardrails(game, is_short)

    format_hints = {
        "gameplay": "Style: trailer breakdown / feature overview. Discuss modes, updates, and official reveals.",
        "bestgames": f"Style: ranked list of best games on {platform or 'PC/PS5/Xbox'}. "
        "Each ranked scene MUST name one specific real game in headline + narration (for gameplay footage).",
        "upcoming": "Style: upcoming releases, dates if known, hype and why viewers should care.",
        "industry": "Style: gaming industry news breakdown — acquisitions, releases, trends.",
        "news": "Style: quick gaming news hit — what happened and why it matters.",
        "tips": "Style: actionable pro tips for better gameplay. Talk to the viewer like a gamer friend.",
    }
    hint = format_hints.get(fmt.name, "")
    structure = _structure_hint(fmt.name, n)
    tip_rule = (
        "Use tip numbering in narration (First up, Next up) and tip-style headlines."
        if fmt.name == "tips"
        else "CRITICAL: This is NOT a tips video. NEVER say tip, tip number, tip 1, or how-to advice framing."
    )

    prompt = f"""Write a YouTube script for channel {config.CHANNEL_NAME} ({config.CHANNEL_URL}).
Format: {fmt.label} ({fmt.name})
Game focus: {game}
Scenes: exactly {n}
{hint}{topic_line}{trend_line}{platform_line}
{guardrails}
Style: energetic gaming YouTube channel. Factual, no false claims, no invented scandal.
Voice: casual gamer narrator (AI voiceover) — talk TO the viewer ("you", "your rank"). Write how people TALK in Shorts: 2-4 short sentences per scene, each sentence under 14 words. Use contractions and slang (meta, cracked, clutch). Natural openers ok ("Look,", "Real talk,") but not every line.
NEVER long run-on sentences or essay paragraphs — TTS will sound robotic.
NEVER fake first-person gameplay ("I clutched", "we won my match", "my loadout").
NEVER press-release tone ("furthermore", "it is important to note", "has confirmed that").
Visuals use official trailers — write for the format ({fmt.name}), not pretend you are in a live match.
{"Vertical Short: keep each scene narration concise (3-8 seconds spoken) so total stays under 60 seconds." if is_short else "Long-form 4-8 min when spoken — deeper detail per scene"}
{structure}
{tip_rule}
TITLE & HOOK RULES: Write titles like a creator, not a template.
- BAD: "costing you kills", "settings most players get wrong", "ranked players quietly" (overused on this channel)
- BAD: "Game Update Changes EVERYTHING" / generic tips promises
- GOOD: one specific fix — map angle, weapon, bind, peek habit, patch detail
Narration: opinionated gamer voice with personality ("most players miss this", "here's the fix") — not press-release tone.
REQUIRED final scene: subscribe CTA for {config.CHANNEL_NAME} ({config.CHANNEL_URL}), headline SUBSCRIBE.
Every scene needs short headline text (2-5 words) shown on screen — match the format (news headline, game name, #rank, etc.).
REQUIRED footage_game on EVERY scene: exact game title for that scene's gameplay video (e.g. "Halo Infinite", "Elden Ring", "Fortnite").
- List/ranked scenes: footage_game = the specific game discussed in that scene.
- Intro scene: footage_game = the first game you discuss in scene 2.
- SUBSCRIBE scene: footage_game = the main game from the video (or last ranked game).

Return JSON only:
{{
  "title": "YouTube title max 70 chars, SEO strong",
  "hook": "3-5 word thumbnail hook",
  "topic": "short topic slug",
  "scenes": [
    {{"narration": "spoken line", "headline": "ON SCREEN BIG TEXT", "subline": "smaller text", "footage_game": "Exact Game Name"}}
  ]
}}"""
    data = chat_json("You output valid JSON only.", prompt, temperature=0.8)
    if not data or "scenes" not in data:
        return None

    scenes = _ensure_subscribe_outro(
        [
            Scene(
                narration=s["narration"],
                headline=s["headline"],
                subline=s.get("subline", ""),
                footage_game=s.get("footage_game", ""),
            )
            for s in data["scenes"]
        ],
        game,
        n,
    )
    script = VideoScript(
        game=game,
        format=fmt.name,
        title=data["title"],
        hook=data["hook"],
        topic=data.get("topic", fmt.label),
        scenes=scenes,
        is_short=is_short,
    )
    return _sanitize_script_for_format(script)


def generate_script(
    game: str | None = None,
    format_name: str = "tips",
    duration: str = "short",
    topic: str | None = None,
    trend_context: str | None = None,
    platform: str | None = None,
) -> VideoScript:
    fmt = FORMATS.get(format_name, FORMATS["tips"])
    is_short = duration.lower() in ("short", "shorts", "60", "60s")
    n = fmt.scene_count_short if is_short else fmt.scene_count_long

    if game:
        key = resolve_game_key(game)
        game_display = GAME_DISPLAY.get(key, game)
    else:
        picks = [g for g in list_popular_games() if g != "Gaming"]
        game_display = random.choice(picks)

    ai = _ai_script(
        game_display, fmt, n, is_short,
        topic=topic or trend_context,
        trend_context=trend_context,
        platform=platform,
    )
    if ai:
        from llm_client import active_provider
        print(f"   Script: AI ({active_provider()}) — {fmt.name}")
        if topic:
            ai.topic = topic[:80]
        return ai

    builder = _TEMPLATES.get(fmt.name) or _TEMPLATES["news"]
    scenes = _ensure_subscribe_outro(builder(game_display, n), game_display, n)
    hook = "YOU NEED THIS" if fmt.name == "tips" else "WATCH THIS"
    title = f"{hook} — {game_display} {fmt.label} | {config.CHANNEL_NAME}"
    if is_short:
        title = f"{game_display} {fmt.label} #shorts"

    return VideoScript(
        game=game_display,
        format=fmt.name,
        title=title[:100],
        hook=hook,
        topic=fmt.label,
        scenes=scenes,
        is_short=is_short,
    )