"""Rotas HTTP simples: listagem, audio backing, delete, get-ip, index."""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import socket
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse, HTMLResponse

from state import SONGS_DIR, song_manager, queue_manager
from utils.cover import find_cover
from utils.html_includes import render_page
from utils.http import set_no_cache

logger = logging.getLogger(__name__)
router = APIRouter()

CLIENT_DIR = Path(__file__).resolve().parent.parent.parent / "client"


@router.get("/")
async def get_index():
    # index.html é um esqueleto: os parciais de client/partials/ entram aqui.
    response = HTMLResponse(render_page(CLIENT_DIR))
    set_no_cache(response)
    return response


@router.get("/songs")
@router.get("/api/songs")
async def list_songs(response: Response):
    set_no_cache(response)
    return song_manager.list_songs()


@router.get("/api/songs/{song_id}")
async def get_song(song_id: str, response: Response):
    set_no_cache(response)
    data = song_manager.get_song_data(song_id)
    if not data:
        raise HTTPException(status_code=404, detail="Música não encontrada")
    return data



@router.get("/api/songs/{song_id}/cover")
async def get_song_cover(song_id: str):
    """Capa do álbum (iTunes ou miniatura do YouTube), baixada na 1ª vez e guardada na pasta."""
    song_dir = (SONGS_DIR / song_id).resolve()
    if SONGS_DIR.resolve() not in song_dir.parents:
        raise HTTPException(status_code=404, detail="Música não encontrada")
    cover = await asyncio.to_thread(find_cover, song_dir)
    if not cover:
        raise HTTPException(status_code=404, detail="Sem capa")
    return FileResponse(cover, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@router.get("/songs/{song_id}/audio")
async def get_audio(song_id: str):
    audio_path = song_manager.get_audio_path(song_id)
    if not audio_path:
        raise HTTPException(status_code=404, detail="Música não encontrada")
    return FileResponse(audio_path)


@router.delete("/api/delete-song/{song_id}")
async def delete_song(song_id: str):
    try:
        song_dir = SONGS_DIR / song_id
        if not song_dir.exists():
            raise HTTPException(status_code=404, detail="Música não encontrada")
        shutil.rmtree(song_dir)
        logger.info(f"Música deletada do disco: {song_id}")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao deletar a música {song_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/reinstall-song/{song_id}")
async def api_reinstall_song(song_id: str, align_lyrics: bool = False):
    try:
        song_dir = SONGS_DIR / song_id
        if not song_dir.exists():
            raise HTTPException(status_code=404, detail="Música não encontrada")
        
        meta_path = song_dir / "meta.json"
        if not meta_path.exists():
            raise HTTPException(status_code=400, detail="Arquivo meta.json não encontrado na pasta da música")

        from tools.reinstall_song import reinstall_song

        # Aguarda o whisper_lock antes de rodar — garante que não conflite com
        # uma música em andamento no jogo (mesmo lock usado pelo room.py e queue_manager).
        logger.info(f"[Reinstall] Aguardando whisper_lock para reinstalar '{song_id}'...")
        async with queue_manager.whisper_lock:
            logger.info(f"[Reinstall] Lock adquirido. Iniciando reinstalação de '{song_id}'...")
            success = await reinstall_song(str(song_dir), align_lyrics=align_lyrics)
        
        if success:
            logger.info(f"Reinstalação concluída com sucesso para a música: {song_id}")
            return {"success": True, "message": "Reinstalação concluída com sucesso!"}
        else:
            logger.error(f"Reinstalação falhou para a música: {song_id}")
            raise HTTPException(status_code=500, detail="Erro durante o processo de reinstalação da música")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao reinstalar a música {song_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/get-ip")
async def get_ip():
    """IP na rede local e, atrás do túnel, a URL pública (KARAOKE_PUBLIC_URL) para o QR."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return {"ip": ip, "public_url": os.environ.get("KARAOKE_PUBLIC_URL") or None}
