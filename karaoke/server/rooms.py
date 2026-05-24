"""Modelos de sala de karaokê (display + mic pareados via room_id)."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class KaraokeRoom:
    def __init__(self, song_id: str):
        self.song_id = song_id
        self.display: Optional[WebSocket] = None
        self.mic: Optional[WebSocket] = None
        # Multiplayer properties
        self.players: dict[str, WebSocket] = {}
        self.unregistered_mics: list[WebSocket] = []
        self.active_players: list[str] = []
        self.game_mode: str = "solo"
        self.player_segment_scores: dict[str, dict[int, float]] = {}
        self.player_segment_buffers: dict[str, dict[int, bytearray]] = {}
        # Buffers de áudio dedicados por índice de segmento. O `audio_buffer`
        # global antigo foi removido — não era mais lido por nenhum caminho.
        self.segment_buffers: dict[int, bytearray] = {}
        self.client_sample_rate = 48000
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

    async def broadcast(self, msg: dict) -> None:
        """Envia uma mensagem para display, players e fila (quando conectados), tolerando falhas."""
        targets = [self.display]
        for ws in self.players.values():
            targets.append(ws)
        for ws in self.unregistered_mics:
            targets.append(ws)
        if self.mic and self.mic not in targets:
            targets.append(self.mic)

        for ws in targets:
            if ws is None:
                continue
            try:
                await ws.send_json(msg)
            except Exception as e:
                logger.debug(f"Falha ao enviar para websocket: {e}")


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
