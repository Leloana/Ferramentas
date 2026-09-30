"""Perfis dos cantores (players/<apelido>/profile.json): histórico, recordes, ranking.

Saiu do ws/room.py para as rotas (routes/players.py) lerem os mesmos
arquivos sem importar o WebSocket. `KARAOKE_PLAYERS_DIR` troca a pasta (os
testes usam uma temporária — antes gravavam "PlayerOne" nos perfis reais).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PLAYERS_DIR = Path(os.environ.get("KARAOKE_PLAYERS_DIR")
                   or Path(__file__).resolve().parent.parent / "players")


def profile_key(name: str) -> str:
    """Nome da pasta do perfil (também evita path traversal)."""
    return "".join(c for c in (name or "") if c.isalnum() or c in ("-", "_")).strip()


def get_player_profile_path(name: str) -> Path:
    return PLAYERS_DIR / (profile_key(name) or "default_player") / "profile.json"


def load_profile(name: str) -> Optional[dict]:
    """Perfil existente ou None (não cria nada)."""
    path = get_player_profile_path(name)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Perfil ilegível em {path}: {e}")
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("songs_sung"), list):
        data["songs_sung"] = []
    return data


def get_or_create_profile(name: str) -> dict:
    path = get_player_profile_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        profile = load_profile(name)
        if profile is not None:
            return profile
        # guarda o arquivo ruim em vez de sobrescrever o histórico
        try:
            path.replace(path.with_suffix(".corrompido.json"))
        except OSError:
            pass
    profile = {"name": name, "songs_sung": []}
    save_profile(name, profile)
    return profile


def save_profile(name: str, profile: dict) -> None:
    path = get_player_profile_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    # escrita atômica: queda no meio não deixa profile.json pela metade
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _same_song(entry: dict, song_id: str, song_name: str) -> bool:
    if song_id and entry.get("song_id"):
        return entry["song_id"] == song_id
    return entry.get("name") == song_name


def record_game(name: str, song_id: str, song_name: str, score: float,
                pitch: Optional[float] = None, mode: str = "solo") -> dict:
    """Soma a partida ao perfil e diz se é recorde pessoal naquela música.

    Devolve {"best_before", "is_record", "times_sung", "total_songs"}.
    """
    profile = get_or_create_profile(name)
    songs = profile["songs_sung"]
    previous = [e for e in songs if _same_song(e, song_id, song_name)]
    best_before = max((float(e.get("score", 0) or 0) for e in previous), default=None)
    entry = {
        "name": song_name,
        "song_id": song_id,
        "score": score,
        "date": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": mode,
    }
    if pitch is not None:
        entry["pitch"] = pitch
    songs.append(entry)
    save_profile(name, profile)
    return {
        "best_before": best_before,
        "is_record": best_before is None or score > best_before,
        "times_sung": len(previous) + 1,
        "total_songs": len(songs),
    }


def summarize(profile: dict) -> dict:
    """Resumo para a lista de cantores e para o topo do perfil."""
    songs = profile.get("songs_sung") or []
    scores = [float(e.get("score", 0) or 0) for e in songs]
    pitches = [float(e["pitch"]) for e in songs if isinstance(e.get("pitch"), (int, float))]
    best = max(songs, key=lambda e: float(e.get("score", 0) or 0), default=None)
    return {
        "name": profile.get("name", ""),
        "games": len(songs),
        "avg": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "best": round(float(best.get("score", 0)), 1) if best else 0.0,
        "best_song": best.get("name") if best else None,
        "avg_pitch": round(sum(pitches) / len(pitches), 1) if pitches else None,
        "last_date": max((e.get("date", "") for e in songs), default=None),
    }


def profile_detail(profile: dict) -> dict:
    """Perfil completo: resumo, melhor nota por música e as últimas partidas."""
    songs = profile.get("songs_sung") or []
    per_song: dict = {}
    for e in songs:
        key = e.get("song_id") or e.get("name")
        cur = per_song.get(key)
        score = float(e.get("score", 0) or 0)
        if cur is None:
            per_song[key] = {"song_id": e.get("song_id"), "name": e.get("name"), "best": score, "times": 1,
                             "last_date": e.get("date")}
        else:
            cur["times"] += 1
            cur["best"] = max(cur["best"], score)
            cur["last_date"] = max(cur["last_date"] or "", e.get("date") or "")
    records = sorted(per_song.values(), key=lambda r: -r["best"])
    recent = sorted(songs, key=lambda e: e.get("date", ""), reverse=True)[:10]
    return {**summarize(profile), "records": records, "recent": recent}


def list_profiles() -> list[dict]:
    """Todos os cantores, do mais ativo para o menos."""
    if not PLAYERS_DIR.exists():
        return []
    out = []
    for folder in sorted(PLAYERS_DIR.iterdir()):
        if not (folder / "profile.json").exists():
            continue
        profile = load_profile(folder.name)
        if profile and profile.get("songs_sung"):
            out.append(summarize(profile))
    out.sort(key=lambda p: (-p["games"], -p["avg"]))
    return out


def song_leaderboard(song_id: str, song_name: str, limit: int = 5) -> list[dict]:
    """Melhor nota de cada cantor numa música (para "melhor da sala")."""
    board = []
    if not PLAYERS_DIR.exists():
        return board
    for folder in PLAYERS_DIR.iterdir():
        profile = load_profile(folder.name) if (folder / "profile.json").exists() else None
        if not profile:
            continue
        best = max((float(e.get("score", 0) or 0) for e in profile["songs_sung"]
                    if _same_song(e, song_id, song_name)), default=None)
        if best is not None:
            board.append({"name": profile.get("name", folder.name), "best": round(best, 1)})
    board.sort(key=lambda r: -r["best"])
    return board[:limit]
