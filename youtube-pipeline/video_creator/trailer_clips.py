"""Official trailer clips: gameplay + cinematic via yt-dlp."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import requests

import config
from video_creator.game_assets import (
    footage_search_queries,
    title_matches_game,
)

_trailer_cache: dict[str, Path] = {}
_short_pair_cache: dict[str, dict[str, Path]] = {}
_gameplay_pool_cache: dict[str, list[Path]] = {}
_game_seek_counters: dict[str, int] = {}
_yt_download_blocked: bool = False


def init_trailer_session(work_dir: Path) -> None:
    """Reset per-video trailer state so scenes don't reuse wrong offsets/games."""
    global _yt_download_blocked
    _yt_download_blocked = False
    prefix = str(work_dir.resolve())
    for cache in (_gameplay_pool_cache, _short_pair_cache, _game_seek_counters):
        for key in list(cache.keys()):
            if key.startswith(prefix):
                del cache[key]


def _work_key(work_dir: Path, game: str) -> str:
    return f"{work_dir.resolve()}:{_slug(game)}"


def _next_game_seek_index(work_dir: Path, game: str) -> int:
    key = _work_key(work_dir, game)
    idx = _game_seek_counters.get(key, 0)
    _game_seek_counters[key] = idx + 1
    return idx


def _footage_style() -> str:
    return getattr(config, "TRAILER_FOOTAGE_STYLE", "gameplay").lower()


def _yt_format(is_short: bool = False) -> str:
    if is_short:
        h = getattr(config, "YT_MAX_HEIGHT", 1080)
        cap = getattr(config, "YT_MAX_FILESIZE", "400M")
    else:
        h = getattr(config, "YT_MAX_HEIGHT_LONG", getattr(config, "VIDEO_LONG_HEIGHT", 1440))
        cap = getattr(config, "YT_MAX_FILESIZE_LONG", "800M")
    return (
        f"bv*[height<={h}][filesize<{cap}][ext=mp4]/"
        f"bv*[height<={h}][filesize<{cap}]+ba/b[height<={h}][filesize<{cap}]"
    )


def _pool_size() -> int:
    return max(1, min(int(getattr(config, "GAMEPLAY_POOL_SIZE", 2)), 4))


def _scene_uses_gameplay(scene_index: int) -> bool:
    style = _footage_style()
    if style == "gameplay":
        return True
    if style == "cinematic":
        return False
    return scene_index % 2 == 0

STEAM_SEARCH = "https://store.steampowered.com/api/storesearch/"
STEAM_APP = "https://store.steampowered.com/api/appdetails"


def _slug(game: str) -> str:
    s = re.sub(r"[^\w\s-]", "", game.lower())
    return re.sub(r"[-\s]+", "_", s).strip("_")[:40]


def _yt_dlp_base_args(*, with_auth: bool = False) -> list[str]:
    """Search works without cookies; downloads need auth when YouTube blocks bots."""
    args = ["yt-dlp", "--no-warnings", "--no-update"]
    if with_auth:
        browser = getattr(config, "YT_DLP_COOKIES_FROM_BROWSER", "").strip()
        cookies_file = getattr(config, "YT_DLP_COOKIES_FILE", None)
        if cookies_file and Path(cookies_file).is_file():
            args.extend(["--cookies", str(cookies_file)])
        elif browser:
            args.extend(["--cookies-from-browser", browser])
    extra = getattr(config, "YT_DLP_EXTRA_ARGS", "").strip()
    if extra:
        args.extend(extra.split())
    return args


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _probe_duration(path: Path) -> float:
    try:
        out = _run(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            timeout=30,
        )
        if out.returncode == 0:
            return max(float(out.stdout.strip()), 10.0)
    except (ValueError, subprocess.TimeoutExpired):
        pass
    return 90.0


def _yt_dlp_available() -> bool:
    try:
        out = _run(["yt-dlp", "--version"], timeout=15)
        return out.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _download_url(url: str, dest: Path) -> bool:
    try:
        r = requests.get(url, timeout=120, stream=True)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return dest.exists() and dest.stat().st_size > 50_000
    except requests.RequestException:
        return False


