"""Busca letras de música via LRCLIB (primário) e Lyrics.ovh (fallback).

Com a duração do áudio, o LRCLIB é consultado pelo `/api/search` e vence a
versão de duração mais próxima: a mesma música costuma ter dezenas de entradas
(estúdio, remaster, ao vivo, o álbum inteiro numa faixa só) e a sincronia de
uma não serve para a outra. LRC de versão longe demais não volta (só o texto).
"""
from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Optional

from rapidfuzz import fuzz
from unidecode import unidecode

logger = logging.getLogger(__name__)

LRCLIB_API = "https://lrclib.net/api/get"
LRCLIB_SEARCH_API = "https://lrclib.net/api/search"
OVH_API = "https://api.lyrics.ovh/v1"
REQUEST_TIMEOUT = 10
USER_AGENT = "KaraokeAI/1.0"

# Versão do LRCLIB aceita para a sincronia: até isso de diferença de duração.
# Acima disso é outra versão (ao vivo, edit, estendida): vale só o texto, e o
# alinhamento acha os tempos no áudio.
SYNC_MAX_DURATION_DIFF_SEC = 20.0
# nomes que o /api/search devolve e ainda são a mesma música
TRACK_MIN_SIMILARITY = 85
ARTIST_MIN_SIMILARITY = 70


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _name_key(text: str) -> str:
    """Nome para comparar: sem acento, sem "(Remastered 2009)", "- Live" etc."""
    text = unidecode(text or "").lower()
    text = re.sub(r"[\(\[].*?[\)\]]", " ", text)
    text = re.sub(r"\s+-\s+.*$", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def pick_lrclib_candidate(candidates: list, artist: str, track: str, duration: float) -> Optional[dict]:
    """Entrada do /api/search que serve para um áudio de `duration` segundos.

    Só a mesma música (nome parecido, não instrumental). Entre as sincronizadas,
    a de duração mais próxima. Nenhuma sincronizada perto: a de duração mais
    próxima com letra, sem o LRC (a sincronia seria de outra versão).
    """
    want_track, want_artist = _name_key(track), _name_key(artist)
    same = []
    for c in candidates or []:
        if not isinstance(c, dict) or c.get("instrumental"):
            continue
        if not (c.get("plainLyrics") or "").strip():
            continue
        if fuzz.token_set_ratio(_name_key(c.get("trackName")), want_track) < TRACK_MIN_SIMILARITY:
            continue
        if fuzz.token_set_ratio(_name_key(c.get("artistName")), want_artist) < ARTIST_MIN_SIMILARITY:
            continue
        diff = abs(float(c["duration"]) - duration) if c.get("duration") else float("inf")
        same.append((diff, c))
    if not same:
        return None
    synced = sorted((x for x in same if (x[1].get("syncedLyrics") or "").strip()), key=lambda x: x[0])
    if synced and synced[0][0] <= SYNC_MAX_DURATION_DIFF_SEC:
        diff, best = synced[0]
        return {**best, "durationDiff": diff}
    diff, best = min(same, key=lambda x: x[0])
    return {**best, "syncedLyrics": None, "durationDiff": diff}


def search_lyrics_lrclib(artist: str, track: str, duration: float) -> Optional[dict]:
    """LRCLIB /api/search + `pick_lrclib_candidate`. Mesmo formato de `fetch_lyrics_lrclib`."""
    params = urllib.parse.urlencode({"artist_name": artist, "track_name": track})
    url = f"{LRCLIB_SEARCH_API}?{params}"
    logger.info(f"[LyricsFetcher] LRCLIB search: GET {url} (áudio de {duration:.1f}s)")
    try:
        candidates = _get_json(url)
    except Exception as e:
        logger.warning(f"[LyricsFetcher] LRCLIB search falhou: {e}")
        return None
    best = pick_lrclib_candidate(candidates, artist, track, duration)
    if not best:
        logger.info("[LyricsFetcher] LRCLIB search: nenhuma versão da mesma música.")
        return None
    synced = (best.get("syncedLyrics") or "").strip() or None
    logger.info(
        "[LyricsFetcher] LRCLIB search: %d candidatos, escolhida id=%s (%ss, diferença %.1fs), syncedLyrics=%s",
        len(candidates or []), best.get("id"), best.get("duration"), best["durationDiff"],
        "presente" if synced else "ausente (versão longe demais)",
    )
    return {
        "plainLyrics": best["plainLyrics"].strip(),
        "syncedLyrics": synced,
        "source": "lrclib",
        "duration": best.get("duration"),
    }


def fetch_lyrics_lrclib(artist: str, track: str) -> Optional[dict]:
    """Busca letra no LRCLIB. Retorna dict com plainLyrics e syncedLyrics (pode ser None)."""
    params = urllib.parse.urlencode({
        "artist_name": artist,
        "track_name": track,
    })
    url = f"{LRCLIB_API}?{params}"
    logger.info(f"[LyricsFetcher] LRCLIB: GET {url}")

    try:
        data = _get_json(url)
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
        "duration": data.get("duration"),
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


def fetch_lyrics(artist: str, track: str, duration: float | None = None) -> Optional[dict]:
    """Orquestra a busca: LRCLIB primeiro, depois Lyrics.ovh como fallback.

    `duration` (segundos do áudio que vai tocar): escolhe a versão pelo
    `/api/search`; sem resultado lá, cai no `/api/get` de sempre.
    """
    result = search_lyrics_lrclib(artist, track, duration) if duration else None
    if not result:
        result = fetch_lyrics_lrclib(artist, track)
        if result and duration and result.get("duration") and result.get("syncedLyrics") \
                and abs(float(result["duration"]) - duration) > SYNC_MAX_DURATION_DIFF_SEC:
            logger.info("[LyricsFetcher] LRC do /api/get é de outra versão (%ss × %.1fs): só o texto",
                        result["duration"], duration)
            result = {**result, "syncedLyrics": None}
    if result:
        return result
    logger.info("[LyricsFetcher] LRCLIB sem resultado, tentando Lyrics.ovh...")
    return fetch_lyrics_ovh(artist, track)
