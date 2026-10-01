"""Separação voz × instrumental (um lugar só para fila e reinstall).

Dois separadores, escolhidos por `KARAOKE_SEPARATOR`:
- `roformer`: BS-RoFormer pelo pacote opcional `audio-separator` (~+3,5 dB de
  SDR na voz e ~+2 dB no instrumental sobre o htdemucs, MVSEP Multisong).
- `demucs`: o htdemucs de sempre.
- `auto` (padrão): RoFormer se o `audio-separator` estiver instalado e houver
  GPU (na CPU um trecho de 30 s passou de 20 min), senão Demucs. Falha do RoFormer cai no Demucs (com GPU, sem tentar o RoFormer na CPU).

O RoFormer é mais pesado na VRAM: quem separa durante uma partida (fase 1 da
fila, fora do whisper_lock) passa `heavy_ok` e cai no Demucs enquanto houver
jogo. Cada tentativa tem `SEPARATION_TIMEOUT_SEC`: separação travada não pode
segurar o lock da GPU para sempre.

- Uma separação por vez (`_SEPARATION_LOCK`): cada música adicionada disparava
  o seu Demucs na hora, e várias ao mesmo tempo na GPU (junto com o Whisper da
  partida) estouravam a VRAM.
- Chama `python -m demucs.separate` com o Python do servidor: o executável
  `demucs` no PATH não existe quando o venv não está ativado (Linux).
- Modelo e bitrate configuráveis (`KARAOKE_DEMUCS_MODEL`, `KARAOKE_MP3_BITRATE`).
  O MP3 saía no padrão do LAME (~128 kbps) depois de dois outros passos com
  perda; 320 kbps preserva pratos e reverb do instrumental.
- Falha na GPU tenta de novo na CPU e o erro vem com o fim do stderr.
- `cancel` (threading.Event, da fila): remover a música mata o separador na hora.
  Antes o cancelamento só parava a tarefa da fila e a separação seguia na thread,
  segurando a GPU e recriando a pasta da música depois de apagada.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DEMUCS_MODEL = os.environ.get("KARAOKE_DEMUCS_MODEL", "htdemucs")
SEPARATOR = os.environ.get("KARAOKE_SEPARATOR", "auto").strip().lower()
ROFORMER_MODEL = os.environ.get("KARAOKE_ROFORMER_MODEL", "model_bs_roformer_ep_317_sdr_12.9755.ckpt")
SEPARATION_TIMEOUT_SEC = float(os.environ.get("KARAOKE_SEPARATION_TIMEOUT", "1200"))
# fora do /tmp (padrão do audio-separator): o modelo tem ~600 MB e sumiria no reboot
ROFORMER_MODEL_DIR = os.environ.get("KARAOKE_ROFORMER_MODEL_DIR",
                                    str(Path.home() / ".cache" / "audio-separator-models"))
MP3_BITRATE = os.environ.get("KARAOKE_MP3_BITRATE", "320k")

_SEPARATION_LOCK = threading.Lock()
# de quanto em quanto tempo o separador em andamento confere o cancelamento
CANCEL_POLL_SEC = 0.5


class SeparationCancelled(Exception):
    """A música saiu da fila durante a separação."""


def _check(cancel) -> None:
    if cancel is not None and cancel.is_set():
        raise SeparationCancelled()


def _run_cmd(cmd: list[str], env, timeout: float, cancel=None):
    """subprocess.run com cancelamento: com `cancel`, o processo morre quando ele é ligado."""
    if cancel is None:
        return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)
    # stderr num arquivo: barra de progresso enche o pipe e travaria o processo
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as err:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=err, env=env)
        deadline = time.monotonic() + timeout
        try:
            while True:
                try:
                    proc.wait(timeout=CANCEL_POLL_SEC)
                    break
                except subprocess.TimeoutExpired:
                    if cancel.is_set():
                        raise SeparationCancelled()
                    if time.monotonic() > deadline:
                        raise subprocess.TimeoutExpired(cmd, timeout)
        except BaseException:
            proc.kill()
            proc.wait()
            raise
        err.seek(0)
        return subprocess.CompletedProcess(cmd, proc.returncode, "", err.read())


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


def roformer_available() -> bool:
    return importlib.util.find_spec("audio_separator") is not None


def separator_backend() -> str:
    """"roformer" ou "demucs", pelo KARAOKE_SEPARATOR (auto: RoFormer instalado e com GPU)."""
    if SEPARATOR == "demucs":
        return "demucs"
    if SEPARATOR == "roformer" or (roformer_available() and _best_device() == "cuda"):
        return "roformer"
    return "demucs"


def roformer_command(audio_path: Path, out_dir: Path, model: str = ROFORMER_MODEL) -> list[str]:
    script = "from audio_separator.utils.cli import main; main()"
    return [
        sys.executable, "-c", script,
        str(audio_path),
        "-m", model,
        "--model_file_dir", ROFORMER_MODEL_DIR,
        "--output_dir", str(out_dir),
        "--output_format", "WAV",
        "--custom_output_names", json.dumps({"Vocals": "vocals", "Instrumental": "no_vocals"}),
        "--log_level", "warning",
        "--use_autocast",  # fp16 onde dá: ~metade da VRAM
    ]


def _run_on_devices(name: str, make_cmd, device: str, label: str, cpu_retry: bool = True, cancel=None) -> None:
    """Roda o separador no device e, se falhar na GPU, de novo na CPU. Levanta na falha."""
    devices = [device] if device == "cpu" or not cpu_retry else [device, "cpu"]
    last_error = ""
    for dev in devices:
        _check(cancel)
        cmd, env = make_cmd(dev)
        logger.info(f"[{name}] device={dev}: {label}")
        try:
            proc = _run_cmd(cmd, env, SEPARATION_TIMEOUT_SEC, cancel)
        except subprocess.TimeoutExpired:  # o processo filho já morreu
            last_error = f"passou de {SEPARATION_TIMEOUT_SEC:.0f}s"
            logger.error(f"[{name}] {last_error} em {dev}")
            continue
        if proc.returncode == 0:
            return
        last_error = _stderr_tail(proc.stderr)
        logger.error(f"[{name}] falhou em {dev} (exit {proc.returncode}):\n{last_error}")
    raise RuntimeError(f"{name} falhou: {last_error.splitlines()[-1] if last_error else 'sem detalhes'}")


def _separate_roformer(audio_path: Path, out_dir: Path, device: str, cancel=None) -> tuple[Path, Path]:
    out = out_dir / "roformer" / audio_path.stem
    out.mkdir(parents=True, exist_ok=True)

    def make_cmd(dev):
        env = dict(os.environ)
        if dev == "cpu":
            env["CUDA_VISIBLE_DEVICES"] = ""  # o audio-separator escolhe a GPU sozinho
        return roformer_command(audio_path, out), env

    logger.info(f"[RoFormer] modelo={ROFORMER_MODEL}")
    # com GPU, falha vai direto ao Demucs: RoFormer na CPU levaria muitos minutos com o lock
    _run_on_devices("RoFormer", make_cmd, device, audio_path.name, cpu_retry=False, cancel=cancel)
    vocals, no_vocals = out / "vocals.wav", out / "no_vocals.wav"
    if not vocals.exists() or not no_vocals.exists():
        raise RuntimeError("RoFormer não gerou os arquivos separados.")
    return vocals, no_vocals


def _separate_demucs(audio_path: Path, out_dir: Path, device: str, cancel=None) -> tuple[Path, Path]:
    logger.info(f"[Demucs] modelo={DEMUCS_MODEL}")
    _run_on_devices("Demucs", lambda dev: (demucs_command(audio_path, out_dir, dev), None), device, audio_path.name,
                    cancel=cancel)
    separated = out_dir / DEMUCS_MODEL / audio_path.stem
    vocals, no_vocals = separated / "vocals.wav", separated / "no_vocals.wav"
    if not vocals.exists() or not no_vocals.exists():
        raise RuntimeError("Demucs não gerou os arquivos separados.")
    return vocals, no_vocals


def separate_stems(audio_path: Path, out_dir: Path, heavy_ok=True, cancel=None) -> tuple[Path, Path]:
    """Separa e devolve (vocals.wav, no_vocals.wav). Bloqueante: use em thread.

    `heavy_ok` (bool ou função): False enquanto uma partida usa a GPU, e aí vai o Demucs.
    `cancel` (threading.Event): ligado, levanta SeparationCancelled e mata o separador.
    """
    audio_path = Path(audio_path)
    out_dir = Path(out_dir)
    device = _best_device()
    # esperando outra separação: confere o cancelamento enquanto espera a vez
    while not _SEPARATION_LOCK.acquire(timeout=CANCEL_POLL_SEC):
        _check(cancel)
    try:
        _check(cancel)
        heavy = heavy_ok() if callable(heavy_ok) else heavy_ok
        if separator_backend() == "roformer" and not heavy:
            logger.info("[RoFormer] partida em andamento: separando com o Demucs")
        elif separator_backend() == "roformer":
            try:
                return _separate_roformer(audio_path, out_dir, device, cancel)
            except SeparationCancelled:
                raise
            except Exception as e:
                logger.warning(f"[RoFormer] {e}; separando com o Demucs")
        return _separate_demucs(audio_path, out_dir, device, cancel)
    finally:
        _SEPARATION_LOCK.release()


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
