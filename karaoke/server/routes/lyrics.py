"""Rotas de leitura/edição manual de letras LRC."""
from __future__ import annotations

import json
import logging
import shutil
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Response

from state import SONGS_DIR
from utils.http import set_no_cache
from utils.prepare import run_prepare_song
from utils.text import normalize_lyrics_text, slugify

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/get-lyrics")
async def get_lyrics(slug: str, response: Response):
    set_no_cache(response)
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


@router.post("/api/save-meta")
async def save_meta(
    slug: str = Form(...),
    meta_json: str = Form(...),
):
    """Salva apenas o meta.json sem disparar o pipeline de alinhamento."""
    try:
        song_dir = SONGS_DIR / slug
        if not song_dir.exists():
            raise HTTPException(status_code=404, detail="Diretório da música não encontrado")

        if not meta_json.strip():
            raise HTTPException(status_code=400, detail="meta_json está vazio")

        try:
            meta_data = json.loads(meta_json)
            if not isinstance(meta_data, dict):
                raise ValueError("O JSON deve ser um objeto contendo chaves/valores.")
        except Exception as je:
            raise HTTPException(status_code=400, detail=f"Erro de sintaxe no meta.json: {je}")

        if isinstance(meta_data.get("lyrics"), dict):
            pl = meta_data["lyrics"].get("plain_lyrics")
            if isinstance(pl, str):
                meta_data["lyrics"]["plain_lyrics"] = normalize_lyrics_text(pl)

        meta_path = song_dir / "meta.json"
        with open(meta_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(meta_data, f, indent=4, ensure_ascii=False)

        # Renomeia a pasta se o título ou artista mudou
        title = (meta_data.get("meta") or {}).get("title") or meta_data.get("title", "")
        artist = (meta_data.get("meta") or {}).get("artist") or meta_data.get("artist", "")
        new_slug = slugify(f"{title}-{artist}") if (title and artist) else None

        if new_slug and new_slug != slug:
            new_dir = SONGS_DIR / new_slug
            if new_dir.exists():
                # Conflito: apaga a pasta antiga e mantém a existente
                shutil.rmtree(song_dir)
                logger.info(f"Conflito de slug: pasta antiga '{slug}' removida, mantida '{new_slug}'")
            else:
                song_dir.rename(new_dir)
                logger.info(f"Pasta renomeada de '{slug}' para '{new_slug}'")
            return {"success": True, "slug": new_slug}

        return {"success": True, "slug": slug}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao salvar meta.json: {e}", exc_info=True)
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

            # Normaliza `plain_lyrics` antes de persistir — evita que `\r\n` do
            # editor do usuário se infiltre no JSON e quebre o lyrics.txt depois.
            if isinstance(meta_data.get("lyrics"), dict):
                pl = meta_data["lyrics"].get("plain_lyrics")
                if isinstance(pl, str):
                    meta_data["lyrics"]["plain_lyrics"] = normalize_lyrics_text(pl)

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

        import asyncio
        await asyncio.to_thread(run_prepare_song, str(song_dir), language)
        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao salvar letras e processar alinhamento: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
