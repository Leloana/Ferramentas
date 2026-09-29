"""Modo gravação: salva cada partida para repetir offline com outros parâmetros.

Ligado por padrão em `karaoke/recordings/` (fora do git). KARAOKE_RECORD_DIR
troca a pasta; KARAOKE_RECORD=0 desliga. Cada partida vira uma subpasta com:

- `<jogador>.wav` — microfone inteiro a 16 kHz, já no tempo da música
  (amostra 0 = segundo 0 da música; trecho sem pacote = silêncio);
- `session.json` — versos, janelas, o que o Whisper ouviu e a nota de cada verso.

`tools/replay_recording.py` pontua a gravação de novo sem precisar cantar.
"""
from __future__ import annotations

import json
import logging
import os
import re
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from mic_stream import STREAM_SR, MicTimeline

logger = logging.getLogger(__name__)

SESSION_FILE = "session.json"
FORMAT_VERSION = 1


DEFAULT_RECORD_DIR = Path(__file__).resolve().parent.parent / "recordings"


def recording_base_dir() -> Path | None:
    """Pasta das gravações, ou None com KARAOKE_RECORD=0."""
    if os.environ.get("KARAOKE_RECORD", "1").strip().lower() in ("0", "false", "no", "off"):
        return None
    value = os.environ.get("KARAOKE_RECORD_DIR", "").strip()
    return Path(value) if value else DEFAULT_RECORD_DIR


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w-]", "_", name).strip("_") or "jogador"


def covered_intervals(covered: np.ndarray, sample_rate: int = STREAM_SR) -> list[list[float]]:
    """Máscara de amostras recebidas → [[início, fim], ...] em segundos."""
    if not covered.any():
        return []
    edges = np.diff(np.concatenate(([0], covered.astype(np.int8), [0])))
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)
    # 6 casas: volta para a mesma amostra no covered_mask (1 amostra = 62,5 µs).
    return [[round(s / sample_rate, 6), round(e / sample_rate, 6)] for s, e in zip(starts, ends)]


def covered_mask(intervals: list[list[float]], n_samples: int, sample_rate: int = STREAM_SR) -> np.ndarray:
    mask = np.zeros(n_samples, dtype=bool)
    for start, end in intervals:
        mask[int(round(start * sample_rate)):int(round(end * sample_rate))] = True
    return mask


def write_wav(path: Path, audio: np.ndarray, sample_rate: int = STREAM_SR) -> None:
    # Inverso exato do read_wav (amostras do celular são Int16 / 32768).
    pcm = np.clip(np.round(audio * 32768.0), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(pcm.tobytes())


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as f:
        if f.getnchannels() != 1 or f.getsampwidth() != 2 or f.getframerate() != STREAM_SR:
            raise ValueError(f"{path.name}: esperado mono Int16 a {STREAM_SR} Hz")
        return np.frombuffer(f.readframes(f.getnframes()), dtype="<i2").astype(np.float32) / 32768.0


class GameRecording:
    """Uma partida em gravação. `save` grava o áudio e as notas no disco."""

    def __init__(self, base_dir: Path, song_id: str, song_title: str, segments: list[dict],
                 scoring_mode: str, windows: dict) -> None:
        self.started_at = datetime.now()
        self.dir = base_dir / f"{self.started_at:%Y%m%d-%H%M%S}_{_safe_name(song_id)}"
        self.song_id = song_id
        self.song_title = song_title
        self.segments = segments
        self.scoring_mode = scoring_mode
        self.windows = windows
        self.results: list[dict] = []

    def add_segment_result(self, player: str, seg_idx: int, window: tuple[float, float], rms: float,
                           transcription: str, words: list[dict], result: dict) -> None:
        self.results.append({
            "player": player,
            "segment": seg_idx,
            "window": [round(window[0], 4), round(window[1], 4)],
            "rms": round(rms, 6),
            "transcription": transcription,
            "words": words,
            "score": result["score"],
            "matched_words": result.get("matched_words"),
            "total_expected": result.get("total_expected"),
        })

    def save(self, timelines: dict[str, MicTimeline], complete: bool, whisper_model: str | None) -> Path | None:
        """Grava a partida. Sem áudio de nenhum jogador não cria nada."""
        players = {}
        audio_by_player = {}
        for player, timeline in timelines.items():
            end = timeline.end_time()
            if end is None or end <= 0:
                continue
            audio, covered = timeline.extract(0.0, end)
            if not covered.any():
                continue
            filename = f"{_safe_name(player)}.wav"
            audio_by_player[filename] = audio
            players[player] = {"audio": filename, "covered": covered_intervals(covered)}
        if not players:
            return None

        self.dir.mkdir(parents=True, exist_ok=True)
        for filename, audio in audio_by_player.items():
            write_wav(self.dir / filename, audio)
        session = {
            "format": FORMAT_VERSION,
            "song_id": self.song_id,
            "song_title": self.song_title,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "complete": complete,
            "scoring_mode": self.scoring_mode,
            "whisper_model": whisper_model,
            "sample_rate": STREAM_SR,
            "windows": self.windows,
            "segments": self.segments,
            "players": players,
            "results": sorted(self.results, key=lambda r: (r["player"], r["segment"])),
        }
        (self.dir / SESSION_FILE).write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Gravação da partida salva em {self.dir}")
        return self.dir
