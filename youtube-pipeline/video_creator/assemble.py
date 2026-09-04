"""Assemble scenes + voiceover into final MP4 with ffmpeg."""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

from video_creator.script_gen import VideoScript
from video_creator.visuals import SceneVisual


def _check_ffmpeg() -> None:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, timeout=10)
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise RuntimeError(
            "ffmpeg is required. Install: brew install ffmpeg (Mac) or apt install ffmpeg"
        )


def _scene_clip_image(
    image: Path,
    duration: float,
    out_path: Path,
    is_short: bool,
    overlay: Path | None = None,
) -> None:
    from video_creator.video_fit import frame_size, fill_frame_filter

    w, h = frame_size(is_short)
    dur = max(duration, 1.5)
    frames = max(int(dur * 25), 25)
    fit = fill_frame_filter(is_short)

    if overlay and overlay.exists():
        vf = (
            f"[0:v]{fit},zoompan=z='min(zoom+0.0012,1.08)':d={frames}:s={w}x{h}:fps=25[bg];"
            f"[1:v]scale={w}:{h}[ov];[bg][ov]overlay=0:0"
        )
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", str(image),
            "-loop", "1", "-i", str(overlay),
            "-filter_complex", vf, "-t", str(dur), "-r", "25",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(out_path),
        ]
    else:
        vf = f"{fit},zoompan=z='min(zoom+0.0015,1.1)':d={frames}:s={w}x{h}:fps=25"
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", str(image),
            "-vf", vf, "-t", str(dur), "-r", "25",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(out_path),
        ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        subprocess.run(
            [
                "ffmpeg", "-y", "-loop", "1", "-i", str(image),
                "-vf", fit, "-t", str(dur), "-r", "25",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(out_path),
            ],
            check=True,
            capture_output=True,
            timeout=180,
        )


def _scene_clip_video(
    video: Path,
    duration: float,
    out_path: Path,
    is_short: bool,
    overlay: Path | None,
) -> None:
    from video_creator.video_fit import (
        encode_shorts_clip,
        fill_frame_filter,
        ffmpeg_video_args,
        frame_size,
        shorts_fit_filter_complex,
    )

    dur = max(duration, 1.5)

    if is_short and not overlay:
        if encode_shorts_clip(video, out_path, duration=dur):
            return

    fit = fill_frame_filter(is_short)
    if is_short and overlay and overlay.exists():
        w, h = 1080, 1920
        vf = (
            f"[0:v]trim=0:{dur},setpts=PTS-STARTPTS,split=2[main][bgsrc];"
            f"[bgsrc]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=35:18[bg];"
            f"[main]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[vid];"
            f"[1:v]scale={w}:{h}[ov];[vid][ov]overlay=0:0,setsar=1,setdar=9/16"
        )
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(video),
                "-loop", "1", "-i", str(overlay),
                "-filter_complex", vf,
                "-t", str(dur), *ffmpeg_video_args(True),
                "-an", str(out_path),
            ],
            check=True,
            capture_output=True,
            timeout=180,
        )
        return

    if overlay and overlay.exists():
        w, h = frame_size(is_short)
        vf = (
            f"[0:v]trim=0:{dur},setpts=PTS-STARTPTS,{fit}[bg];"
            f"[1:v]scale={w}:{h}[ov];[bg][ov]overlay=0:0"
        )
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(video),
                "-loop", "1", "-i", str(overlay),
                "-filter_complex", vf,
                "-t", str(dur), *ffmpeg_video_args(is_short),
                "-an", str(out_path),
            ],
            check=True,
            capture_output=True,
            timeout=180,
        )
    else:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(video),
                "-vf", f"trim=0:{dur},setpts=PTS-STARTPTS,{fit}",
                "-t", str(dur), *ffmpeg_video_args(is_short),
                "-an", str(out_path),
            ],
            check=True,
            capture_output=True,
            timeout=300 if not is_short else 180,
        )


def _trim_video_to_duration(
    src: Path,
    duration: float,
    out: Path,
    is_short: bool,
) -> Path | None:
    """Trim to scene length."""
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
                "-vf", f"trim=0:{dur},setpts=PTS-STARTPTS,{fill_frame_filter(False)}",
                "-t", str(dur), "-an", *ffmpeg_video_args(False),
                str(out),
            ],
            check=True,
            capture_output=True,
            timeout=300,
        )
        return out if out.exists() else None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def _build_short_video_clip(
    visual: SceneVisual,
    duration: float,
    out_path: Path,
    scene_index: int,
) -> bool:
    """Overlay text on the per-scene gameplay clip (already matched to scene game)."""
    from video_creator.trailer_clips import render_short_trailer_clip

    clip = visual.background
    if not clip.exists():
        return False

    # Re-cut only when narration runs longer than the pre-built segment.
    built_dur = _probe_duration(clip)
    scene_game = visual.scene_game or ""
    if scene_game and duration > built_dur + 0.4:
        work = clip.parent.parent
        extended = render_short_trailer_clip(scene_game, scene_index, work, duration)
        if extended and extended.exists():
            clip = extended

    vis2 = SceneVisual(
        clip, True, visual.overlay, visual.source, scene_game=scene_game
    )
    _build_scene_clip(vis2, duration, out_path, True)
    return out_path.exists()


