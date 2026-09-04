"""Game-matched stock video — Pexels + Pixabay + Coverr."""

from __future__ import annotations

import subprocess
from pathlib import Path

import config
from video_creator.game_assets import build_scene_video_queries
from video_creator.video_providers import fetch_from_providers


def fetch_stock_for_scene(
    game: str,
    scene_index: int,
    work_dir: Path,
    is_short: bool,
    headline: str,
    narration: str = "",
    gameplay_mode: bool = True,
) -> tuple[Path | None, str, str]:
    """Returns (clip_path, matched_query, provider)."""
    if not config.USE_STOCK_FOOTAGE:
        return None, "", ""
    if not any([
        config.PEXELS_API_KEY,
        getattr(config, "PIXABAY_API_KEY", ""),
        getattr(config, "COVERR_API_KEY", ""),
    ]):
        return None, "", ""

    queries = build_scene_video_queries(game, headline, narration, gameplay_mode)
    path, query, provider = fetch_from_providers(queries, work_dir, scene_index, is_short)
    return path, query, provider


def trim_stock(src: Path, duration: float, out: Path, is_short: bool) -> Path | None:
    from video_creator.video_fit import encode_shorts_clip, fill_frame_filter, ffmpeg_video_args

    dur = max(duration, 1.5)
    try:
        if is_short:
            if encode_shorts_clip(src, out, duration=dur):
                return out
            return None
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(src),
                "-vf", fill_frame_filter(False),
                "-t", str(dur), "-an", *ffmpeg_video_args(),
                str(out),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        return out if out.exists() else None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None