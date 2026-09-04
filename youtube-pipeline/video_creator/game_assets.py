"""Game-matched visuals: scene keywords, Steam screenshots, Pexels game media."""

from __future__ import annotations

import json
import re
from pathlib import Path

import requests

import config
from popular_games import (
    GAME_DISPLAY,
    detect_game_from_text,
    footage_search_name,
    game_match_terms,
    list_popular_games,
    resolve_game_key,
)
from video_creator.script_gen import Scene

STEAM_SEARCH = "https://store.steampowered.com/api/storesearch/"
STEAM_APP = "https://store.steampowered.com/api/appdetails"
PEXELS_PHOTOS = "https://api.pexels.com/v1/search"
PEXELS_VIDEO = "https://api.pexels.com/videos/search"


def _is_named_game(game: str) -> bool:
    return game.lower().strip() not in ("gaming", "video games", "esports", "")


def _normalize_game_name(name: str) -> str:
    """Map alias/raw name to footage search title (full name, not short SEO label)."""
    name = name.strip()
    if not name:
        return name
    return footage_search_name(name)


def _game_from_headline(headline: str) -> str | None:
    """Parse ranked/tip headlines like '#3 HALO INFINITE' or 'TIP 2: FORZA'."""
    for pattern in (
        r"#\s*\d+\s*[:\-]?\s*(.+)",
        r"TIP\s*#?\s*\d+\s*[:\-]?\s*(.+)",
        r"TIP\s*\d+\s*[:\-]?\s*(.+)",
        r"NUMBER\s*\d+\s*[:\-]?\s*(.+)",
    ):
        m = re.search(pattern, headline, re.I)
        if m:
            raw = m.group(1).strip()
            found = _normalize_game_name(raw)
            if found and found != "Gaming":
                return found
    return None


def _detect_scene_game_quick(scene: Scene) -> str | None:
    if scene.footage_game and scene.footage_game.strip():
        return _normalize_game_name(scene.footage_game)
    from_headline = _game_from_headline(scene.headline)
    if from_headline:
        return from_headline
    for text in (f"{scene.headline} {scene.narration}", scene.narration, scene.subline):
        detected = detect_game_from_text(text)
        if detected != "Gaming":
            return detected
    return None


def resolve_scene_game(
    scene: Scene,
    video_game: str,
    scene_index: int = 0,
    all_scenes: list[Scene] | None = None,
) -> str:
    """Pick the exact game whose gameplay should play during this scene."""
    all_scenes = all_scenes or []

    quick = _detect_scene_game_quick(scene)
    if quick:
        return quick

    if scene.headline.upper() == "SUBSCRIBE" and scene_index > 0:
        for prev in reversed(all_scenes[:scene_index]):
            g = _detect_scene_game_quick(prev)
            if g:
                return g

    if scene_index == 0:
        for future in all_scenes[1:]:
            if future.headline.upper() == "SUBSCRIBE":
                continue
            g = _detect_scene_game_quick(future)
            if g:
                return g

    if _is_named_game(video_game):
        return video_game

    games = [g for g in list_popular_games() if g != "Gaming"]
    if games:
        return games[scene_index % len(games)]
    return video_game or "Fortnite"


# Map canonical keys → better stock / YouTube search terms
GAME_SEARCH_ALIASES: dict[str, list[str]] = {
    "fortnite": ["fortnite", "fortnite battle royale", "fortnite gameplay"],
    "valorant": ["valorant", "valorant fps", "valorant gameplay"],
    "call of duty": ["call of duty", "warzone gameplay", "cod gameplay"],
    "marvel rivals": ["marvel rivals", "marvel rivals gameplay"],
    "minecraft": ["minecraft", "minecraft gameplay"],
    "roblox": ["roblox", "roblox game"],
    "gta": ["gta 5", "gta online", "grand theft auto v", "grand theft auto"],
    "apex": ["apex legends", "apex gameplay"],
    "cs2": ["counter-strike 2", "counter strike 2", "cs2", "csgo"],
    "league of legends": ["league of legends", "lol gameplay"],
    "genshin impact": ["genshin impact", "genshin gameplay"],
    "animal crossing": ["animal crossing", "animal crossing new horizons"],
    "halo": ["halo infinite", "halo gameplay"],
    "zelda": ["zelda tears of the kingdom", "zelda gameplay"],
    "mario": ["super mario", "mario gameplay"],
    "gaming": ["video game", "gaming", "esports"],
}


