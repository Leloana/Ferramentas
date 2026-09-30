"""Gravações de partida: versos para o cantor anotar o gabarito (certo/errado/cantarolei)."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from recorder import SESSION_FILE, VERSE_LABELS, find_recording, load_labels, save_labels

router = APIRouter()


class GabaritoIn(BaseModel):
    player: str
    labels: dict[str, str]


def _session_dir(recording_id: str):
    session_dir = find_recording(recording_id)
    if session_dir is None:
        raise HTTPException(status_code=404, detail="Gravação não encontrada.")
    return session_dir


@router.get("/api/recordings/{recording_id}")
async def get_recording(recording_id: str):
    """Versos da partida com nota e transcrição de cada jogador, e o gabarito já anotado."""
    session_dir = _session_dir(recording_id)
    session = json.loads((session_dir / SESSION_FILE).read_text(encoding="utf-8"))
    results = {(r["player"], r["segment"]): r for r in session["results"]}
    players = list(session["players"].keys())
    verses = []
    for idx, seg in enumerate(session["segments"]):
        verses.append({
            "n": idx + 1,
            "lyrics": seg["lyrics"],
            "start": seg["sing_start"],
            "players": {
                p: {"score": results[(p, idx)]["score"], "heard": results[(p, idx)]["transcription"]}
                for p in players if (p, idx) in results
            },
        })
    return {
        "id": recording_id,
        "song_title": session.get("song_title") or session["song_id"],
        "players": players,
        "verses": verses,
        "labels": load_labels(session_dir),
        "allowed_labels": list(VERSE_LABELS),
    }


@router.post("/api/recordings/{recording_id}/gabarito")
async def post_gabarito(recording_id: str, body: GabaritoIn):
    session_dir = _session_dir(recording_id)
    session = json.loads((session_dir / SESSION_FILE).read_text(encoding="utf-8"))
    if body.player not in session["players"]:
        raise HTTPException(status_code=400, detail="Jogador não está nesta gravação.")
    n_verses = len(session["segments"])
    if any(not k.isdigit() or not 1 <= int(k) <= n_verses for k in body.labels):
        raise HTTPException(status_code=400, detail="Verso fora da música.")
    try:
        labels = save_labels(session_dir, body.player, body.labels)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "labels": labels}
