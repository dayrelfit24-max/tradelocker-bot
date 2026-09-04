"""Daily ProGamer schedule — long at 8 AM, Short at 6 PM (split runs)."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import config
from growth_test import short_uploaded_today, should_run_slot, shorts_only, status_line
from content_planner import (
    PlannedVideo,
    build_daily_plan,
    load_daily_plan,
    save_plan,
)
from video_creator.create import create_video

from pipeline import process_video
from youtube_upload import upload_from_bundle


def _plan_for_slot(slot: str | None) -> tuple[list[PlannedVideo], Path | None]:
    """Build or load today's plan, filtered to long / short / all."""
    plan_path: Path | None = None

    if slot == "long":
        full = build_daily_plan()
        plan_path = save_plan(full)
        return [p for p in full if p.duration == "long"], plan_path

    if slot == "short":
        primary = getattr(config, "CHANNEL_PRIMARY_GAME", "").strip()
        loaded = load_daily_plan()
        if loaded and not shorts_only():
            shorts = [p for p in loaded if p.duration == "short"]
            if shorts:
                plan_path = config.GENERATED_DIR / f"daily_plan_{datetime.now():%Y%m%d}.json"
                return shorts, plan_path
        if loaded and shorts_only() and primary:
            shorts = [p for p in loaded if p.duration == "short"]
            if shorts and (shorts[0].game or "").lower() == primary.lower():
                plan_path = config.GENERATED_DIR / f"daily_plan_{datetime.now():%Y%m%d}.json"
                return shorts, plan_path
        if shorts_only():
            print("   🧪 Growth test — fresh Fortnite Short plan for today")
        else:
            print("   ⚠️  No morning plan found — building Short-only plan for today")
        short_plan = build_daily_plan(long_count=0, short_count=1)
        plan_path = save_plan(short_plan)
        return short_plan, plan_path

    full = build_daily_plan()
    plan_path = save_plan(full)
    return full, plan_path


def _slot_label(slot: str | None) -> str:
    if slot == "long":
        return "LONG (8 AM)"
    if slot == "short":
        return "SHORT (6 PM)"
    return "FULL"


def run_daily(
    upload: bool | None = None,
    public: bool = False,
    plan_only: bool = False,
    slot: str | None = None,
) -> dict:
    upload = upload if upload is not None else getattr(config, "AUTO_UPLOAD_DAILY", False)

    if not should_run_slot(slot):
        if slot == "short" and short_uploaded_today():
            msg = "Today's Short already uploaded (early run)."
        else:
            msg = status_line() or "Growth test: this slot is paused today."
        print(f"\n⏭️  Skipping {_slot_label(slot)} — {msg}")
        return {"plan": None, "videos": [], "skipped": True}

    plan, plan_path = _plan_for_slot(slot)

    print(f"\n📅 ProGamer Daily Plan — {datetime.now():%Y-%m-%d} [{_slot_label(slot)}]")
    if status_line():
        print(f"   {status_line()}")
    if getattr(config, "CHANNEL_FOCUS_ENABLED", False):
        games = ", ".join(getattr(config, "CHANNEL_FOCUS_GAMES", []) or ["—"])
        print(f"   🎯 FOCUS MODE: {getattr(config, 'CHANNEL_FOCUS_PLATFORM', 'PC')} — {games}")
    print(f"   This run: {sum(1 for p in plan if p.duration == 'long')} long + "
          f"{sum(1 for p in plan if p.duration == 'short')} Short = {len(plan)} video(s)")
    if slot == "long":
        print("   Evening Short uses the plan saved this morning (6 PM job)")
    print("   Topics: fresh Reddit + Google News — no repeat within 14 days")
    if plan_path:
        print(f"   Plan: {plan_path}\n")

    for i, item in enumerate(plan, 1):
        print(f"  {i}. {item.label()}")

    if plan_only:
        return {"plan": str(plan_path) if plan_path else None, "videos": []}

    if not plan:
        print("\n   Nothing scheduled for this slot.")
        return {"plan": str(plan_path) if plan_path else None, "videos": []}

    results: list[dict] = []
    delay = getattr(config, "UPLOAD_DELAY_SEC", 45)
    suffix = f"_{slot}" if slot else ""
    log_path = config.GENERATED_DIR / f"daily_log_{datetime.now():%Y%m%d}{suffix}.json"

    for i, item in enumerate(plan, 1):
        print(f"\n{'='*60}")
        print(f"VIDEO {i}/{len(plan)} — {item.slot}")
        print(f"{'='*60}")
        try:
            result = _create_from_plan(item)
            bundle = None
            if config.AUTO_PROCESS_AFTER_CREATE or upload:
                bundle = process_video(
                    result["video"],
                    game=result["game"],
                    hook=result["hook"],
                    topic=result["topic"],
                    title=result["title"],
                    game_reference=Path(result["game_reference"]) if result.get("game_reference") else None,
                )
            if upload and bundle:
                privacy = "public" if public else None
                upload_from_bundle(bundle, privacy=privacy or "public")
                print("   🚀 Uploaded to YouTube")
                if i < len(plan):
                    print(f"   ⏳ Waiting {delay}s before next upload...")
                    time.sleep(delay)
            results.append({**result, "bundle": str(bundle) if bundle else None, "slot": item.slot})
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results.append({"slot": item.slot, "error": str(e)})

    log_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\n✅ Daily run complete. Log: {log_path}")
    return {"plan": str(plan_path) if plan_path else None, "log": str(log_path), "videos": results}


def _create_from_plan(item: PlannedVideo) -> dict:
    duration = "short" if item.duration == "short" else "long"
    game = item.game
    if item.format in ("industry", "bestgames", "upcoming", "news") and not game:
        game = "Gaming"
    return create_video(
        game=game,
        format_name=item.format,
        duration=duration,
        topic=item.topic,
        trend_context=item.trend_title,
        platform=item.platform,
    )


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--upload", action="store_true")
    p.add_argument("--public", action="store_true")
    p.add_argument("--plan-only", action="store_true")
    p.add_argument("--long-only", action="store_true", help="8 AM — long video only")
    p.add_argument("--short-only", action="store_true", help="6 PM — Short only (uses morning plan)")
    args = p.parse_args()
    slot = None
    if args.long_only:
        slot = "long"
    elif args.short_only:
        slot = "short"
    run_daily(upload=args.upload, public=args.public, plan_only=args.plan_only, slot=slot)