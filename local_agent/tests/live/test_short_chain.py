"""PLANO.md secão 8.4 — cadeia curta (2-3 passos): buscar -> ler -> resumir."""
from __future__ import annotations

import pytest

from agent.loop import run_agent


@pytest.mark.live
def test_busca_le_e_resume_arquivo(live_registry, live_client, live_config):
    workdir = live_config.allowed_dirs[0]
    arquivo = workdir / "relatorio.txt"
    arquivo.write_text("O projeto Foo atingiu a meta trimestral de vendas.")

    result = run_agent(
        f"Busque arquivos .txt no diretório {workdir}, leia o relatorio.txt encontrado "
        f"e resuma o conteúdo dele em uma frase.",
        registry=live_registry,
        client=live_client,
        config=live_config,
    )

    ferramentas_usadas = [t["tool"] for t in result.trace]
    assert "buscar_arquivo" in ferramentas_usadas, ferramentas_usadas
    assert "ler_arquivo" in ferramentas_usadas, ferramentas_usadas
    assert ferramentas_usadas.index("buscar_arquivo") < ferramentas_usadas.index("ler_arquivo")
    assert result.status == "ok"

    conteudo = result.content.lower()
    assert any(p in conteudo for p in ["foo", "meta", "trimestral", "vendas"]), result.content
