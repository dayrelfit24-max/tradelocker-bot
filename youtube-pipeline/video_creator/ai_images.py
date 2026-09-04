"""AI-generated cinematic scene backgrounds (OpenAI Images)."""

from __future__ import annotations

import base64
from pathlib import Path

import requests

import config
from video_creator.script_gen import Scene


def _build_prompt(game: str, scene: Scene, is_short: bool) -> str:
    return (
        f"In-game screenshot style image of the video game '{game}', "
        f"scene moment: {scene.headline}. {scene.subline or ''}. "
        f"Context from narration: {scene.narration[:120]}. "
        "Looks like real gameplay on a gaming monitor, HUD optional, "
        "dramatic lighting, sharp focus, NO text overlays, NO logos, NO watermarks, "
        "original generic interpretation not copyrighted characters."
    )


def generate_scene_image(
    game: str,
    scene: Scene,
    index: int,
    out_path: Path,
    is_short: bool,
) -> Path | None:
    if not getattr(config, "USE_AI_IMAGES", True):
        return None
    if not config.OPENAI_API_KEY:
        return None

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and out_path.stat().st_size > 5000:
        return out_path

    prompt = _build_prompt(game, scene, is_short)
    size = getattr(config, "OPENAI_IMAGE_SIZE_SHORT", "1024x1792")
    if not is_short:
        size = getattr(config, "OPENAI_IMAGE_SIZE_LONG", "1792x1024")
    model = getattr(config, "OPENAI_IMAGE_MODEL", "dall-e-3")

    try:
        from openai import OpenAI

        client = OpenAI(api_key=config.OPENAI_API_KEY)
        resp = client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            quality="standard",
            n=1,
        )
        item = resp.data[0]
        if item.b64_json:
            out_path.write_bytes(base64.b64decode(item.b64_json))
            return out_path
        if item.url:
            r = requests.get(item.url, timeout=60)
            r.raise_for_status()
            out_path.write_bytes(r.content)
            return out_path
    except Exception as e:
        print(f"      ⚠ AI image skipped: {e}")
    return None