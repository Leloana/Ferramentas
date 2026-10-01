"""Modo gravação: salva cada partida para repetir offline com outros parâmetros.

Ligado por padrão em `karaoke/recordings/` (fora do git). KARAOKE_RECORD_DIR
troca a pasta; KARAOKE_RECORD=0 desliga. Cada partida vira uma subpasta com:

- `<jogador>.wav` — microfone inteiro a 16 kHz, já no tempo da música
  (amostra 0 = segundo 0 da música; trecho sem pacote = silêncio);
- `session.json` — versos, janelas, o que o Whisper ouviu e a nota de cada verso;
  no formato 3 também: configuração da partida (tom, velocidade, sincronia,
  volumes, times, revezamento), linha do tempo da TV (play/pausa/seek/...),
  aparelho e rede de cada celular, ruído de fundo nas pausas, afinação e
  dados crus do Whisper por verso, tempo até a nota, versões (commit e
  constantes) e o resultado final;
- `song_meta.json` / `song_pitch.json` — cópia do meta.json e do pitch.json da
  música naquele momento (a letra e a melodia de referência podem mudar depois).

`tools/replay_recording.py` pontua a gravação de novo sem precisar cantar.
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import re
import shutil
import subprocess
import wave
from time import monotonic as _monotonic
from datetime import datetime
from pathlib import Path

import numpy as np

from mic_stream import STREAM_SR, MicTimeline
from utils.jsonsafe import jsonable
from utils.segment_timing import match_word_pairs

logger = logging.getLogger(__name__)

SESSION_FILE = "session.json"
# 2: resultados com as duas passadas do Whisper (prompted_words/unprompted_words/used).
# 3: gravação completa (config, events, devices, network, noise_floor, versions,
#    final; por verso: pitch, whisper_raw, timing).
# Leitores usam .get: sessões dos formatos 1 e 2 continuam valendo.
FORMAT_VERSION = 3
NOISE_FRAME_SEC = 0.5

# Gabarito anotado pelo cantor no fim da partida (botão discreto da tela final).
GABARITO_FILE = "gabarito.json"
TIMING_FILE = "tempo_palavras.json"  # palavras que o cantor marcou com tempo errado
VERSE_LABELS = ("certo", "errado", "cantarolei")
_RECORDING_ID_RE = re.compile(r"^[\w.-]+$")


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


def find_recording(recording_id: str, base_dir: Path | None = None) -> Path | None:
    """Pasta da partida `recording_id` (nome da pasta), ou None se não existe/for inválido."""
    base = base_dir or recording_base_dir()
    if not base or not recording_id or not _RECORDING_ID_RE.match(recording_id) or recording_id in (".", ".."):
        return None
    path = base / recording_id
    return path if (path / SESSION_FILE).is_file() else None


def list_player_recordings(player: str, base_dir: Path | None = None) -> list[dict]:
    """Partidas gravadas em que `player` cantou, da mais nova para a mais antiga.

    Perfil do cantor: cada item abre a análise verso a verso (/api/recordings/<id>).
    Gravação ilegível é pulada.
    """
    base = base_dir or recording_base_dir()
    if not base or not base.is_dir() or not player:
        return []
    found = []
    for session_path in base.glob(f"*/{SESSION_FILE}"):
        try:
            session = json.loads(session_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if player not in (session.get("players") or {}):
            continue
        final = session.get("final") or {}
        score = (final.get("player_scores") or {}).get(player)
        found.append({
            "id": session_path.parent.name,
            "song_id": session.get("song_id"),
            "song_title": session.get("song_title") or session.get("song_id"),
            "date": session.get("started_at"),
            "score": score,
            "complete": bool(session.get("complete")),
        })
    found.sort(key=lambda r: r["date"] or "", reverse=True)
    return found


def load_labels(session_dir: Path) -> dict[str, dict[str, str]]:
    """{jogador: {"3": "certo", ...}} (versos numerados a partir de 1)."""
    path = session_dir / GABARITO_FILE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("labels", {})


def save_labels(session_dir: Path, player: str, labels: dict[str, str]) -> dict[str, dict[str, str]]:
    """Substitui as anotações de `player`. Rótulo fora de VERSE_LABELS levanta ValueError."""
    bad = {v for v in labels.values() if v not in VERSE_LABELS}
    if bad:
        raise ValueError(f"Rótulos inválidos: {sorted(bad)}")
    if any(not str(k).isdigit() for k in labels):
        raise ValueError("Versos devem ser números")
    all_labels = load_labels(session_dir)
    all_labels[player] = {str(int(k)): v for k, v in sorted(labels.items(), key=lambda kv: int(kv[0]))}
    payload = {"labels": all_labels, "updated_at": datetime.now().isoformat(timespec="seconds")}
    (session_dir / GABARITO_FILE).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return all_labels


def load_timing_marks(session_dir: Path) -> dict[str, dict[str, list[int]]]:
    """{jogador: {"3": [0, 2], ...}}: índices das palavras (a partir de 0) com tempo errado."""
    path = session_dir / TIMING_FILE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("marks", {})


def save_timing_marks(session_dir: Path, player: str, marks: dict[str, list[int]]) -> dict[str, dict[str, list[int]]]:
    """Substitui as palavras marcadas de `player`. Verso sem palavra marcada some."""
    if any(not str(k).isdigit() for k in marks):
        raise ValueError("Versos devem ser números")
    clean = {}
    for k, words in sorted(marks.items(), key=lambda kv: int(kv[0])):
        idx = sorted({int(w) for w in words if int(w) >= 0})
        if idx:
            clean[str(int(k))] = idx
    all_marks = load_timing_marks(session_dir)
    all_marks[player] = clean
    payload = {"marks": all_marks, "updated_at": datetime.now().isoformat(timespec="seconds")}
    (session_dir / TIMING_FILE).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return all_marks


def sung_word_times(segment: dict, result: dict) -> list[dict]:
    """Cada palavra da letra do verso com o tempo esperado e o que o cantor cantou
    (segundos da música; `sung` None quando o Whisper não ouviu a palavra)."""
    timed = segment.get("lyrics_timed") or []
    whisper = result.get("words") or []
    pairs = match_word_pairs([w["word"] for w in timed], whisper) if whisper else {}
    zero = float(result["window"][0]) if result.get("window") else float(segment["sing_start"])
    out = []
    for i, w in enumerate(timed):
        sung = None
        if i in pairs:
            sung = round(zero + float(whisper[pairs[i]]["start"]), 2)
        out.append({
            "word": w["word"],
            "expected": round(float(segment["sing_start"]) + float(w["expected_start"]), 2),
            "sung": sung,
        })
    return out


class GameRecording:
    """Uma partida em gravação. `save` grava o áudio e as notas no disco."""

    def __init__(self, base_dir: Path, song_id: str, song_title: str, segments: list[dict],
                 scoring_mode: str, windows: dict, song_dir: Path | None = None) -> None:
        self.started_at = datetime.now()
        self._t0 = _monotonic()
        self.song_dir = Path(song_dir) if song_dir else None
        self.config: dict = {}
        self.events: list[dict] = []
        self.devices: dict[str, dict] = {}
        self.dir = base_dir / f"{self.started_at:%Y%m%d-%H%M%S}_{_safe_name(song_id)}"
        self.song_id = song_id
        self.song_title = song_title
        self.segments = segments
        self.scoring_mode = scoring_mode
        self.windows = windows
        self.results: list[dict] = []

    def add_segment_result(self, player: str, seg_idx: int, window: tuple[float, float], rms: float,
                           transcription: str, words: list[dict], result: dict,
                           prompted_words: list[dict] | None = None,
                           unprompted_words: list[dict] | None = None,
                           used: str | None = None, **extra) -> None:
        """`words` é a passada que valeu; com `used`, grava também as duas passadas
        (já no tempo do sing_start) para repontuar com outro portão de confiança.
        `extra`: pitch, whisper_raw (tempos relativos à janela), timing."""
        entry = {
            "player": player,
            "segment": seg_idx,
            "window": [round(window[0], 4), round(window[1], 4)],
            "rms": round(rms, 6),
            "transcription": transcription,
            "words": words,
            "score": result["score"],
            "matched_words": result.get("matched_words"),
            "total_expected": result.get("total_expected"),
        }
        if used is not None:
            entry.update(prompted_words=prompted_words, unprompted_words=unprompted_words, used=used)
        entry.update({k: v for k, v in extra.items() if v is not None})
        self.results.append(entry)

    # --- contexto da partida -------------------------------------------------

    def set_config(self, config: dict) -> None:
        self.config.update({k: v for k, v in config.items() if v is not None})

    def add_event(self, kind: str, song_time: float | None = None, **data) -> None:
        """Linha do tempo: play/pausa/seek/velocidade/tom/entrada e saída de celular."""
        event = {"t": round(_monotonic() - self._t0, 3), "kind": kind}
        if song_time is not None:
            event["song_time"] = round(float(song_time), 3)
        event.update({k: v for k, v in data.items() if v is not None})
        self.events.append(event)

    def set_device(self, player: str, info: dict) -> None:
        self.devices[player] = {**self.devices.get(player, {}), **info}

    def save(self, timelines: dict[str, MicTimeline], complete: bool, whisper_model: str | None,
             final: dict | None = None) -> Path | None:
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
            players[player] = {
                "audio": filename,
                "covered": covered_intervals(covered),
                "network": network_stats(timeline),
                "noise_floor": noise_floor(audio, covered, self.segments, self.windows),
            }
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
            "config": self.config,
            "events": self.events,
            "devices": self.devices,
            "versions": versions(),
            "final": final,
        }
        self._copy_song_files()
        text = json.dumps(jsonable(session), ensure_ascii=False, indent=2)
        (self.dir / SESSION_FILE).write_text(text, encoding="utf-8", errors="replace")
        logger.info(f"Gravação da partida salva em {self.dir}")
        return self.dir

    def _copy_song_files(self) -> None:
        if not self.song_dir:
            return
        for src, dst in (("meta.json", "song_meta.json"), ("pitch.json", "song_pitch.json"), ("lyrics.lrc", "song_lyrics.lrc")):
            try:
                if (self.song_dir / src).is_file():
                    shutil.copyfile(self.song_dir / src, self.dir / dst)
            except OSError as e:
                logger.debug(f"Não copiou {src} para a gravação: {e}")
        if (self.song_dir / ".lyrics_edited").exists():
            (self.dir / "song_lyrics_edited").write_text("", encoding="utf-8")


def _percentile(values, q: float):
    if not len(values):
        return None
    return round(float(np.percentile(np.asarray(values, dtype=float), q)), 4)


def network_stats(timeline: MicTimeline) -> dict:
    """Pacotes, trechos (contador parado/época nova) e atraso de chegada."""
    stats = getattr(timeline, "stats", {}) or {}
    late = stats.get("late_samples") or []
    return {
        "packets": stats.get("packets", 0),
        "in_flight": stats.get("in_flight", 0),  # chegaram depois de a música parar
        "spans": len(timeline.anchors),
        "late_median": _percentile(late, 50),
        "late_p90": _percentile(late, 90),
        "late_max": round(float(stats.get("late_max", 0.0)), 3),
    }


def noise_floor(audio: np.ndarray, covered: np.ndarray, segments: list[dict], windows: dict,
                sample_rate: int = STREAM_SR) -> dict | None:
    """RMS do microfone fora dos versos (pausas instrumentais): o ruído de fundo
    daquele celular — base para trocar o gate fixo de silêncio por um por aparelho."""
    pre = float((windows or {}).get("pre_sing_sec", 1.5))
    post = float((windows or {}).get("post_sing_sec", 0.5))
    mask = covered.copy()
    for seg in segments or []:
        if not str(seg.get("lyrics") or "").strip():
            continue
        a = max(0, int((seg["sing_start"] - pre) * sample_rate))
        b = min(len(mask), int((seg["sing_end"] + post) * sample_rate))
        mask[a:b] = False
    frame = int(NOISE_FRAME_SEC * sample_rate)
    rms = []
    for i in range(0, len(audio) - frame + 1, frame):
        if mask[i:i + frame].all():
            chunk = audio[i:i + frame]
            rms.append(float(np.sqrt(np.mean(chunk ** 2))))
    if not rms:
        return None
    return {"frames": len(rms), "rms_median": _percentile(rms, 50), "rms_p90": _percentile(rms, 90),
            "rms_min": round(min(rms), 6)}


_VERSIONS_CACHE: dict = {}


def _git(*args) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=Path(__file__).resolve().parent, capture_output=True,
                             text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def _constants(module_name: str) -> dict:
    try:
        mod = importlib.import_module(module_name)
    except Exception:
        return {}
    out = {}
    for name, value in vars(mod).items():
        if name.isupper() and isinstance(value, (int, float, str, bool, tuple)) and not name.startswith("_"):
            out[name] = list(value) if isinstance(value, tuple) else value
    return out


def versions() -> dict:
    """Commit do código e constantes que decidem a nota (para saber, meses depois,
    com que regras aquela partida foi pontuada)."""
    if not _VERSIONS_CACHE:
        _VERSIONS_CACHE.update({
            "commit": _git("rev-parse", "--short", "HEAD"),
            "dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
            "constants": {m: _constants(m) for m in
                          ("score_engine", "segment_scoring", "stt_engine", "mic_stream", "pitch", "ws.room")},
        })
    return dict(_VERSIONS_CACHE)
