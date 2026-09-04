"""Orchestrate AI video creation end-to-end."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import config
from video_creator.assemble import assemble_video, save_script_json, write_srt
from video_creator.formats import FORMAT_CHOICES
from video_creator.script_gen import generate_script
from video_creator.tts import concat_audio, get_tts_profile, synthesize_scene
from video_creator.visuals import (
    build_scene_visual,
    finalize_visual_session,
    init_visual_session,
)


def _slug(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "_", s).strip("_")[:60]


def _print_visual_setup() -> None:
    from llm_client import active_provider
    from video_creator.video_providers import list_active_providers

    ai_img = bool(config.OPENAI_API_KEY) and getattr(config, "USE_AI_IMAGES", True)
    llm = active_provider()
    providers = list_active_providers()
    rawg = bool(getattr(config, "RAWG_API_KEY", ""))
    trailers = getattr(config, "USE_TRAILER_CLIPS", True)
    print("   Pipeline:")
    print(f"      Voice (AI, locked): {get_tts_profile().label()}")
    print(f"      Scripts/SEO LLM: {llm.upper() if llm else 'templates only'}")
    print(f"      Trailers (yt-dlp): {'ON' if trailers else 'OFF'}")
    style = getattr(config, "TRAILER_FOOTAGE_STYLE", "gameplay")
    pool = getattr(config, "GAMEPLAY_POOL_SIZE", 2)
    quality = getattr(config, "VIDEO_ENCODE_QUALITY", "normal")
    from video_creator.footage_auth import youtube_footage_auth_label

    print(f"      Game footage: {style.upper()} (pool={pool} sources)")
    print(f"      YouTube auth: {youtube_footage_auth_label()}")
    print(f"      Encode quality: {quality.upper()}")
    if getattr(config, "SHORTS_ASPECT_MODE", "fit") == "fit":
        print("      Shorts framing: FIT (full trailer, not zoomed)")
    from video_creator.video_fit import long_frame_size
    lw, lh = long_frame_size()
    if lh > 1080:
        print(f"      Long video output: {lw}×{lh}")
    stock = getattr(config, "USE_STOCK_FOOTAGE", False)
    print(f"      Stock B-roll: {'OFF (gameplay only)' if not stock else ', '.join(providers)}")
    print(f"      Game stills: RAWG={'ON' if rawg else 'OFF'}, Steam")
    print(f"      AI scene images: {'ON' if ai_img else 'OFF'}")


def create_video(
    game: str | None = None,
    format_name: str = "tips",
    duration: str = "short",
    output_dir: Path | None = None,
    topic: str | None = None,
    trend_context: str | None = None,
    platform: str | None = None,
) -> dict:
    """
    Create a full faceless gaming video (no recording required).
    Real gameplay clips per scene (YouTube/Steam) — no stock B-roll. AI TTS voiceover.
    """
    script = generate_script(
        game=game,
        format_name=format_name,
        duration=duration,
        topic=topic,
        trend_context=trend_context or topic,
        platform=platform,
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slug(f"{script.game}_{script.format}_{stamp}")
    out_root = output_dir or config.GENERATED_DIR
    work_dir = out_root / "work" / slug
    work_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n🎬 Creating {'Short' if script.is_short else 'video'}: {script.game} — {script.format}")
    print(f"   Title: {script.title}")
    print(f"   Scenes: {len(script.scenes)}")
    _print_visual_setup()

    ref_image = init_visual_session(work_dir, script.game, script.is_short)
    scene_audios: list[Path] = []
    durations: list[float] = []
    for i, scene in enumerate(script.scenes):
        aud = work_dir / f"scene_{i:02d}.mp3"
        print(f"   [{i + 1}/{len(script.scenes)}] {scene.headline[:40]}... (voice)")
        dur = synthesize_scene(scene.narration, aud)
        scene_audios.append(aud)
        durations.append(dur)

    scene_visuals = []
    sources: list[str] = []
    for i, scene in enumerate(script.scenes):
        print(f"   [{i + 1}/{len(script.scenes)}] {scene.headline[:40]}... (visual {durations[i]:.1f}s)")
        visual = build_scene_visual(
            scene, script.game, i, work_dir, script.is_short,
            format_name=script.format, ref_image=ref_image,
            clip_duration=durations[i] + 0.5,
            all_scenes=script.scenes,
        )
        scene_visuals.append(visual)
        sources.append(visual.source)

    narration = work_dir / "narration.mp3"
    concat_audio(scene_audios, narration)
    write_srt(script, durations, work_dir / "captions.srt")
    save_script_json(script, work_dir / "script.json", scene_sources=sources)

    video_name = f"{slug}_short.mp4" if script.is_short else f"{slug}.mp4"
    final = out_root / video_name
    finalize_visual_session(work_dir, script.game)
    assemble_video(script, scene_visuals, scene_audios, narration, work_dir, final)

    from video_creator.trailer_clips import cleanup_trailer_downloads
    cleanup_trailer_downloads(work_dir)

    print(f"\n✅ Video ready: {final}")
    print(f"   Script: {work_dir / 'script.json'}")
    print(f"   Captions: {work_dir / 'captions.srt'}")
    return {
        "video": final,
        "script_path": work_dir / "script.json",
        "work_dir": work_dir,
        "title": script.title,
        "hook": script.hook,
        "topic": script.topic,
        "game": script.game,
        "is_short": script.is_short,
        "scene_sources": sources,
        "game_reference": str(ref_image) if ref_image else None,
    }


def list_formats() -> list[str]:
    return list(FORMAT_CHOICES)