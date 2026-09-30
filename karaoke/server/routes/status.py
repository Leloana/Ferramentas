"""Painel de saúde (/api/status): fila da GPU, tempo por verso, celulares e disco."""
from __future__ import annotations

import os
import shutil

from fastapi import APIRouter, Response

from state import SONGS_DIR, queue_manager, room_manager
from utils.http import set_no_cache

router = APIRouter()


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


@router.get("/api/status")
async def api_status(response: Response):
    set_no_cache(response)
    rooms = []
    for room_id, room in list(room_manager.rooms.items()):
        lat = list(room.verse_latencies)
        rooms.append({
            "id": room_id,
            "song": room.song_title or room.song_id or None,
            "display": room.display is not None,
            "players": sorted(room.players.keys()),
            "waiting_mics": len(room.unregistered_mics),
            "singing": room.is_singing_active,
            "pending_verses": len(room.pending_tasks),
            "verse_latency_median": _percentile(lat, 0.5),
            "verse_latency_p90": _percentile(lat, 0.9),
            "verses_measured": len(lat),
        })
    queue = queue_manager.get_queue_status()
    disk = shutil.disk_usage(SONGS_DIR if SONGS_DIR.exists() else SONGS_DIR.parent)
    songs = [p for p in SONGS_DIR.iterdir() if p.is_dir()] if SONGS_DIR.exists() else []
    return {
        "gpu": {
            "locked": queue_manager.whisper_lock.locked(),
            "game_active": bool(getattr(queue_manager, "_gpu_game_active", False)),
            "whisper_model": os.environ.get("KARAOKE_WHISPER_MODEL", "large-v3-turbo"),
        },
        "queue": {
            "total": len(queue),
            "by_status": {s: sum(1 for q in queue if q.get("status") == s) for s in {q.get("status") for q in queue}},
        },
        "rooms": rooms,
        "disk": {"free_gb": round(disk.free / 1e9, 1), "total_gb": round(disk.total / 1e9, 1)},
        "songs": len(songs),
    }
