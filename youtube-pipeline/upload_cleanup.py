"""Remove local video files after a successful YouTube upload."""

from __future__ import annotations

import shutil
from pathlib import Path

import config


def work_dir_for_video(video_path: Path) -> Path:
    stem = video_path.stem
    if stem.endswith("_short"):
        stem = stem[: -len("_short")]
    return config.GENERATED_DIR / "work" / stem


def cleanup_after_upload(data: dict) -> list[str]:
    """Delete rendered MP4, work folder, and thumbnail. Keep bundle JSON."""
    if not getattr(config, "AUTO_CLEANUP_AFTER_UPLOAD", False):
        return []

    removed: list[str] = []
    video_path = Path(data["video"])
    thumb_path = Path(data["thumbnail"]) if data.get("thumbnail") else None
    work_dir = work_dir_for_video(video_path)

    if video_path.exists():
        video_path.unlink()
        removed.append(str(video_path))

    if work_dir.is_dir():
        shutil.rmtree(work_dir, ignore_errors=True)
        removed.append(str(work_dir))

    if thumb_path and thumb_path.exists():
        thumb_path.unlink()
        removed.append(str(thumb_path))

    return removed