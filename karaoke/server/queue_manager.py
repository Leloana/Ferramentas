"""Gerenciador de fila de músicas com processamento em segundo plano.

Estratégia "Download eager, Process lazy":
- Fase 1 (Download + Demucs): roda em paralelo com o jogo — seguro na RTX 4070 12GB.
- Fase 2 (Whisper + alinhamento): roda SOMENTE quando a GPU está ociosa (entre músicas).

O `whisper_lock` é compartilhado com o game loop (ws/room.py) para garantir
que o singleton CTranslate2 do Whisper nunca seja chamado em paralelo.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MAX_QUEUE_SIZE = 5


class QueueStatus(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    SEPARATING = "separating"
    AWAITING_ALIGNMENT = "awaiting_alignment"
    ALIGNING = "aligning"
    FINALIZING = "finalizing"
    READY = "ready"
    ERROR = "error"


@dataclass
class QueueItem:
    id: str
    slug: str
    title: str
    artist: str
    language: str
    youtube_url: str
    plain_lyrics: Optional[str] = None
    synced_lrc: Optional[str] = None
    align_lyrics: bool = False
    status: QueueStatus = QueueStatus.QUEUED
    progress_pct: int = 0
    error_msg: Optional[str] = None
    added_by: Optional[str] = None
    _task: Optional[asyncio.Task] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slug": self.slug,
            "title": self.title,
            "artist": self.artist,
            "language": self.language,
            "status": self.status.value,
            "progress_pct": self.progress_pct,
            "error_msg": self.error_msg,
            "added_by": self.added_by,
            "align_lyrics": self.align_lyrics,
        }


class SongQueueManager:
    def __init__(self, songs_dir: Path):
        self.songs_dir = songs_dir
        self.queue: list[QueueItem] = []
        self.whisper_lock = asyncio.Lock()
        self._gpu_game_active = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def enqueue(
        self,
        title: str,
        artist: str,
        language: str,
        youtube_url: str,
        plain_lyrics: Optional[str] = None,
        synced_lrc: Optional[str] = None,
        added_by: Optional[str] = None,
        align_lyrics: bool = False,
    ) -> QueueItem:
        """Adiciona música à fila e dispara Fase 1 imediatamente."""
        if len(self.queue) >= MAX_QUEUE_SIZE:
            raise ValueError(f"Fila cheia! Máximo de {MAX_QUEUE_SIZE} músicas simultâneas.")

        from utils.text import slugify

        slug = slugify(f"{title}-{artist}")
        item = QueueItem(
            id=str(uuid.uuid4())[:8],
            slug=slug,
            title=title,
            artist=artist,
            language=language,
            youtube_url=youtube_url,
            plain_lyrics=plain_lyrics,
            synced_lrc=synced_lrc,
            align_lyrics=align_lyrics,
            added_by=added_by,
        )
        self.queue.append(item)
        logger.info(f"[QUEUE] Música adicionada à fila: '{title}' por {added_by or 'anônimo'} (id={item.id})")

        # Dispara Fase 1 (download + separação) imediatamente
        item._task = asyncio.create_task(self._process_phase1(item))
        return item

    def get_queue_status(self) -> list[dict]:
        """Retorna status de todos os itens da fila."""
        return [item.to_dict() for item in self.queue]

    def remove_item(self, item_id: str) -> bool:
        """Remove item da fila. Cancela task se estiver rodando."""
        for i, item in enumerate(self.queue):
            if item.id == item_id:
                if item._task and not item._task.done():
                    item._task.cancel()
                self.queue.pop(i)
                logger.info(f"[QUEUE] Item removido da fila: {item_id} ({item.title})")
                return True
        return False

    def notify_game_started(self) -> None:
        """Chamado quando o jogo inicia — bloqueia Fase 2."""
        self._gpu_game_active = True
        logger.info("[QUEUE] Jogo iniciado — Fase 2 bloqueada para novos itens.")

    def notify_game_ended(self) -> None:
        """Chamado quando o jogo termina — libera Fase 2 e processa pendentes."""
        self._gpu_game_active = False
        logger.info("[QUEUE] Jogo encerrado — verificando itens pendentes na fila.")
        asyncio.create_task(self._try_process_pending())

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    async def _process_phase1(self, item: QueueItem) -> None:
        """Fase 1: Download YouTube + Demucs (separação). Seguro rodar em paralelo com o jogo."""
        song_dir = self.songs_dir / item.slug
        song_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Criar meta.json mínimo
            item.status = QueueStatus.DOWNLOADING
            item.progress_pct = 5
            logger.info(f"[QUEUE:{item.id}] Fase 1 — Criando meta.json e iniciando download...")

            # Se temos synced LRC (ex: LRCLIB), salva diretamente.
            # O reinstall_song preserva lyrics.lrc existente quando align_lyrics=False.
            if item.synced_lrc:
                clean_lrc = [line.strip() for line in item.synced_lrc.splitlines() if line.strip()]
                if clean_lrc:
                    (song_dir / "lyrics.lrc").write_text("\n".join(clean_lrc) + "\n", encoding="utf-8")
                    logger.info(f"[QUEUE:{item.id}] lyrics.lrc salvo via synced LRC da API.")

            meta = {
                "meta": {
                    "title": item.title,
                    "artist": item.artist,
                    "language": item.language,
                    "slug": item.slug,
                },
                "audio": {
                    "youtube_vocal_url": item.youtube_url,
                    "youtube_backing_url": "",
                },
                "lyrics": {
                    "plain_lyrics": item.plain_lyrics,
                },
            }
            meta_path = song_dir / "meta.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=4, ensure_ascii=False)

            # Salvar lyrics.txt se fornecido (mesmo com synced LRC, para referência)
            if item.plain_lyrics and item.plain_lyrics.strip():
                from utils.text import normalize_lyrics_text

                normalized = normalize_lyrics_text(item.plain_lyrics)
                if normalized:
                    (song_dir / "lyrics.txt").write_text(normalized + "\n", encoding="utf-8")

            # 2. Download do YouTube
            item.progress_pct = 15
            from state import ffmpeg_bin_dir
            from utils.youtube import download_youtube_audio

            original_audio = song_dir / "original.mp3"
            logger.info(f"[QUEUE:{item.id}] Baixando áudio do YouTube...")
            success = await download_youtube_audio(item.youtube_url, original_audio, ffmpeg_bin_dir)
            if not success or not original_audio.exists():
                raise RuntimeError("Falha ao baixar áudio do YouTube.")

            item.progress_pct = 35

            # 3. Demucs (separação vocal/instrumental) — roda na GPU, seguro em paralelo
            item.status = QueueStatus.SEPARATING
            item.progress_pct = 40
            logger.info(f"[QUEUE:{item.id}] Executando Demucs (separação de áudio)...")

            await self._run_demucs(item, song_dir, original_audio)

            item.progress_pct = 70

            # Limpeza de temporários
            if original_audio.exists():
                original_audio.unlink()
            demucs_out = song_dir / "demucs_output"
            if demucs_out.exists():
                shutil.rmtree(demucs_out)

            # 4. Marca como pronto para Fase 2
            item.status = QueueStatus.AWAITING_ALIGNMENT
            item.progress_pct = 75
            logger.info(f"[QUEUE:{item.id}] Fase 1 concluída! Aguardando GPU ociosa para alinhamento...")

            # Tenta processar o próximo pendente na fila se o jogo não está ativo
            if not self._gpu_game_active:
                await self._try_process_pending()

        except asyncio.CancelledError:
            logger.info(f"[QUEUE:{item.id}] Processamento cancelado pelo usuário.")
            item.status = QueueStatus.ERROR
            item.error_msg = "Cancelado pelo usuário"
        except Exception as e:
            logger.error(f"[QUEUE:{item.id}] Erro na Fase 1: {e}", exc_info=True)
            item.status = QueueStatus.ERROR
            item.error_msg = str(e)

    async def _process_phase2(self, item: QueueItem) -> None:
        """Fase 2: Whisper + alinhamento. DEVE rodar com exclusividade na GPU."""
        song_dir = self.songs_dir / item.slug

        try:
            item.status = QueueStatus.ALIGNING
            item.progress_pct = 78
            async with self.whisper_lock:
                item.progress_pct = 80
                logger.info(f"[QUEUE:{item.id}] Fase 2 — Whisper lock adquirido. Gerando LRC + alinhamento...")

                # Determinar se usa PRO (forced alignment) ou FLASH
                align_lyrics = item.align_lyrics

                from utils.prepare import run_reinstall_song

                success = await run_reinstall_song(
                    str(song_dir),
                    language=item.language,
                    clean_existing=False,
                    skip_prepare_song=False,  # Auto-aprovar: gera segments.json direto
                    align_lyrics=align_lyrics,
                )

                if not success:
                    raise RuntimeError("Pipeline de alinhamento falhou.")

                item.status = QueueStatus.FINALIZING
                item.progress_pct = 95

            # Sucesso!
            item.status = QueueStatus.READY
            item.progress_pct = 100
            logger.info(f"[QUEUE:{item.id}] ✅ Música '{item.title}' pronta para cantar!")

            # Agenda a remoção automática após 10 segundos
            asyncio.create_task(self._delayed_remove(item.id, delay=10.0))

        except asyncio.CancelledError:
            logger.info(f"[QUEUE:{item.id}] Alinhamento cancelado.")
            item.status = QueueStatus.ERROR
            item.error_msg = "Cancelado"
        except Exception as e:
            logger.error(f"[QUEUE:{item.id}] Erro na Fase 2: {e}", exc_info=True)
            item.status = QueueStatus.ERROR
            item.error_msg = str(e)
        finally:
            if not self._gpu_game_active:
                await self._try_process_pending()

    async def _try_process_pending(self) -> None:
        """Processa o próximo item pendente na fila (um por vez)."""
        if self._gpu_game_active:
            return

        # Garante que não há nenhuma outra música ativamente rodando a Fase 2
        for item in self.queue:
            if item.status in (QueueStatus.ALIGNING, QueueStatus.FINALIZING):
                logger.info("[QUEUE] Fase 2 já está ativa para outro item. Aguardando.")
                return

        for item in self.queue:
            if item.status == QueueStatus.AWAITING_ALIGNMENT:
                logger.info(f"[QUEUE] Processando item pendente: {item.id} ({item.title})")
                item._task = asyncio.create_task(self._process_phase2(item))
                return  # Um por vez — o próximo será processado quando este terminar

    async def _delayed_remove(self, item_id: str, delay: float) -> None:
        """Remove o item da fila após um atraso (em segundos)."""
        await asyncio.sleep(delay)
        self.remove_item(item_id)

    async def _run_demucs(self, item: QueueItem, song_dir: Path, audio_path: Path) -> None:
        """Executa Demucs como subprocesso para separar vocal/instrumental."""
        import subprocess
        import sys

        python_dir = Path(sys.executable).parent
        demucs_exe = python_dir / "demucs.exe"
        if not demucs_exe.exists():
            demucs_exe = python_dir / "Scripts" / "demucs.exe"
        if not demucs_exe.exists():
            demucs_exe = "demucs"

        device = "cpu"
        try:
            import torch
            if torch.cuda.is_available():
                device = "cuda"
        except Exception:
            pass

        demucs_out_dir = song_dir / "demucs_output"
        demucs_cmd = [
            str(demucs_exe),
            "--two-stems", "vocals",
            "-d", device,
            "-o", str(demucs_out_dir),
            str(audio_path),
        ]

        logger.info(f"[QUEUE:{item.id}] Demucs device={device}, cmd={' '.join(demucs_cmd)}")
        process = await asyncio.to_thread(
            subprocess.run, demucs_cmd, capture_output=True, text=True
        )
        if process.returncode != 0:
            logger.error(f"[QUEUE:{item.id}] Demucs stderr: {process.stderr}")
            raise RuntimeError(f"Demucs falhou (exit code {process.returncode})")

        # Localizar arquivos separados
        separated_dir = demucs_out_dir / "htdemucs" / audio_path.stem
        vocals_wav = separated_dir / "vocals.wav"
        no_vocals_wav = separated_dir / "no_vocals.wav"

        if not vocals_wav.exists() or not no_vocals_wav.exists():
            raise RuntimeError("Demucs não gerou os arquivos de áudio separados.")

        # Exportar como MP3
        from pydub import AudioSegment

        vocal_audio = AudioSegment.from_file(str(vocals_wav))
        backing_audio = AudioSegment.from_file(str(no_vocals_wav))
        vocal_audio.export(str(song_dir / "vocal.mp3"), format="mp3")
        backing_audio.export(str(song_dir / "backing_track.mp3"), format="mp3")
        logger.info(f"[QUEUE:{item.id}] Áudios vocal e backing exportados com sucesso.")
