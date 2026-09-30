"""Handler WebSocket de sala: pareia display+mic, dispara transcrição e scoring por segmento."""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from mic_stream import STREAM_SR, MicTimeline, parse_packet, segment_window
from recorder import GameRecording, recording_base_dir
from segment_scoring import (
    needs_whisper, score_whisper_free, score_words, shift_words, transcribe_kwargs,
)
from state import room_manager, song_manager, queue_manager
from pitch import load_or_build_reference, verse_pitch_score
from players import get_or_create_profile, record_game, song_leaderboard
from song_requests import add_request, remove_request, requests_payload
from stt_engine import get_stt_engine
from utils.audio import load_audio_full

logger = logging.getLogger(__name__)
router = APIRouter()

# Janelas de captura/transição relativas aos timestamps do segmento.
PRE_SING_BUFFER_SEC = 1.5
POST_SING_BUFFER_SEC = 0.5
SINGING_PRE_BUFFER_SEC = 1.0
# Espera extra após o fim da janela: os últimos pacotes do celular ainda
# podem estar a caminho (rede local ou túnel). Piso folgado porque um pico de
# atraso só nos últimos pacotes ainda não aparece no atraso medido.
LATE_PACKET_GRACE_SEC = 0.6
# Com rede lenta a folga acompanha o atraso observado, até este teto.
MAX_LATE_PACKET_GRACE_SEC = 2.0
PENDING_TASKS_TIMEOUT_SEC = 10.0

MAX_NICKNAME_LEN = 15
RESERVED_NICKNAMES = ("solo", "local", "tv", "pc_local")


def _nickname_taken(room, name: str, sanitized: str) -> bool:
    # compara pelo nome da pasta do perfil, sem caixa: "Ana." e "ana" são o mesmo perfil
    key = sanitized.lower()
    if name.lower() in RESERVED_NICKNAMES or key in RESERVED_NICKNAMES:
        return True
    for other in room.players:
        other_key = "".join(c for c in other if c.isalnum() or c in ("-", "_")).strip().lower()
        if other == name or other_key == key:
            return True
    return False


async def _send_segment_start(ws: WebSocket, segments: list, idx: int, song_title: str = "",
                              turn: list | None = None) -> None:
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
        "language": segment.get("language"),  # japonês junta as palavras sem espaço
        "lyrics_romaji": segment.get("lyrics_romaji"),  # só em japonês (celular)
        "prev_lyrics": prev_lyrics,
        "next_lyrics": next_lyrics,
        "upcoming_lyrics": upcoming_lyrics,
        "song_title": song_title,
        "turn": turn,  # revezar versos: de quem é este verso (None = todos)
    })


async def _broadcast_segment_start(room, idx: int) -> None:
    if not room.segments or idx < 0 or idx >= len(room.segments):
        logger.warning(f"Tentativa de broadcast_segment_start com idx {idx} inválido ou sem segmentos carregados na sala {room.song_id}.")
        return
    turn = turn_owner(room.segments, room.turn_order, idx)
    if room.display:
        await _send_segment_start(room.display, room.segments, idx, room.song_title, turn)
    # list(): um celular pode entrar/sair durante o await e mudar o dict
    for ws in list(room.players.values()):
        try:
            await _send_segment_start(ws, room.segments, idx, room.song_title, turn)
        except Exception as e:
            logger.debug(f"Falha ao enviar segment_start a um celular: {e}")
    if room.mic:
        await _send_segment_start(room.mic, room.segments, idx, room.song_title, turn)


