"""Medição de VRAM/RAM para os testes na GPU."""

from __future__ import annotations

import json
import time
from pathlib import Path

import torch


def ram():
    try:
        import psutil

        vm = psutil.virtual_memory()
        proc = psutil.Process().memory_info().rss
        return {"ram_livre_gib": round(vm.available / 2**30, 2), "ram_processo_gib": round(proc / 2**30, 2)}
    except ImportError:
        return {}


def vram():
    if not torch.cuda.is_available():
        return {}
    livre, total = torch.cuda.mem_get_info()
    return {
        "vram_livre_gib": round(livre / 2**30, 2),
        "vram_total_gib": round(total / 2**30, 2),
        "vram_alocada_gib": round(torch.cuda.memory_allocated() / 2**30, 2),
        "vram_pico_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2),
    }


def zerar_pico():
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()


def retrato(**extra):
    return {"t": time.strftime("%Y-%m-%d %H:%M:%S"), **vram(), **ram(), **extra}


def registrar(arquivo: Path, **dados):
    arquivo = Path(arquivo)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    with arquivo.open("a", encoding="utf-8") as f:
        f.write(json.dumps(retrato(**dados), ensure_ascii=False) + "\n")
