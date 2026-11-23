"""Gravação dos segmentos, estado para retomar e pós-processamento com ffmpeg.

Usa o ffmpeg do ``imageio-ffmpeg`` (vem no pip, funciona no Windows) se não
houver um no PATH.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Sequence

import numpy as np


def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def para_uint8(saida) -> np.ndarray:
    """Saída do pipeline (float 0..1, [T,H,W,3]) para uint8."""
    a = np.asarray(saida)
    if a.dtype != np.uint8:
        a = (np.clip(a, 0.0, 1.0) * 255.0).round().astype(np.uint8)
    return a


def gravar_mp4(quadros: np.ndarray, caminho: Path, fps: float, crf: int = 12):
    quadros = para_uint8(quadros)
    t, h, w, _ = quadros.shape
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_name(caminho.stem + ".parcial" + caminho.suffix)
    cmd = [ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{w}x{h}", "-r", f"{fps}", "-i", "-", "-c:v", "libx264", "-preset", "medium",
           "-crf", str(crf), "-pix_fmt", "yuv420p", str(tmp)]
    subprocess.run(cmd, input=np.ascontiguousarray(quadros).tobytes(), check=True)
    os.replace(tmp, caminho)


def salvar_npy(arr: np.ndarray, caminho: Path):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_name(caminho.stem + ".parcial.npy")
    np.save(tmp, arr)
    os.replace(tmp, caminho)


def concatenar(partes: Sequence[Path], saida: Path):
    saida = Path(saida)
    lista = saida.with_suffix(".lista.txt")
    lista.write_text("".join(f"file '{Path(p).resolve().as_posix()}'\n" for p in partes), encoding="utf-8")
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lista), "-c", "copy", str(saida)], check=True)
    lista.unlink()


def filtro_pos(fps_final: int, tamanho: str, interp: str) -> str:
    filtros = []
    if interp == "minterpolate" and fps_final:
        filtros.append(f"minterpolate=fps={fps_final}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1")
    elif fps_final:
        filtros.append(f"fps={fps_final}")
    if tamanho:
        w, h = tamanho.lower().split("x")
        filtros.append(f"scale={w}:{h}:flags=lanczos")
    return ",".join(filtros)


def pos_processar(entrada: Path, saida: Path, duracao_s: float, fps_final: int = 30,
                  tamanho: str = "720x1280", interp: str = "minterpolate", crf: int = 14):
    vf = filtro_pos(fps_final, tamanho, interp)
    cmd = [ffmpeg(), "-y", "-loglevel", "error", "-i", str(entrada), "-t", f"{duracao_s}"]
    if vf:
        cmd += ["-vf", vf]
    cmd += ["-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(saida)]
    subprocess.run(cmd, check=True)


class Estado:
    """``estado.json`` na pasta de saída: o que já foi feito, para retomar."""

    def __init__(self, pasta: Path):
        self.caminho = Path(pasta) / "estado.json"
        self.d = json.loads(self.caminho.read_text(encoding="utf-8")) if self.caminho.exists() else {}

    def get(self, k, padrao=None):
        return self.d.get(k, padrao)

    def set(self, **kw):
        self.d.update(kw)
        tmp = self.caminho.with_suffix(".parcial")
        tmp.write_text(json.dumps(self.d, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.caminho)


class QuadrosEstagio1:
    """Lê quadros do estágio 1 (``quadros/NNN.npy``) por intervalo global, sem carregar tudo."""

    def __init__(self, arquivos: List[Path]):
        self.partes = [np.load(p, mmap_mode="r") for p in arquivos]
        self.inicios = np.cumsum([0] + [len(p) for p in self.partes])

    def __len__(self):
        return int(self.inicios[-1])

    def intervalo(self, ini: int, fim: int) -> np.ndarray:
        fim = min(fim, len(self))
        out = []
        for k, parte in enumerate(self.partes):
            a, b = self.inicios[k], self.inicios[k + 1]
            lo, hi = max(ini, a), min(fim, b)
            if lo < hi:
                out.append(np.asarray(parte[lo - a:hi - a]))
        return np.concatenate(out) if out else np.zeros((0,), np.uint8)