async def _notify_mics_display_status(room, status: str) -> None:
    """Avisa os celulares (registrados ou na fila) se a TV está conectada."""
    targets = list(room.players.values()) + room.unregistered_mics
    if room.mic and room.mic not in targets:
        targets.append(room.mic)
    for ws in targets:
        try:
            await ws.send_json({"type": "pairing_status", "status": status, "role": "display"})
        except Exception as e:
            logger.debug(f"Falha ao avisar o celular do estado da TV ({status}): {e}")


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
    segments: list[dict],
    seg_idx: int,
    active_audio: dict[str, tuple[np.ndarray, float]],
    window: tuple[float, float],
    scoring_mode: str = "timing"
) -> None:
    stt = get_stt_engine()
    results = {}
    game_id = room.game_id
    started = time.monotonic()
    # Lista capturada no disparo: a TV pode trocar de música antes do Whisper terminar.
    segment = segments[seg_idx]
    prev_segment = segments[seg_idx - 1] if seg_idx > 0 else None
    window_offset = window[0] - segment["sing_start"]

    async def process_player(player_name: str, audio_data: np.ndarray, rms_original: float):
        try:
            duration = len(audio_data) / STREAM_SR

            logger.info(
                f"\n========================================\n"
                f"🎤 [DEBUG MULTI {player_name}] Segmento {seg_idx + 1} - Sala {room.song_id}\n"
                f"   - Letra Esperada: '{segment['lyrics']}'\n"
                f"   - Duração do Áudio: {duration:.2f}s\n"
                f"   - RMS: {rms_original:.6f}\n"
                f"========================================"
            )

            words = []
            # as duas passadas do Whisper (com e sem a letra como dica), para o gravador
            stt_runs: dict = {}
            if needs_whisper(segment, rms_original):
                def compute():
                    return stt.transcribe(audio_data, **transcribe_kwargs(segment), details=stt_runs)

                async with queue_manager.whisper_lock:
                    if room.game_id != game_id:
                        return  # partida acabou/trocou enquanto esperava a GPU
                    transcribed_text, words = await asyncio.to_thread(compute)
                if room.game_id != game_id:
                    return
                pitch = await _pitch_for(room, audio_data, window[0])
                words = shift_words(words, window_offset)
                result = score_words(segment, prev_segment, words, scoring_mode)
            else:
                result = score_whisper_free(segment, rms_original)
                transcribed_text = result["transcription"]
                pitch = None

            if room.recording:
                runs = {k: shift_words(stt_runs[k], window_offset) if stt_runs.get(k) is not None else None
                        for k in ("prompted_words", "unprompted_words")}
                room.recording.add_segment_result(
                    player_name, seg_idx, window, rms_original, transcribed_text, words, result,
                    used=stt_runs.get("used"), **runs,
                )

            if player_name not in room.player_segment_scores:
                room.player_segment_scores[player_name] = {}
            room.player_segment_scores[player_name][seg_idx] = result["score"]

            running_avg = round(sum(room.player_segment_scores[player_name].values()) / len(room.player_segment_scores[player_name]), 1)

            pitch_avg = None
            if pitch is not None:
                pscores = room.player_pitch_scores.setdefault(player_name, {})
                pscores[seg_idx] = pitch
                pitch_avg = round(sum(pscores.values()) / len(pscores), 1)

            results[player_name] = {
                "score": result["score"],
                "total_score": running_avg,
                "transcription": result.get("transcription", transcribed_text),
                # afinação: informativa por enquanto, fora da nota (calibrar no servidor)
                "pitch": pitch,
                "pitch_avg": pitch_avg,
            }

        except Exception as e:
            logger.error(f"Erro no processamento do player {player_name}: {e}", exc_info=True)
            results[player_name] = {
                "score": 0.0,
                "total_score": 0.0,
                "transcription": f"(erro: {str(e)})"
            }

    await asyncio.gather(*(process_player(name, audio, rms) for name, (audio, rms) in active_audio.items()))
    if room.game_id != game_id:
        logger.info(f"Resultado do verso {seg_idx + 1} descartado: é de uma partida anterior")
        return

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

    room.verse_latencies.append(round(time.monotonic() - started, 2))
    await room.broadcast({
        "type": "segment_result",
        "score": primary_res["score"],
        "transcription": primary_res["transcription"],
        "total_score": primary_res["total_score"],
        "pitch": primary_res.get("pitch"),
        "pitch_avg": primary_res.get("pitch_avg"),
        "player_scores": results
    })


def _track(room, task) -> None:
    room.background_tasks.add(task)
    task.add_done_callback(room.background_tasks.discard)


async def _pitch_for(room, audio: np.ndarray, window_start: float):
    """Nota de afinação do verso (None sem referência ou sem voz suficiente)."""
    reference = room.pitch_reference
    if not reference:
        return None
    result = await asyncio.to_thread(verse_pitch_score, audio, window_start, reference, room.transpose)
    return result["score"] if result else None


async def _load_pitch_reference(room, song_id: str) -> None:
    """Carrega (ou gera, ~2 s de CPU) o pitch.json da música em segundo plano."""
    song_dir = song_manager.get_song_dir(song_id)
    if song_dir is None:
        return
    reference = await asyncio.to_thread(load_or_build_reference, song_dir, load_audio_full)
    if room.song_id == song_id:
        room.pitch_reference = reference