def footage_search_queries(game: str) -> list[str]:
    """Ordered search titles for trailer/gameplay lookups."""
    primary = footage_search_name(game)
    key = resolve_game_key(game)
    queries = [primary]
    if key in GAME_SEARCH_ALIASES:
        queries.extend(GAME_SEARCH_ALIASES[key][:3])
    if game.strip().lower() not in {q.lower() for q in queries}:
        queries.append(game.strip())
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        q = q.strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out


def title_matches_game(title: str, game: str) -> bool:
    """True if a YouTube title likely belongs to this game."""
    t = title.lower()
    for term in game_match_terms(game):
        if len(term) <= 4:
            import re
            if re.search(rf"\b{re.escape(term)}\b", t):
                return True
        elif term in t:
            return True
    return False

STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "in", "on", "for", "of", "is", "are",
    "this", "that", "with", "you", "your", "we", "our", "it", "at", "by", "from",
    "subscribe", "progamer", "watch", "here", "now", "today",
}


def _headers() -> dict[str, str]:
    return {"Authorization": getattr(config, "PEXELS_API_KEY", "")}


def game_search_terms(game: str) -> list[str]:
    key = resolve_game_key(game)
    if key in GAME_SEARCH_ALIASES:
        return list(GAME_SEARCH_ALIASES[key])
    primary = footage_search_name(game).lower()
    short = primary.split()[0].lower()
    return [primary, f"{primary} gameplay", f"{short} video game", f"{short} game screen"]


def scene_keywords(scene_headline: str, scene_narration: str, max_words: int = 4) -> list[str]:
    text = f"{scene_headline} {scene_narration}".lower()
    text = re.sub(r"[^\w\s]", " ", text)
    words = [w for w in text.split() if len(w) > 3 and w not in STOPWORDS]
    seen: set[str] = set()
    out: list[str] = []
    for w in words:
        if w not in seen:
            seen.add(w)
            out.append(w)
        if len(out) >= max_words:
            break
    return out


def build_scene_video_queries(
    game: str,
    headline: str,
    narration: str,
    gameplay_mode: bool = True,
) -> list[str]:
    """Pexels queries prioritized to match spoken content + game."""
    terms = game_search_terms(game)
    kw = scene_keywords(headline, narration)
    queries: list[str] = []

    for t in terms[:3]:
        queries.append(f"{t} gameplay no commentary")
        queries.append(f"{t} gameplay screen recording")
        queries.append(f"{t} multiplayer gameplay")
    for k in kw[:3]:
        queries.append(f"{game} {k} gameplay")
        queries.append(f"{terms[0]} {k}")
    if gameplay_mode:
        queries.extend([
            f"{terms[0]} gameplay 4k",
            f"{terms[0]} actual gameplay",
            f"{terms[0]} game screen",
        ])
    headline_q = re.sub(r"[^\w\s]", "", headline.lower())[:40]
    if headline_q:
        queries.append(f"{game} {headline_q}")

    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out[:12]


def best_steam_app_id(game: str) -> int | None:
    """Pick Steam app that actually matches the game name."""
    try:
        needles = [q.lower() for q in footage_search_queries(game)]
        for term in needles:
            r = requests.get(
                STEAM_SEARCH,
                params={"term": term, "l": "english", "cc": "US"},
                timeout=15,
            )
            r.raise_for_status()
            items = r.json().get("items", [])
            if not items:
                continue
            for item in items[:8]:
                name = (item.get("name") or "").lower()
                for needle in needles:
                    if needle in name or name in needle:
                        return int(item["id"])
                first_token = needles[0].split()[0]
                if len(first_token) >= 4 and first_token in name:
                    return int(item["id"])
            return int(items[0]["id"])
        return None
    except (requests.RequestException, ValueError, KeyError):
        return None


