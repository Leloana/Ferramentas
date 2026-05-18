"""Singletons compartilhados entre rotas HTTP, WebSocket e bootstrap.

Manter num módulo dedicado evita import circular (rooms ↔ ws ↔ routes).
"""
from __future__ import annotations

from rooms import RoomManager
from song_manager import SongManager
from utils.ffmpeg_bootstrap import bootstrap as _bootstrap_ffmpeg

room_manager = RoomManager()
song_manager = SongManager()

# Localizador idempotente: configurado uma vez aqui para que rotas e
# downloaders compartilhem o mesmo caminho sem re-bootstrapping.
ffmpeg_bin_dir: str | None = _bootstrap_ffmpeg()
