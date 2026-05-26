import asyncio
import logging
import shutil
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, UploadFile, File

from state import queue_manager, SONGS_DIR

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/queue/add")
async def queue_add_song(
    title: str = Form(""),
    artist: str = Form(""),
    language: str = Form("en"),
    youtube_url: str = Form(""),
    youtube_vocal_url: Optional[str] = Form(None),
    plain_lyrics: Optional[str] = Form(None),
    synced_lrc: Optional[str] = Form(None),
    added_by: str = Form(""),
    align_lyrics: bool = Form(False),
    vocal_file: Optional[UploadFile] = File(None),
    backing_file: Optional[UploadFile] = File(None),
):
    """Adiciona música à fila de processamento em segundo plano.

    Retorna imediatamente com o ID do item para polling de status.
    O download + separação (Demucs) começam imediatamente.
    O alinhamento (Whisper) roda quando a GPU estiver ociosa.
    """
    if youtube_vocal_url and youtube_vocal_url.strip() and not youtube_url.strip():
        youtube_url = youtube_vocal_url

    if not youtube_url or not youtube_url.strip():
        # Se vocal_file foi fornecido, o youtube_url pode ser opcional ou vazio
        if not (vocal_file and vocal_file.filename):
            raise HTTPException(status_code=400, detail="URL do YouTube ou arquivo local é obrigatório.")


    # Auto-detecta metadados se título/artista estiverem vazios
    if not title.strip() or not artist.strip():
        if youtube_url.strip():
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

    # Salva arquivos locais antes de enfileirar se fornecidos
    from utils.text import slugify
    slug = slugify(f"{title}-{artist}")
    song_dir = SONGS_DIR / slug
    song_dir.mkdir(parents=True, exist_ok=True)

    if vocal_file and vocal_file.filename:
        # Se temos vocal e backing tracks locais, salva vocal.mp3 e backing_track.mp3
        # Caso contrário, vocal_file é o áudio principal que precisa de Demucs (original.mp3)
        if backing_file and backing_file.filename:
            with open(song_dir / "vocal.mp3", "wb") as f:
                shutil.copyfileobj(vocal_file.file, f)
        else:
            with open(song_dir / "original.mp3", "wb") as f:
                shutil.copyfileobj(vocal_file.file, f)

    if backing_file and backing_file.filename:
        with open(song_dir / "backing_track.mp3", "wb") as f:
            shutil.copyfileobj(backing_file.file, f)

    # Se plain_lyrics e synced_lrc forem ambos None (omitidos do form), faz auto-fetch
    if plain_lyrics is None and synced_lrc is None:
        synced_lrc = None
        plain_lyrics = ""
        try:
            from utils.lyrics_fetcher import fetch_lyrics

            fetched = await asyncio.to_thread(fetch_lyrics, artist.strip(), title.strip())
            if fetched:
                plain_lyrics = fetched.get("plainLyrics") or ""
                synced_lrc = fetched.get("syncedLyrics")
                logger.info(
                    "[Queue] Letra encontrada via %s para '%s - %s': plain=%s, synced=%s",
                    fetched.get("source"), artist, title, bool(plain_lyrics), bool(synced_lrc),
                )
            else:
                logger.info("[Queue] Nenhuma letra encontrada nas APIs para '%s - %s'. Whisper fará transcrição.", artist, title)
        except Exception as e:
            logger.warning(f"[Queue] Falha ao buscar letra: {e}")
    else:
        # Usa o valor fornecido explicitamente pelo formulário do frontend
        plain_lyrics = plain_lyrics or ""
        synced_lrc = synced_lrc or None

    if synced_lrc:
        align_lyrics = False

    try:
        item = await queue_manager.enqueue(
            title=title.strip(),
            artist=artist.strip(),
            language=language.strip(),
            youtube_url=youtube_url.strip(),
            plain_lyrics=plain_lyrics.strip() or None,
            synced_lrc=synced_lrc,
            added_by=added_by.strip() or None,
            align_lyrics=align_lyrics,
        )
        return {
            "success": True,
            "item": item.to_dict(),
            "message": f"'{title}' adicionada à fila! Processamento iniciado.",
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


@router.post("/api/queue/clear_gpu_lock")
async def queue_clear_gpu_lock():
    """Libera manualmente o status da GPU, permitindo que a Fase 2 continue."""
    queue_manager.notify_game_ended()
    return {"success": True, "message": "Status da GPU redefinido para livre."}


@router.delete("/api/queue/remove/{item_id}")
async def queue_remove(item_id: str):
    """Remove um item da fila. Cancela o processamento se estiver em andamento."""
    removed = queue_manager.remove_item(item_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Item não encontrado na fila.")
    return {"success": True, "message": "Item removido da fila."}