def fetch_steam_screenshot(game: str, dest: Path) -> Path | None:
    """Official Steam screenshots for PC games (real in-game imagery)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 5000:
        return dest
    try:
        appid = best_steam_app_id(game)
        if not appid:
            return None
        d = requests.get(
            STEAM_APP,
            params={"appids": appid, "l": "english"},
            timeout=15,
        )
        d.raise_for_status()
        app = d.json().get(str(appid), {}).get("data", {})
        shots = app.get("screenshots", [])
        if not shots:
            header = app.get("header_image")
            if header:
                shots = [{"path_full": header}]
        if not shots:
            return None
        url = shots[min(len(shots) - 1, 1)]["path_full"]
        img = requests.get(url, timeout=30)
        img.raise_for_status()
        dest.write_bytes(img.content)
        return dest if dest.stat().st_size > 3000 else None
    except requests.RequestException:
        return None


def fetch_scene_game_still(
    game: str,
    scene,
    index: int,
    work_dir: Path,
    ref_image: Path | None,
) -> Path | None:
    """Per-scene still from RAWG (rotates screenshots)."""
    still = work_dir / f"scene_{index:02d}_game.jpg"
    if still.exists():
        return still

    rawg = fetch_rawg_screenshot(game, still, index=index % 4)
    if rawg:
        return rawg

    if ref_image and ref_image.exists():
        still.write_bytes(ref_image.read_bytes())
        return still

    return None


def fetch_pexels_photo(query: str, dest: Path, orientation: str = "landscape") -> Path | None:
    if not getattr(config, "PEXELS_API_KEY", ""):
        return None
    try:
        r = requests.get(
            PEXELS_PHOTOS,
            headers=_headers(),
            params={"query": query, "per_page": 8, "orientation": orientation},
            timeout=20,
        )
        r.raise_for_status()
        photos = r.json().get("photos", [])
        for photo in photos:
            src = photo.get("src", {})
            url = src.get("large2x") or src.get("large") or src.get("original")
            if not url:
                continue
            data = requests.get(url, timeout=30)
            data.raise_for_status()
            dest.write_bytes(data.content)
            if dest.stat().st_size > 3000:
                return dest
    except requests.RequestException:
        pass
    return None


def _download_image_url(url: str, dest: Path) -> Path | None:
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return dest if dest.stat().st_size > 3000 else None
    except requests.RequestException:
        return None


def fetch_rawg_images(game: str) -> list[str]:
    """RAWG API — screenshots for console + PC games (Fortnite, Marvel Rivals, etc.)."""
    key = getattr(config, "RAWG_API_KEY", "")
    if not key:
        return []
    try:
        r = requests.get(
            "https://api.rawg.io/api/games",
            params={"key": key, "search": game, "page_size": 3},
            timeout=15,
        )
        r.raise_for_status()
        urls: list[str] = []
        for item in r.json().get("results", []):
            if item.get("background_image"):
                urls.append(item["background_image"])
            urls.extend(item.get("short_screenshots", [])[:4])
        return urls
    except requests.RequestException:
        return []


def fetch_rawg_screenshot(game: str, dest: Path, index: int = 1) -> Path | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    urls = fetch_rawg_images(game)
    if not urls:
        return None
    pick = urls[min(index, len(urls) - 1)]
    return _download_image_url(pick, dest)


def fetch_pixabay_photo(query: str, dest: Path) -> Path | None:
    key = getattr(config, "PIXABAY_API_KEY", "")
    if not key:
        return None
    try:
        r = requests.get(
            "https://pixabay.com/api/",
            params={"key": key, "q": query, "per_page": 10, "image_type": "photo"},
            timeout=20,
        )
        r.raise_for_status()
        for hit in r.json().get("hits", []):
            url = hit.get("largeImageURL") or hit.get("webformatURL")
            if url and _download_image_url(url, dest):
                return dest
    except requests.RequestException:
        pass
    return None


def fetch_game_reference_image(game: str, work_dir: Path, is_short: bool) -> Path | None:
    """One reference image of the actual game for thumbnails + fallbacks."""
    cache = work_dir / "game_reference.jpg"
    if cache.exists() and cache.stat().st_size > 3000:
        return cache

    if fetch_rawg_screenshot(game, cache):
        print(f"      🖼 Game reference (RAWG)")
        return cache
    cache.unlink(missing_ok=True)

    orientation = "portrait" if is_short else "landscape"
    for q in game_search_terms(game):
        if fetch_pexels_photo(f"{q} screenshot", cache, orientation):
            print(f"      🖼 Game reference (Pexels): {q}")
            return cache
        cache.unlink(missing_ok=True)
        if fetch_pixabay_photo(f"{q} game", cache):
            print(f"      🖼 Game reference (Pixabay): {q}")
            return cache
        cache.unlink(missing_ok=True)

    if fetch_steam_screenshot(game, cache):
        print(f"      🖼 Game reference (Steam)")
        return cache

    return None


def save_game_context(work_dir: Path, game: str, queries_log: list[dict]) -> None:
    (work_dir / "game_context.json").write_text(
        json.dumps({"game": game, "scene_queries": queries_log}, indent=2),
        encoding="utf-8",
    )