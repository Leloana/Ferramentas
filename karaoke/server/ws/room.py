"""Handler WebSocket de sala: pareia display+mic, dispara transcrição e scoring por segmento."""
from __future__ import annotations

import asyncio
import json
import logging
import math
import re

import numpy as np
import scipy.signal
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from score_engine import calculate_score
from state import room_manager, song_manager
from stt_engine import get_stt_engine

logger = logging.getLogger(__name__)
router = APIRouter()

# Trechos não-lexicais que pulam o Whisper e são pontuados só por energia (RMS).
VOCALIZE_WORDS = {
    "oh", "la", "uh", "na", "ah", "oo", "woo", "yeah", "yeh", "wow",
    "hm", "hmm", "hey", "hei",
}
VOCALIZE_HIGH_RMS = 0.008
VOCALIZE_LOW_RMS = 0.002

# Janelas de captura/transição relativas aos timestamps do segmento.
PRE_SING_BUFFER_SEC = 1.5
POST_SING_BUFFER_SEC = 0.5
SINGING_PRE_BUFFER_SEC = 1.0
PAUSE_END_LEAD_SEC = 0.15
WHISPER_TARGET_SR = 16000
PENDING_TASKS_TIMEOUT_SEC = 10.0


async def _send_segment_start(ws: WebSocket, segments: list, idx: int, song_title: str = "") -> None:
    segment = segments[idx]
    prev_lyrics = segments[idx - 1]["lyrics"] if idx > 0 else ""
    next_lyrics = segments[idx + 1]["lyrics"] if idx < len(segments) - 1 else ""

    await ws.send_json({
        "type": "segment_start",
        "id": segment["id"],
        "label": segment["label"],
        "sing_start": segment["sing_start"],
        "sing_end": segment["sing_end"],
        "lyrics": segment["lyrics"],
        "lyrics_timed": segment["lyrics_timed"],
        "prev_lyrics": prev_lyrics,
        "next_lyrics": next_lyrics,
        "song_title": song_title,
    })


async def _broadcast_segment_start(room, idx: int) -> None:
    if room.display:
        await _send_segment_start(room.display, room.segments, idx, room.song_title)
    if room.mic:
        await _send_segment_start(room.mic, room.segments, idx, room.song_title)


def _score_vocalize(seg_text: str, rms: float) -> tuple[float, str, int, int]:
    """Pontua segmentos não-lexicais (oh-oh, la-la-la) só pela energia."""
    clean_words = [re.sub(r"[^\w]", "", w.lower()) for w in seg_text.split()]
    total = len(clean_words)
    if rms > VOCALIZE_HIGH_RMS:
        return 100.0, seg_text, total, total
    if rms > VOCALIZE_LOW_RMS:
        return 50.0, "(som baixo)", total // 2, total
    return 0.0, "(silêncio)", 0, total


def _is_vocalize(seg_text: str) -> bool:
    clean_words = [re.sub(r"[^\w]", "", w.lower()) for w in seg_text.split()]
    return len(clean_words) > 0 and all(w in VOCALIZE_WORDS for w in clean_words if w)


