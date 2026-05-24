"""Handler WebSocket de sala: pareia display+mic, dispara transcrição e scoring por segmento."""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import scipy.signal
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from score_engine import calculate_score
from state import room_manager, song_manager
from stt_engine import get_stt_engine
from utils.whisper_params import WHISPER_SR

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
PENDING_TASKS_TIMEOUT_SEC = 10.0

# Pasta para perfis de jogadores
PLAYERS_DIR = Path(__file__).resolve().parent.parent.parent / "players"


def get_player_profile_path(name: str) -> Path:
    # Sanitiza o nome para evitar Path Traversal
    sanitized_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip()
    if not sanitized_name:
        sanitized_name = "default_player"
    return PLAYERS_DIR / sanitized_name / "profile.json"


def get_or_create_profile(name: str) -> dict:
    path = get_player_profile_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # Cria novo perfil
    profile = {
        "name": name,
        "songs_sung": []
    }
    save_profile(name, profile)
    return profile


def save_profile(name: str, profile: dict) -> None:
    path = get_player_profile_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)


async def _send_segment_start(ws: WebSocket, segments: list, idx: int, song_title: str = "") -> None:
    if not segments or idx < 0 or idx >= len(segments):
        logger.warning(f"Tentativa de enviar segment_start com idx {idx} inválido ou sem segmentos carregados.")
        return
    segment = segments[idx]
    prev_lyrics = segments[idx - 1]["lyrics"] if idx > 0 else ""
    next_lyrics = segments[idx + 1]["lyrics"] if idx < len(segments) - 1 else ""
    upcoming_lyrics = segments[idx + 2]["lyrics"] if idx < len(segments) - 2 else ""

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
        "upcoming_lyrics": upcoming_lyrics,
        "song_title": song_title,
    })


async def _broadcast_segment_start(room, idx: int) -> None:
    if not room.segments or idx < 0 or idx >= len(room.segments):
        logger.warning(f"Tentativa de broadcast_segment_start com idx {idx} inválido ou sem segmentos carregados na sala {room.song_id}.")
        return
    if room.display:
        await _send_segment_start(room.display, room.segments, idx, room.song_title)
    for ws in room.players.values():
        await _send_segment_start(ws, room.segments, idx, room.song_title)
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


async def _notify_players_status(room) -> None:
    status = "paired" if room.players else "unpaired"
    if room.display:
        try:
            await room.display.send_json({"type": "pairing_status", "status": status, "role": "display"})
        except Exception:
            pass
    await room.broadcast({
        "type": "players_update",
        "players": list(room.players.keys()),
        "queue_count": len(room.unregistered_mics)
    })


async def _advance_registration_queue(room) -> None:
    while room.unregistered_mics:
        next_ws = room.unregistered_mics[0]
        try:
            await next_ws.send_json({"type": "register_request"})
            break
        except Exception:
            room.unregistered_mics.pop(0)
    
    for idx, ws in enumerate(room.unregistered_mics[1:], start=1):
        try:
            await ws.send_json({"type": "register_wait", "position": idx})
        except Exception:
            pass


