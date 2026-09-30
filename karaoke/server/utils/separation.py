"""Separação voz × instrumental com o Demucs (um lugar só para fila e reinstall).

- Uma separação por vez (`_SEPARATION_LOCK`): cada música adicionada disparava
  o seu Demucs na hora, e várias ao mesmo tempo na GPU (junto com o Whisper da
  partida) estouravam a VRAM.
- Chama `python -m demucs.separate` com o Python do servidor: o executável
  `demucs` no PATH não existe quando o venv não está ativado (Linux).
- Modelo e bitrate configuráveis (`KARAOKE_DEMUCS_MODEL`, `KARAOKE_MP3_BITRATE`).
  O MP3 saía no padrão do LAME (~128 kbps) depois de dois outros passos com
  perda; 320 kbps preserva pratos e reverb do instrumental.
- Falha na GPU tenta de novo na CPU e o erro vem com o fim do stderr.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

DEMUCS_MODEL = os.environ.get("KARAOKE_DEMUCS_MODEL", "htdemucs")
MP3_BITRATE = os.environ.get("KARAOKE_MP3_BITRATE", "320k")

_SEPARATION_LOCK = threading.Lock()


def _best_device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def demucs_command(audio_path: Path, out_dir: Path, device: str, model: str = DEMUCS_MODEL) -> list[str]:
    return [
        sys.executable, "-m", "demucs.separate",
        "-n", model,
        "--two-stems", "vocals",
        "-d", device,
        "-o", str(out_dir),
        str(audio_path),
    ]


def _stderr_tail(text: str, lines: int = 8) -> str:
    return "\n".join((text or "").strip().splitlines()[-lines:])


def separate_stems(audio_path: Path, out_dir: Path) -> tuple[Path, Path]:
    """Roda o Demucs e devolve (vocals.wav, no_vocals.wav). Bloqueante: use em thread."""
    audio_path = Path(audio_path)
    out_dir = Path(out_dir)
    device = _best_device()
    with _SEPARATION_LOCK:
        devices = [device] if device == "cpu" else [device, "cpu"]
        last_error = ""
        for dev in devices:
            cmd = demucs_command(audio_path, out_dir, dev)
            logger.info(f"[Demucs] modelo={DEMUCS_MODEL} device={dev}: {audio_path.name}")
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode == 0:
                break
            last_error = _stderr_tail(proc.stderr)
            logger.error(f"[Demucs] falhou em {dev} (exit {proc.returncode}):\n{last_error}")
        else:
            raise RuntimeError(f"Demucs falhou: {last_error.splitlines()[-1] if last_error else 'sem detalhes'}")

    separated = out_dir / DEMUCS_MODEL / audio_path.stem
    vocals, no_vocals = separated / "vocals.wav", separated / "no_vocals.wav"
    if not vocals.exists() or not no_vocals.exists():
        raise RuntimeError("Demucs não gerou os arquivos separados.")
    return vocals, no_vocals


def export_mp3(src: Path, dst: Path) -> None:
    """WAV/qualquer formato → MP3 no bitrate configurado. Bloqueante."""
    from pydub import AudioSegment

    AudioSegment.from_file(str(src)).export(str(dst), format="mp3", bitrate=MP3_BITRATE)


def export_backing_mp3(src, dst: Path, meta_path: Path | None = None) -> dict | None:
    """Exporta o instrumental já com o volume normalizado (utils/loudness.py, ~−16 LUFS).

    `src` é um caminho ou um pydub.AudioSegment. A normalização nunca derruba a
    música: se falhar, exporta o áudio como veio. Com `meta_path` (padrão: o
    meta.json ao lado de `dst`, se existir) grava `loudness` = {lufs_before, gain_db}.
    """
    from pydub import AudioSegment

    audio = src if hasattr(src, "export") else AudioSegment.from_file(str(src))
    info = None
    try:
        from utils.loudness import normalize_audiosegment

        audio, info = normalize_audiosegment(audio)
        logger.info(f"[Loudness] {Path(dst).name}: {info['lufs_before']} LUFS, ganho {info['gain_db']:+.1f} dB")
    except Exception as e:
        logger.warning(f"[Loudness] normalização falhou, exportando sem ajuste: {e}")
    audio.export(str(dst), format="mp3", bitrate=MP3_BITRATE)

    meta_path = Path(meta_path) if meta_path else Path(dst).parent / "meta.json"
    if info is not None and meta_path.exists():
        try:
            import json

            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["loudness"] = info
            meta_path.write_text(json.dumps(meta, indent=4, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning(f"[Loudness] não gravou no meta.json: {e}")
    return info
