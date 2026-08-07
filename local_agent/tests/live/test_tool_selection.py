"""PLANO.md secão 8.3 — dado o conjunto de 3-6 ferramentas, o modelo escolhe
a correta em pelo menos 8 de 10 casos.
"""
from __future__ import annotations

import pytest

from agent.loop import run_agent


@pytest.mark.live
def test_selecao_de_ferramenta_pelo_menos_8_de_10(live_registry, live_client, live_config):
    workdir = live_config.allowed_dirs[0]
    nota = workdir / "nota.txt"
    nota.write_text("Reunião de projeto marcada para sexta-feira às 15h.")

    casos = [
        ("Que horas são agora, exatamente?", "data_hora_atual"),
        ("Me diga a data de hoje.", "data_hora_atual"),
        ("Quanto é 15 * 8?", "calcular"),
        ("Calcule 100 dividido por 4.", "calcular"),
        (f"Liste o conteúdo do diretório {workdir}.", "listar_diretorio"),
        (f"Quais arquivos e pastas existem dentro de {workdir}?", "listar_diretorio"),
        (f"Procure por arquivos com extensão .txt dentro de {workdir}.", "buscar_arquivo"),
        (f"Encontre arquivos que combinem com o padrão nota*.txt em {workdir}.", "buscar_arquivo"),
        (f"Leia o conteúdo do arquivo {nota}.", "ler_arquivo"),
        (f"Mostre o texto que está dentro do arquivo {nota}.", "ler_arquivo"),
    ]

    acertos = 0
    detalhes = []
    for pergunta, esperado in casos:
        result = run_agent(pergunta, registry=live_registry, client=live_client, config=live_config)
        usada = result.trace[0]["tool"] if result.trace else None
        ok = usada == esperado
        acertos += ok
        detalhes.append((pergunta, esperado, usada, ok))

    resumo = "\n".join(f"  esperado={e!r} usada={u!r} ok={ok}  <- {p!r}" for p, e, u, ok in detalhes)
    assert acertos >= 8, f"Acertos: {acertos}/10\n{resumo}"
