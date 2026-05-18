"""Singletons compartilhados entre rotas HTTP, WebSocket e bootstrap.

Manter num módulo dedicado evita import circular (rooms ↔ ws ↔ routes).
"""
from __future__ import annotations

from rooms import RoomManager
from song_manager import SongManager

room_manager = RoomManager()
song_manager = SongManager()
