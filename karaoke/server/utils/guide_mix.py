"""Voz guia: a música com a voz original, num arquivo só.

Antes a TV tocava o vocal.mp3 num segundo <audio> que corria atrás do
instrumental; as gravações mostravam a voz sempre 80–200 ms atrasada (cada
salto de correção também custa tempo). Aqui o instrumental e a voz são somados
amostra a amostra pelo FFmpeg — os dois saem da mesma separação, então o tempo é
o da gravação — e a TV troca o arquivo do player em vez de sincronizar dois.

`guide_mix_<nível>.mp3` (50 = voz pela metade, 100 = voz normal) é gerado na
primeira vez que alguém pede e guardado na pasta da música; refeito se o
instrumental ou a voz mudarem (reinstalar). O instrumental foi normalizado
(`meta.json["loudness"]["gain_db"]`): a voz ganha o mesmo ganho, para a
proporção voz × instrumental ser a original. Um limitador segura os picos.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path

from utils.separation import MP3_BITRATE

logger = logging.getLogger(__name__)

LEVELS = (50, 100)
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(str(path), threading.Lock())


def _backing_gain_db(song_dir: Path) -> float:
    try:
        meta = json.loads((song_dir / "meta.json").read_text(encoding="utf-8"))
        return float((meta.get("loudness") or {}).get("gain_db") or 0.0)
    except Exception:
        return 0.0


def _is_fresh(out: Path, sources: list[Path]) -> bool:
    if not out.exists() or out.stat().st_size == 0:
        return False
    return all(out.stat().st_mtime >= s.stat().st_mtime for s in sources)


def guide_mix_path(song_dir: Path, level: int) -> Path | None:
    """Caminho da mixagem instrumental + voz no nível pedido (gera se faltar).

    None se a música não tem voz separada ou o FFmpeg falhar (aí vale o instrumental).
    """
    level = min(LEVELS, key=lambda lv: abs(lv - level))
    backing, vocal = song_dir / "backing_track.mp3", song_dir / "vocal.mp3"
    if not backing.exists() or not vocal.exists():
        return None
    out = song_dir / f"guide_mix_{level}.mp3"
    with _lock_for(out):
        if _is_fresh(out, [backing, vocal]):
            return out
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            logger.warning("[Voz guia] FFmpeg não encontrado: sem mixagem com a voz")
            return None
        vocal_gain = (level / 100.0) * 10 ** (_backing_gain_db(song_dir) / 20.0)
        tmp = out.with_suffix(".tmp.mp3")
        cmd = [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(backing), "-i", str(vocal),
            "-filter_complex",
            f"[1:a]volume={vocal_gain:.4f}[v];"
            "[0:a][v]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.97:level=false[out]",
            "-map", "[out]", "-c:a", "libmp3lame", "-b:a", MP3_BITRATE, str(tmp),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
            os.replace(tmp, out)
        except Exception as e:
            err = getattr(e, "stderr", b"") or b""
            logger.error(f"[Voz guia] Falha ao mixar {song_dir.name} ({level}%): {e} {err[-300:]!r}")
            tmp.unlink(missing_ok=True)
            return None
        logger.info(f"[Voz guia] Mixagem {song_dir.name} com a voz em {level}% pronta")
        return out
