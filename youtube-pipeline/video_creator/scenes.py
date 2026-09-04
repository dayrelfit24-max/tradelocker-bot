"""Generate visual scene slides (no gameplay footage required)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import config
from video_creator.script_gen import Scene
from video_creator.video_fit import frame_size, long_scale

SIZE_SHORT = (1080, 1920)

PALETTES = [
    {"bg": (14, 10, 36), "a": (0, 255, 200), "b": (255, 50, 140), "text": (255, 255, 255)},
    {"bg": (24, 6, 6), "a": (255, 140, 0), "b": (255, 30, 0), "text": (255, 245, 230)},
    {"bg": (6, 18, 40), "a": (90, 200, 255), "b": (200, 240, 255), "text": (245, 250, 255)},
    {"bg": (10, 10, 14), "a": (255, 255, 255), "b": (160, 160, 170), "text": (255, 255, 255)},
]


def _font(size: int, bold: bool = True):
    paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
    ]
    for p in paths:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap(text: str, max_chars: int) -> list[str]:
    words = text.upper().split()
    lines: list[str] = []
    cur: list[str] = []
    n = 0
    for w in words:
        if n + len(w) + 1 > max_chars and cur:
            lines.append(" ".join(cur))
            cur, n = [w], len(w)
        else:
            cur.append(w)
            n += len(w) + 1
    if cur:
        lines.append(" ".join(cur))
    return lines[:3]


def render_scene(
    scene: Scene,
    game: str,
    index: int,
    out_path: Path,
    is_short: bool,
    palette_idx: int = 0,
) -> Path:
    size = frame_size(is_short)
    pal = PALETTES[palette_idx % len(PALETTES)]
    img = Image.new("RGB", size, pal["bg"])
    draw = ImageDraw.Draw(img)

    w, h = size
    ls = 1.0 if is_short else long_scale()
    draw.rectangle([0, h - int(120 * ls), w, h], fill=(0, 0, 0))
    draw.text((40, h - int(90 * ls)), config.CHANNEL_NAME.upper(), font=_font(int(28 * ls)), fill=pal["a"])

    brand_font = _font(int(36 * ls))
    draw.text((40, 40), "PROGAMER", font=brand_font, fill=pal["b"])
    game_font = _font(int(48 * ls))
    draw.text((40, int(90 * ls)), game.upper()[:24], font=game_font, fill=pal["a"])

    lines = _wrap(scene.headline, 14 if is_short else 18)
    y = (h // 2) - (len(lines) * int(70 * ls))
    hf = _font(int(96 * ls) if is_short else int(110 * ls))
    for line in lines:
        draw.text((40, y), line, font=hf, fill=pal["text"])
        y += int(100 * ls) if is_short else int(115 * ls)

    if scene.subline:
        draw.text((40, y + int(12 * ls)), scene.subline[:50], font=_font(int(36 * ls)), fill=pal["b"])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


def render_overlay(
    scene: Scene,
    game: str,
    index: int,
    out_path: Path,
    is_short: bool,
    palette_idx: int = 0,
) -> Path:
    size = frame_size(is_short)
    w, h = size
    ls = 1.0 if is_short else long_scale()
    pal = PALETTES[palette_idx % len(PALETTES)]
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    subscribe = scene.headline.upper() in ("SUBSCRIBE", "FOLLOW", "FOLLOW FOR MORE")
    if is_short:
        bar_h = int(h * 0.24) if subscribe else int(h * 0.30)
    else:
        bar_h = int(h * 0.38)
    for row in range(bar_h):
        alpha = int(220 * (row / bar_h))
        draw.line([(0, h - bar_h + row), (w, h - bar_h + row)], fill=(0, 0, 0, alpha))

    draw.rectangle([0, h - int(100 * ls), w, h], fill=(0, 0, 0, 240))
    draw.text((36, h - int(82 * ls)), config.CHANNEL_NAME.upper(), font=_font(int(26 * ls)), fill=(*pal["a"], 255))

    draw.text((36, 36), "PROGAMER", font=_font(int(32 * ls)), fill=(*pal["b"], 255))
    draw.text((36, int(78 * ls)), game.upper()[:22], font=_font(int(40 * ls)), fill=(*pal["a"], 255))

    lines = _wrap(scene.headline, 12 if is_short else 16)
    y = h - bar_h + int(40 * ls)
    hf = _font(int(72 * ls) if is_short else int(88 * ls))
    for line in lines:
        draw.text((40, y), line, font=hf, fill=(*pal["text"], 255))
        y += int(78 * ls) if is_short else int(92 * ls)

    if scene.subline:
        draw.text((40, y + int(8 * ls)), scene.subline[:48], font=_font(int(34 * ls)), fill=(*pal["b"], 255))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


def render_shorts_overlay(
    scene: Scene,
    game: str,
    out_path: Path,
    palette_idx: int = 0,
    badge_label: str | None = None,
    *,
    tip_number: int | None = None,
) -> Path:
    """On-screen text for Shorts over gameplay/cinematic clips."""
    w, h = SIZE_SHORT
    pal = PALETTES[palette_idx % len(PALETTES)]
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    subscribe = scene.headline.upper() == "SUBSCRIBE"

    if subscribe:
        for row in range(int(h * 0.35)):
            alpha = int(180 * (row / (h * 0.35)))
            draw.line([(0, h - int(h * 0.35) + row), (w, h - int(h * 0.35) + row)], fill=(0, 0, 0, alpha))
        draw.text((w // 2 - 280, h // 2 - 120), "SUBSCRIBE", font=_font(110), fill=(255, 230, 0, 255))
        draw.text((w // 2 - 320, h // 2 + 20), config.CHANNEL_NAME.upper(), font=_font(56), fill=(*pal["a"], 255))
        draw.text((w // 2 - 240, h // 2 + 90), "MORE VIDEOS DAILY", font=_font(40), fill=(*pal["text"], 255))
        draw.text((36, 36), "PROGAMER", font=_font(28), fill=(*pal["b"], 200))
    else:
        bar_h = int(h * 0.22)
        for row in range(bar_h):
            alpha = int(210 * (row / bar_h))
            draw.line([(0, h - bar_h + row), (w, h - bar_h + row)], fill=(0, 0, 0, alpha))
        draw.text((36, 28), "PROGAMER", font=_font(30), fill=(*pal["b"], 255))
        label = badge_label
        if label is None and tip_number is not None and tip_number > 0:
            label = f"TIP #{tip_number}"
        if label:
            draw.text((36, 68), label.upper()[:16], font=_font(44), fill=(*pal["a"], 255))
        headline = scene.headline.upper()[:32]
        draw.text((36, h - bar_h + 20), headline, font=_font(64), fill=(*pal["text"], 255))
        if scene.subline:
            draw.text((36, h - 72), scene.subline[:45], font=_font(32), fill=(*pal["a"], 240))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


# Backwards compat alias
render_shorts_caption = render_shorts_overlay