async def process_segment_multiplayer(
    room,
    seg_idx: int,
    active_buffers: dict[str, bytearray],
    seg_lang: str,
    seg_lyrics: list,
    seg_text: str
) -> None:
    stt = get_stt_engine()
    results = {}

    async def process_player(player_name: str, seg_buffer: bytearray):
        try:
            audio_data = np.frombuffer(seg_buffer, dtype=np.float32).copy()
            duration = len(audio_data) / room.client_sample_rate
            rms_original = float(np.sqrt(np.mean(audio_data ** 2))) if len(audio_data) > 0 else 0.0

            logger.info(
                f"\n========================================\n"
                f"🎤 [DEBUG MULTI {player_name}] Segmento {seg_idx + 1} - Sala {room.song_id}\n"
                f"   - Letra Esperada: '{seg_text}'\n"
                f"   - Duração do Áudio: {duration:.2f}s\n"
                f"   - RMS: {rms_original:.6f}\n"
                f"========================================"
            )

            if _is_vocalize(seg_text):
                score, transcription_processed, matched_count, total = _score_vocalize(seg_text, rms_original)
                transcribed_text = transcription_processed
                result = {
                    "score": score,
                    "transcription": transcription_processed,
                    "matched_words": matched_count,
                    "total_expected": total,
                }
            else:
                if rms_original < 0.0018:
                    transcribed_text = ""
                    result = {
                        "score": 0.0,
                        "transcription": "",
                        "matched_words": 0,
                        "total_expected": len(seg_lyrics),
                    }
                else:
                    def compute():
                        gcd = math.gcd(WHISPER_SR, room.client_sample_rate)
                        up = WHISPER_SR // gcd
                        down = room.client_sample_rate // gcd
                        resampled = scipy.signal.resample_poly(audio_data, up, down).astype(np.float32)
                        return stt.transcribe(resampled, language=seg_lang, initial_prompt=seg_text)

                    transcribed_text, words = await asyncio.to_thread(compute)

                    prev_lyrics = None
                    if seg_idx > 0 and seg_idx - 1 < len(room.segments):
                        prev_lyrics = room.segments[seg_idx - 1]["lyrics"].split()

                    result = calculate_score(seg_lyrics, words, prev_expected_words=prev_lyrics, language=seg_lang)

            if player_name not in room.player_segment_scores:
                room.player_segment_scores[player_name] = {}
            room.player_segment_scores[player_name][seg_idx] = result["score"]

            running_avg = round(sum(room.player_segment_scores[player_name].values()) / len(room.player_segment_scores[player_name]), 1)

            results[player_name] = {
                "score": result["score"],
                "total_score": running_avg,
                "transcription": result.get("transcription", transcribed_text),
            }

        except Exception as e:
            logger.error(f"Erro no processamento do player {player_name}: {e}", exc_info=True)
            results[player_name] = {
                "score": 0.0,
                "total_score": 0.0,
                "transcription": f"(erro: {str(e)})"
            }

    await asyncio.gather(*(process_player(name, buf) for name, buf in active_buffers.items()))

    primary_name = "Solo"
    if "Solo" not in results and results:
        primary_name = list(results.keys())[0]

    primary_res = results.get(primary_name, {"score": 0.0, "total_score": 0.0, "transcription": ""})

    if primary_name == "Solo":
        room.segment_scores[seg_idx] = primary_res["score"]
        room.total_score = sum(room.segment_scores.values())
        room.scored_count = len(room.segment_scores)
    else:
        room.segment_scores[seg_idx] = primary_res["score"]
        room.total_score = sum(room.segment_scores.values())
        room.scored_count = len(room.segment_scores)

    await room.broadcast({
        "type": "segment_result",
        "score": primary_res["score"],
        "transcription": primary_res["transcription"],
        "total_score": primary_res["total_score"],
        "player_scores": results
    })


