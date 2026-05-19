"""Rota POST /api/upload-song: download/upload, corte de áudio, geração de LRC."""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sys
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydub import AudioSegment

from state import SONGS_DIR, ffmpeg_bin_dir
from stt_engine import get_stt_engine
from utils.audio import vocal_to_float32_mono_16k
from utils.lrc_align import align_plain_lyrics, draft_lrc_from_whisper
from utils.prepare import run_prepare_song, run_reinstall_song
from utils.text import normalize_lyrics_text, slugify
from utils.whisper_params import TRANSCRIBE_KWARGS
from utils.youtube import download_youtube_audio, get_youtube_video_info

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
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    artist: str = Form(...),
    language: str = Form("en"),
    vocal_file: Optional[UploadFile] = File(None),
    backing_file: Optional[UploadFile] = File(None),
    lrc_file: Optional[UploadFile] = File(None),
    youtube_vocal_url: Optional[str] = Form(None),
    youtube_backing_url: Optional[str] = Form(None),
    plain_lyrics: Optional[str] = Form(None),
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

        # --- Caminho 1: usuário forneceu .lrc pronto ---
        if (song_dir / "lyrics.lrc").exists():
            background_tasks.add_task(run_reinstall_song, str(song_dir), language, False)
            return {"success": True, "lyrics_status": "ready", "slug": slug, "fallback_used": False}

        # --- Caminho 2: usuário forneceu letra plana → alinha em segundo plano ---
        if plain_lyrics and plain_lyrics.strip():
            background_tasks.add_task(run_reinstall_song, str(song_dir), language, False)
            return {"success": True, "lyrics_status": "ready", "slug": slug, "fallback_used": False}

        # --- Caminho 3: gera rascunho LRC só com Whisper para edição manual ---
        # Nesse caminho, precisamos gerar a transcrição no primeiro plano para abrir o editor LRC.
        # Por isso, precisamos garantir que o vocal.mp3 esteja disponível no disco.
        if not vocal_path.exists():
            if youtube_vocal_url and youtube_vocal_url.strip():
                logger.info(f"Baixando canal Vocal em primeiro plano para transcrição de rascunho: {youtube_vocal_url}")
                v_ok = await download_youtube_audio(youtube_vocal_url.strip(), vocal_path, ffmpeg_bin_dir)
                if not v_ok or not vocal_path.exists():
                    raise HTTPException(status_code=400, detail="Falha ao baixar o áudio Vocal do YouTube. Verifique a URL.")
            else:
                raise HTTPException(status_code=400, detail="Você precisa subir um arquivo local de áudio ou fornecer o link do YouTube.")

        logger.info("Nenhum arquivo LRC enviado. Transcrevendo vocal com o Whisper em primeiro plano...")
        stt = get_stt_engine()
        vocal_audio = AudioSegment.from_file(str(vocal_path))
        raw_data = vocal_to_float32_mono_16k(vocal_audio)
        segments, _info = stt.model.transcribe(
            raw_data,
            language=language,
            **TRANSCRIBE_KWARGS,
        )
        segments_list = list(segments)

        # Agenda a conclusão do processo em segundo plano (backing track Demucs, etc.)
        background_tasks.add_task(run_reinstall_song, str(song_dir), language, False)

        draft = draft_lrc_from_whisper(segments_list, title, artist)
        return {"success": True, "lyrics_status": "draft", "draft_lrc": draft, "slug": slug, "fallback_used": False}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao adicionar música: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
