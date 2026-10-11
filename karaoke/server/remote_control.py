"""Controle da sala pelo celular: o celular escolhe a música, monta a sala e dá o play.

A TV continua dona da partida (é ela que toca o áudio): o celular manda
`{"type": "remote", "action": ...}`, o servidor confere as travas e repassa para
a TV, que executa com as mesmas funções dos botões dela. A TV publica o estado
do lobby (`lobby_state`) e o servidor espelha para os celulares (`remote_state`),
somando o que só ele sabe: partida em andamento e GPU ocupada.

Travas (mutex):
- música tocando: trocar a música, mexer nos cantores/times, revezar versos,
  forma de pontuação e iniciar outra ficam bloqueados até ela acabar;
- GPU gerando letra: não inicia (a nota de cada verso esperaria o Whisper);
- tom, velocidade, volume da música e da voz guia, pausar e encerrar valem sempre.
"""
from __future__ import annotations

MAX_SEATS = 6
TEAMS = ("A", "B", "C", "D")
PC_MIC = "PC_Local"

ACTIONS = ("select_song", "seats", "turns", "scoring_mode", "transpose", "speed", "volume", "guide_volume",
           "pause", "stop", "start")
# só fora da partida: mudam quem canta, a música ou como pontua
LOCKED_WHILE_PLAYING = ("select_song", "seats", "turns", "scoring_mode", "start")
# ajustes de som (controle de arrastar no celular): faixa de valores aceitos
SOUND_RANGES = {"transpose": (-6, 6), "speed": (0.75, 1.5), "volume": (0.0, 1.0), "guide_volume": (0.0, 1.0)}
# precisam de uma partida em andamento
ONLY_WHILE_PLAYING = ("pause", "stop")


def check_remote(action: str, in_game: bool, gpu_busy: str | None, has_display: bool) -> str | None:
    """Motivo para recusar o comando (texto para o celular) ou None."""
    if action not in ACTIONS:
        return "Comando desconhecido."
    if not has_display:
        return "TV desconectada: abra o karaokê na TV."
    if in_game and action in LOCKED_WHILE_PLAYING:
        return "Espere a música acabar."
    if not in_game and action in ONLY_WHILE_PLAYING:
        return "Nenhuma música tocando."
    if action == "start" and gpu_busy:
        return f"GPU ocupada: gerando a letra de {gpu_busy}."
    return None


def clean_seats(seats, players: list[str]) -> list[dict] | None:
    """Vagas válidas [{mic, team}] (microfones da sala, sem repetir) ou None se inválido."""
    if not isinstance(seats, list) or len(seats) > MAX_SEATS:
        return None
    valid_mics = set(players) | {PC_MIC}
    out, seen = [], set()
    for seat in seats:
        if not isinstance(seat, dict):
            return None
        mic, team = str(seat.get("mic") or ""), str(seat.get("team") or "")
        if mic not in valid_mics or mic in seen or team not in TEAMS:
            return None
        seen.add(mic)
        out.append({"mic": mic, "team": team})
    return out


def clean_command(action: str, data: dict, players: list[str], ready_song_ids) -> tuple[dict | None, str | None]:
    """(comando para a TV, erro). Só repassa campos conhecidos e já validados."""
    if action == "select_song":
        song_id = str(data.get("song_id") or "")
        if song_id not in ready_song_ids:
            return None, "Música não encontrada."
        return {"action": action, "song_id": song_id}, None
    if action == "seats":
        seats = clean_seats(data.get("seats"), players)
        if seats is None:
            return None, "Cantores inválidos."
        return {"action": action, "seats": seats}, None
    if action == "turns":
        return {"action": action, "value": bool(data.get("value"))}, None
    if action == "scoring_mode":
        mode = data.get("value")
        if mode not in ("timing", "words"):
            return None, "Forma de pontuação inválida."
        return {"action": action, "value": mode}, None
    if action in SOUND_RANGES:
        low, high = SOUND_RANGES[action]
        value = data.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
            return None, "Ajuste inválido."
        value = int(round(value)) if action == "transpose" else round(float(value), 2)
        return {"action": action, "value": value}, None
    return {"action": action}, None


def remote_state_payload(lobby_state: dict | None, in_game: bool, gpu_busy: str | None,
                         has_display: bool) -> dict:
    """Estado da sala para os celulares (o que a TV publicou + travas do servidor)."""
    payload = {"type": "remote_state"}
    payload.update(lobby_state or {})
    payload.update({"in_game": in_game, "gpu_busy": gpu_busy, "has_display": has_display})
    return payload
