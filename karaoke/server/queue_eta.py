"""Tempo estimado de processamento de uma música da fila.

Cada etapa (baixar, separar, gerar a letra) grava quanto levou, e a média
móvel por minuto de áudio vira a estimativa da próxima música. Começa dos
valores medidos no servidor (RTX 4070, 2026-10-01) e se ajusta sozinha.
"""
from __future__ import annotations

import json
import logging
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

STATS_FILE = Path(__file__).resolve().parent / "queue_stats.json"
# duração suposta enquanto o áudio não foi baixado e o YouTube não disse
DEFAULT_AUDIO_SEC = 240.0
# peso da última medida na média
EMA_ALPHA = 0.3

# segundos fixos (download) ou segundos por minuto de áudio (o resto)
DEFAULTS = {
    "download": 20.0,
    "separate_roformer": 18.0,
    "separate_demucs": 5.0,
    "align_fast": 12.0,
    "align_pro": 25.0,
}
PER_MINUTE = {"separate_roformer", "separate_demucs", "align_fast", "align_pro"}

_lock = threading.Lock()


def _load() -> dict:
    try:
        data = json.loads(STATS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def estimate(stage: str, audio_sec: float | None) -> float:
    """Segundos que a etapa deve levar para um áudio de `audio_sec`."""
    rate = _load().get(stage, DEFAULTS[stage])
    if stage in PER_MINUTE:
        return rate * (audio_sec or DEFAULT_AUDIO_SEC) / 60.0
    return rate


def record(stage: str, seconds: float, audio_sec: float | None) -> None:
    """Junta a medida de uma etapa à média (só com a duração do áudio conhecida)."""
    if seconds <= 0 or (stage in PER_MINUTE and not audio_sec):
        return
    value = seconds * 60.0 / audio_sec if stage in PER_MINUTE else seconds
    with _lock:
        data = _load()
        old = data.get(stage, DEFAULTS[stage])
        data[stage] = round(old + EMA_ALPHA * (value - old), 2)
        try:
            STATS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as e:
            logger.warning(f"[ETA] não gravou {STATS_FILE.name}: {e}")


def probe_duration(path: Path, ffmpeg_bin_dir: str | None) -> float | None:
    """Duração do áudio pelo ffprobe (None se não der)."""
    exe = "ffprobe"
    if ffmpeg_bin_dir:
        local = Path(ffmpeg_bin_dir) / "ffprobe.exe"
        exe = str(local) if local.exists() else str(Path(ffmpeg_bin_dir) / "ffprobe")
    try:
        out = subprocess.run([exe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                             capture_output=True, text=True, timeout=30)
        return float(out.stdout.strip())
    except Exception:
        return None
