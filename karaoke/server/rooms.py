"""Modelos de sala de karaokê (display + mic pareados via room_id)."""
from __future__ import annotations

import logging
from collections import deque
from typing import Optional

from fastapi import WebSocket

from mic_stream import MicTimeline, SongClock
from utils.jsonsafe import jsonable
from recorder import GameRecording

logger = logging.getLogger(__name__)


class KaraokeRoom:
    def __init__(self, song_id: str):
        self.song_id = song_id
        self.display: Optional[WebSocket] = None
        self.mic: Optional[WebSocket] = None
        # Multiplayer properties
        self.players: dict[str, WebSocket] = {}
        # apelido → id do aparelho (celular): o mesmo aparelho retoma o apelido ao
        # reconectar (página recarregada, rede caiu) sem esbarrar em "já está em uso"
        self.player_devices: dict[str, str] = {}
        self.unregistered_mics: list[WebSocket] = []
        self.active_players: list[str] = []
        # Partida em andamento (start_game até game_over): celular que volta no meio
        # recebe game_started de novo, senão descarta o próprio áudio.
        self.in_game: bool = False
        self.game_mode: str = "solo"
        # Estilo de pontuação escolhido no lobby: "timing" (palavras + tempo
        # correto) ou "words" (somente palavras acertadas).
        self.scoring_mode: str = "timing"
        self.player_segment_scores: dict[str, dict[int, float]] = {}
        # Áudio de cada microfone indexado pelo tempo da música. Chave "Solo"
        # quando o jogo roda sem jogadores registrados.
        self.mic_timelines: dict[str, MicTimeline] = {}
        self.song_clock = SongClock()
        self.current_segment_idx = 0
        self.transcribed_segments: set[int] = set()
        self.segment_scores: dict[int, float] = {}
        self.total_score = 0.0
        # nº de segmentos efetivamente pontuados — correto para média mesmo
        # quando tasks de transcrição terminam fora de ordem.
        self.scored_count = 0
        self.last_client_time = 0.0
        self.segments: list = []
        self.is_active = True
        self.is_singing_active = False
        self.song_title = ""
        self.pending_tasks: set = set()
        # Sobe a cada partida/reset: resultado do Whisper de uma partida antiga
        # (que ficou esperando o lock) é descartado em vez de cair na nova.
        self.game_id = 0
        # Afinação (pitch.py): melodia de referência do vocal separado, tom
        # transposto pela TV e nota de afinação por jogador e verso.
        self.pitch_reference: Optional[dict] = None
        self.transpose = 0.0
        self.player_pitch_scores: dict = {}
        # Aparelho de cada celular (client_info): vai para a gravação da partida
        self.device_info: dict = {}
        # Tarefas de fundo (ex.: gerar pitch.json) — referência forte para o GC
        self.background_tasks: set = set()
        # Revezar versos: times em rodízio por verso (None = todos cantam tudo)
        self.turn_order: Optional[list] = None
        # Painel de saúde: segundos entre fechar o verso e a nota chegar (últimos 30)
        self.verse_latencies: deque = deque(maxlen=30)
        # Fila da noite: pedidos "quero cantar" (song_requests.py)
        self.song_requests: list = []
        # Partida em gravação (KARAOKE_RECORD_DIR) ou None.
        self.recording: Optional[GameRecording] = None

    def finish_recording(self, complete: bool, final: Optional[dict] = None) -> Optional[str]:
        """Salva a partida em gravação, se houver. Devolve o id (nome da pasta) ou None.

        Falha ao salvar não derruba o jogo.
        """
        recording, self.recording = self.recording, None
        if recording is None:
            return None
        import stt_engine
        model = stt_engine.engine.model_size if stt_engine.engine else None
        try:
            saved = recording.save(self.mic_timelines, complete=complete, whisper_model=model, final=final)
        except Exception as e:
            logger.error(f"Falha ao salvar a gravação da partida: {e}", exc_info=True)
            return None
        return saved.name if saved else None

    def reset_audio(self) -> None:
        """Descarta o áudio capturado e o relógio (nova música ou novo jogo).

        Partida em gravação que não chegou ao fim é salva antes, como incompleta.
        """
        self.finish_recording(complete=False)
        self.mic_timelines.clear()
        self.song_clock = SongClock()

    async def broadcast(self, msg: dict) -> None:
        """Envia uma mensagem para display, players e fila (quando conectados), tolerando falhas."""
        targets = [self.display]
        for ws in self.players.values():
            targets.append(ws)
        for ws in self.unregistered_mics:
            targets.append(ws)
        if self.mic and self.mic not in targets:
            targets.append(self.mic)

        msg = jsonable(msg)
        for ws in targets:
            if ws is None:
                continue
            try:
                await ws.send_json(msg)
            except Exception as e:
                # aviso (não debug): um game_over perdido deixa a TV e o celular presos
                logger.warning(f"Falha ao enviar '{msg.get('type')}' para um websocket: {type(e).__name__}: {e}")


class RoomManager:
    def __init__(self):
        self.rooms: dict[str, KaraokeRoom] = {}

    def get_or_create_room(self, room_id: str, song_id: str, segments: list) -> KaraokeRoom:
        if room_id not in self.rooms:
            room = KaraokeRoom(song_id)
            room.segments = segments
            self.rooms[room_id] = room
            logger.info(f"Sala de Karaokê criada: {room_id} para a música {song_id}")
        return self.rooms[room_id]

    def clean_room(self, room_id: str) -> None:
        if room_id in self.rooms:
            room = self.rooms[room_id]
            if not room.display and not room.mic and not room.players and not room.unregistered_mics:
                del self.rooms[room_id]
                logger.info(f"Sala de Karaokê removida por inatividade: {room_id}")
