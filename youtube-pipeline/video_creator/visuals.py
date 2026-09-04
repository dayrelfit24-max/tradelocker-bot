"""Per-scene visuals: real gameplay matched to each scene's game (no stock)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import config
from video_creator.ai_images import generate_scene_image
from video_creator.game_assets import (
    fetch_game_reference_image,
    fetch_scene_game_still,
    resolve_scene_game,
    save_game_context,
)
from video_creator.formats import scene_overlay_badge
from video_creator.scenes import render_overlay, render_shorts_overlay
from video_creator.script_gen import Scene
from video_creator.stock_footage import trim_stock
from video_creator.trailer_clips import fetch_trailer_for_scene
from video_creator.video_providers import fetch_game_footage_fallback

_query_log: list[dict] = []


@dataclass
class SceneVisual:
    background: Path
    is_video: bool
    overlay: Path | None
    source: str  # trailer | game_photo | ai | slide
    scene_game: str = ""  # exact game whose footage is in background


def _scene_overlay(
    scene: Scene,
    game: str,
    index: int,
    work_dir: Path,
    is_short: bool,
    on_video: bool,
    format_name: str = "tips",
) -> Path | None:
    if is_short:
        path = work_dir / f"scene_{index:02d}_overlay.png"
        render_shorts_overlay(
            scene,
            game,
            path,
            palette_idx=index,
            badge_label=scene_overlay_badge(format_name, index, scene.headline),
        )
        return path
    path = work_dir / f"scene_{index:02d}_overlay.png"
    render_overlay(scene, game, index, path, is_short, palette_idx=index)
    return path


def build_scene_visual(
    scene: Scene,
    game: str,
    index: int,
    work_dir: Path,
    is_short: bool,
    format_name: str = "tips",
    ref_image: Path | None = None,
    clip_duration: float = 6.0,
    all_scenes: list[Scene] | None = None,
) -> SceneVisual:
    global _query_log
    shorts_video_only = is_short and getattr(config, "SHORTS_VIDEO_ONLY", True)
    all_scenes = all_scenes or []

    scene_game = resolve_scene_game(scene, game, scene_index=index, all_scenes=all_scenes)
    print(f"      🎯 Scene game: {scene_game} ← {scene.headline[:36]}")

    trailer = None
    if getattr(config, "USE_TRAILER_CLIPS", True):
        trailer = fetch_trailer_for_scene(
            scene_game,
            index,
            work_dir,
            is_short,
            duration=clip_duration,
            headline=scene.headline,
            narration=scene.narration,
        )

    if trailer:
        overlay = _scene_overlay(
            scene, scene_game, index, work_dir, is_short, on_video=True, format_name=format_name,
        )
        _query_log.append({
            "scene": index,
            "source": "trailer",
            "game": scene_game,
            "headline": scene.headline,
        })
        return SceneVisual(trailer, True, overlay, "trailer", scene_game=scene_game)

    if shorts_video_only:
        stock_raw, stock_query, stock_provider = fetch_game_footage_fallback(
            scene_game, scene.headline, scene.narration, index, work_dir, is_short,
        )
        if stock_raw:
            stock_clip = work_dir / "stock" / f"scene_{index:02d}_clip.mp4"
            trimmed = trim_stock(stock_raw, clip_duration, stock_clip, is_short)
            if trimmed:
                overlay = _scene_overlay(
                    scene, scene_game, index, work_dir, is_short, on_video=True,
                    format_name=format_name,
                )
                _query_log.append({
                    "scene": index,
                    "source": "game_stock",
                    "game": scene_game,
                    "query": stock_query,
                    "provider": stock_provider,
                })
                print(f"      🎮 Game footage fallback ({stock_provider}): {stock_query}")
                return SceneVisual(trimmed, True, overlay, "game_stock", scene_game=scene_game)
        print(f"      ⚠️  No gameplay found for {scene_game}")

    overlay_path = _scene_overlay(
        scene, scene_game, index, work_dir, is_short, on_video=False, format_name=format_name,
    )

    if not shorts_video_only:
        still = fetch_scene_game_still(scene_game, scene, index, work_dir, ref_image)
        if still:
            _query_log.append({"scene": index, "query": scene_game, "source": "game_photo"})
            print(f"      🖼 Game still ({scene_game})")
            return SceneVisual(still, False, overlay_path, "game_photo")

    ai_path = work_dir / "ai" / f"scene_{index:02d}.jpg"
    if generate_scene_image(scene_game, scene, index, ai_path, is_short):
        _query_log.append({"scene": index, "source": "ai", "game": scene_game})
        print(f"      🎨 AI ({scene_game})")
        return SceneVisual(ai_path, False, overlay_path, "ai")

    from video_creator.scenes import render_scene
    slide = work_dir / f"scene_{index:02d}.jpg"
    render_scene(scene, scene_game, index, slide, is_short, palette_idx=index)
    print("      📊 Slide fallback")
    return SceneVisual(slide, False, overlay_path, "slide")


def init_visual_session(work_dir: Path, game: str, is_short: bool) -> Path | None:
    global _query_log
    from video_creator.trailer_clips import init_trailer_session

    _query_log = []
    init_trailer_session(work_dir)
    return fetch_game_reference_image(game, work_dir, is_short)


def finalize_visual_session(work_dir: Path, game: str) -> None:
    save_game_context(work_dir, game, _query_log)