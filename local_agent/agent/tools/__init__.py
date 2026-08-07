"""Conjunto de ferramentas do agente local.

PLANO.md secão 6.1: conjunto pequeno (3–6) e whitelistado — nunca registrar
dezenas de ferramentas, isso degrada a seleção do modelo pequeno.
"""
from __future__ import annotations

from agent.config import AgentConfig, DEFAULT_CONFIG
from agent.tools import buscar_arquivo, calcular, data_hora, ler_arquivo, listar_diretorio
from agent.tools.registry import ToolRegistry


def build_default_registry(config: AgentConfig | None = None) -> ToolRegistry:
    config = config or DEFAULT_CONFIG
    registry = ToolRegistry()
    for module in (buscar_arquivo, ler_arquivo, listar_diretorio, calcular, data_hora):
        registry.register(module.build_spec(config))
    return registry


default_registry = build_default_registry()