def _download_hls_trailer(url: str, dest: Path, max_seconds: int = 120) -> bool:
    """Download Steam HLS/DASH trailer via ffmpeg."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part.mp4")
    try:
        out = _run(
            [
                "ffmpeg", "-y", "-i", url,
                "-t", str(max_seconds),
                "-c", "copy", "-movflags", "+faststart",
                str(tmp),
            ],
            timeout=300,
        )
        if out.returncode != 0 or not tmp.exists() or tmp.stat().st_size < 50_000:
            tmp.unlink(missing_ok=True)
            return False
        tmp.replace(dest)
        return True
    except (subprocess.TimeoutExpired, OSError):
        tmp.unlink(missing_ok=True)
        return False


def fetch_steam_trailer(game: str, dest: Path) -> Path | None:
    from video_creator.game_assets import best_steam_app_id

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 50_000:
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
        for movie in app.get("movies", []):
            mp4 = movie.get("mp4") or {}
            url = mp4.get("max") or mp4.get("480")
            if url and _download_url(url, dest):
                return dest
            hls = movie.get("hls_h264") or movie.get("dash_h264")
            if hls and _download_hls_trailer(hls, dest):
                return dest
        dest.unlink(missing_ok=True)
    except requests.RequestException:
        dest.unlink(missing_ok=True)
    return None


def _yt_candidates(query: str) -> list[tuple[str, str]]:
    try:
        out = _run(
            [*_yt_dlp_base_args(), "--flat-playlist", "--print", "%(id)s\t%(title)s", query],
            timeout=45,
        )
    except subprocess.TimeoutExpired:
        return []
    if out.returncode != 0:
        return []
    rows: list[tuple[str, str]] = []
    for line in out.stdout.splitlines():
        if "\t" in line:
            vid, title = line.split("\t", 1)
            vid = vid.strip()
            if vid and len(vid) >= 8:
                rows.append((vid, title.strip()))
    return rows


def _search_trailer_by_type(game: str, trailer_type: str) -> str | None:
    """trailer_type: gameplay | cinematic"""
    search_names = footage_search_queries(game)
    primary = search_names[0]
    if trailer_type == "gameplay":
        queries = []
        for name in search_names[:2]:
            queries.extend([
                f"ytsearch15:{name} official gameplay trailer",
                f"ytsearch12:{name} gameplay no commentary",
                f"ytsearch10:{name} multiplayer gameplay 4k",
            ])
        queries.append(f"ytsearch8:{primary} actual gameplay pc")
        prefer = re.compile(
            r"gameplay|game play|in-game|in game|no commentary|multiplayer|4k gameplay",
            re.I,
        )
        penalize = re.compile(
            r"cinematic only|story trailer|movie trailer|launch cinematic|reveal trailer|"
            r"live action|anime opening",
            re.I,
        )
    else:
        queries = [
            f"ytsearch10:{primary} official cinematic trailer",
            f"ytsearch8:{primary} cinematic trailer official",
        ]
        prefer = re.compile(r"cinematic|launch|announcement|reveal", re.I)
        penalize = re.compile(r"gameplay trailer|let's play|walkthrough", re.I)

    skip = re.compile(
        r"reaction|reacts|ranking|tier list|walkthrough full|movie recap|"
        r"how to download|hack|cheat|mod apk|tips and tricks|guide video|"
        r"funny moments|compilation|livestream|podcast|review only",
        re.I,
    )

    best: list[tuple[int, str]] = []
    seen: set[str] = set()
    for query in queries:
        for vid, title in _yt_candidates(query):
            if vid in seen:
                continue
            seen.add(vid)
            if skip.search(title):
                continue
            if not title_matches_game(title, game):
                continue
            if penalize.search(title) and not prefer.search(title):
                continue
            score = 0
            if prefer.search(title):
                score += 5
            if "official" in title.lower():
                score += 3
            if primary.lower() in title.lower():
                score += 2
            if trailer_type == "gameplay" and "gameplay" in title.lower():
                score += 4
            if trailer_type == "gameplay" and "no commentary" in title.lower():
                score += 3
            if trailer_type == "gameplay" and re.search(r"\b4k\b", title, re.I):
                score += 2
            best.append((score, vid))

    if not best:
        return None
    best.sort(key=lambda x: -x[0])
    return f"https://www.youtube.com/watch?v={best[0][1]}"


def _search_scene_gameplay(game: str, headline: str, narration: str) -> str | None:
    """Find gameplay video matching this specific scene's game + topic."""
    from video_creator.game_assets import scene_keywords

    primary = footage_search_queries(game)[0]
    kw = scene_keywords(headline, narration)[:2]
    topic = " ".join(kw) if kw else headline.split()[-1] if headline else ""
    queries = [
        f"ytsearch12:{primary} {topic} gameplay no commentary",
        f"ytsearch10:{primary} {headline[:30]} gameplay",
        f"ytsearch10:{primary} official gameplay",
    ]
    skip = re.compile(r"compilation|top 10|tier list|react|ranking all", re.I)
    best: list[tuple[int, str]] = []
    seen: set[str] = set()
    for query in queries:
        for vid, title in _yt_candidates(query):
            if vid in seen or skip.search(title):
                continue
            seen.add(vid)
            if not title_matches_game(title, game):
                continue
            score = 10
            if "gameplay" in title.lower():
                score += 5
            if "no commentary" in title.lower():
                score += 3
            if topic and topic.lower() in title.lower():
                score += 4
            best.append((score, vid))
    if not best:
        return _search_trailer_by_type(game, "gameplay")
    best.sort(key=lambda x: -x[0])
    return f"https://www.youtube.com/watch?v={best[0][1]}"