@router.websocket("/ws/room/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()

    role = websocket.query_params.get("role", "display")
    song_id = websocket.query_params.get("song_id")
    player_name = None

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
        room.segment_scores = {}
        room.total_score = 0.0
        room.scored_count = 0
        room.last_client_time = 0.0
        room.segment_buffers = {}
        room.player_segment_buffers.clear()
        room.player_segment_scores.clear()
        room.is_singing_active = False

    # Pareamento
    if role == "mic":
        room.unregistered_mics.append(websocket)
        logger.info(f"Microfone conectado na fila de registro. Fila total: {len(room.unregistered_mics)}")
        
        if len(room.unregistered_mics) == 1:
            await websocket.send_json({"type": "register_request"})
        else:
            await websocket.send_json({"type": "register_wait", "position": len(room.unregistered_mics) - 1})
    else:
        if room.display:
            try:
                await room.display.close(code=1000, reason="Novo display conectado")
            except Exception as e:
                logger.debug(f"Falha ao fechar display anterior: {e}")
        room.display = websocket
        logger.info(f"Display (TV) conectado para a sala: {room_id}")
        await _notify_players_status(room)

    try:
        await websocket.send_json({"type": "singing_state", "active": room.is_singing_active})
    except Exception as e:
        logger.debug(f"Falha ao enviar estado inicial: {e}")

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message:
                # Áudio PCM Float32 do microfone — distribui nos buffers dos segmentos ativos.
                effective_player = player_name
                if role == "display" and "PC_Local" in room.active_players:
                    effective_player = "PC_Local"

                if effective_player and effective_player in room.active_players:
                    current_time = room.last_client_time
                    for seg_idx, seg in enumerate(room.segments):
                        if (seg["sing_start"] - PRE_SING_BUFFER_SEC) <= current_time <= (seg["sing_end"] + POST_SING_BUFFER_SEC):
                            if effective_player not in room.player_segment_buffers:
                                room.player_segment_buffers[effective_player] = {}
                            if seg_idx not in room.player_segment_buffers[effective_player]:
                                room.player_segment_buffers[effective_player][seg_idx] = bytearray()
                            room.player_segment_buffers[effective_player][seg_idx].extend(message["bytes"])
                elif not room.active_players:
                    current_time = room.last_client_time
                    for seg_idx, seg in enumerate(room.segments):
                        if (seg["sing_start"] - PRE_SING_BUFFER_SEC) <= current_time <= (seg["sing_end"] + POST_SING_BUFFER_SEC):
                            if seg_idx not in room.segment_buffers:
                                room.segment_buffers[seg_idx] = bytearray()
                            room.segment_buffers[seg_idx].extend(message["bytes"])

            elif "text" in message:
                data = json.loads(message["text"])
                msg_type = data.get("type")

                if msg_type == "register_name":
                    name = data.get("name", "").strip()
                    sanitized = "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip()
                    if not name:
                        await websocket.send_json({"type": "registration_error", "message": "O apelido não pode ser vazio!"})
                    elif not sanitized:
                        await websocket.send_json({"type": "registration_error", "message": "O apelido deve conter pelo menos uma letra ou número!"})
                    elif name in room.players or sanitized in room.players or name.lower() in ("solo", "local", "tv") or sanitized.lower() in ("solo", "local", "tv"):
                        await websocket.send_json({"type": "registration_error", "message": "Este apelido já está em uso!"})
                    else:
                        player_name = name
                        room.players[name] = websocket
                        if websocket in room.unregistered_mics:
                            room.unregistered_mics.remove(websocket)
                        
                        get_or_create_profile(name)
                        await websocket.send_json({"type": "registration_success", "name": name})
                        await _notify_players_status(room)
                        await _advance_registration_queue(room)

                elif msg_type == "start_game":
                    room.game_mode = data.get("game_mode", "solo")
                    room.active_players = data.get("active_players", [])
                    logger.info(f"Jogo iniciado no modo {room.game_mode} com: {room.active_players}")
                    
                    room.player_segment_buffers.clear()
                    room.player_segment_scores.clear()
                    room.segment_buffers.clear()
                    room.segment_scores.clear()
                    room.total_score = 0.0
                    room.scored_count = 0
                    room.transcribed_segments.clear()
                    room.current_segment_idx = 0
                    room.is_singing_active = False

                    await room.broadcast({
                        "type": "game_started",
                        "game_mode": room.game_mode,
                        "active_players": room.active_players
                    })

                elif msg_type == "client_info":
                    room.client_sample_rate = data.get("sample_rate", 48000)
                    logger.info(f"Sample rate do cliente na sala {room_id}: {room.client_sample_rate}")
                    await _broadcast_segment_start(room, 0)

                elif msg_type == "playback_time":
                    current_time = data.get("current_time", 0.0)
                    room.last_client_time = current_time

                    new_idx = len(room.segments)
                    for idx, seg in enumerate(room.segments):
                        if current_time < seg["sing_end"]:
                            new_idx = idx
                            break

                    if new_idx != room.current_segment_idx:
                        # Se retrocedeu o player (seek para trás)
                        if new_idx < room.current_segment_idx:
                            logger.info(f"Retrocesso detectado: {room.current_segment_idx} -> {new_idx}")
                            for idx in list(room.segment_buffers.keys()):
                                if idx >= new_idx:
                                    room.segment_buffers.pop(idx, None)
                            
                            for p in room.player_segment_buffers:
                                for idx in list(room.player_segment_buffers[p].keys()):
                                    if idx >= new_idx:
                                        room.player_segment_buffers[p].pop(idx, None)

                            room.transcribed_segments = {idx for idx in room.transcribed_segments if idx < new_idx}
                            
                            for idx in list(room.segment_scores.keys()):
                                if idx >= new_idx:
                                    room.segment_scores.pop(idx, None)

                            for p in room.player_segment_scores:
                                for idx in list(room.player_segment_scores[p].keys()):
                                    if idx >= new_idx:
                                        room.player_segment_scores[p].pop(idx, None)

                            room.total_score = sum(room.segment_scores.values())
                            room.scored_count = len(room.segment_scores)
                            running_avg = round(room.total_score / room.scored_count, 1) if room.scored_count > 0 else 0.0

                            # Envia as notas atualizadas para o display
                            p_scores_recalc = {}
                            for p in room.player_segment_scores:
                                if room.player_segment_scores[p]:
                                    p_avg = round(sum(room.player_segment_scores[p].values()) / len(room.player_segment_scores[p]), 1)
                                else:
                                    p_avg = 0.0
                                p_scores_recalc[p] = {
                                    "score": 0.0,
                                    "total_score": p_avg,
                                    "transcription": ""
                                }

                            await room.broadcast({
                                "type": "segment_result",
                                "score": 0.0,
                                "transcription": "",
                                "total_score": running_avg,
                                "player_scores": p_scores_recalc
                            })

                        room.current_segment_idx = new_idx

                        if room.current_segment_idx < len(room.segments):
                            await _broadcast_segment_start(room, room.current_segment_idx)
                        else:
                            logger.info(f"Fim de segmentos alcançado. Transmitindo outro_start.")
                            await room.broadcast({"type": "outro_start"})

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

                    # Verifica se o segmento passou do tempo de transcrição
                    for idx, seg in enumerate(room.segments):
                        if idx not in room.transcribed_segments:
                            has_buffer = False
                            if room.active_players:
                                has_buffer = any(
                                    p in room.player_segment_buffers and idx in room.player_segment_buffers[p]
                                    for p in room.active_players
                                )
                            else:
                                has_buffer = (idx in room.segment_buffers)

                            if has_buffer:
                                should_transcribe = (
                                    current_time >= (seg["sing_end"] + POST_SING_BUFFER_SEC)
                                    or current_time >= (seg["pause_end"] - PAUSE_END_LEAD_SEC)
                                )
                                if should_transcribe:
                                    room.transcribed_segments.add(idx)
                                    logger.info(f"Processando segmento {idx + 1} para a sala {room_id}")

                                    active_buffers = {}
                                    if room.active_players:
                                        for p in room.active_players:
                                            if p in room.player_segment_buffers and idx in room.player_segment_buffers[p]:
                                                buf = room.player_segment_buffers[p].pop(idx, None)
                                                if buf:
                                                    active_buffers[p] = buf
                                    else:
                                        buf = room.segment_buffers.pop(idx, None)
                                        if buf:
                                            active_buffers["Solo"] = buf

                                    if active_buffers:
                                        task = asyncio.create_task(process_segment_multiplayer(
                                            room,
                                            idx,
                                            active_buffers,
                                            seg["language"],
                                            seg["lyrics_timed"],
                                            seg["lyrics"]
                                        ))
                                        room.pending_tasks.add(task)
                                        task.add_done_callback(room.pending_tasks.discard)

                elif msg_type == "audio_ended":
                    logger.info(f"Áudio finalizado na sala {room_id}. Finalizando jogo...")
                    if room.pending_tasks:
                        try:
                            await asyncio.wait_for(
                                asyncio.gather(*room.pending_tasks, return_exceptions=True),
                                timeout=PENDING_TASKS_TIMEOUT_SEC,
                            )
                        except asyncio.TimeoutError:
                            logger.warning(f"Timeout aguardando transcrições pendentes na sala {room_id}")
                    
                    total_score_avg = round(room.total_score / max(1, len(room.segments)), 1)

                    player_final_scores = {}
                    for p in room.active_players:
                        if p in room.player_segment_scores:
                            p_score = round(sum(room.player_segment_scores[p].values()) / max(1, len(room.segments)), 1)
                            player_final_scores[p] = p_score
                            
                            # Salva perfil
                            profile = get_or_create_profile(p)
                            profile["songs_sung"].append({
                                "name": room.song_title or room.song_id,
                                "score": p_score,
                                "date": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                            })
                            save_profile(p, profile)
                            logger.info(f"Salvo perfil de {p} com nota {p_score}% na musica {room.song_title}")

                    await room.broadcast({
                        "type": "game_over",
                        "total_score": total_score_avg,
                        "player_scores": player_final_scores
                    })
                    break

    except (WebSocketDisconnect, RuntimeError):
        logger.info(f"Conexão do papel {role} desconectada.")
    except Exception as e:
        logger.error(f"Erro no WebSocket da sala {room_id}: {e}", exc_info=True)
    finally:
        if role == "mic":
            if player_name:
                room.players.pop(player_name, None)
                if player_name in room.active_players:
                    room.active_players.remove(player_name)
                logger.info(f"Jogador {player_name} desconectado da sala.")
            
            if websocket in room.unregistered_mics:
                is_front = (room.unregistered_mics[0] == websocket)
                room.unregistered_mics.remove(websocket)
                if is_front:
                    await _advance_registration_queue(room)
                else:
                    for idx, ws in enumerate(room.unregistered_mics[1:], start=1):
                        try:
                            await ws.send_json({"type": "register_wait", "position": idx})
                        except Exception:
                            pass

            await _notify_players_status(room)

            if room.mic == websocket:
                room.mic = None
        else:
            room.display = None
            targets = list(room.players.values()) + room.unregistered_mics
            if room.mic and room.mic not in targets:
                targets.append(room.mic)
            for ws in targets:
                try:
                    await ws.send_json({"type": "pairing_status", "status": "unpaired", "role": "display"})
                except Exception as e:
                    logger.debug(f"Falha ao notificar mic do unpair: {e}")

        try:
            await websocket.close()
        except Exception as e:
            logger.debug(f"Falha ao fechar websocket: {e}")

        room_manager.clean_room(room_id)