def _build_scene_clip(visual: SceneVisual, duration: float, out_path: Path, is_short: bool) -> None:
    if visual.is_video:
        _scene_clip_video(visual.background, duration, out_path, is_short, visual.overlay)
    else:
        _scene_clip_image(visual.background, duration, out_path, is_short, visual.overlay)


def _concat_clips(clips: list[Path], out_path: Path, is_short: bool) -> None:
    lst = out_path.with_suffix(".concat.txt")
    lst.write_text("\n".join(f"file '{c.resolve()}'" for c in clips), encoding="utf-8")
    if is_short:
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                "-c", "copy", str(out_path),
            ],
            check=True,
            capture_output=True,
            timeout=300,
        )
    else:
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                "-c", "copy", str(out_path),
            ],
            check=True,
            capture_output=True,
            timeout=300,
        )
    lst.unlink(missing_ok=True)


def _merge_audio_video(video: Path, audio: Path, out_path: Path) -> None:
    vdur = _probe_duration(video)
    adur = _probe_duration(audio)
    video_in = video
    if vdur < adur - 0.3:
        padded = video.with_suffix(".padded.mp4")
        pad_sec = adur - vdur + 0.1
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(video),
                "-vf", f"tpad=stop_mode=clone:stop_duration={pad_sec:.2f}",
                "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(padded),
            ],
            check=True,
            capture_output=True,
            timeout=300,
        )
        video_in = padded

    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video_in), "-i", str(audio),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", str(adur),
            "-movflags", "+faststart", str(out_path),
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )
    if video_in != video and video_in.exists():
        video_in.unlink(missing_ok=True)


def assemble_video(
    script: VideoScript,
    scene_visuals: list[SceneVisual],
    scene_audios: list[Path],
    narration: Path,
    work_dir: Path,
    out_path: Path,
) -> Path:
    _check_ffmpeg()
    work_dir.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []

    sources = [v.source for v in scene_visuals]
    trailers = sources.count("trailer")
    game_vid = sum(1 for s in sources if "game_stock" in s or s == "stock")
    game_img = sources.count("game_photo")
    ai_n = sources.count("ai")
    print(
        f"   Visuals: {trailers} trailer, {game_vid} stock, {game_img} stills, "
        f"{ai_n} AI, {sources.count('slide')} slides"
    )

    for i, (vis, aud) in enumerate(zip(scene_visuals, scene_audios)):
        dur = _probe_duration(aud) + 0.35
        clip_path = work_dir / f"clip_{i:02d}.mp4"

        if vis.is_video and script.is_short:
            if _build_short_video_clip(vis, dur, clip_path, i):
                clips.append(clip_path)
                continue

        if vis.is_video and not (vis.overlay and vis.overlay.exists()):
            if _trim_video_to_duration(vis.background, dur, clip_path, script.is_short):
                clips.append(clip_path)
                continue

        _build_scene_clip(vis, dur, clip_path, script.is_short)
        clips.append(clip_path)

    concat_path = work_dir / "concat.mp4"
    _concat_clips(clips, concat_path, script.is_short)
    _merge_audio_video(concat_path, narration, out_path)

    if script.is_short:
        from video_creator.video_fit import finalize_short_mp4
        finalize_short_mp4(out_path)
        from video_creator.video_fit import shorts_aspect_mode
        print(f"   Short frame: 1080x1920 (9:16, mode={shorts_aspect_mode()})")

    for c in clips:
        c.unlink(missing_ok=True)
    concat_path.unlink(missing_ok=True)
    return out_path


def _probe_duration(path: Path) -> float:
    try:
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
    except (ValueError, subprocess.TimeoutExpired):
        pass
    return 3.0


def write_srt(script: VideoScript, scene_durations: list[float], path: Path) -> None:
    lines: list[str] = []
    t = 0.0
    for i, (scene, dur) in enumerate(zip(script.scenes, scene_durations)):
        end = t + dur
        lines.append(str(i + 1))
        lines.append(f"{_srt_time(t)} --> {_srt_time(end)}")
        wrapped = textwrap.fill(scene.narration, width=42)
        lines.append(wrapped)
        lines.append("")
        t = end
    path.write_text("\n".join(lines), encoding="utf-8")


def _srt_time(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int((sec % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def save_script_json(script: VideoScript, path: Path, scene_sources: list[str] | None = None) -> None:
    from video_creator.tts import get_tts_profile

    data = {
        "title": script.title,
        "hook": script.hook,
        "topic": script.topic,
        "game": script.game,
        "format": script.format,
        "is_short": script.is_short,
        "tts_profile": get_tts_profile().as_dict(),
        "scene_sources": scene_sources or [],
        "scenes": [
            {
                "narration": s.narration,
                "headline": s.headline,
                "subline": s.subline,
                "footage_game": getattr(s, "footage_game", ""),
            }
            for s in script.scenes
        ],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")