"""Rebuild deleted local videos from work dirs or bundle metadata, then upload."""

from __future__ import annotations

import json
import time
from pathlib import Path

import config
from video_creator.create import create_video
from video_creator.rerender import rerender_from_work
from youtube_upload import upload_from_bundle

FORMAT_MARKERS = ("bestgames", "industry", "upcoming", "news", "tips")


def _bundle_dates() -> list[str]:
    return ["20260611", "20260612", "20260613", "20260614"]


def _pending_bundles(dates: list[str] | None = None) -> list[Path]:
    dates = dates or _bundle_dates()
    out: list[Path] = []
    for bundle in sorted(config.PROCESSED_DIR.glob("*_upload.json")):
        if "upload_result" in bundle.read_text(encoding="utf-8"):
            continue
        if not any(d in bundle.name for d in dates):
            continue
        out.append(bundle)
    return out


def _format_from_stem(stem: str) -> str:
    for fmt in FORMAT_MARKERS:
        if f"_{fmt}_" in stem:
            return fmt
    raise ValueError(f"Cannot detect format in {stem}")


def _work_dir_for_stem(stem: str) -> Path:
    base = stem[:-6] if stem.endswith("_short") else stem
    return config.GENERATED_DIR / "work" / base


def rerender_bundle(bundle_path: Path) -> Path:
    data = json.loads(bundle_path.read_text(encoding="utf-8"))
    video_path = Path(data["video"])
    work_dir = _work_dir_for_stem(video_path.stem)
    if not (work_dir / "script.json").exists():
        raise FileNotFoundError(f"No work dir for {bundle_path.name}")
    return rerender_from_work(work_dir, video_path)


def recreate_bundle(bundle_path: Path) -> Path:
    data = json.loads(bundle_path.read_text(encoding="utf-8"))
    meta = data["metadata"]
    old_video = Path(data["video"])
    fmt = _format_from_stem(old_video.stem)
    duration = "short" if meta["is_short"] else "long"
    topic = meta.get("topic") or meta["hook"] or meta["title"]

    print(f"\n🔄 Recreating: {meta['title'][:60]}")
    result = create_video(
        game=meta["game"],
        format_name=fmt,
        duration=duration,
        topic=topic,
    )
    new_video = Path(result["video"])
    data["video"] = str(new_video.resolve())
    bundle_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return new_video


def rebuild_bundle(bundle_path: Path) -> Path:
    data = json.loads(bundle_path.read_text(encoding="utf-8"))
    video_path = Path(data["video"])
    work_dir = _work_dir_for_stem(video_path.stem)
    if (work_dir / "script.json").exists():
        return rerender_bundle(bundle_path)
    return recreate_bundle(bundle_path)


def rebuild_and_upload(
    dates: list[str] | None = None,
    public: bool = True,
    skip_upload: bool = False,
) -> list[dict]:
    bundles = _pending_bundles(dates)
    print(f"\n📦 Backlog: {len(bundles)} videos to rebuild")
    results: list[dict] = []
    delay = getattr(config, "UPLOAD_DELAY_SEC", 45)

    for i, bundle in enumerate(bundles, 1):
        print(f"\n{'=' * 60}")
        print(f"BACKLOG {i}/{len(bundles)} — {bundle.name}")
        print(f"{'=' * 60}")
        try:
            video = rebuild_bundle(bundle)
            if not skip_upload:
                upload_from_bundle(bundle, privacy="public" if public else None)
                print("   🚀 Uploaded to YouTube")
                if i < len(bundles):
                    print(f"   ⏳ Waiting {delay}s...")
                    time.sleep(delay)
            results.append({"bundle": str(bundle), "video": str(video), "ok": True})
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results.append({"bundle": str(bundle), "error": str(e), "ok": False})

    ok = sum(1 for r in results if r.get("ok"))
    print(f"\n✅ Backlog complete: {ok}/{len(bundles)} succeeded")
    return results


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Rebuild and upload deleted backlog videos")
    p.add_argument("--dates", nargs="*", default=_bundle_dates())
    p.add_argument("--public", action="store_true", default=True)
    p.add_argument("--no-upload", action="store_true")
    args = p.parse_args()
    rebuild_and_upload(dates=args.dates, public=args.public, skip_upload=args.no_upload)