def _late_packet_grace(room) -> float:
    """Folga antes de fechar um verso: piso fixo ou o atraso do celular mais lento."""
    lateness = max((t.lateness for t in room.mic_timelines.values()), default=0.0)
    return min(MAX_LATE_PACKET_GRACE_SEC, max(LATE_PACKET_GRACE_SEC, lateness + 0.1))


def turn_owner(segments: list, turn_order: list | None, idx: int) -> list | None:
    """Revezar versos: o k-ésimo verso com letra é do time k % n (None = todos).

    Mesma regra do front (client/js/turns.js)."""
    if not turn_order or len(turn_order) < 2 or not (0 <= idx < len(segments)):
        return None
    if not str(segments[idx].get("lyrics") or "").strip():
        return None
    k = sum(1 for seg in segments[:idx] if str(seg.get("lyrics") or "").strip())
    return turn_order[k % len(turn_order)]


def _verse_players(room, idx: int) -> list:
    """Quem é pontuado neste verso (no revezamento, só o time da vez)."""
    players = room.active_players or ["Solo"]
    owner = turn_owner(room.segments, room.turn_order, idx)
    if owner is None:
        return players
    return [p for p in players if p in owner]


def _all_audio_arrived(room, t1: float, players: list | None = None) -> bool:
    players = players or room.active_players or ["Solo"]
    for player in players:
        timeline = room.mic_timelines.get(player)
        end = timeline.end_time() if timeline else None
        if end is None or end < t1:
            return False
    return True


def _dispatch_due_segments(room, current_time: float | None) -> None:
    """Fecha e pontua os versos cuja janela já passou (None = todos, fim da música)."""
    grace = _late_packet_grace(room)
    for idx in range(len(room.segments)):
        if idx in room.transcribed_segments:
            continue
        t0, t1 = segment_window(room.segments, idx, PRE_SING_BUFFER_SEC, POST_SING_BUFFER_SEC)
        if current_time is not None and current_time < t1 + grace:
            # A folga é para pacotes atrasados: se o áudio de todos os celulares
            # já cobre a janela, pontua na hora (~0,5 s mais cedo na rede local).
            if current_time < t1 or not _all_audio_arrived(room, t1, _verse_players(room, idx)):
                continue
        room.transcribed_segments.add(idx)

        active_audio = {}
        for player in _verse_players(room, idx):
            timeline = room.mic_timelines.get(player)
            if not timeline:
                continue
            audio, covered = timeline.extract(t0, t1)
            if not room.recording:  # a gravação guarda a música inteira
                timeline.prune_before(t1)
            if covered.any():
                rms = float(np.sqrt(np.mean(audio[covered] ** 2)))
                active_audio[player] = (audio, rms)

        if not active_audio:
            continue
        logger.info(f"Processando segmento {idx + 1} (janela {t0:.2f}s–{t1:.2f}s) para a sala {room.song_id}")
        task = asyncio.create_task(process_segment_multiplayer(
            room, room.segments, idx, active_audio, (t0, t1), room.scoring_mode
        ))
        room.pending_tasks.add(task)
        task.add_done_callback(room.pending_tasks.discard)


DISPLAY_REPLACED_CODE = 4001


