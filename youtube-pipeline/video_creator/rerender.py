"""Re-assemble a video from an existing work/ folder (script + audio + visuals on disk)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import config
from video_creator.assemble import assemble_video
from video_creator.script_gen import Scene, VideoScript
from video_creator.visuals import SceneVisual


def load_script_json(path: Path) -> VideoScript:
    data = json.loads(path.read_text(encoding="utf-8"))
    scenes = [
        Scene(
            narration=s["narration"],
            headline=s["headline"],
            subline=s.get("subline", ""),
            footage_game=s.get("footage_game", ""),
        )
        for s in data["scenes"]
    ]
    return VideoScript(
        game=data["game"],
        format=data["format"],
        title=data["title"],
        hook=data["hook"],
        topic=data["topic"],
        scenes=scenes,
        is_short=data["is_short"],
    )


def _scene_trailer(work_dir: Path, index: int) -> Path | None:
    trailer_dir = work_dir / "trailers"
    if not trailer_dir.is_dir():
        return None
    matches = sorted(trailer_dir.glob(f"scene_{index:02d}_*.mp4"))
    return matches[0] if matches else None


def _scene_still(work_dir: Path, index: int) -> Path | None:
    for name in (
        f"scene_{index:02d}_game.jpg",
        f"scene_{index:02d}_ai.jpg",
        f"scene_{index:02d}.jpg",
    ):
        path = work_dir / name
        if path.exists():
            return path
    return None


def visuals_from_work(work_dir: Path, script: VideoScript) -> list[SceneVisual]:
    data = json.loads((work_dir / "script.json").read_text(encoding="utf-8"))
    sources: list[str] = data.get("scene_sources") or []
    visuals: list[SceneVisual] = []

    for i, scene in enumerate(script.scenes):
        overlay = work_dir / f"scene_{i:02d}_overlay.png"
        if not overlay.exists():
            overlay = None
        source = sources[i] if i < len(sources) else "game_photo"
        trailer = _scene_trailer(work_dir, i)
        still = _scene_still(work_dir, i)

        if trailer and source in ("trailer", "game_stock", "stock", "gameplay"):
            visuals.append(
                SceneVisual(
                    background=trailer,
                    is_video=True,
                    overlay=overlay,
                    source=source if source != "game_photo" else "trailer",
                    scene_game=scene.footage_game or script.game,
                )
            )
        elif still:
            visuals.append(
                SceneVisual(
                    background=still,
                    is_video=False,
                    overlay=overlay,
                    source=source,
                    scene_game=scene.footage_game or script.game,
                )
            )
        elif trailer:
            visuals.append(
                SceneVisual(
                    background=trailer,
                    is_video=True,
                    overlay=overlay,
                    source="trailer",
                    scene_game=scene.footage_game or script.game,
                )
            )
        else:
            raise FileNotFoundError(f"No visual assets for scene {i} in {work_dir}")

    return visuals


def rerender_from_work(work_dir: Path, out_path: Path | None = None) -> Path:
    script_path = work_dir / "script.json"
    if not script_path.exists():
        raise FileNotFoundError(f"Missing script: {script_path}")

    script = load_script_json(script_path)
    scene_audios = [work_dir / f"scene_{i:02d}.mp3" for i in range(len(script.scenes))]
    missing = [str(p) for p in scene_audios if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing scene audio: {', '.join(missing)}")

    narration = work_dir / "narration.mp3"
    if not narration.exists():
        raise FileNotFoundError(f"Missing narration: {narration}")

    if out_path is None:
        name = f"{work_dir.name}_short.mp4" if script.is_short else f"{work_dir.name}.mp4"
        out_path = config.GENERATED_DIR / name

    out_path.parent.mkdir(parents=True, exist_ok=True)
    visuals = visuals_from_work(work_dir, script)
    print(f"   Re-rendering {len(script.scenes)} scenes → {out_path.name}")
    assemble_video(script, visuals, scene_audios, narration, work_dir, out_path)
    return out_path