def _download_youtube_trailer(
    url: str,
    dest: Path,
    trailer_dir: Path,
    is_short: bool = False,
) -> Path | None:
    global _yt_download_blocked
    if _yt_download_blocked:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    for partial in trailer_dir.glob(f"{dest.stem}*"):
        if partial != dest:
            partial.unlink(missing_ok=True)

    def _attempt(fmt: str) -> subprocess.CompletedProcess:
        return _run(
            [
                *_yt_dlp_base_args(with_auth=True),
                "-f", fmt,
                "--merge-output-format", "mp4",
                "--no-playlist",
                "-o", str(dest),
                url,
            ],
            timeout=900 if not is_short else 600,
        )

    out = _attempt(_yt_format(is_short))
    if out.returncode != 0:
        err_text = (out.stderr or out.stdout or "").lower()
        if "format is not available" in err_text or "requested format" in err_text:
            h = getattr(config, "YT_MAX_HEIGHT", 1080) if is_short else getattr(
                config, "YT_MAX_HEIGHT_LONG", 1440,
            )
            cap = getattr(config, "YT_MAX_FILESIZE", "400M") if is_short else getattr(
                config, "YT_MAX_FILESIZE_LONG", "800M",
            )
            out = _attempt(
                f"bv*[height<={h}][filesize<{cap}]+ba/"
                f"bv*[height<={h}][filesize<{cap}]/"
                f"b[height<={h}][filesize<{cap}]"
            )

    if out.returncode != 0:
        err = (out.stderr or out.stdout or "").strip().splitlines()
        hint = err[-1][:120] if err else "unknown error"
        if "bot" in hint.lower() or "sign in" in hint.lower():
            _yt_download_blocked = True
            print(
                "      ⚠️  YouTube blocked download — run ./export_youtube_cookies.sh"
            )
        elif "format is not available" not in hint.lower():
            print(f"      ⚠️  YouTube download failed: {hint}")
    if not dest.exists() or dest.stat().st_size < 50_000:
        candidates = [
            p for p in trailer_dir.glob(f"{dest.stem}*")
            if p.suffix in (".mp4", ".mkv", ".webm") and p.stat().st_size > 50_000
        ]
        if candidates:
            picked = max(candidates, key=lambda p: p.stat().st_size)
            if picked != dest:
                _run(
                    [
                        "ffmpeg", "-y", "-i", str(picked),
                        "-c:v", "libx264", "-c:a", "aac",
                        "-movflags", "+faststart", str(dest),
                    ],
                    timeout=300,
                )
                picked.unlink(missing_ok=True)
    if not dest.exists() or dest.stat().st_size < 50_000:
        dest.unlink(missing_ok=True)
        return None
    if out.returncode != 0:
        dest.unlink(missing_ok=True)
        return None
    max_mb = 450 if is_short else 850
    size_mb = dest.stat().st_size / 1_000_000
    if size_mb > max_mb:
        print(f"      ⚠️  YouTube clip too large ({size_mb:.0f}MB) — skipping")
        dest.unlink(missing_ok=True)
        return None
    return dest


def _gameplay_url_candidates(
    game: str,
    headline: str = "",
    narration: str = "",
) -> list[str]:
    """YouTube URLs that look like real in-game footage."""
    primary = footage_search_queries(game)[0]
    url_candidates: list[str] = []
    scene_url = _search_scene_gameplay(game, headline, narration) if headline or narration else None
    if scene_url:
        url_candidates.append(scene_url)
    main = _search_trailer_by_type(game, "gameplay")
    if main and main not in url_candidates:
        url_candidates.append(main)
    for q in (
        f"ytsearch10:{primary} gameplay no commentary 4k",
        f"ytsearch8:{primary} multiplayer gameplay",
        f"ytsearch8:{primary} online gameplay pc",
    ):
        for vid, title in _yt_candidates(q):
            if not title_matches_game(title, game):
                continue
            if re.search(r"gameplay|no commentary|multiplayer|online", title, re.I):
                url = f"https://www.youtube.com/watch?v={vid}"
                if url not in url_candidates:
                    url_candidates.append(url)
                break
    return url_candidates


