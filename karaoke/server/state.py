"""Singletons compartilhados entre rotas HTTP, WebSocket e bootstrap.

Manter num módulo dedicado evita import circular (rooms ↔ ws ↔ routes).
"""
from __future__ import annotations

from pathlib import Path

from rooms import RoomManager
from song_manager import SongManager
from utils.ffmpeg_bootstrap import bootstrap as _bootstrap_ffmpeg

# Diretório raiz onde cada música vive em sua própria subpasta.
# Antes era redefinido em 4 lugares (song_manager + 3 routes).
SONGS_DIR: Path = Path(__file__).resolve().parent / "songs"

room_manager = RoomManager()
song_manager = SongManager(SONGS_DIR)

# Localizador idempotente: configurado uma vez aqui para que rotas e
# downloaders compartilhem o mesmo caminho sem re-bootstrapping.
ffmpeg_bin_dir: str | None = _bootstrap_ffmpeg()
