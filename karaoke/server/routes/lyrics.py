"""Rotas de leitura/edição manual de letras LRC."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Response

from utils.prepare import run_prepare_song

from typing import Optional

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
        
        # Carrega o meta.json
        meta_content = ""
        meta_path = song_dir / "meta.json"
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                try:
                    meta_content = json.dumps(json.load(f), indent=4, ensure_ascii=False)
                except Exception:
                    f.seek(0)
                    meta_content = f.read()

        lrc_content = ""
        if lrc_path.exists():
            with open(lrc_path, "r", encoding="utf-8") as f:
                lrc_content = f.read()

        clean_lines = [line.strip() for line in lrc_content.splitlines() if line.strip()]
        lrc_content = "\n".join(clean_lines)

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

        return {"success": True, "lyrics": lrc_content, "language": language, "meta_json": meta_content}
    except Exception as e:
        logger.error(f"Erro ao obter letras: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/save-lyrics")
async def save_lyrics(
    slug: str = Form(...),
    language: str = Form("en"),
    lyrics_lrc: str = Form(...),
    meta_json: Optional[str] = Form(None),
):
    try:
        song_dir = SONGS_DIR / slug
        if not song_dir.exists():
            raise HTTPException(status_code=404, detail="Diretório da música não encontrado")

        # Salva o meta.json se fornecido
        if meta_json is not None and meta_json.strip():
            try:
                meta_data = json.loads(meta_json)
                if not isinstance(meta_data, dict):
                    raise ValueError("O JSON deve ser um objeto contendo chaves/valores.")
            except Exception as je:
                raise HTTPException(status_code=400, detail=f"Erro de sintaxe no meta.json: {je}")
            
            meta_path = song_dir / "meta.json"
            with open(meta_path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(meta_data, f, indent=4, ensure_ascii=False)
            
            meta_lang = None
            if "meta" in meta_data and isinstance(meta_data["meta"], dict):
                meta_lang = meta_data["meta"].get("language")
            if not meta_lang:
                meta_lang = meta_data.get("language")
            if meta_lang:
                language = meta_lang

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
