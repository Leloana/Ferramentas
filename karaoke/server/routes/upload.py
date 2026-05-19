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

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, BackgroundTasks
from pydub import AudioSegment

from state import ffmpeg_bin_dir
from stt_engine import get_stt_engine
from utils.lrc_align import align_plain_lyrics, draft_lrc_from_whisper
from utils.prepare import run_prepare_song
from utils.text import parse_time_to_seconds, slugify
from utils.youtube import download_youtube_audio, get_youtube_video_info

logger = logging.getLogger(__name__)
router = APIRouter()

SONGS_DIR = Path(__file__).resolve().parent.parent / "songs"
WHISPER_SR = 16000


def _slice_with_padding(audio: AudioSegment, start_sec: float, end_sec: float, padding_sec: float) -> AudioSegment:
    """Corta `audio` e prepende `padding_sec` de silêncio (se > 0)."""
    duration_ms = len(audio)
    start_ms = max(0, int(start_sec * 1000))
    end_ms = int(end_sec * 1000) if end_sec > 0 else duration_ms
    end_ms = min(end_ms, duration_ms)
    sliced = audio[start_ms:end_ms]
    if padding_sec > 0:
        silence = AudioSegment.silent(duration=int(padding_sec * 1000), frame_rate=sliced.frame_rate)
        return silence + sliced
    return sliced


def _vocal_to_float32_mono_16k(vocal: AudioSegment) -> np.ndarray:
    """Resamplea vocal para 16kHz mono float32 normalizado, pronto para o Whisper."""
    resampled = vocal.set_frame_rate(WHISPER_SR).set_channels(1)
    raw = np.array(resampled.get_array_of_samples(), dtype=np.float32)
    if resampled.sample_width == 2:
        raw /= 32768.0
    elif resampled.sample_width == 4:
        raw /= 2147483648.0
    return raw


def _build_meta(form: dict) -> dict:
    """Estrutura `meta.json` salvo junto da música para auditoria/reprodução."""
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
            "vocal_start": form["vocal_start"],
            "vocal_end": form["vocal_end"],
            "backing_start": form["backing_start"],
            "backing_end": form["backing_end"],
            "silence_padding": form["silence_padding"],
            "force_vocal_start": form.get("force_vocal_start") == "true" or form.get("force_vocal_start") is True,
        },
        "lyrics": {
            "lyrics_start": form["lyrics_start"],
            "plain_lyrics": form.get("plain_lyrics"),
        },
        "status": {
            "has_vocal_file": form["vocal_file"] is not None and form["vocal_file"].filename != "",
            "has_backing_file": form["backing_file"] is not None and form["backing_file"].filename != "",
            "has_lrc_file": form["lrc_file"] is not None and form["lrc_file"].filename != "",
        }
    }


async def _acquire_vocal(
    youtube_vocal_url: Optional[str],
    vocal_file: Optional[UploadFile],
    temp_vocal: Path,
) -> None:
    """Garante que `temp_vocal` exista no disco — via YouTube ou upload local do vocal."""
    has_yt_v = bool(youtube_vocal_url and youtube_vocal_url.strip())

    if has_yt_v:
        logger.info(f"Iniciando download do canal Vocal do YouTube: {youtube_vocal_url}")
        v_ok = await download_youtube_audio(youtube_vocal_url.strip(), temp_vocal, ffmpeg_bin_dir)
        if not v_ok or not temp_vocal.exists():
            raise HTTPException(status_code=400, detail="Falha ao baixar o áudio Vocal do YouTube. Verifique a URL.")
        return

    # Caminho do upload de arquivo local ou erro
    if not vocal_file or not vocal_file.filename:
        raise HTTPException(status_code=400, detail="Você precisa subir um arquivo local de áudio ou fornecer o link do YouTube.")
        
    with open(temp_vocal, "wb") as f:
        shutil.copyfileobj(vocal_file.file, f)