def _try_stock_gameplay_slot(
    game: str,
    headline: str,
    narration: str,
    work_dir: Path,
    trailer_dir: Path,
    slug: str,
    pool: list[Path],
    is_short: bool,
) -> None:
    """Pexels/Pixabay game-matched clips — real gameplay when YouTube is blocked."""
    if not getattr(config, "GAME_FOOTAGE_FALLBACK", True):
        return
    from video_creator.video_providers import fetch_game_footage_fallback

    idx = len(pool)
    stock_raw, query, provider = fetch_game_footage_fallback(
        game, headline, narration, idx, work_dir, is_short,
    )
    if not stock_raw or not stock_raw.exists():
        return
    dest = trailer_dir / f"{slug}_stock_{idx}.mp4"
    if stock_raw.resolve() != dest.resolve():
        dest.write_bytes(stock_raw.read_bytes())
    if dest.stat().st_size > 50_000:
        pool.append(dest)
        print(f"      🎮 Gameplay source ({provider}): {query}")


def ensure_gameplay_pool(
    game: str,
    work_dir: Path,
    headline: str = "",
    narration: str = "",
    is_short: bool = False,
) -> list[Path]:
    """Download gameplay sources for a specific game (scoped to this video)."""
    slug = _slug(game)
    cache_key = f"{work_dir.resolve()}:{slug}:pool"
    if cache_key in _gameplay_pool_cache:
        return _gameplay_pool_cache[cache_key]

    trailer_dir = work_dir / "trailers"
    trailer_dir.mkdir(parents=True, exist_ok=True)
    pool: list[Path] = []
    seen_urls: set[str] = set()
    primary = footage_search_queries(game)[0]
    style = _footage_style()

    if style == "cinematic":
        steam = trailer_dir / f"{slug}_steam.mp4"
        if fetch_steam_trailer(game, steam):
            pool.append(steam)
            print(f"      🎬 Cinematic source (Steam): {primary}")

    if style in ("gameplay", "mix"):
        for url in _gameplay_url_candidates(game, headline, narration):
            if not url or url in seen_urls or len(pool) >= _pool_size():
                continue
            seen_urls.add(url)
            dest = trailer_dir / f"{slug}_gp_{len(pool)}.mp4"
            if dest.exists() and dest.stat().st_size > 50_000:
                pool.append(dest)
                continue
            downloaded = _download_youtube_trailer(url, dest, trailer_dir, is_short=is_short)
            if downloaded:
                pool.append(downloaded)
                print(f"      🎮 Gameplay source (YouTube): {url.split('v=')[-1]}")

        while len(pool) < _pool_size():
            before = len(pool)
            _try_stock_gameplay_slot(
                game, headline, narration, work_dir, trailer_dir, slug, pool, is_short,
            )
            if len(pool) == before:
                break

    if not pool:
        steam = trailer_dir / f"{slug}_steam.mp4"
        if fetch_steam_trailer(game, steam):
            pool.append(steam)
            label = "fallback" if style == "gameplay" else "source"
            print(f"      🎬 Cinematic trailer {label} (Steam): {primary}")

    if pool:
        _gameplay_pool_cache[cache_key] = pool
    return pool


