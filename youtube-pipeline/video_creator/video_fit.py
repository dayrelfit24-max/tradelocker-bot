"""FFmpeg framing — Shorts fit (no zoom) or fill (crop), long 16:9."""

from __future__ import annotations

import subprocess
from pathlib import Path

import config

SIZE_SHORT = (1080, 1920)
_LONG_STRIP = "crop=iw:ih*0.86:0:ih*0.07"


def long_frame_size() -> tuple[int, int]:
    """Long-form output dimensions (default 2560×1440). Shorts unchanged."""
    h = getattr(config, "VIDEO_LONG_HEIGHT", 1080)
    h = max(1080, min(h, 2160))
    w = int(round(h * 16 / 9))
    if w % 2:
        w += 1
    return w, h


def long_scale() -> float:
    """Scale factor vs legacy 1080p long overlays."""
    return long_frame_size()[1] / 1080


def shorts_aspect_mode() -> str:
    """fit = full trailer in frame + blurred fill (default). fill = center-crop zoom."""
    return getattr(config, "SHORTS_ASPECT_MODE", "fit").lower()


def frame_size(is_short: bool) -> tuple[int, int]:
    return SIZE_SHORT if is_short else long_frame_size()


def shorts_crop_fill_vf() -> str:
    """Legacy: crop zoom to fill 9:16 (can feel too tight)."""
    w, h = SIZE_SHORT
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h}:(iw-{w})/2:(ih-{h})/2,"
        f"setsar=1,setdar=9/16"
    )


def shorts_fit_filter_complex() -> str:
    """Show full 16:9 trailer inside 9:16 — sharp center, blurred background."""
    w, h = SIZE_SHORT
    return (
        "[0:v]split=2[main][bgsrc];"
        f"[bgsrc]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=35:18[bg];"
        f"[main]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,setdar=9/16"
    )


def shorts_fill_filter() -> str:
    return shorts_crop_fill_vf()


def fill_frame_filter(is_short: bool) -> str:
    if is_short and shorts_aspect_mode() == "fit":
        return shorts_fit_filter_complex()
    if is_short:
        return shorts_crop_fill_vf()
    return long_fill_filter()


def long_fill_filter() -> str:
    w, h = long_frame_size()
    return (
        f"{_LONG_STRIP},"
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h}:(iw-{w})/2:(ih-{h})/2,"
        f"setsar=1,setdar=16/9"
    )


def ffmpeg_video_args(is_short: bool | None = None) -> list[str]:
    high = getattr(config, "VIDEO_ENCODE_QUALITY", "normal").lower() == "high"
    preset = "slow" if high else "medium"
    crf = "18" if high else "20"
    # Slightly tighter quality for 1440p/4K long renders
    if is_short is False and long_frame_size()[1] > 1080:
        crf = "17" if high else "19"
    return ["-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p", "-r", "30"]


def encode_shorts_clip(
    input_path: Path,
    output_path: Path,
    duration: float | None = None,
    seek: float | None = None,
) -> bool:
    """Encode one Shorts scene with correct aspect (fit or fill)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    inp = ["-ss", str(seek)] if seek is not None else []
    dur = ["-t", str(duration)] if duration is not None else []
    mode = shorts_aspect_mode()

    try:
        if mode == "fit":
            fc = shorts_fit_filter_complex()
            subprocess.run(
                [
                    "ffmpeg", "-y", *inp, "-i", str(input_path), *dur,
                    "-filter_complex", fc,
                    "-an", *ffmpeg_video_args(),
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                timeout=180,
            )
        else:
            vf = shorts_crop_fill_vf()
            subprocess.run(
                [
                    "ffmpeg", "-y", *inp, "-i", str(input_path), *dur,
                    "-vf", vf,
                    "-an", *ffmpeg_video_args(),
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                timeout=180,
            )
        return output_path.exists() and output_path.stat().st_size > 5000
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def probe_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0:s=x", str(path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if out.returncode == 0 and "x" in out.stdout.strip():
            w, h = out.stdout.strip().split("x")
            return int(w), int(h)
    except (ValueError, subprocess.TimeoutExpired):
        pass
    return None


def is_exact_short_frame(path: Path) -> bool:
    return probe_dimensions(path) == SIZE_SHORT


def finalize_short_mp4(path: Path) -> None:
    """Skip re-encode when already 1080x1920."""
    if is_exact_short_frame(path):
        return
    p = Path(path)
    tmp = p.with_suffix(".tmp.mp4")
    mode = shorts_aspect_mode()
    cmd = ["ffmpeg", "-y", "-i", str(p), "-an", *ffmpeg_video_args(), "-movflags", "+faststart", str(tmp)]
    if mode == "fit":
        cmd[4:4] = ["-filter_complex", shorts_fit_filter_complex()]
    else:
        cmd[4:4] = ["-vf", shorts_crop_fill_vf()]
    subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    tmp.replace(p)