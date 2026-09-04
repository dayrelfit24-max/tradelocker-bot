#!/usr/bin/env python3
"""
ProGamer YouTube Pipeline — AI video creation + SEO + upload

Usage:
  python pipeline.py create --game Fortnite --format tips --duration short
  python pipeline.py batch --count 5 --auto
  python pipeline.py process path/to/video.mp4
  python pipeline.py upload processed/bundle_upload.json --public
  python pipeline.py auth
  python pipeline.py stats
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import config
from ai_seo import build_metadata
from growth import print_growth_report
from popular_games import list_popular_games
from seo_generator import save_metadata_bundle
from thumbnail_maker import create_thumbnail
from youtube_auth import run_auth_cli
from video_creator.create import create_video, list_formats
from youtube_upload import _video_duration, upload_from_bundle


def process_video(
    video_path: Path,
    game: str | None = None,
    hook: str | None = None,
    topic: str | None = None,
    title: str | None = None,
    game_reference: Path | None = None,
    auto_upload: bool = False,
    privacy: str | None = None,
) -> Path:
    video_path = Path(video_path).resolve()
    if not video_path.exists():
        raise FileNotFoundError(video_path)

    duration = _video_duration(video_path)
    metadata = build_metadata(
        video_path,
        game=game,
        hook=hook,
        topic=topic,
        duration_sec=duration,
        custom_title=title,
    )

    thumb_path = config.THUMBNAILS_DIR / f"{video_path.stem}_thumb.jpg"
    game_ref = game_reference
    if not game_ref or not game_ref.exists():
        stem = video_path.stem.replace("_short", "")
        candidate = config.GENERATED_DIR / "work" / stem / "game_reference.jpg"
        if candidate.exists():
            game_ref = candidate
    create_thumbnail(
        metadata.game,
        metadata.hook,
        topic or video_path.stem.replace("_", " "),
        thumb_path,
        video_path=video_path,
        game_image=game_ref,
    )

    bundle_path = save_metadata_bundle(
        video_path, metadata, thumb_path, config.PROCESSED_DIR
    )

    print("\n✅ Ready for upload")
    print(f"   Title: {metadata.title}")
    print(f"   Game:  {metadata.game}")
    print(f"   Tags:  {len(metadata.tags)} tags")
    print(f"   Thumb: {thumb_path}")
    print(f"   Bundle: {bundle_path}")

    if config.REQUIRE_REVIEW and not auto_upload:
        print("\n📋 Review bundle JSON, edit title/description if needed, then:")
        print(f"   python pipeline.py upload {bundle_path}")
        return bundle_path

    if auto_upload:
        upload_from_bundle(bundle_path, privacy=privacy)
        dest = config.PROCESSED_DIR / video_path.name
        if video_path.parent == config.INCOMING_DIR:
            shutil.move(str(video_path), str(dest))

    return bundle_path


class IncomingHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm"}:
            return
        time.sleep(2)
        if not path.exists() or path.stat().st_size < 1000:
            return
        print(f"\n🎬 New video detected: {path.name}")
        try:
            process_video(path, auto_upload=False)
        except Exception as e:
            print(f"❌ Error processing {path.name}: {e}")


def watch_folder() -> None:
    config.INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    print(f"👀 Watching {config.INCOMING_DIR} — drop videos here (Ctrl+C to stop)")
    handler = IncomingHandler()
    observer = Observer()
    observer.schedule(handler, str(config.INCOMING_DIR), recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube Gaming Upload Pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("auth", help="Authorize YouTube OAuth")
    sub.add_parser("stats", help="Channel stats & monetization progress")
    sub.add_parser("watch", help="Watch incoming/ folder for new videos")
    sub.add_parser("games", help="List all supported popular games for SEO")

    p_process = sub.add_parser("process", help="Generate SEO + thumbnail")
    p_process.add_argument("video", type=Path)
    p_process.add_argument("--game", default=None)
    p_process.add_argument("--hook", default=None)
    p_process.add_argument("--topic", default=None)
    p_process.add_argument("--upload", action="store_true", help="Upload immediately")
    p_process.add_argument("--public", action="store_true")
    p_process.add_argument("--unlisted", action="store_true")

    p_upload = sub.add_parser("upload", help="Upload from bundle JSON")
    p_upload.add_argument("bundle", type=Path)
    p_upload.add_argument("--public", action="store_true")
    p_upload.add_argument("--private", action="store_true")

    p_preview = sub.add_parser("preview", help="Print metadata only")
    p_preview.add_argument("video", type=Path)
    p_preview.add_argument("--game", default=None)

    p_create = sub.add_parser("create", help="AI-create faceless gaming video (no recording)")
    p_create.add_argument("--game", default=None, help="Game name or auto-pick trending")
    p_create.add_argument(
        "--format",
        default="tips",
        choices=list_formats(),
        help="tips|gameplay|news|bestgames|upcoming|industry|...",
    )
    p_create.add_argument("--topic", default=None, help="Trending topic or headline")
    p_create.add_argument("--platform", default=None, help="PC, PS5, Xbox, Nintendo Switch")
    p_create.add_argument(
        "--duration",
        default="short",
        choices=["short", "long"],
        help="short=vertical Short, long=horizontal video",
    )
    p_create.add_argument("--upload", action="store_true", help="Upload after create+SEO")
    p_create.add_argument("--public", action="store_true")

    p_batch = sub.add_parser("batch", help="Create multiple AI videos")
    p_batch.add_argument("--count", type=int, default=3)
    p_batch.add_argument("--format", default="tips", choices=list_formats())
    p_batch.add_argument("--duration", default="short", choices=["short", "long"])
    p_batch.add_argument("--auto", action="store_true", help="Rotate random popular games")
    p_batch.add_argument("--game", default=None)

    p_daily = sub.add_parser("daily", help="Daily videos (long 8 AM + Short 6 PM)")
    p_daily.add_argument("--upload", action="store_true", help="Upload to YouTube")
    p_daily.add_argument("--public", action="store_true")
    p_daily.add_argument("--plan-only", action="store_true", help="Show plan without creating")
    p_daily.add_argument("--long-only", action="store_true", help="Long video only (morning run)")
    p_daily.add_argument("--short-only", action="store_true", help="Short only (evening run)")

    p_trends = sub.add_parser("trends", help="Show trending gaming topics")

    p_rebuild = sub.add_parser("rebuild-backlog", help="Re-render deleted videos and upload")
    p_rebuild.add_argument("--dates", nargs="*", default=["20260611", "20260612", "20260613", "20260614"])
    p_rebuild.add_argument("--public", action="store_true", default=True)
    p_rebuild.add_argument("--no-upload", action="store_true")

    args = parser.parse_args()

    if args.command == "auth":
        run_auth_cli()
    elif args.command == "stats":
        print_growth_report()
    elif args.command == "games":
        games = list_popular_games()
        print(f"\n🎮 ProGamer pipeline — {len(games)} popular games supported\n")
        for i, g in enumerate(games, 1):
            print(f"  {i:2}. {g}")
        print("\nTip: put the game name in your video filename (e.g. valorant_ace_ranked.mp4)")
        print("     or pass --game \"Marvel Rivals\"\n")
    elif args.command == "watch":
        watch_folder()
    elif args.command == "process":
        privacy = None
        if args.public:
            privacy = "public"
        elif getattr(args, "unlisted", False):
            privacy = "unlisted"
        process_video(
            args.video,
            game=args.game,
            hook=args.hook,
            topic=args.topic,
            auto_upload=args.upload,
            privacy=privacy,
        )
    elif args.command == "upload":
        privacy = "public" if args.public else ("private" if args.private else None)
        upload_from_bundle(Path(args.bundle), privacy=privacy)
    elif args.command == "preview":
        m = build_metadata(args.video, game=args.game)
        print(json.dumps(m.to_dict(), indent=2))
    elif args.command == "trends":
        from trending_topics import _recently_used_titles, get_all_trends, pick_fresh_trends
        used = _recently_used_titles()
        print("\n🔥 Fresh gaming trends (live fetch)\n")
        for i, t in enumerate(pick_fresh_trends(15), 1):
            src = f"[{t.feed}/{t.subreddit}]" if t.subreddit else f"[{t.source}]"
            print(f"  {i:2}. {t.title[:68]} {src}")
        print(f"\n   Skipping {len(used)} topics used in the last "
              f"{getattr(config, 'TREND_HISTORY_DAYS', 14)} days")
        print("   Run: python pipeline.py daily --plan-only\n")
    elif args.command == "daily":
        from daily_run import run_daily
        slot = None
        if getattr(args, "long_only", False):
            slot = "long"
        elif getattr(args, "short_only", False):
            slot = "short"
        run_daily(
            upload=args.upload,
            public=args.public,
            plan_only=args.plan_only,
            slot=slot,
        )
    elif args.command == "rebuild-backlog":
        from rebuild_backlog import rebuild_and_upload
        rebuild_and_upload(
            dates=args.dates,
            public=args.public,
            skip_upload=args.no_upload,
        )
    elif args.command == "create":
        result = create_video(
            game=args.game,
            format_name=args.format,
            duration=args.duration,
            topic=args.topic,
            trend_context=args.topic,
            platform=args.platform,
        )
        if config.AUTO_PROCESS_AFTER_CREATE or args.upload:
            bundle = process_video(
                result["video"],
                game=result["game"],
                hook=result["hook"],
                topic=result["topic"],
                title=result["title"],
                game_reference=Path(result["game_reference"]) if result.get("game_reference") else None,
                auto_upload=args.upload,
                privacy="public" if args.public else None,
            )
            if not args.upload:
                print(f"\n📦 Upload when ready:\n   python pipeline.py upload {bundle}")
    elif args.command == "batch":
        import random
        from popular_games import list_popular_games

        games = list_popular_games()
        print(f"\n🚀 Batch creating {args.count} AI videos for ProGamer\n")
        for i in range(args.count):
            g = None
            if args.auto:
                g = random.choice(games)
            elif args.game:
                g = args.game
            print(f"\n--- Video {i + 1}/{args.count}" + (f" ({g})" if g else " (random)") + " ---")
            result = create_video(game=g, format_name=args.format, duration=args.duration)
            if config.AUTO_PROCESS_AFTER_CREATE:
                process_video(
                    result["video"],
                    game=result["game"],
                    hook=result["hook"],
                    topic=result["topic"],
                    title=result["title"],
                )
        print("\n✅ Batch done. Review files in generated/ and processed/")


if __name__ == "__main__":
    main()