def ensure_short_trailers(game: str, work_dir: Path) -> dict[str, Path]:
    """Gameplay/cinematic sources for Shorts — gameplay-first by default."""
    slug = _slug(game)
    cache_key = f"{work_dir.resolve()}:{slug}:short:pair"
    if cache_key in _short_pair_cache:
        return _short_pair_cache[cache_key]

    paths: dict[str, Path] = {}
    style = _footage_style()

    if style == "gameplay":
        pool = ensure_gameplay_pool(game, work_dir, is_short=True)
        for i, p in enumerate(pool):
            paths[f"gameplay{i}" if i else "gameplay"] = p
        if pool:
            _short_pair_cache[cache_key] = paths
            return paths

    trailer_dir = work_dir / "trailers"
    trailer_dir.mkdir(parents=True, exist_ok=True)
    meta_path = trailer_dir / f"{slug}_short_meta.json"
    meta: dict = {"game": game, "style": style}

    types = ("gameplay", "cinematic") if style == "mix" else (style,)
    for ttype in types:
        if ttype not in ("gameplay", "cinematic"):
            ttype = "gameplay"
        dest = trailer_dir / f"{slug}_short_{ttype}.mp4"
        if dest.exists() and dest.stat().st_size > 50_000:
            paths[ttype] = dest
            continue
        url = _search_trailer_by_type(game, ttype)
        if not url:
            continue
        downloaded = _download_youtube_trailer(url, dest, trailer_dir, is_short=True)
        if downloaded:
            paths[ttype] = downloaded
            meta[f"{ttype}_url"] = url
            print(f"      🎬 Short trailer ({ttype}): {url.split('v=')[-1]}")

    if meta_path.exists() and not paths:
        try:
            for ttype in ("gameplay", "cinematic"):
                dest = trailer_dir / f"{slug}_short_{ttype}.mp4"
                if dest.exists():
                    paths[ttype] = dest
        except json.JSONDecodeError:
            pass

    if paths:
        meta_path.write_text(
            json.dumps({**meta, "available": list(paths.keys())}, indent=2),
            encoding="utf-8",
        )
        _short_pair_cache[cache_key] = paths
    return paths


def _pick_from_pair(pair: dict[str, Path], scene_index: int, gameplay: bool) -> Path | None:
    if not pair:
        return None
    if gameplay:
        keys = [k for k in pair if k.startswith("gameplay")]
        if keys:
            return pair[keys[scene_index % len(keys)]]
        return pair.get("gameplay")
    return pair.get("cinematic") or pair.get("gameplay")


def ensure_trailer(game: str, work_dir: Path, is_short: bool = False) -> Path | None:
    if not getattr(config, "USE_TRAILER_CLIPS", True) or not _yt_dlp_available():
        return None

    if is_short:
        pair = ensure_short_trailers(game, work_dir)
        return _pick_from_pair(pair, 0, True) or _pick_from_pair(pair, 0, False)

    key = _slug(game)
    if key in _trailer_cache and _trailer_cache[key].exists():
        return _trailer_cache[key]

    if _footage_style() == "gameplay":
        pool = ensure_gameplay_pool(game, work_dir, is_short=is_short)
        if pool:
            _trailer_cache[key] = pool[0]
            return pool[0]

    trailer_dir = work_dir / "trailers"
    dest = trailer_dir / f"{key}_trailer.mp4"
    if dest.exists() and dest.stat().st_size > 50_000:
        _trailer_cache[key] = dest
        return dest

    url = _search_trailer_by_type(game, "gameplay") or _search_trailer_by_type(game, "cinematic")
    if url:
        got = _download_youtube_trailer(url, dest, trailer_dir, is_short=is_short)
        if got:
            _trailer_cache[key] = got
            print("      🎬 Trailer source: YouTube (long)")
            return got

    steam = fetch_steam_trailer(game, dest)
    if steam:
        _trailer_cache[key] = steam
        print(f"      🎬 Trailer source: Steam ({game})")
        return steam
    return None


def _scene_start(
    scene_index: int,
    trailer_dur: float,
    clip_dur: float,
    is_short: bool = False,
    gameplay: bool = False,
) -> float:
    usable = max(trailer_dur - clip_dur - 2, 5)
    if is_short:
        intro_skip = 5.0 if gameplay else 16.0
        intro_skip = min(intro_skip, usable * 0.15)
        step = 8.0 + (scene_index % 3) * 1.5
        base = intro_skip + scene_index * step
        return max(0.0, min(base, usable))
    base = 5.0 + (scene_index * 7.5) % usable
    if scene_index % 3 == 1:
        base = min(base + usable * 0.35, usable)
    elif scene_index % 3 == 2:
        base = min(base + usable * 0.65, usable)
    return max(0.0, min(base, usable))


