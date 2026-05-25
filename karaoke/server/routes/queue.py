"""Rotas HTTP para a fila de músicas com processamento em segundo plano."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Form, HTTPException

from state import queue_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/queue/add")
async def queue_add_song(
    title: str = Form(""),
    artist: str = Form(""),
    language: str = Form("en"),
    youtube_url: str = Form(""),
    plain_lyrics: str = Form(""),
    added_by: str = Form(""),
    align_lyrics: bool = Form(False),
):
    """Adiciona música à fila de processamento em segundo plano.

    Retorna imediatamente com o ID do item para polling de status.
    O download + separação (Demucs) começam imediatamente.
    O alinhamento (Whisper) roda quando a GPU estiver ociosa.
    """
    if not youtube_url or not youtube_url.strip():
        raise HTTPException(status_code=400, detail="URL do YouTube é obrigatória.")

    # Auto-detecta metadados se título/artista estiverem vazios
    if not title.strip() or not artist.strip():
        try:
            from utils.youtube import get_youtube_video_info

            info = await get_youtube_video_info(youtube_url.strip())
            if not title.strip():
                title = info.get("title", "Música Desconhecida")
            if not artist.strip():
                artist = info.get("artist", "Artista Desconhecido")
        except Exception as e:
            logger.warning(f"Falha ao buscar metadados do YouTube: {e}")
            if not title.strip():
                title = "Música Desconhecida"
            if not artist.strip():
                artist = "Artista Desconhecido"

    try:
        item = await queue_manager.enqueue(
            title=title.strip(),
            artist=artist.strip(),
            language=language.strip(),
            youtube_url=youtube_url.strip(),
            plain_lyrics=plain_lyrics.strip() or None,
            added_by=added_by.strip() or None,
            align_lyrics=align_lyrics,
        )
        return {
            "success": True,
            "item": item.to_dict(),
            "message": f"'{title}' adicionada à fila! Download iniciado.",
        }
    except ValueError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao adicionar à fila: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/queue/status")
async def queue_status():
    """Retorna o status de todos os itens na fila."""
    return {
        "queue": queue_manager.get_queue_status(),
        "gpu_busy": queue_manager._gpu_game_active,
    }


@router.delete("/api/queue/remove/{item_id}")
async def queue_remove(item_id: str):
    """Remove um item da fila. Cancela o processamento se estiver em andamento."""
    removed = queue_manager.remove_item(item_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Item não encontrado na fila.")
    return {"success": True, "message": "Item removido da fila."}
