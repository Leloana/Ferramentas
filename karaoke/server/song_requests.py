"""Fila da noite: pedidos de "quero cantar" por sala.

O celular (ou a TV) pede uma música pronta; a TV mostra "Próximas" e, no fim
de cada partida, abre a próxima no lobby com quem pediu já escalado. Fica só
na memória da sala: a festa acaba, a fila acaba.
"""
from __future__ import annotations

import time
import uuid

MAX_REQUESTS = 30
MAX_PER_SINGER = 3


def add_request(room, song: dict, singer: str) -> tuple[dict | None, str | None]:
    """Soma um pedido. Devolve (pedido, erro). `song`: {"id", "title", "artist"}."""
    if len(room.song_requests) >= MAX_REQUESTS:
        return None, "A fila está cheia."
    mine = [r for r in room.song_requests if r["singer"] == singer]
    if len(mine) >= MAX_PER_SINGER:
        return None, f"Você já tem {MAX_PER_SINGER} pedidos na fila."
    if any(r["song_id"] == song["id"] and r["singer"] == singer for r in room.song_requests):
        return None, "Essa música já está na sua fila."
    req = {
        "id": uuid.uuid4().hex[:8],
        "song_id": song["id"],
        "title": song.get("title") or song["id"],
        "artist": song.get("artist") or "",
        "singer": singer,
        "at": time.time(),
    }
    room.song_requests.append(req)
    return req, None


def remove_request(room, req_id: str, singer: str | None = None) -> bool:
    """Tira um pedido (o celular só tira os próprios; a TV, qualquer um)."""
    for i, r in enumerate(room.song_requests):
        if r["id"] == req_id and (singer is None or r["singer"] == singer):
            room.song_requests.pop(i)
            return True
    return False


def requests_payload(room) -> dict:
    return {"type": "requests_update", "requests": list(room.song_requests)}
