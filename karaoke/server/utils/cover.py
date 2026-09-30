"""Capa do álbum de uma música, guardada em `server/songs/<slug>/cover.jpg`.

Ordem: arquivo já salvo → arte do álbum na busca do iTunes → miniatura do vídeo
do YouTube do meta.json. Sem nada, grava `cover.none` para não repetir a busca
a cada abertura do lobby (apague o arquivo para tentar de novo).
Só usa a biblioteca padrão (mesmo esquema do lyrics_fetcher).
"""
from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 6
COVER_NAME = "cover.jpg"
MISS_NAME = "cover.none"
_YT_ID_RE = re.compile(r"(?:v=|youtu\.be/|/embed/|/shorts/)([\w-]{11})")


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Karaoke/1.0"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return resp.read()


def _itunes_artwork(artist: str, title: str) -> str | None:
    term = f"{artist} {title}".strip()
    if not term:
        return None
    query = urllib.parse.urlencode({"term": term, "entity": "song", "limit": 1})
    data = json.loads(_get(f"https://itunes.apple.com/search?{query}").decode("utf-8"))
    results = data.get("results") or []
    art = results[0].get("artworkUrl100") if results else None
    # a URL aceita qualquer tamanho no nome do arquivo
    return art.replace("100x100bb", "600x600bb") if art else None


def youtube_id(url: str | None) -> str | None:
    match = _YT_ID_RE.search(url or "")
    return match.group(1) if match else None


def _read_meta(song_dir: Path) -> dict:
    try:
        return json.loads((song_dir / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def find_cover(song_dir: Path) -> Path | None:
    """Devolve o caminho da capa, baixando na primeira vez. Bloqueante (use em thread)."""
    cover = song_dir / COVER_NAME
    if cover.exists():
        return cover
    if (song_dir / MISS_NAME).exists() or not song_dir.is_dir():
        return None

    meta = _read_meta(song_dir)
    info = meta.get("meta") or {}
    audio = meta.get("audio") or {}
    candidates = []
    had_error = False
    try:
        art = _itunes_artwork(info.get("artist") or "", info.get("title") or "")
        if art:
            candidates.append(art)
    except Exception as e:  # rede fora, API mudou... a capa é opcional
        logger.info(f"[Capa] iTunes indisponível para {song_dir.name}: {e}")
        had_error = True
    vid = youtube_id(audio.get("youtube_vocal_url") or audio.get("youtube_backing_url"))
    if vid:
        candidates.append(f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg")

    for url in candidates:
        try:
            cover.write_bytes(_get(url))
            return cover
        except Exception as e:
            logger.info(f"[Capa] Falha ao baixar {url}: {e}")
            had_error = True

    if had_error:
        return None  # tenta de novo na próxima vez
    try:
        (song_dir / MISS_NAME).write_text("", encoding="utf-8")
    except OSError:
        pass
    return None