def extract_trailer_segment(
    trailer: Path,
    scene_index: int,
    work_dir: Path,
    duration: float,
    is_short: bool,
    tag: str = "trailer",
    gameplay: bool = False,
    game: str = "",
) -> Path | None:
    out = work_dir / "trailers" / f"scene_{scene_index:02d}_{tag}.mp4"
    out.unlink(missing_ok=True)

    trailer_dur = _probe_duration(trailer)
    clip_dur = max(duration, 2.5)
    seek_idx = _next_game_seek_index(work_dir, game) if game else scene_index
    start = _scene_start(
        seek_idx,
        trailer_dur,
        clip_dur,
        is_short=is_short,
        gameplay=gameplay,
    )

    if is_short:
        from video_creator.video_fit import encode_shorts_clip
        ok = encode_shorts_clip(trailer, out, duration=clip_dur + 0.5, seek=start)
        return out if ok else None

    from video_creator.video_fit import fill_frame_filter, ffmpeg_video_args
    try:
        _run(
            [
                "ffmpeg", "-y", "-ss", str(start), "-i", str(trailer),
                "-t", str(clip_dur + 0.5),
                "-vf", fill_frame_filter(False),
                "-an", *ffmpeg_video_args(is_short),
                str(out),
            ],
            timeout=180 if not is_short else 120,
        )
        return out if out.exists() and out.stat().st_size > 5000 else None
    except subprocess.TimeoutExpired:
        return None


def render_short_trailer_clip(
    game: str,
    scene_index: int,
    work_dir: Path,
    duration: float,
) -> Path | None:
    """Re-cut from gameplay pool / trailers for exact narration length."""
    use_gameplay = _scene_uses_gameplay(scene_index)
    if _footage_style() == "gameplay":
        pool = ensure_gameplay_pool(game, work_dir, is_short=True)
        if pool:
            trailer = pool[scene_index % len(pool)]
            return extract_trailer_segment(
                trailer, scene_index, work_dir, duration, True,
                tag=f"gp{scene_index % len(pool)}", gameplay=True, game=game,
            )
    pair = ensure_short_trailers(game, work_dir)
    trailer = _pick_from_pair(pair, scene_index, use_gameplay)
    if not trailer:
        return None
    tag = "gameplay" if use_gameplay else "cinematic"
    return extract_trailer_segment(
        trailer, scene_index, work_dir, duration, True, tag=tag, gameplay=use_gameplay, game=game,
    )


def cleanup_trailer_downloads(work_dir: Path) -> None:
    """Remove full-length gameplay downloads after scene clips are cut (saves disk)."""
    trailer_dir = work_dir / "trailers"
    if not trailer_dir.is_dir():
        return
    for pattern in ("*_gp_*.mp4", "*_short_*.mp4", "*_steam.mp4", "*_trailer.mp4"):
        for path in trailer_dir.glob(pattern):
            try:
                if path.stat().st_size > 20_000_000:
                    path.unlink(missing_ok=True)
            except OSError:
                pass


def fetch_trailer_for_scene(
    game: str,
    scene_index: int,
    work_dir: Path,
    is_short: bool,
    duration: float = 6.0,
    headline: str = "",
    narration: str = "",
) -> Path | None:
    use_gameplay = _scene_uses_gameplay(scene_index)

    if _footage_style() == "gameplay":
        pool = ensure_gameplay_pool(
            game, work_dir, headline=headline, narration=narration, is_short=is_short,
        )
        if pool:
            seek_idx = _game_seek_counters.get(_work_key(work_dir, game), 0)
            trailer = pool[seek_idx % len(pool)]
            print(f"      🎮 Matched footage: {game} (scene {scene_index + 1})")
            return extract_trailer_segment(
                trailer,
                scene_index,
                work_dir,
                duration,
                is_short=is_short,
                tag=f"{_slug(game)}_{seek_idx}",
                gameplay=True,
                game=game,
            )

    if is_short:
        pair = ensure_short_trailers(game, work_dir)
        if not pair:
            return None
        trailer = _pick_from_pair(pair, scene_index, use_gameplay)
        if not trailer:
            return None
        label = "Gameplay" if use_gameplay else "Cinematic"
        print(f"      🎮 {label} clip ({game})")
        return extract_trailer_segment(
            trailer,
            scene_index,
            work_dir,
            duration,
            is_short=True,
            tag="gameplay" if use_gameplay else "cinematic",
            gameplay=use_gameplay,
            game=game,
        )

    pool = (
        ensure_gameplay_pool(
            game, work_dir, headline=headline, narration=narration, is_short=False,
        )
        if use_gameplay else []
    )
    trailer = pool[_game_seek_counters.get(_work_key(work_dir, game), 0) % len(pool)] if pool else ensure_trailer(game, work_dir, is_short=False)
    if not trailer:
        return None
    print(f"      🎬 Matched footage: {game} (scene {scene_index + 1})")
    return extract_trailer_segment(
        trailer, scene_index, work_dir, duration, is_short=False,
        gameplay=use_gameplay, game=game,
    )