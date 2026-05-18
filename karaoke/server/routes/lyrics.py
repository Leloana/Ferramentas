"""Rotas de leitura/edição manual de letras LRC."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Response

from utils.prepare import run_prepare_song

logger = logging.getLogger(__name__)
router = APIRouter()

SONGS_DIR = Path(__file__).resolve().parent.parent / "songs"


def _no_cache(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"


@router.get("/api/get-lyrics")
async def get_lyrics(slug: str, response: Response):
    _no_cache(response)
    try:
        song_dir = SONGS_DIR / slug
        lrc_path = song_dir / "lyrics.lrc"
        if not lrc_path.exists():
            return {"success": False, "lyrics": "", "language": "en"}

        with open(lrc_path, "r", encoding="utf-8") as f:
            content = f.read()

        clean_lines = [line.strip() for line in content.splitlines() if line.strip()]
        content = "\n".join(clean_lines)

        # Idioma vem do primeiro segmento processado por prepare_song
        language = "en"
        segments_path = song_dir / "segments.json"
        if segments_path.exists():
            try:
                with open(segments_path, "r", encoding="utf-8") as sf:
                    segs = json.load(sf)
                    if segs:
                        language = segs[0].get("language", "en")
            except Exception as e:
                logger.debug(f"Falha ao ler language de segments.json: {e}")

        return {"success": True, "lyrics": content, "language": language}
    except Exception as e:
        logger.error(f"Erro ao obter letras: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/save-lyrics")
async def save_lyrics(
    slug: str = Form(...),
    language: str = Form("en"),
    lyrics_lrc: str = Form(...),
):
    try:
        song_dir = SONGS_DIR / slug
        if not song_dir.exists():
            raise HTTPException(status_code=404, detail="Diretório da música não encontrado")

        clean_lines = [line.strip() for line in lyrics_lrc.splitlines() if line.strip()]
        lrc_path = song_dir / "lyrics.lrc"
        with open(lrc_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(clean_lines))

        run_prepare_song(str(song_dir), language)
        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao salvar letras e processar alinhamento: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
