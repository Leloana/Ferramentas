"""Gerenciador de fila de músicas com processamento em segundo plano.

Estratégia "Download eager, Process lazy":
- Fase 1 (Download + Demucs): roda em paralelo com o jogo — seguro na RTX 4070 12GB.
- Fase 2 (Whisper + alinhamento): roda SOMENTE quando a GPU está ociosa (entre músicas).

O `whisper_lock` é compartilhado com o game loop (ws/room.py) para garantir
que o singleton CTranslate2 do Whisper nunca seja chamado em paralelo.

A fila é gravada em `songs/.queue.json` a cada mudança e retomada quando o servidor
sobe (`resume_saved`): antes ela só existia na memória e uma música ficava pela
metade, sem segments.json, se o servidor caísse no meio.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# cabe uma playlist inteira (utils/youtube.PLAYLIST_LIMIT) e mais algumas avulsas.
# Os downloads andam queue_eta.DOWNLOAD_SLOTS por vez; separação e letra, uma por vez.
MAX_QUEUE_SIZE = 60
QUEUE_FILE = ".queue.json"
# campos que bastam para refazer o item depois de reiniciar (o resto é estado da execução)
_SAVED_FIELDS = ("id", "slug", "title", "artist", "language", "youtube_url", "plain_lyrics",
                 "synced_lrc", "align_lyrics", "added_by", "clean_existing", "audio_sec")


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
    clean_existing: bool = False  # reinstalação: limpa a pasta antes (só uma vez, ver _save)
    audio_sec: Optional[float] = None  # duração do áudio (YouTube, depois o arquivo baixado)
    separator: str = "demucs"  # o que deve separar este áudio (estimativa de tempo)
    stage_started: float = field(default_factory=time.monotonic)
    _task: Optional[asyncio.Task] = field(default=None, repr=False)
    # ligado ao remover da fila: mata a separação que roda na thread (utils/separation.py)
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    def remaining_stages(self, running: Optional[bool] = None) -> list[tuple[str, float]]:
        """Etapas que faltam como (etapa, segundos estimados) — queue_eta.py.

        `running`: a etapa atual já está rodando (desconta o tempo passado). None
        deduz pelo status; a fila passa False para quem só espera a vez de separar."""
        import queue_eta

        stages = ["download", f"separate_{self.separator}", "align_pro" if self.align_lyrics else "align_fast"]
        current = {
            QueueStatus.QUEUED: 0, QueueStatus.DOWNLOADING: 0, QueueStatus.SEPARATING: 1,
            QueueStatus.AWAITING_ALIGNMENT: 2, QueueStatus.ALIGNING: 2, QueueStatus.FINALIZING: 2,
        }.get(self.status)
        if current is None:
            return []
        if running is None:
            running = self.status in (QueueStatus.DOWNLOADING, QueueStatus.SEPARATING,
                                      QueueStatus.ALIGNING, QueueStatus.FINALIZING)
        out = []
        for i, stage in enumerate(stages[current:]):
            est = queue_eta.estimate(stage, self.audio_sec)
            if i == 0 and running:
                # passou da conta: "quase lá" em vez de zero ou negativo
                est = max(est * 0.1, est - (time.monotonic() - self.stage_started), 5.0)
            out.append((stage, est))
        return out

    def eta_sec(self) -> Optional[int]:
        """Segundos que esta música leva sozinha (sem esperar as outras nem partida)."""
        stages = self.remaining_stages()
        if not stages:
            return None
        return int(round(sum(sec for _, sec in stages)))

    def to_dict(self, eta_sec: Optional[int] = None) -> dict:
        """`eta_sec`: tempo já contando a espera na fila (SongQueueManager.etas)."""
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
            "has_lrc": bool(self.synced_lrc),
            "has_plain_lyrics": bool(self.plain_lyrics) and not bool(self.synced_lrc),
            "clean_existing": self.clean_existing,
            "audio_sec": self.audio_sec,
            "eta_sec": eta_sec if eta_sec is not None else self.eta_sec(),
        }


class SongQueueManager:
    def __init__(self, songs_dir: Path):
        self.songs_dir = songs_dir
        self.queue: list[QueueItem] = []
        self.whisper_lock = asyncio.Lock()
        self._gpu_game_active = False
        # Trabalhos longos de GPU fora da partida (gerar letra, recalcular
        # segmentos): enquanto houver um, a TV não inicia partida (mutex de GPU)
        self._gpu_jobs: list[str] = []
        import queue_eta

        # uma playlist inteira na fila não abre dezenas de yt-dlp de uma vez
        self._download_slots = asyncio.Semaphore(queue_eta.DOWNLOAD_SLOTS)

    # ------------------------------------------------------------------
    # Fila em disco
    # ------------------------------------------------------------------

    def _save(self) -> None:
        """Grava o que ainda falta fazer (pronto e erro não voltam ao reiniciar)."""
        pending = [
            {k: getattr(item, k) for k in _SAVED_FIELDS}
            for item in self.queue if item.status not in (QueueStatus.READY, QueueStatus.ERROR)
        ]
        path = self.songs_dir / QUEUE_FILE
        try:
            if not pending:
                path.unlink(missing_ok=True)
                return
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(pending, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(path)
        except OSError as e:
            logger.warning(f"[QUEUE] Não foi possível gravar a fila em disco: {e}")

    def resume_saved(self) -> int:
        """Retoma a fila gravada (servidor reiniciado no meio). Devolve quantos voltaram.
        A fase 1 pula o que já foi baixado/separado, então retomar é barato.
        KARAOKE_QUEUE_RESUME=0 desliga (os testes usam)."""
        if os.environ.get("KARAOKE_QUEUE_RESUME", "1") == "0":
            return 0
        try:
            saved = json.loads((self.songs_dir / QUEUE_FILE).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return 0
        except (OSError, ValueError) as e:
            logger.warning(f"[QUEUE] Fila gravada ilegível, ignorada: {e}")
            return 0
        known = {item.id for item in self.queue}
        resumed = 0
        for data in saved[:MAX_QUEUE_SIZE]:
            fields = {k: data.get(k) for k in _SAVED_FIELDS}
            if not fields["id"] or not fields["slug"] or fields["id"] in known:
                continue
            fields["align_lyrics"] = bool(fields["align_lyrics"])
            fields["clean_existing"] = bool(fields["clean_existing"])
            item = QueueItem(**fields, separator=self._separator_now())
            self.queue.append(item)
            item._task = asyncio.create_task(self._process_phase1(item))
            resumed += 1
            logger.info(f"[QUEUE] Retomando da fila gravada: '{item.title}' (id={item.id})")
        return resumed

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
        clean_existing: bool = False,
        audio_sec: Optional[float] = None,
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
            clean_existing=clean_existing,
            audio_sec=audio_sec if audio_sec and audio_sec > 0 else None,
            separator=self._separator_now(),
        )
        self.queue.append(item)
        self._save()
        logger.info(f"[QUEUE] Música adicionada à fila: '{title}' por {added_by or 'anônimo'} (id={item.id})")

        # Dispara Fase 1 (download + separação) imediatamente
        item._task = asyncio.create_task(self._process_phase1(item))
        return item

    def _separator_now(self) -> str:
        """Separador que a fase 1 usaria agora (RoFormer só sem partida)."""
        from utils.separation import separator_backend

        return "demucs" if self._gpu_game_active else separator_backend()

    def _pending_jobs(self) -> tuple[list[QueueItem], list[list[tuple[str, float]]]]:
        """Itens ainda em processamento e as etapas que faltam a cada um, na ordem da fila."""
        items, jobs = [], []
        separating_seen = False
        for item in self.queue:
            running = None
            if item.status == QueueStatus.SEPARATING:
                # vários ficam em SEPARATING esperando o lock; só o primeiro está separando
                running = not separating_seen
                separating_seen = True
            stages = item.remaining_stages(running)
            if stages:
                items.append(item)
                jobs.append(stages)
        return items, jobs

    def etas(self) -> dict[str, int]:
        """Segundos até cada item ficar pronto, contando a espera pelos da frente."""
        import queue_eta

        items, jobs = self._pending_jobs()
        finish = queue_eta.pipeline_finish(jobs)
        return {item.id: int(round(t)) for item, t in zip(items, finish)}

    def estimate_batch(self, durations: list[Optional[float]], align_lyrics: bool = False) -> dict:
        """Tempo para a fila atual mais as músicas `durations` (ex.: uma playlist).

        Devolve {"total_sec": tudo pronto, "own_sec": só as novas, sem a fila, "queued"}."""
        import queue_eta

        _, jobs = self._pending_jobs()
        separator = self._separator_now()
        align = "align_pro" if align_lyrics else "align_fast"
        new = [
            [(stage, queue_eta.estimate(stage, d if d and d > 0 else None))
             for stage in ("download", f"separate_{separator}", align)]
            for d in durations
        ]
        total = max(queue_eta.pipeline_finish(jobs + new), default=0.0)
        own = max(queue_eta.pipeline_finish(new), default=0.0)
        return {"total_sec": int(round(total)), "own_sec": int(round(own)), "queued": len(jobs)}

    def item_status(self, item: QueueItem) -> dict:
        """to_dict do item com o tempo já contando a fila da frente."""
        return item.to_dict(self.etas().get(item.id))

    def get_queue_status(self) -> list[dict]:
        """Retorna status de todos os itens da fila."""
        etas = self.etas()
        return [item.to_dict(etas.get(item.id)) for item in self.queue]

    def remove_item(self, item_id: str) -> bool:
        """Remove item da fila. Cancela task se estiver rodando."""
        for i, item in enumerate(self.queue):
            if item.id == item_id:
                # Fase 2 roda o Whisper numa thread que não para com cancel(): cancelar
                # soltaria o whisper_lock com a GPU ainda ocupada. Deixa terminar.
                in_phase2 = item.status in (QueueStatus.ALIGNING, QueueStatus.FINALIZING)
                if item._task and not item._task.done() and not in_phase2:
                    item._cancel.set()
                    item._task.cancel()
                self.queue.pop(i)
                self._save()
                logger.info(f"[QUEUE] Item removido da fila: {item_id} ({item.title})")
                return True
        return False

    @contextlib.asynccontextmanager
    async def gpu_job(self, label: str):
        """Trabalho longo na GPU (Whisper/MMS de uma música): pega o whisper_lock e
        fica visível em `alignment_busy()` — a TV não começa partida por cima."""
        async with self.whisper_lock:
            self._gpu_jobs.append(label)
            try:
                yield
            finally:
                self._gpu_jobs.remove(label)

    def alignment_busy(self) -> str | None:
        """Nome do que está gerando letra na GPU agora (None = livre para cantar)."""
        return self._gpu_jobs[0] if self._gpu_jobs else None

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
            item.stage_started = time.monotonic()
            item.progress_pct = 5
            logger.info(f"[QUEUE:{item.id}] Fase 1 — Criando meta.json e iniciando download...")

            # Reinstalação: limpa ANTES de gravar a letra (antes a limpeza vinha
            # depois e apagava o lyrics.lrc/lyrics.txt recém-gravados).
            if item.clean_existing:
                logger.info(f"[QUEUE:{item.id}] Reinstalação solicitada. Limpando arquivos anteriores...")
                for sub in song_dir.iterdir():
                    if sub.name == "meta.json":
                        continue
                    try:
                        if sub.is_dir():
                            shutil.rmtree(sub)
                        else:
                            sub.unlink()
                    except Exception as e:
                        logger.warning(f"Não foi possível remover arquivo residual {sub.name} na limpeza da fila: {e}")
                # retomado depois de reiniciar, não limpa de novo (apagaria o download)
                item.clean_existing = False
                self._save()

            # Se temos synced LRC (ex: LRCLIB), salva diretamente.
            # O reinstall_song preserva lyrics.lrc existente quando align_lyrics=False.
            if item.synced_lrc:
                clean_lrc = [line.strip() for line in item.synced_lrc.splitlines() if line.strip()]
                if clean_lrc:
                    (song_dir / "lyrics.lrc").write_text("\n".join(clean_lrc) + "\n", encoding="utf-8")
                    logger.info(f"[QUEUE:{item.id}] lyrics.lrc salvo via synced LRC da API.")
            if item.synced_lrc or item.plain_lyrics:
                # a letra da fila vem do LRCLIB (modal de adicionar), buscada sem o áudio
                from utils.song_paths import API_LYRICS_MARKER

                (song_dir / API_LYRICS_MARKER).touch()

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

            # 2. Download do YouTube (ou detecção de arquivos locais já carregados)
            item.progress_pct = 15
            original_audio = song_dir / "original.mp3"
            vocal_audio = song_dir / "vocal.mp3"
            backing_audio = song_dir / "backing_track.mp3"

            skip_download = False
            if vocal_audio.exists() and backing_audio.exists():
                logger.info(f"[QUEUE:{item.id}] Arquivos vocal e backing já existem. Pulando download e separação.")
                skip_download = True
            elif original_audio.exists():
                logger.info(f"[QUEUE:{item.id}] Áudio original já existe. Pulando download.")
                skip_download = True

            if not skip_download:
                from state import ffmpeg_bin_dir
                from utils.youtube import download_youtube_audio

                item.status = QueueStatus.QUEUED  # espera a vez de baixar
                async with self._download_slots:
                    item.status = QueueStatus.DOWNLOADING
                    item.stage_started = time.monotonic()
                    logger.info(f"[QUEUE:{item.id}] Baixando áudio do YouTube...")
                    success = await download_youtube_audio(item.youtube_url, original_audio, ffmpeg_bin_dir)
                if not success or not original_audio.exists():
                    raise RuntimeError("Falha ao baixar áudio do YouTube.")
                import queue_eta

                queue_eta.record("download", time.monotonic() - item.stage_started, None)

            item.progress_pct = 35

            # duração real do áudio: a estimativa das próximas etapas passa a valer para ele
            import queue_eta
            from state import ffmpeg_bin_dir as _ffmpeg_dir

            probe_target = original_audio if original_audio.exists() else vocal_audio
            if probe_target.exists():
                item.audio_sec = await asyncio.to_thread(queue_eta.probe_duration, probe_target, _ffmpeg_dir) or item.audio_sec

            # 3. Demucs (separação vocal/instrumental) — roda na GPU, seguro em paralelo
            item.status = QueueStatus.SEPARATING
            item.separator = self._separator_now()
            item.stage_started = time.monotonic()
            item.progress_pct = 40

            if vocal_audio.exists() and backing_audio.exists():
                logger.info(f"[QUEUE:{item.id}] Vocal e backing já existem. Pulando Demucs.")
            else:
                logger.info(f"[QUEUE:{item.id}] Executando Demucs (separação de áudio)...")
                target_audio = original_audio if original_audio.exists() else vocal_audio
                await self._run_demucs(item, song_dir, target_audio)
                queue_eta.record(f"separate_{item.separator}", time.monotonic() - item.stage_started, item.audio_sec)

            item.progress_pct = 70

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
            self._save()
        finally:
            # Saída do Demucs (~80 MB de WAV) sai também em erro/cancelamento.
            # O original.mp3 só sai depois de separado: numa nova tentativa ele
            # evita baixar de novo.
            shutil.rmtree(song_dir / "demucs_output", ignore_errors=True)
            original = song_dir / "original.mp3"
            if original.exists() and (song_dir / "vocal.mp3").exists() and (song_dir / "backing_track.mp3").exists():
                try:
                    original.unlink()
                except OSError:
                    pass

    async def _process_phase2(self, item: QueueItem) -> None:
        """Fase 2: Whisper + alinhamento. DEVE rodar com exclusividade na GPU."""
        song_dir = self.songs_dir / item.slug

        try:
            item.status = QueueStatus.ALIGNING
            item.progress_pct = 78
            async with self.gpu_job(item.title or item.slug):
                item.stage_started = time.monotonic()
                item.progress_pct = 80
                logger.info(f"[QUEUE:{item.id}] Fase 2 — Whisper lock adquirido. Gerando LRC + alinhamento...")

                # Determinar se usa PRO (forced alignment) ou FLASH
                align_lyrics = item.align_lyrics

                from utils.prepare import run_reinstall_song

                success = await run_reinstall_song(
                    str(song_dir),
                    language=item.language,
                    # a fase 1 já limpou e separou: limpar de novo baixava e rodava o
                    # Demucs outra vez, segurando o whisper_lock (e a partida) por minutos
                    clean_existing=False,
                    skip_prepare_song=False,  # Auto-aprovar: gera segments.json direto
                    align_lyrics=align_lyrics,
                )

                if not success:
                    raise RuntimeError("Pipeline de alinhamento falhou.")
                import queue_eta

                queue_eta.record("align_pro" if align_lyrics else "align_fast",
                                 time.monotonic() - item.stage_started, item.audio_sec)

                item.status = QueueStatus.FINALIZING
                item.progress_pct = 95

            # Sucesso!
            item.status = QueueStatus.READY
            item.progress_pct = 100
            logger.info(f"[QUEUE:{item.id}] ✅ Música '{item.title}' pronta para cantar!")
            self._save()

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
            self._save()
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
                # marca antes de agendar: duas chamadas no mesmo tick não disparam a fase 2 duas vezes
                item.status = QueueStatus.ALIGNING
                item._task = asyncio.create_task(self._process_phase2(item))
                return  # Um por vez — o próximo será processado quando este terminar

    async def _delayed_remove(self, item_id: str, delay: float) -> None:
        """Remove o item da fila após um atraso (em segundos)."""
        await asyncio.sleep(delay)
        self.remove_item(item_id)

    async def _run_demucs(self, item: QueueItem, song_dir: Path, audio_path: Path) -> None:
        """Separa vocal/instrumental (utils/separation.py: uma separação por vez)."""
        from utils.separation import SeparationCancelled, export_backing_mp3, export_mp3, separate_stems

        def _separate_and_export():
            # RoFormer (pesado na VRAM) só sem partida: a fase 1 roda fora do whisper_lock
            try:
                vocals_wav, no_vocals_wav = separate_stems(audio_path, song_dir / "demucs_output",
                                                           heavy_ok=lambda: not self._gpu_game_active,
                                                           cancel=item._cancel)
            except SeparationCancelled:
                # a tarefa da fila já saiu; a thread limpa o que o separador deixou
                shutil.rmtree(song_dir / "demucs_output", ignore_errors=True)
                logger.info(f"[QUEUE:{item.id}] Separação interrompida (música removida da fila).")
                raise
            if item._cancel.is_set():
                shutil.rmtree(song_dir / "demucs_output", ignore_errors=True)
                raise SeparationCancelled()
            # Exporta numa thread: leva segundos e a fase 1 roda durante a partida
            export_mp3(vocals_wav, song_dir / "vocal.mp3")
            # instrumental com volume normalizado (~−16 LUFS); falha só loga
            export_backing_mp3(no_vocals_wav, song_dir / "backing_track.mp3")
            # melodia de referência da afinação (pitch.json): ~2 s de CPU, já pronta na 1ª partida
            try:
                from pitch import load_or_build_reference
                from utils.audio import load_audio_full
                (song_dir / "pitch.json").unlink(missing_ok=True)
                load_or_build_reference(song_dir, load_audio_full)
            except Exception as e:
                logger.warning(f"[QUEUE:{item.id}] pitch.json não gerado: {e}")

        await asyncio.to_thread(_separate_and_export)
        logger.info(f"[QUEUE:{item.id}] Áudios vocal e backing exportados com sucesso.")