async def background_acquire_and_process_backing(
    youtube_backing_url: Optional[str],
    backing_file_path: Optional[Path],
    temp_vocal_path: Path,
    song_dir: Path,
    b_start: float,
    b_end: float,
    padding: float,
    language: str,
) -> None:
    """Adquire e processa a faixa instrumental (backing track) em segundo plano, correndo prepare_song no final."""
    try:
        temp_backing = song_dir / "temp_backing.mp3"
        use_demucs = not youtube_backing_url or not youtube_backing_url.strip()
        
        if backing_file_path and backing_file_path.exists():
            use_demucs = False
            shutil.move(str(backing_file_path), str(temp_backing))

        if use_demucs:
            logger.info("Nenhuma URL ou arquivo de backing fornecido. Executando separação Demucs com GPU CUDA em segundo plano...")
            demucs_out_dir = song_dir / "demucs_output"
            python_dir = Path(sys.executable).parent
            demucs_exe = python_dir / "demucs.exe"
            if not demucs_exe.exists():
                demucs_exe = python_dir / "Scripts" / "demucs.exe"
            if not demucs_exe.exists():
                demucs_exe = "demucs"
                
            demucs_cmd = [
                str(demucs_exe),
                "--two-stems", "vocals",
                "-d", "cuda",
                "-o", str(demucs_out_dir),
                str(temp_vocal_path)
            ]
            
            process = subprocess.run(demucs_cmd, capture_output=True, text=True)
            if process.returncode != 0:
                logger.error(f"Erro no Demucs em segundo plano: {process.stderr}")
                return
                
            separated_dir = demucs_out_dir / "htdemucs" / temp_vocal_path.stem
            no_vocals_wav = separated_dir / "no_vocals.wav"
            
            if not no_vocals_wav.exists():
                logger.error("Erro crítico em segundo plano: no_vocals.wav não foi localizado.")
                return
                
            backing_audio = AudioSegment.from_file(str(no_vocals_wav))
            processed_backing = _slice_with_padding(backing_audio, b_start, b_end, padding)
            processed_backing.export(str(song_dir / "backing_track.mp3"), format="mp3")
            
            try:
                shutil.rmtree(demucs_out_dir)
            except Exception:
                pass
        else:
            # Se já temos o arquivo local movido para temp_backing
            if not temp_backing.exists():
                logger.info(f"Baixando canal backing do YouTube em segundo plano: {youtube_backing_url}")
                success = await download_youtube_audio(youtube_backing_url.strip(), temp_backing, ffmpeg_bin_dir)
                if not success or not temp_backing.exists():
                    logger.error("Erro crítico em segundo plano: Falha ao baixar o backing do YouTube.")
                    return
                    
            backing_audio = AudioSegment.from_file(str(temp_backing))
            processed_backing = _slice_with_padding(backing_audio, b_start, b_end, padding)
            processed_backing.export(str(song_dir / "backing_track.mp3"), format="mp3")
            
            try:
                temp_backing.unlink()
            except Exception:
                pass
                
        logger.info("Backing track gerado com sucesso em segundo plano! Rodando prepare_song final...")
        run_prepare_song(str(song_dir), language)
        
        # Limpeza do temp_vocal_path
        if temp_vocal_path.exists():
            try:
                temp_vocal_path.unlink()
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Erro no processamento em segundo plano do backing track: {e}", exc_info=True)


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
    vocal_start: str = Form("0.0"),
    vocal_end: str = Form("-1.0"),
    backing_start: str = Form("0.0"),
    backing_end: str = Form("-1.0"),
    silence_padding: str = Form("0.0"),
    lyrics_start: str = Form("0.0"),
    youtube_vocal_url: Optional[str] = Form(None),
    youtube_backing_url: Optional[str] = Form(None),
    plain_lyrics: Optional[str] = Form(None),
    force_vocal_start: str = Form("false"),
):
    try:
        slug = slugify(f"{title}-{artist}")
        song_dir = SONGS_DIR / slug
        song_dir.mkdir(parents=True, exist_ok=True)

        # Snapshot de parâmetros para auditoria.
        meta = _build_meta(locals())
        with open(song_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=4, ensure_ascii=False)

        force_vocal_start_bool = False

        v_start = 0.0
        v_end = parse_time_to_seconds(vocal_end)
        b_start = 0.0
        b_end = parse_time_to_seconds(backing_end)
        padding = max(0.0, parse_time_to_seconds(silence_padding))
        lyrics_start_val = 0.0

        temp_vocal = song_dir / "temp_vocal.mp3"

        # Adquire vocal sincronamente
        await _acquire_vocal(youtube_vocal_url, vocal_file, temp_vocal)

        # Corte + padding de silêncio na faixa vocal.
        final_vocal = _slice_with_padding(AudioSegment.from_file(str(temp_vocal)), v_start, v_end, padding)
        final_vocal.export(str(song_dir / "vocal.mp3"), format="mp3")

        # Salva backing file local se fornecido
        backing_file_path = None
        if backing_file and backing_file.filename:
            backing_file_path = song_dir / "temp_backing_upload.mp3"
            with open(backing_file_path, "wb") as f:
                shutil.copyfileobj(backing_file.file, f)

        # Agenda processamento do backing track em segundo plano
        background_tasks.add_task(
            background_acquire_and_process_backing,
            youtube_backing_url,
            backing_file_path,
            temp_vocal,
            song_dir,
            b_start,
            b_end,
            padding,
            language,
        )

        # --- Caminho 1: usuário forneceu .lrc pronto ---
        if lrc_file is not None and lrc_file.filename:
            lrc_content = await lrc_file.read()
            try:
                lrc_text = lrc_content.decode("utf-8")
            except UnicodeDecodeError:
                lrc_text = lrc_content.decode("latin-1")
            clean_lines = [line.strip() for line in lrc_text.splitlines() if line.strip()]
            with open(song_dir / "lyrics.lrc", "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(clean_lines))
            run_prepare_song(str(song_dir), language)
            return {"success": True, "lyrics_status": "ready", "slug": slug, "fallback_used": False}

        # --- Caminho 2 e 3: sem .lrc — transcreve vocal recortado com Whisper ---
        logger.info("Nenhum arquivo LRC enviado. Transcrevendo vocais recortados com o Whisper...")
        stt = get_stt_engine()
        raw_data = _vocal_to_float32_mono_16k(final_vocal)
        segments, _info = stt.model.transcribe(
            raw_data,
            language=language,
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
            word_timestamps=True,
        )
        segments_list = list(segments)

        # --- Caminho 2: usuário forneceu letra plana → alinha com Whisper ---
        if plain_lyrics and plain_lyrics.strip():
            logger.info("Letra de referência fornecida. Alinhando com a transcrição do Whisper...")
            txt_lines = [line.strip() for line in plain_lyrics.splitlines() if line.strip()]
            with open(song_dir / "lyrics.txt", "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(txt_lines) + "\n")

            total_duration = len(final_vocal) / 1000.0
            lrc_text, fallback_used = align_plain_lyrics(
                plain_lyrics, segments_list, title, artist, lyrics_start_val, total_duration,
            )
            with open(song_dir / "lyrics.lrc", "w", encoding="utf-8", newline="\n") as f:
                f.write(lrc_text)
            run_prepare_song(str(song_dir), language)
            return {"success": True, "lyrics_status": "ready", "slug": slug, "fallback_used": fallback_used}

        # --- Caminho 3: gera rascunho LRC só com Whisper para edição manual ---
        draft = draft_lrc_from_whisper(segments_list, title, artist, lyrics_start_val)
        return {"success": True, "lyrics_status": "draft", "draft_lrc": draft, "slug": slug, "fallback_used": False}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao adicionar música: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
