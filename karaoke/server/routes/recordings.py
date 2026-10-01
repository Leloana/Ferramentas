"""Gravações de partida: versos para o cantor anotar o gabarito (certo/errado/cantarolei)
e as palavras com tempo errado."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from recorder import (
    SESSION_FILE, VERSE_LABELS, find_recording, list_player_recordings, load_labels, load_timing_marks,
    save_labels, save_timing_marks, sung_word_times,
)

router = APIRouter()


class GabaritoIn(BaseModel):
    player: str
    labels: dict[str, str]


class TimingMarksIn(BaseModel):
    player: str
    marks: dict[str, list[int]]


def _session_dir(recording_id: str):
    session_dir = find_recording(recording_id)
    if session_dir is None:
        raise HTTPException(status_code=404, detail="Gravação não encontrada.")
    return session_dir


@router.get("/api/players/{name}/recordings")
async def player_recordings(name: str):
    """Partidas gravadas do cantor (perfil → análise verso a verso)."""
    return {"recordings": await asyncio.to_thread(list_player_recordings, name)}


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
            "end": seg.get("sing_end", seg["sing_start"]),
            "players": {
                p: {
                    "score": results[(p, idx)]["score"],
                    "heard": results[(p, idx)]["transcription"],
                    "words": sung_word_times(seg, results[(p, idx)]),
                }
                for p in players if (p, idx) in results
            },
        })
    return {
        "id": recording_id,
        "song_title": session.get("song_title") or session["song_id"],
        "song_id": session.get("song_id"),
        "players": players,
        "verses": verses,
        "labels": load_labels(session_dir),
        "timing_marks": load_timing_marks(session_dir),
        "allowed_labels": list(VERSE_LABELS),
    }


@router.get("/api/recordings/{recording_id}/audio/{player}")
async def get_recording_audio(recording_id: str, player: str):
    """Voz gravada do cantor (WAV 16 kHz no tempo da música): "ouvir a apresentação"."""
    session_dir = _session_dir(recording_id)
    session = json.loads((session_dir / SESSION_FILE).read_text(encoding="utf-8"))
    info = session["players"].get(player)
    if not info:
        raise HTTPException(status_code=404, detail="Jogador não está nesta gravação.")
    path = (session_dir / info["audio"]).resolve()
    if path.parent != session_dir.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Áudio não encontrado.")
    return FileResponse(path, media_type="audio/wav")


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


@router.post("/api/recordings/{recording_id}/tempo-palavras")
async def post_timing_marks(recording_id: str, body: TimingMarksIn):
    """Palavras que o cantor marcou com tempo errado (índices por verso)."""
    session_dir = _session_dir(recording_id)
    session = json.loads((session_dir / SESSION_FILE).read_text(encoding="utf-8"))
    if body.player not in session["players"]:
        raise HTTPException(status_code=400, detail="Jogador não está nesta gravação.")
    segments = session["segments"]
    for k, words in body.marks.items():
        if not k.isdigit() or not 1 <= int(k) <= len(segments):
            raise HTTPException(status_code=400, detail="Verso fora da música.")
        n_words = len(segments[int(k) - 1].get("lyrics_timed") or [])
        if any(not 0 <= w < n_words for w in words):
            raise HTTPException(status_code=400, detail="Palavra fora do verso.")
    try:
        marks = save_timing_marks(session_dir, body.player, body.marks)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "marks": marks}