@router.websocket("/ws/room/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()

    role = websocket.query_params.get("role", "display")
    song_id = websocket.query_params.get("song_id")

    segments = []
    song_title = ""
    if song_id:
        song_data = song_manager.get_song_data(song_id)
        if not song_data:
            await websocket.close(code=1008, reason="Música não encontrada")
            return
        segments = song_data["segments"]
        artist = song_data.get("artist")
        title = song_data.get("title", "")
        song_title = f"{title} - {artist}" if artist else title

    room = room_manager.get_or_create_room(room_id, song_id or "", segments)
    if song_title:
        room.song_title = song_title

    # Display novo para outra música → reset da sala.
    if role == "display" and song_id:
        room.song_id = song_id
        room.song_title = song_title
        room.segments = segments
        room.current_segment_idx = 0
        room.transcribed_segments = set()
        room.total_score = 0.0
        room.scored_count = 0
        room.last_client_time = 0.0
        room.audio_buffer = bytearray()
        room.segment_buffers = {}
        room.is_singing_active = False

    # Pareamento
    if role == "mic":
        if room.mic:
            try:
                await room.mic.close(code=1000, reason="Novo microfone conectado")
            except Exception as e:
                logger.debug(f"Falha ao fechar mic anterior: {e}")
        room.mic = websocket
        logger.info(f"Microfone conectado para a sala: {room_id}")
        await websocket.send_json({"type": "pairing_status", "status": "paired", "role": "mic"})
        if room.display:
            await room.display.send_json({"type": "pairing_status", "status": "paired", "role": "display"})
    else:
        if room.display:
            try:
                await room.display.close(code=1000, reason="Novo display conectado")
            except Exception as e:
                logger.debug(f"Falha ao fechar display anterior: {e}")
        room.display = websocket
        logger.info(f"Display (TV) conectado para a sala: {room_id}")
        if room.mic:
            await websocket.send_json({"type": "pairing_status", "status": "paired", "role": "display"})
            try:
                await room.mic.send_json({"type": "pairing_status", "status": "paired", "role": "mic"})
            except Exception as e:
                logger.debug(f"Falha ao notificar mic do pareamento: {e}")
        else:
            await websocket.send_json({"type": "pairing_status", "status": "unpaired", "role": "display"})

    try:
        await websocket.send_json({"type": "singing_state", "active": room.is_singing_active})
    except Exception as e:
        logger.debug(f"Falha ao enviar estado inicial: {e}")

    stt = get_stt_engine()

    async def process_and_score(seg_idx: int, audio_data: np.ndarray, seg_lang: str, seg_lyrics, seg_text: str) -> None:
        try:
            duration = len(audio_data) / room.client_sample_rate
            rms_original = float(np.sqrt(np.mean(audio_data ** 2))) if len(audio_data) > 0 else 0.0

            logger.info(
                f"\n========================================\n"
                f"🎤 [DEBUG MICROFONE] Segmento {seg_idx + 1} - Sala {room_id}\n"
                f"   - Letra Esperada: '{seg_text}'\n"
                f"   - Duração do Áudio Recebido: {duration:.2f}s ({len(audio_data)} samples)\n"
                f"   - RMS de Entrada: {rms_original:.6f}\n"
                f"========================================"
            )

            if _is_vocalize(seg_text):
                logger.info(f"⚡ [Bypass Vocalize] '{seg_text}' avaliado por energia (RMS: {rms_original:.6f})")
                score, transcription_processed, matched_count, total = _score_vocalize(seg_text, rms_original)
                transcribed_text = transcription_processed
                room.total_score += score
                result = {
                    "score": score,
                    "transcription": transcription_processed,
                    "matched_words": matched_count,
                    "total_expected": total,
                }
            else:
                # Resampling polifásico para 16 kHz com filtro FIR anti-aliasing
                def compute():
                    gcd = math.gcd(WHISPER_TARGET_SR, room.client_sample_rate)
                    up = WHISPER_TARGET_SR // gcd
                    down = room.client_sample_rate // gcd
                    resampled = scipy.signal.resample_poly(audio_data, up, down).astype(np.float32)
                    return stt.transcribe(resampled, language=seg_lang, initial_prompt=seg_text)

                transcribed_text, words = await asyncio.to_thread(compute)

                prev_lyrics = None
                if seg_idx > 0 and seg_idx - 1 < len(room.segments):
                    prev_lyrics = room.segments[seg_idx - 1]["lyrics"].split()

                result = calculate_score(seg_lyrics, words, prev_expected_words=prev_lyrics, language=seg_lang)
                room.total_score += result["score"]

            room.scored_count += 1
            running_avg = round(room.total_score / room.scored_count, 1)

            logger.info(
                f"\n========================================\n"
                f"📝 [DEBUG TRANSCRIÇÃO] Segmento {seg_idx + 1} - Sala {room_id}\n"
                f"   - Texto Transcrito (Whisper): '{transcribed_text}'\n"
                f"   - Palavras Mapeadas: {result['matched_words']}/{result['total_expected']}\n"
                f"   - Transcrição acústica processada: '{result['transcription']}'\n"
                f"   - Pontuação Deste Segmento: {result['score']}%\n"
                f"   - Média de Pontuação Geral Atual: {running_avg}%\n"
                f"========================================"
            )

            await room.broadcast({
                "type": "segment_result",
                "score": result["score"],
                "transcription": result["transcription"],
                "total_score": running_avg,
            })
        except Exception as e:
            logger.error(f"Erro no processamento do segmento: {e}", exc_info=True)

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message:
                # Áudio PCM Float32 do microfone — distribui nos buffers dos segmentos ativos.
                current_time = room.last_client_time
                for seg_idx, seg in enumerate(room.segments):
                    if (seg["sing_start"] - PRE_SING_BUFFER_SEC) <= current_time <= (seg["sing_end"] + POST_SING_BUFFER_SEC):
                        if seg_idx not in room.segment_buffers:
                            room.segment_buffers[seg_idx] = bytearray()
                        room.segment_buffers[seg_idx].extend(message["bytes"])

                # Buffer global (retrocompatibilidade)
                if room.current_segment_idx < len(room.segments):
                    current_seg = room.segments[room.current_segment_idx]
                    if (current_seg["sing_start"] - PRE_SING_BUFFER_SEC) <= current_time <= (current_seg["sing_end"] + POST_SING_BUFFER_SEC):
                        room.audio_buffer.extend(message["bytes"])

            elif "text" in message:
                data = json.loads(message["text"])
                msg_type = data.get("type")

                if msg_type == "client_info":
                    room.client_sample_rate = data.get("sample_rate", 48000)
                    logger.info(f"Sample rate do cliente na sala {room_id}: {room.client_sample_rate}")
                    await _broadcast_segment_start(room, 0)

                elif msg_type == "playback_time":
                    current_time = data.get("current_time", 0.0)
                    room.last_client_time = current_time

                    is_singing = False
                    if room.current_segment_idx < len(room.segments):
                        current_seg = room.segments[room.current_segment_idx]
                        is_singing = (
                            (current_seg["sing_start"] - SINGING_PRE_BUFFER_SEC)
                            <= current_time
                            <= (current_seg["sing_end"] + POST_SING_BUFFER_SEC)
                        )

                    if is_singing != room.is_singing_active:
                        room.is_singing_active = is_singing
                        await room.broadcast({"type": "singing_state", "active": is_singing})

                    if room.current_segment_idx < len(room.segments):
                        current_seg = room.segments[room.current_segment_idx]
                        should_transcribe = (
                            current_time >= (current_seg["sing_end"] + POST_SING_BUFFER_SEC)
                            or current_time >= current_seg["pause_end"] - PAUSE_END_LEAD_SEC
                        )

                        seg_buffer = room.segment_buffers.get(room.current_segment_idx)
                        if should_transcribe and seg_buffer and room.current_segment_idx not in room.transcribed_segments:
                            room.transcribed_segments.add(room.current_segment_idx)
                            logger.info(f"Processando segmento {room.current_segment_idx + 1} para a sala {room_id}")

                            raw_audio = np.frombuffer(seg_buffer, dtype=np.float32).copy()
                            room.segment_buffers.pop(room.current_segment_idx, None)
                            room.audio_buffer = bytearray()

                            # Referência forte → evita GC prematuro da task.
                            task = asyncio.create_task(process_and_score(
                                room.current_segment_idx,
                                raw_audio,
                                current_seg["language"],
                                current_seg["lyrics_timed"],
                                current_seg["lyrics"],
                            ))
                            room.pending_tasks.add(task)
                            task.add_done_callback(room.pending_tasks.discard)

                        # Avança para o próximo segmento ao término do canto.
                        if current_time >= current_seg["sing_end"]:
                            room.current_segment_idx += 1
                            if room.current_segment_idx < len(room.segments):
                                await _broadcast_segment_start(room, room.current_segment_idx)
                            else:
                                logger.info(f"Último segmento cantado na sala {room_id}. Aguardando o backing track terminar...")
                                await room.broadcast({"type": "outro_start"})

                elif msg_type == "audio_ended":
                    logger.info(f"Áudio finalizado pelo cliente na sala {room_id}. Finalizando jogo...")
                    if room.pending_tasks:
                        try:
                            await asyncio.wait_for(
                                asyncio.gather(*room.pending_tasks, return_exceptions=True),
                                timeout=PENDING_TASKS_TIMEOUT_SEC,
                            )
                        except asyncio.TimeoutError:
                            logger.warning(f"Timeout aguardando transcrições pendentes na sala {room_id}")
                    total_score_avg = round(room.total_score / max(1, len(room.segments)), 1)
                    await room.broadcast({"type": "game_over", "total_score": total_score_avg})
                    break

    except (WebSocketDisconnect, RuntimeError):
        logger.info(f"Conexão do papel {role} desconectada na sala {room_id}.")
    except Exception as e:
        logger.error(f"Erro no WebSocket da sala {room_id}: {e}", exc_info=True)
    finally:
        if role == "mic":
            room.mic = None
            if room.display:
                try:
                    await room.display.send_json({"type": "pairing_status", "status": "unpaired", "role": "mic"})
                except Exception as e:
                    logger.debug(f"Falha ao notificar display do unpair: {e}")
        else:
            room.display = None
            if room.mic:
                try:
                    await room.mic.send_json({"type": "pairing_status", "status": "unpaired", "role": "display"})
                except Exception as e:
                    logger.debug(f"Falha ao notificar mic do unpair: {e}")

        try:
            await websocket.close()
        except Exception as e:
            logger.debug(f"Falha ao fechar websocket: {e}")

        room_manager.clean_room(room_id)
