"""PLANO.md secão 8.6 — VRAM sob carga com num_ctx de produção.

Heurística automatizável: memória da GPU continua abaixo de 12GB e a latência
por resposta não explode (o que indicaria offload para RAM, ~1-2 tok/s).
Para confirmação visual, rode `nvidia-smi -l 1` em paralelo durante o teste.
"""
from __future__ import annotations

import subprocess
import time

import pytest

from agent.loop import run_agent

LATENCIA_MAXIMA_S = 60.0  # generoso; offload para RAM tipicamente estoura isso de longe


def _vram_usada_mib() -> int | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return int(out.stdout.strip().splitlines()[0])


@pytest.mark.live
def test_cadeia_real_sob_num_ctx_de_producao_sem_offload(live_registry, live_client, live_config):
    workdir = live_config.allowed_dirs[0]
    arquivo = workdir / "dados.txt"
    arquivo.write_text("Vendas do trimestre: Q1 120k, Q2 135k, Q3 140k, Q4 160k.")

    inicio = time.monotonic()
    result = run_agent(
        f"Leia o arquivo {arquivo} e me diga qual trimestre teve a maior venda.",
        registry=live_registry,
        client=live_client,
        config=live_config,
    )
    duracao = time.monotonic() - inicio

    assert result.status == "ok"
    assert duracao < LATENCIA_MAXIMA_S, (
        f"resposta demorou {duracao:.1f}s — possível offload de VRAM para RAM"
    )

    usados = _vram_usada_mib()
    if usados is None:
        pytest.skip("nvidia-smi indisponível para checar VRAM")
    assert usados < 12 * 1024, f"VRAM usada ({usados} MiB) estourou os 12 GB da placa."
