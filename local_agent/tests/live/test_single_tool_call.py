"""PLANO.md secão 8.2 — uma pergunta que exige exatamente uma tool call.

Se este teste falhar com a tool call malformada, o problema é quase sempre o
chat template do serving (PLANO.md secão 4.3), não o modelo.
"""
from __future__ import annotations

import pytest

from agent.loop import run_agent


@pytest.mark.live
def test_uma_pergunta_que_exige_exatamente_uma_tool_call(live_registry, live_client, live_config):
    result = run_agent(
        "Quanto é 47 * 12? Use a ferramenta de cálculo para responder com precisão.",
        registry=live_registry,
        client=live_client,
        config=live_config,
    )

    assert len(result.trace) >= 1, "modelo não fez nenhuma tool call"
    primeira = result.trace[0]
    assert primeira["tool"] == "calcular", f"ferramenta errada: {primeira['tool']}"
    assert primeira["result"]["ok"] is True, f"args malformados: {primeira}"
    assert primeira["result"]["resultado"] == 564
    assert result.status == "ok"
