"""PLANO.md secão 8.1 — smoke test de serving."""
from __future__ import annotations

import subprocess

import pytest

from agent.loop import run_agent


@pytest.mark.live
def test_modelo_responde_a_prompt_simples(live_registry, live_client, live_config):
    result = run_agent(
        "Responda apenas com a palavra: ok",
        registry=live_registry,
        client=live_client,
        config=live_config,
    )
    assert result.status == "ok"
    assert result.content.strip() != ""


@pytest.mark.live
def test_vram_usada_fica_abaixo_de_12gb():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("nvidia-smi indisponível")
    usados_mib = int(out.stdout.strip().splitlines()[0])
    assert usados_mib < 12 * 1024, f"VRAM usada ({usados_mib} MiB) estourou os 12 GB da placa."
