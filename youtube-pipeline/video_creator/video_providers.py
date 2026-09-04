"""Multi-source gaming footage: Pexels, Pixabay, Coverr."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Callable

import requests

import config

_used_urls: dict[str, set[str]] = {}


def _session_key(work_dir: Path) -> str:
    return str(work_dir.resolve())


def _mark_used(work_dir: Path, url: str) -> bool:
    sk = _session_key(work_dir)
    _used_urls.setdefault(sk, set())
    if url in _used_urls[sk]:
        return False
    _used_urls[sk].add(url)
    return True


def _download(url: str, dest: Path) -> Path | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(url, timeout=90, stream=True)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return dest if dest.stat().st_size > 5000 else None
    except requests.RequestException:
        return None


# --- Pexels ---
def _pexels_search(query: str, orientation: str, per_page: int = 10) -> list[dict]:
    if not config.PEXELS_API_KEY:
        return []
    try:
        r = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": config.PEXELS_API_KEY},
            params={"query": query, "per_page": per_page, "orientation": orientation},
            timeout=20,
        )
        r.raise_for_status()
        return r.json().get("videos", [])
    except requests.RequestException:
        return []


def _pexels_pick_url(video: dict, vertical: bool) -> str | None:
    files = video.get("video_files", [])
    if not files:
        return None
    if vertical:
        pool = [f for f in files if f.get("height", 0) > f.get("width", 0)] or files
    else:
        pool = [f for f in files if f.get("width", 0) >= f.get("height", 0)] or files
    pool.sort(key=lambda f: f.get("width", 0), reverse=True)
    for f in pool:
        u = f.get("link")
        if u and f.get("width", 0) >= 720:
            return u
    return pool[0].get("link") if pool else None


# --- Pixabay ---
def _pixabay_search(query: str, per_page: int = 15) -> list[dict]:
    if not getattr(config, "PIXABAY_API_KEY", ""):
        return []
    try:
        r = requests.get(
            "https://pixabay.com/api/videos/",
            params={
                "key": config.PIXABAY_API_KEY,
                "q": query,
                "per_page": per_page,
                "video_type": "all",
            },
            timeout=20,
        )
        r.raise_for_status()
        return r.json().get("hits", [])
    except requests.RequestException:
        return []


def _pixabay_pick_url(hit: dict, vertical: bool) -> str | None:
    videos = hit.get("videos", {})
    order = (
        ["large", "medium", "small", "tiny"]
        if not vertical
        else ["medium", "large", "small", "tiny"]
    )
    for key in order:
        v = videos.get(key, {})
        url = v.get("url")
        if url:
            return url
    return None


# --- Coverr ---
def _coverr_search(query: str, per_page: int = 12) -> list[dict]:
    if not getattr(config, "COVERR_API_KEY", ""):
        return []
    try:
        r = requests.get(
            "https://api.coverr.co/videos",
            headers={"Authorization": f"Bearer {config.COVERR_API_KEY}"},
            params={"query": query, "page_size": per_page},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else data.get("videos", data.get("hits", []))
    except requests.RequestException:
        return []


def _coverr_pick_url(item: dict) -> str | None:
    for key in ("mp4", "url", "video_url", "download_url"):
        if item.get(key):
            return item[key]
    urls = item.get("urls") or item.get("assets") or {}
    if isinstance(urls, dict):
        return urls.get("mp4") or urls.get("download")
    return None


def fetch_from_providers(
    queries: list[str],
    work_dir: Path,
    scene_index: int,
    is_short: bool,
    *,
    allow_without_stock_flag: bool = False,
) -> tuple[Path | None, str, str]:
    """
    Try each query across all providers.
    Returns (clip_path, matched_query, provider_name).
    """
    if not config.USE_STOCK_FOOTAGE and not allow_without_stock_flag:
        return None, "", ""

    dest = work_dir / "stock" / f"scene_{scene_index:02d}_raw.mp4"
    if dest.exists() and dest.stat().st_size > 5000:
        return dest, "cached", "cache"

    vertical = is_short
    orientation = "portrait" if vertical else "landscape"
    shuffled = list(queries)
    random.shuffle(shuffled)

    providers: list[tuple[str, Callable]] = [
        ("pexels", lambda q: (_pexels_search(q, orientation), _pexels_pick_url)),
        ("pixabay", lambda q: (_pixabay_search(q), _pixabay_pick_url)),
        ("coverr", lambda q: (_coverr_search(q), _coverr_pick_url)),
    ]

    for q in shuffled:
        for pname, _ in providers:
            if pname == "pexels":
                hits = _pexels_search(q, orientation)
                random.shuffle(hits)
                for hit in hits:
                    url = _pexels_pick_url(hit, vertical)
                    if url and _mark_used(work_dir, url) and _download(url, dest):
                        return dest, q, "pexels"
            elif pname == "pixabay":
                hits = _pixabay_search(q)
                random.shuffle(hits)
                for hit in hits:
                    url = _pixabay_pick_url(hit, vertical)
                    if url and _mark_used(work_dir, url) and _download(url, dest):
                        return dest, q, "pixabay"
            elif pname == "coverr":
                hits = _coverr_search(q)
                random.shuffle(hits)
                for hit in hits:
                    url = _coverr_pick_url(hit)
                    if url and _mark_used(work_dir, url) and _download(url, dest):
                        return dest, q, "coverr"

    return None, "", ""


def fetch_game_footage_fallback(
    game: str,
    headline: str,
    narration: str,
    scene_index: int,
    work_dir: Path,
    is_short: bool,
) -> tuple[Path | None, str, str]:
    """Last-resort game-matched clip when Steam/YouTube trailers fail."""
    if not getattr(config, "GAME_FOOTAGE_FALLBACK", True):
        return None, "", ""
    from video_creator.game_assets import build_scene_video_queries

    queries = build_scene_video_queries(game, headline, narration, gameplay_mode=True)
    return fetch_from_providers(
        queries, work_dir, scene_index, is_short, allow_without_stock_flag=True,
    )


def list_active_providers() -> list[str]:
    out = []
    if config.PEXELS_API_KEY:
        out.append("Pexels")
    if getattr(config, "PIXABAY_API_KEY", ""):
        out.append("Pixabay")
    if getattr(config, "COVERR_API_KEY", ""):
        out.append("Coverr")
    return out