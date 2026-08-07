"""Ferramenta: buscar_arquivo — busca arquivos por padrão de nome em um diretório."""
from __future__ import annotations

from pathlib import Path

from agent.config import AgentConfig
from agent.sandbox import resolve_within_sandbox
from agent.tools.registry import ToolSpec

SCHEMA = {
    "type": "object",
    "properties": {
        "diretorio": {
            "type": "string",
            "description": "Diretório onde buscar (deve estar dentro dos diretórios permitidos).",
        },
        "padrao": {
            "type": "string",
            "description": "Padrão glob do nome do arquivo, ex.: '*.py', 'relatorio*.txt'.",
        },
    },
    "required": ["diretorio", "padrao"],
    "additionalProperties": False,
}

MAX_RESULTS = 50


def make_handler(config: AgentConfig):
    def buscar_arquivo(diretorio: str, padrao: str) -> dict:
        base = resolve_within_sandbox(diretorio, config.allowed_dirs)
        if not base.exists():
            return {"ok": False, "error": f"Diretório não existe: {base}"}
        if not base.is_dir():
            return {"ok": False, "error": f"Não é um diretório: {base}"}

        matches = []
        for p in base.rglob(padrao):
            if p.is_file():
                matches.append(str(p))
            if len(matches) >= MAX_RESULTS:
                break

        return {
            "ok": True,
            "diretorio": str(base),
            "padrao": padrao,
            "total_encontrado": len(matches),
            "truncado": len(matches) >= MAX_RESULTS,
            "arquivos": matches,
        }

    return buscar_arquivo


def build_spec(config: AgentConfig) -> ToolSpec:
    return ToolSpec(
        name="buscar_arquivo",
        description="Busca arquivos por padrão de nome (glob) dentro de um diretório permitido.",
        parameters=SCHEMA,
        handler=make_handler(config),
    )
