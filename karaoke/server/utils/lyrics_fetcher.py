"""Busca letras de música via LRCLIB (primário) e Lyrics.ovh (fallback)."""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

LRCLIB_API = "https://lrclib.net/api/get"
OVH_API = "https://api.lyrics.ovh/v1"
REQUEST_TIMEOUT = 10


def fetch_lyrics_lrclib(artist: str, track: str) -> Optional[dict]:
    """Busca letra no LRCLIB. Retorna dict com plainLyrics e syncedLyrics (pode ser None)."""
    params = urllib.parse.urlencode({
        "artist_name": artist,
        "track_name": track,
    })
    url = f"{LRCLIB_API}?{params}"
    logger.info(f"[LyricsFetcher] LRCLIB: GET {url}")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "KaraokeAI/1.0"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"[LyricsFetcher] LRCLIB falhou: {e}")
        return None

    plain = (data.get("plainLyrics") or "").strip()
    synced = (data.get("syncedLyrics") or "").strip() or None

    if not plain:
        logger.info("[LyricsFetcher] LRCLIB retornou mas sem plainLyrics.")
        return None

    logger.info(
        "[LyricsFetcher] LRCLIB sucesso: plainLyrics=%d chars, syncedLyrics=%s",
        len(plain), "presente" if synced else "ausente",
    )
    return {
        "plainLyrics": plain,
        "syncedLyrics": synced,
        "source": "lrclib",
    }


def fetch_lyrics_ovh(artist: str, track: str) -> Optional[dict]:
    """Busca letra no Lyrics.ovh (fallback). Retorna apenas plainLyrics, sem syncedLyrics."""
    safe_artist = urllib.parse.quote(artist, safe="")
    safe_track = urllib.parse.quote(track, safe="")
    url = f"{OVH_API}/{safe_artist}/{safe_track}"
    logger.info(f"[LyricsFetcher] Lyrics.ovh: GET {url}")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "KaraokeAI/1.0"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"[LyricsFetcher] Lyrics.ovh falhou: {e}")
        return None

    plain = (data.get("lyrics") or "").strip()
    if not plain:
        logger.info("[LyricsFetcher] Lyrics.ovh retornou mas sem lyrics.")
        return None

    logger.info("[LyricsFetcher] Lyrics.ovh sucesso: plainLyrics=%d chars", len(plain))
    return {
        "plainLyrics": plain,
        "syncedLyrics": None,
        "source": "ovh",
    }


def fetch_lyrics(artist: str, track: str) -> Optional[dict]:
    """Orquestra a busca: LRCLIB primeiro, depois Lyrics.ovh como fallback."""
    result = fetch_lyrics_lrclib(artist, track)
    if result:
        return result
    logger.info("[LyricsFetcher] LRCLIB sem resultado, tentando Lyrics.ovh...")
    return fetch_lyrics_ovh(artist, track)
