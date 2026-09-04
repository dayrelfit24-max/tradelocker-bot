"""Upload videos to YouTube with metadata and custom thumbnail."""

from __future__ import annotations

import json
import mimetypes
import re
from pathlib import Path

from googleapiclient.http import MediaFileUpload

from seo_generator import VideoMetadata
from youtube_auth import get_youtube_service

import config
from upload_cleanup import cleanup_after_upload


def _video_duration(path: Path) -> float | None:
    try:
        import subprocess
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
            return float(out.stdout.strip())
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired):
        pass
    return None


def sanitize_youtube_tags(tags: list[str]) -> list[str]:
    """YouTube: each tag ≤30 chars, total ≤500 chars, letters/numbers/spaces/hyphens."""
    out: list[str] = []
    total = 0
    for raw in tags:
        t = re.sub(r"[^\w\s-]", "", str(raw).strip().lower())
        t = re.sub(r"\s+", " ", t).strip()[:25]
        if len(t) < 2 or t in out:
            continue
        if not re.match(r"^[a-z0-9][\w\s-]*[a-z0-9]$", t) and not re.match(r"^[a-z0-9]{2,}$", t):
            continue
        if "aaa" in t or t.startswith("vs "):
            continue
        if re.search(r"\b20\d{2}\b", t):
            continue
        blocked = ("eshop", "tier list", "must-play", "must play", "how to get better")
        if any(b in t for b in blocked):
            continue
        add = len(t) + (1 if out else 0)
        if total + add > 450:
            break
        out.append(t)
        total += add
        if len(out) >= 15:
            break
    return out


def upload_from_bundle(bundle_path: Path, privacy: str | None = None) -> dict:
    data = json.loads(bundle_path.read_text(encoding="utf-8"))
    video_path = Path(data["video"])
    thumb_path = Path(data["thumbnail"]) if data.get("thumbnail") else None
    meta = data["metadata"]
    yt_cfg = data.get("youtube", {})
    privacy_status = privacy or yt_cfg.get("privacy", config.DEFAULT_PRIVACY)

    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    metadata = VideoMetadata(
        title=meta["title"],
        description=meta["description"],
        tags=meta["tags"],
        game=meta["game"],
        hook=meta["hook"],
        is_short=meta["is_short"],
        hashtags=meta.get("hashtags", ""),
        chapters_placeholder=meta.get("chapters_placeholder", ""),
    )

    youtube = get_youtube_service()
    body = {
        "snippet": {
            "title": metadata.title,
            "description": metadata.description,
            "tags": sanitize_youtube_tags(metadata.tags),
            "categoryId": yt_cfg.get("category_id", config.YOUTUBE_CATEGORY_ID),
            "defaultLanguage": yt_cfg.get("language", config.DEFAULT_LANGUAGE),
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    mime, _ = mimetypes.guess_type(str(video_path))
    media = MediaFileUpload(
        str(video_path),
        mimetype=mime or "video/*",
        chunksize=1024 * 1024 * 8,
        resumable=True,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"Upload {pct}%")

    video_id = response["id"]
    print(f"✅ Uploaded: https://youtu.be/{video_id}")

    if thumb_path and thumb_path.exists():
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(thumb_path), mimetype="image/jpeg"),
        ).execute()
        print("✅ Custom thumbnail set")

    playlist_id = yt_cfg.get("playlist_id") or config.DEFAULT_PLAYLIST_ID
    if playlist_id:
        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        ).execute()
        print(f"✅ Added to playlist {playlist_id}")

    result = {"video_id": video_id, "url": f"https://youtu.be/{video_id}"}
    final_data = {**data, "upload_result": result}
    bundle_path.write_text(
        json.dumps(final_data, indent=2),
        encoding="utf-8",
    )

    cleaned = cleanup_after_upload(final_data)
    if cleaned:
        print(f"🧹 Cleaned up {len(cleaned)} local file(s) after upload")

    return result