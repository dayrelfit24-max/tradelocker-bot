"""Text-to-speech — one locked channel profile, optional OpenAI for natural voice.

edge-tts is free but can sound synthetic; OpenAI tts-1-hd is much more human.
All outputs get light ffmpeg polish (compression + warmth).
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import config

DEFAULT_PROVIDER = "edge"
# Channel-locked narrator — every long video + Short uses this voice
LOCKED_CHANNEL_VOICE = "en-US-AndrewMultilingualNeural"
DEFAULT_VOICE_EDGE = LOCKED_CHANNEL_VOICE
DEFAULT_VOICE_OPENAI = "onyx"
DEFAULT_RATE = "+5%"
DEFAULT_PITCH = "+0Hz"
DEFAULT_VOLUME = "+0%"
DEFAULT_OPENAI_MODEL = "tts-1-hd"
DEFAULT_OPENAI_SPEED = 1.08

# Podcast-style warmth — tames harsh neural edges
_AUDIO_POLISH_FILTER = (
    "highpass=f=85,"
    "equalizer=f=3500:width_type=o:width=2:g=-2,"
    "acompressor=threshold=-24dB:ratio=2.2:attack=12:release=80:makeup=1.5,"
    "alimiter=limit=0.9"
)


@dataclass(frozen=True)
class TTSProfile:
    provider: str
    voice: str
    rate: str
    pitch: str
    volume: str
    openai_model: str
    openai_speed: float
    chunk_sentences: bool
    audio_polish: bool

    def label(self) -> str:
        if self.provider == "openai":
            return f"OpenAI {self.openai_model} / {self.voice} @ {self.openai_speed}x"
        return f"edge-tts {self.voice} @ {self.rate}, pitch {self.pitch}"

    def as_dict(self) -> dict[str, str | float | bool]:
        return {
            "provider": self.provider,
            "voice": self.voice,
            "rate": self.rate,
            "pitch": self.pitch,
            "volume": self.volume,
            "openai_model": self.openai_model,
            "openai_speed": self.openai_speed,
            "chunk_sentences": self.chunk_sentences,
            "audio_polish": self.audio_polish,
        }


_PROFILE: TTSProfile | None = None


def _resolve_provider() -> str:
    """Only use OpenAI TTS when explicitly requested — edge/Andrew stays default."""
    mode = getattr(config, "TTS_PROVIDER", "edge").lower().strip()
    has_openai = bool(getattr(config, "OPENAI_API_KEY", ""))
    if mode == "openai":
        return "openai" if has_openai else "edge"
    if mode == "auto":
        return "openai" if has_openai else "edge"
    return "edge"


def get_tts_profile() -> TTSProfile:
    global _PROFILE
    if _PROFILE is not None:
        return _PROFILE

    provider = _resolve_provider()
    if provider == "openai":
        voice = (getattr(config, "TTS_VOICE", "") or DEFAULT_VOICE_OPENAI).strip()
    else:
        # Always Andrew on edge — channel consistency across longs + Shorts
        voice = LOCKED_CHANNEL_VOICE

    _PROFILE = TTSProfile(
        provider=provider,
        voice=voice,
        rate=(getattr(config, "TTS_RATE", "") or DEFAULT_RATE).strip(),
        pitch=(getattr(config, "TTS_PITCH", "") or DEFAULT_PITCH).strip(),
        volume=(getattr(config, "TTS_VOLUME", "") or DEFAULT_VOLUME).strip(),
        openai_model=(
            getattr(config, "TTS_OPENAI_MODEL", "") or DEFAULT_OPENAI_MODEL
        ).strip(),
        openai_speed=float(getattr(config, "TTS_OPENAI_SPEED", DEFAULT_OPENAI_SPEED)),
        chunk_sentences=getattr(config, "TTS_CHUNK_SENTENCES", True),
        audio_polish=getattr(config, "TTS_AUDIO_POLISH", True),
    )
    return _PROFILE


_WORD_NUMBERS = {
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
}


def humanize_for_tts(text: str) -> str:
    """Shape narration for spoken delivery (casual + breath-friendly)."""
    t = text.strip()
    if not t:
        return t

    t = t.replace("\u2014", ". ").replace("—", ". ").replace("–", ", ")
    t = re.sub(r"\s+", " ", t)

    formal_to_casual = [
        (r"\bTip number (\w+)\b", _tip_number_repl),
        (r"\bHowever,\s*", "But "),
        (r"\bHowever\s+", "But "),
        (r"\bFurthermore,\s*", "Plus, "),
        (r"\bFurthermore\s+", "Plus, "),
        (r"\bIn addition,\s*", "Also, "),
        (r"\bIn addition\s+", "Also, "),
        (r"\bIt is important to note that\s+", "Real talk — "),
        (r"\bIt is important to note\s+", "Real talk — "),
        (r"\bhas confirmed that\b", "confirmed"),
        (r"\bhas announced that\b", "announced"),
        (r"\bartificial intelligence\b", "AI"),
        (r"\butilize\b", "use"),
        (r"\bapproximately\b", "about"),
        (r"\bSignificant\b", "Big"),
        (r"\bsignificant\b", "big"),
        (r"\bWelcome to\b", "Yo, welcome to"),
    ]
    for pattern, repl in formal_to_casual:
        if callable(repl):
            t = re.sub(pattern, repl, t, flags=re.IGNORECASE)
        else:
            t = re.sub(pattern, repl, t, flags=re.IGNORECASE)

    t = re.sub(r",\s*,", ",", t)
    t = re.sub(r"\s+,", ",", t)
    t = re.sub(r"\.\s*\.", ".", t)
    return t.strip()


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(p.split()) > 18:
            for chunk in re.split(r",\s+", p):
                chunk = chunk.strip()
                if chunk and not chunk.endswith((".", "!", "?")):
                    chunk += "."
                if chunk:
                    out.append(chunk)
        else:
            out.append(p)
    return out or [text]


def _tip_number_repl(match: re.Match[str]) -> str:
    word = match.group(1).lower()
    n = _WORD_NUMBERS.get(word, word)
    if n == "1":
        return "First up"
    if n == "2":
        return "Next up"
    return f"Tip {n}"


def polish_audio(path: Path) -> None:
    """Warm/compress neural TTS so it sits more like a real mic."""
    if not get_tts_profile().audio_polish:
        return
    tmp = path.with_suffix(".polished.mp3")
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(path),
                "-af", _AUDIO_POLISH_FILTER,
                "-c:a", "libmp3lame", "-q:a", "2",
                str(tmp),
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
        tmp.replace(path)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        tmp.unlink(missing_ok=True)


async def _synthesize_edge(text: str, out_path: Path, profile: TTSProfile) -> None:
    import edge_tts

    spoken = humanize_for_tts(text)
    sentences = _split_sentences(spoken) if profile.chunk_sentences else [spoken]

    if len(sentences) <= 1:
        communicate = edge_tts.Communicate(
            spoken,
            profile.voice,
            rate=profile.rate,
            pitch=profile.pitch,
            volume=profile.volume,
        )
        await communicate.save(str(out_path))
        polish_audio(out_path)
        return

    chunks: list[Path] = []
    try:
        for i, sentence in enumerate(sentences):
            chunk_path = out_path.parent / f"{out_path.stem}_c{i}.mp3"
            communicate = edge_tts.Communicate(
                sentence,
                profile.voice,
                rate=profile.rate,
                pitch=profile.pitch,
                volume=profile.volume,
            )
            await communicate.save(str(chunk_path))
            polish_audio(chunk_path)
            chunks.append(chunk_path)
        concat_audio(chunks, out_path)
    finally:
        for c in chunks:
            c.unlink(missing_ok=True)


def _synthesize_openai(text: str, out_path: Path, profile: TTSProfile) -> None:
    from openai import OpenAI

    spoken = humanize_for_tts(text)
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    with client.audio.speech.with_streaming_response.create(
        model=profile.openai_model,
        voice=profile.voice,
        input=spoken,
        speed=profile.openai_speed,
    ) as response:
        response.stream_to_file(out_path)
    polish_audio(out_path)


async def _synthesize(text: str, out_path: Path, profile: TTSProfile) -> None:
    if profile.provider == "openai":
        _synthesize_openai(text, out_path, profile)
    else:
        await _synthesize_edge(text, out_path, profile)


def synthesize_scene(text: str, out_path: Path, max_attempts: int = 4) -> float:
    """Generate MP3 for one scene using the locked channel TTS profile."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            asyncio.run(_synthesize(text, out_path, get_tts_profile()))
            return _audio_duration(out_path)
        except Exception as exc:
            last_err = exc
            out_path.unlink(missing_ok=True)
            if attempt >= max_attempts:
                break
            wait = min(2 ** attempt, 12)
            print(f"      ⚠️  TTS retry {attempt}/{max_attempts - 1} in {wait}s ({exc})")
            time.sleep(wait)
    raise last_err  # type: ignore[misc]


def _audio_duration(path: Path) -> float:
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if out.returncode == 0:
            return max(float(out.stdout.strip()), 1.0)
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired):
        pass
    return 3.0


def concat_audio(parts: list[Path], out_path: Path) -> Path:
    """Merge scene MP3s into one narration track."""
    list_file = out_path.with_suffix(".txt")
    lines = [f"file '{p.resolve()}'" for p in parts]
    list_file.write_text("\n".join(lines), encoding="utf-8")
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy", str(out_path),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    list_file.unlink(missing_ok=True)
    return out_path