@router.websocket("/ws/room/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()

    role = websocket.query_params.get("role", "display")
    song_id = websocket.query_params.get("song_id")
    # Display que caiu no meio da música e voltou: mantém placar e gravação.
    resume = websocket.query_params.get("resume") == "1"
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
    resuming = resume and role == "display" and song_id and room.song_id == song_id
    if resuming:
        logger.info(f"Display reconectado na sala {room_id}: partida retomada sem reset")
    if role == "display" and song_id and not resuming:
        room.game_id += 1
        if room.song_id != song_id:
            room.pitch_reference = None
        room.player_pitch_scores = {}
        _track(room, asyncio.create_task(_load_pitch_reference(room, song_id)))
        room.song_id = song_id
        room.song_title = song_title
        room.segments = segments
        room.current_segment_idx = 0
        room.transcribed_segments = set()
        room.segment_scores = {}
        room.total_score = 0.0
        room.scored_count = 0
        room.last_client_time = 0.0
        room.reset_audio()
        room.player_segment_scores.clear()
        room.is_singing_active = False

    # Pareamento
    if role == "mic":
        room.unregistered_mics.append(websocket)
        logger.info(f"Microfone conectado na fila de registro. Fila total: {len(room.unregistered_mics)}")
        
        try:
            if len(room.unregistered_mics) == 1:
                await websocket.send_json({"type": "register_request"})
            else:
                await websocket.send_json({"type": "register_wait", "position": len(room.unregistered_mics) - 1})
        except Exception as e:
            # Celular fechou na hora (recarregou): sem isso o socket morto ficava
            # na frente da fila e ninguém mais recebia register_request.
            logger.debug(f"Celular saiu antes do pareamento: {e}")
            if websocket in room.unregistered_mics:
                was_front = room.unregistered_mics[0] is websocket
                room.unregistered_mics.remove(websocket)
                if was_front:
                    await _advance_registration_queue(room)
            room_manager.clean_room(room_id)
            return
    else:
        if room.display:
            try:
                # 4001: o cliente sabe que foi substituído e não tenta reconectar
                await room.display.close(code=DISPLAY_REPLACED_CODE, reason="Novo display conectado")
            except Exception as e:
                logger.debug(f"Falha ao fechar display anterior: {e}")
        room.display = websocket
        logger.info(f"Display (TV) conectado para a sala: {room_id}")
        await _notify_players_status(room)
        # Celular que viu "TV Desconectada" numa troca de página volta a "pareado".
        await _notify_mics_display_status(room, "paired")

    try:
        await websocket.send_json({"type": "singing_state", "active": room.is_singing_active})
        if room.song_requests:  # fila da noite já em andamento: quem chega vê
            await websocket.send_json(requests_payload(room))
    except Exception as e:
        logger.debug(f"Falha ao enviar estado inicial: {e}")

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message:
                # Pacote do microfone (mic_stream.PACKET_HEADER + Int16 16 kHz) —
                # entra na linha do tempo do jogador pelo tempo da música agora.
                effective_player = player_name
                if role == "display" and "PC_Local" in room.active_players:
                    effective_player = "PC_Local"

                if room.active_players:
                    stream_key = effective_player if effective_player in room.active_players else None
                else:
                    stream_key = "Solo"

                packet = parse_packet(message["bytes"])
                song_time = room.song_clock.now()
                if packet is None:
                    logger.debug("Pacote de áudio fora do formato KM01 descartado.")
                elif stream_key:
                    first_index, sample_rate, samples = packet
                    if sample_rate != STREAM_SR:
                        logger.warning(f"Pacote a {sample_rate} Hz descartado (esperado {STREAM_SR} Hz).")
                    elif song_time is not None:
                        timeline = room.mic_timelines.setdefault(stream_key, MicTimeline())
                        timeline.add(first_index, samples, song_time, room.song_clock.epoch)
                    elif stream_key in room.mic_timelines and room.song_clock.just_stopped():
                        room.mic_timelines[stream_key].add_in_flight(first_index, samples)

            elif "text" in message:
                # Mensagem malformada é ignorada: uma exceção aqui derrubaria a TV
                try:
                    data = json.loads(message["text"])
                except ValueError:
                    logger.debug("Mensagem de texto inválida descartada.")
                    continue
                if not isinstance(data, dict):
                    continue
                msg_type = data.get("type")

                if msg_type == "register_name":
                    raw_name = data.get("name")
                    name = raw_name.strip() if isinstance(raw_name, str) else ""
                    # sem caracteres de controle, tamanho do campo do celular (15)
                    name = "".join(c for c in name if c.isprintable())[:MAX_NICKNAME_LEN].strip()
                    sanitized = "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip()
                    if not name:
                        await websocket.send_json({"type": "registration_error", "message": "O apelido não pode ser vazio!"})
                    elif not sanitized:
                        await websocket.send_json({"type": "registration_error", "message": "O apelido deve conter pelo menos uma letra ou número!"})
                    elif _nickname_taken(room, name, sanitized):
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

                elif msg_type == "start_game" and queue_manager.alignment_busy():
                    # Mutex de GPU: gerando letra de uma música. Começar agora deixaria
                    # a nota de cada verso esperando minutos pelo Whisper.
                    await websocket.send_json({
                        "type": "start_blocked",
                        "reason": f"Gerando a letra de {queue_manager.alignment_busy()}",
                    })

                elif msg_type == "start_game":
                    room.game_mode = data.get("game_mode", "solo")
                    room.active_players = data.get("active_players", [])
                    room.scoring_mode = data.get("scoring_mode", "timing")
                    logger.info(f"Jogo iniciado no modo {room.game_mode} (pontuação: {room.scoring_mode}) com: {room.active_players}")
                    
                    room.game_id += 1
                    room.player_pitch_scores = {}
                    # revezar versos: [[mics do time 1], [mics do time 2], ...]
                    turns = data.get("turn_order")
                    room.turn_order = (
                        [[str(m) for m in g] for g in turns if isinstance(g, list) and g]
                        if data.get("turns") and isinstance(turns, list) else None
                    )
                    if room.turn_order is not None and len(room.turn_order) < 2:
                        room.turn_order = None
                    try:
                        room.transpose = float(data.get("transpose", 0) or 0)
                    except (TypeError, ValueError):
                        room.transpose = 0.0
                    room.reset_audio()
                    room.player_segment_scores.clear()
                    room.segment_scores.clear()
                    base_dir = recording_base_dir()
                    if base_dir:
                        room.recording = GameRecording(
                            base_dir, room.song_id, room.song_title, room.segments, room.scoring_mode,
                            {"pre_sing_sec": PRE_SING_BUFFER_SEC, "post_sing_sec": POST_SING_BUFFER_SEC},
                        )
                        logger.info(f"Gravando a partida em {room.recording.dir}")
                    room.total_score = 0.0
                    room.scored_count = 0
                    room.transcribed_segments.clear()
                    room.current_segment_idx = 0
                    room.is_singing_active = False

                    queue_manager.notify_game_started()

                    await room.broadcast({
                        "type": "game_started",
                        "game_mode": room.game_mode,
                        "active_players": room.active_players
                    })

                elif msg_type == "request_song":
                    # "Quero cantar": celular registrado pede para si; a TV pode pedir para qualquer mic
                    singer = player_name if role == "mic" else str(data.get("singer") or "Local")[:MAX_NICKNAME_LEN]
                    song_id = str(data.get("song_id") or "")
                    song = next((s_ for s_ in song_manager.list_songs() if s_["id"] == song_id and s_.get("is_ready")), None)
                    if not singer:
                        await websocket.send_json({"type": "request_error", "message": "Entre com um apelido primeiro."})
                    elif song is None:
                        await websocket.send_json({"type": "request_error", "message": "Música não encontrada."})
                    else:
                        _, err = add_request(room, song, singer)
                        if err:
                            await websocket.send_json({"type": "request_error", "message": err})
                        else:
                            await room.broadcast(requests_payload(room))

                elif msg_type == "cancel_request":
                    owner = player_name if role == "mic" else None
                    if remove_request(room, str(data.get("id") or ""), owner):
                        await room.broadcast(requests_payload(room))

                elif msg_type == "transpose" and role == "display":
                    # TV mudou o tom da trilha: a referência da afinação acompanha
                    try:
                        room.transpose = float(data.get("semitones", 0) or 0)
                    except (TypeError, ValueError):
                        pass

                elif msg_type == "client_info":
                    # Só informativo: o áudio chega sempre a STREAM_SR, com a taxa no próprio pacote.
                    logger.info(f"Sample rate nativo do cliente ({role}) na sala {room_id}: {data.get('sample_rate')}")
                    # retomada: reenvia o verso atual, não o primeiro
                    await _broadcast_segment_start(room, room.current_segment_idx if resuming else 0)

                elif msg_type == "playback_time":
                    try:
                        current_time = float(data.get("current_time", 0.0))
                    except (TypeError, ValueError):
                        continue
                    if not math.isfinite(current_time) or current_time < 0:
                        continue
                    room.last_client_time = current_time
                    room.song_clock.update(current_time)

                    new_idx = len(room.segments)
                    for idx, seg in enumerate(room.segments):
                        if current_time < seg["sing_end"]:
                            new_idx = idx
                            break

                    if new_idx != room.current_segment_idx:
                        # Se retrocedeu o player (seek para trás)
                        if new_idx < room.current_segment_idx:
                            logger.info(f"Retrocesso detectado: {room.current_segment_idx} -> {new_idx}")
                            if new_idx < len(room.segments):
                                redo_from, _ = segment_window(room.segments, new_idx, PRE_SING_BUFFER_SEC, POST_SING_BUFFER_SEC)
                                for timeline in room.mic_timelines.values():
                                    timeline.drop_from(redo_from)

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
                                "recalc": True,  # só totais: o cliente não mostra nota de verso
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

                    _dispatch_due_segments(room, current_time)

                elif msg_type == "audio_ended":
                    logger.info(f"Áudio finalizado na sala {room_id}. Finalizando jogo...")
                    # Versos cuja janela não fechou antes do fim do áudio. A folga deixa
                    # chegar os últimos pacotes, que vêm por outro WebSocket. O relógio
                    # congela antes: extrapolado, ele empurraria esses pacotes para depois.
                    room.song_clock.stop()
                    await asyncio.sleep(_late_packet_grace(room))
                    _dispatch_due_segments(room, None)
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
                    records = {}
                    for p in room.active_players:
                        if p in room.player_segment_scores:
                            # no revezamento, cada um é medido só nos versos dele
                            own = len(room.segments)
                            if room.turn_order:
                                own = sum(1 for i in range(len(room.segments))
                                          if p in (turn_owner(room.segments, room.turn_order, i) or []))
                            p_score = round(sum(room.player_segment_scores[p].values()) / max(1, own), 1)
                            player_final_scores[p] = p_score
                            
                            # Salva perfil (falha aqui não pode impedir o game_over)
                            if p != "PC_Local":
                                try:
                                    pv = room.player_pitch_scores.get(p) or {}
                                    records[p] = record_game(
                                        p, room.song_id, room.song_title or room.song_id, p_score,
                                        pitch=round(sum(pv.values()) / len(pv), 1) if pv else None,
                                        mode=room.game_mode,
                                    )
                                    logger.info(f"Salvo perfil de {p} com nota {p_score}% na musica {room.song_title}")
                                except Exception as e:
                                    logger.error(f"Falha ao salvar o perfil de {p}: {e}", exc_info=True)

                    # contagem de versos por faixa (mesmas do carimbo: 85 / 70), p/ o cartão do fim
                    player_stats = {
                        p: {
                            "good": sum(1 for v in scores.values() if v >= 85),
                            "ok": sum(1 for v in scores.values() if 70 <= v < 85),
                            "poor": sum(1 for v in scores.values() if v < 70),
                        }
                        for p, scores in room.player_segment_scores.items()
                    }
                    player_pitch = {
                        p: round(sum(v.values()) / len(v), 1)
                        for p, v in room.player_pitch_scores.items() if v
                    }

                    # Salva antes do game_over: a TV recebe o id para o botão de anotar versos.
                    recording_id = room.finish_recording(complete=True)
                    await room.broadcast({
                        "type": "game_over",
                        "total_score": total_score_avg,
                        "player_scores": player_final_scores,
                        "player_pitch": player_pitch,
                        "player_stats": player_stats,
                        "song_id": room.song_id,
                        "song_title": room.song_title,
                        # recorde pessoal por cantor e melhores da sala nesta música
                        "records": records,
                        "leaderboard": song_leaderboard(room.song_id, room.song_title or room.song_id),
                        "recording_id": recording_id,
                    })

                    queue_manager.notify_game_ended()
                    break

    except (WebSocketDisconnect, RuntimeError):
        logger.info(f"Conexão do papel {role} desconectada.")
    except Exception as e:
        logger.error(f"Erro no WebSocket da sala {room_id}: {e}", exc_info=True)
    finally:
        if role == "mic":
            # Só remove o jogador se este socket ainda é o dele: um celular que
            # reconectou com o mesmo nome já registrou o socket novo.
            if player_name and room.players.get(player_name) is websocket:
                room.players.pop(player_name, None)
                # Continua em active_players: se o celular voltar e registrar o
                # mesmo apelido, o áudio volta a pontuar e a nota entra no fim.
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
        elif room.display is websocket:
            # Display substituído (troca de página na TV) fecha depois que o novo
            # já assumiu: não pode apagar o novo nem avisar "TV desconectada".
            room.display = None
            queue_manager.notify_game_ended()
            await _notify_mics_display_status(room, "unpaired")

        try:
            await websocket.close()
        except Exception as e:
            logger.debug(f"Falha ao fechar websocket: {e}")

        room_manager.clean_room(room_id)

