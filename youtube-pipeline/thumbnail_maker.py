"""High-CTR YouTube thumbnails — game imagery + bold hooks."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

import config

WIDTH, HEIGHT = 1280, 720

# YouTube CTR palette
YELLOW = (255, 230, 0)
RED = (255, 40, 40)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
CYAN = (0, 255, 220)


def _font(size: int):
    for path in (
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Impact.ttf",
        "C:\\Windows\\Fonts\\impact.ttf",
    ):
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def extract_frame(video_path: Path, out_path: Path, at_sec: float | None = None) -> bool:
    try:
        if at_sec is None:
            out = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", str(video_path),
                ],
                capture_output=True, text=True, timeout=20,
            )
            dur = float(out.stdout.strip()) if out.returncode == 0 else 10.0
            at_sec = max(1.0, dur * 0.35)
        subprocess.run(
            [
                "ffmpeg", "-y", "-ss", str(at_sec), "-i", str(video_path),
                "-vframes", "1", "-q:v", "2", str(out_path),
            ],
            check=True, capture_output=True, timeout=60,
        )
        return out_path.exists()
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError, subprocess.TimeoutExpired):
        return False


def _draw_stroke_text(draw, xy, text, font, fill, stroke=BLACK, sw=6):
    x, y = xy
    for dx in range(-sw, sw + 1, 2):
        for dy in range(-sw, sw + 1, 2):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=stroke)
    draw.text((x, y), text, font=font, fill=fill)


def _vignette(img: Image.Image, strength: float = 0.55) -> Image.Image:
    w, h = img.size
    vig = Image.new("L", (w, h), 0)
    vd = ImageDraw.Draw(vig)
    vd.ellipse([w * 0.05, h * 0.05, w * 0.95, h * 0.95], fill=int(255 * strength))
    dark = Image.new("RGB", (w, h), BLACK)
    return Image.composite(img, dark, vig)


def _paste_cover(canvas: Image.Image, img: Image.Image, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    tw, th = x1 - x0, y1 - y0
    img = img.copy()
    img.thumbnail((tw, th), Image.Resampling.LANCZOS)
    iw, ih = img.size
    canvas.paste(img, (x0 + (tw - iw) // 2, y0 + (th - ih) // 2))


def _draw_arrow(draw: ImageDraw.ImageDraw) -> None:
    draw.polygon([(920, 520), (1100, 400), (1080, 480), (1180, 480), (1180, 560), (1080, 560), (1100, 640)], fill=RED)
    draw.line([(920, 580), (1180, 420)], fill=WHITE, width=6)


def create_thumbnail(
    game: str,
    hook: str,
    topic: str,
    out_path: Path,
    video_path: Path | None = None,
    game_image: Path | None = None,
    style_name: str | None = None,
) -> Path:
    base = Image.new("RGB", (WIDTH, HEIGHT), (12, 8, 28))

    # Right panel: sharp frame from video
    if video_path and video_path.exists():
        frame_p = out_path.with_suffix(".frame.jpg")
        if extract_frame(video_path, frame_p):
            try:
                frame = Image.open(frame_p).convert("RGB")
                frame = ImageEnhance.Contrast(frame).enhance(1.25)
                frame = ImageEnhance.Color(frame).enhance(1.2)
                _paste_cover(base, frame, (520, 0, WIDTH, HEIGHT))
                frame_p.unlink(missing_ok=True)
            except OSError:
                pass

    # Left panel: actual game image
    if game_image and game_image.exists():
        try:
            gimg = Image.open(game_image).convert("RGB")
            gimg = ImageEnhance.Contrast(gimg).enhance(1.15)
            _paste_cover(base, gimg, (0, 0, 540, HEIGHT))
        except OSError:
            pass

    base = _vignette(base, 0.5)
    draw = ImageDraw.Draw(base)

    # Dark bar for text readability
    draw.rectangle([0, 0, 700, HEIGHT], fill=(0, 0, 0, 0))
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([0, 0, 680, HEIGHT], fill=(0, 0, 0, 140))
    od.rectangle([0, HEIGHT - 8, WIDTH, HEIGHT], fill=CYAN + (255,))
    base = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(base)

    # Brand badge
    draw.rounded_rectangle([28, 24, 220, 72], radius=12, fill=RED)
    _draw_stroke_text(draw, (42, 32), "PROGAMER", _font(32), WHITE, sw=3)

    # Game pill
    g = game.upper()[:18]
    draw.rounded_rectangle([28, 88, 28 + len(g) * 22 + 24, 140], radius=10, fill=(30, 30, 50))
    _draw_stroke_text(draw, (42, 96), g, _font(38), CYAN, sw=4)

    # Hook — 2-3 lines, yellow impact font
    words = hook.upper().replace("|", " ").split()
    lines: list[str] = []
    cur: list[str] = []
    n = 0
    for w in words:
        if n + len(w) > 10 and cur:
            lines.append(" ".join(cur))
            cur, n = [w], len(w)
        else:
            cur.append(w)
            n += len(w) + 1
    if cur:
        lines.append(" ".join(cur))
    lines = lines[:3] or ["WATCH THIS"]

    y = 200
    hf = _font(88)
    for line in lines:
        _draw_stroke_text(draw, (36, y), line, hf, YELLOW, sw=10)
        y += 92

    # Topic subline
    sub = topic[:36].upper()
    _draw_stroke_text(draw, (36, HEIGHT - 100), sub, _font(36), WHITE, sw=5)

    # Shorts badge
    if "short" in str(out_path).lower():
        draw.rounded_rectangle([WIDTH - 200, 24, WIDTH - 24, 80], radius=14, fill=RED)
        _draw_stroke_text(draw, (WIDTH - 178, 36), "#SHORTS", _font(34), WHITE, sw=3)

    _draw_arrow(draw)

    # Shock burst
    draw.ellipse([560, 120, 660, 220], outline=YELLOW, width=5)
    _draw_stroke_text(draw, (575, 148), "!", _font(72), RED, sw=4)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    base.save(out_path, "JPEG", quality=95, optimize=True)
    return out_path