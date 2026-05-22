"""Rota POST /api/upload-song: download/upload, corte de áudio, geração de LRC."""
from __future__ import annotations

import json
import logging
import shutil
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from state import SONGS_DIR
from utils.prepare import run_reinstall_song
from utils.text import normalize_lyrics_text, slugify
from utils.youtube import get_youtube_video_info

logger = logging.getLogger(__name__)
router = APIRouter()

def _build_meta(form: dict) -> dict:
    """Estrutura `meta.json` salvo junto da música para reprodução simples."""
    return {
        "meta": {
            "title": form["title"],
            "artist": form["artist"],
            "language": form["language"],
            "slug": form.get("slug") or form["title"].lower().replace(" ", "-"),
        },
        "audio": {
            "youtube_vocal_url": form["youtube_vocal_url"],
            "youtube_backing_url": form["youtube_backing_url"],
        },
        "lyrics": {
            "plain_lyrics": form.get("plain_lyrics"),
        },
        "status": {
            "has_vocal_file": form["vocal_file"] is not None and form["vocal_file"].filename != "",
            "has_backing_file": form["backing_file"] is not None and form["backing_file"].filename != "",
            "has_lrc_file": form["lrc_file"] is not None and form["lrc_file"].filename != "",
        }
    }


@router.get("/api/youtube-metadata")
async def get_youtube_metadata(url: str):
    """Obtém de forma rápida (metadados apenas) o artista e título do vídeo do YouTube."""
    if not url or not url.strip():
        raise HTTPException(status_code=400, detail="Por favor, forneça uma URL válida do YouTube.")
    
    info = await get_youtube_video_info(url.strip())
    return info


@router.post("/api/upload-song")
async def upload_song(
    title: str = Form(...),
    artist: str = Form(...),
    language: str = Form("en"),
    vocal_file: Optional[UploadFile] = File(None),
    backing_file: Optional[UploadFile] = File(None),
    lrc_file: Optional[UploadFile] = File(None),
    youtube_vocal_url: Optional[str] = Form(None),
    youtube_backing_url: Optional[str] = Form(None),
    plain_lyrics: Optional[str] = Form(None),
    align_lyrics: bool = Form(False),
):
    try:
        slug = slugify(f"{title}-{artist}")
        song_dir = SONGS_DIR / slug
        song_dir.mkdir(parents=True, exist_ok=True)

        # Normaliza line endings logo na entrada — evita que `\r\n\r\n` do
        # Windows propague para meta.json e lyrics.txt e quebre a leitura
        # no Linux/Mac (gera ^M e duplica linhas vazias).
        plain_lyrics = normalize_lyrics_text(plain_lyrics) or None

        # 1. Build and save minimal meta.json
        meta = _build_meta(locals())
        with open(song_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=4, ensure_ascii=False)

        # 2. Save uploaded files if provided
        vocal_path = song_dir / "vocal.mp3"
        if vocal_file and vocal_file.filename:
            with open(vocal_path, "wb") as f:
                shutil.copyfileobj(vocal_file.file, f)

        if backing_file and backing_file.filename:
            with open(song_dir / "backing_track.mp3", "wb") as f:
                shutil.copyfileobj(backing_file.file, f)

        if lrc_file and lrc_file.filename:
            lrc_content = await lrc_file.read()
            try:
                lrc_text = lrc_content.decode("utf-8")
            except UnicodeDecodeError:
                lrc_text = lrc_content.decode("latin-1")
            clean_lines = [line.strip() for line in lrc_text.splitlines() if line.strip()]
            with open(song_dir / "lyrics.lrc", "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(clean_lines))

        if plain_lyrics:
            # `plain_lyrics` já foi normalizado em normalize_lyrics_text acima.
            with open(song_dir / "lyrics.txt", "w", encoding="utf-8", newline="\n") as f:
                f.write(plain_lyrics + "\n")

        # Pipeline completo (download YT + Demucs + Whisper + alinhamento de
        # letra) **menos** `prepare_song`. O usuário precisa aprovar o LRC
        # gerado no editor antes de finalizar — o `segments.json` será gerado
        # depois, em `/api/save-lyrics`, sobre o LRC editado pelo usuário.
        success = await run_reinstall_song(
            str(song_dir),
            language=language,
            clean_existing=False,
            skip_prepare_song=True,
            align_lyrics=align_lyrics,
        )
        if not success:
            raise HTTPException(status_code=500, detail="Falha ao preparar áudio e LRC. Verifique os logs do servidor.")

        # Lê o lyrics.lrc gerado para devolver como draft ao frontend, que
        # vai abrir o editor para o usuário aprovar/ajustar.
        lrc_path = song_dir / "lyrics.lrc"
        if not lrc_path.exists():
            raise HTTPException(status_code=500, detail="Pipeline não gerou lyrics.lrc. Verifique os logs.")

        draft_lrc = lrc_path.read_text(encoding="utf-8")

        # Detecta se o alinhamento caiu no fallback (muitas linhas com [??:??.??]
        # ou alta proporção de linhas — sinaliza para o usuário no toast).
        orphan_lines = sum(1 for line in draft_lrc.splitlines() if line.startswith("[??:??.??]"))

        return {
            "success": True,
            "lyrics_status": "draft",
            "draft_lrc": draft_lrc,
            "slug": slug,
            "orphan_lines": orphan_lines,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao adicionar música: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
