#!/usr/bin/env python3
"""Upload rendered bundles that never made it to YouTube (OAuth failures, etc.)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import config
from youtube_upload import upload_from_bundle


def pending_bundles() -> list[Path]:
    out: list[Path] = []
    for path in sorted(config.PROCESSED_DIR.glob("*_upload.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("upload_result"):
            continue
        video = Path(data.get("video", ""))
        if video.is_file():
            out.append(path)
    return out


def main() -> None:
    bundles = pending_bundles()
    if not bundles:
        print("No pending uploads.")
        return
    print(f"Found {len(bundles)} pending upload(s):")
    for b in bundles:
        print(f"  • {b.name}")
    for bundle in bundles:
        print(f"\n📤 Uploading {bundle.name}...")
        try:
            result = upload_from_bundle(bundle, privacy="public")
            print(f"   ✅ {result['url']}")
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            sys.exit(1)
    print("\n✅ All pending uploads complete.")


if __name__ == "__main__":
    main()