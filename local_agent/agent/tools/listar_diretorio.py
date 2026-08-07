"""Ferramenta: listar_diretorio — lista entradas imediatas de um diretório."""
from __future__ import annotations

from agent.config import AgentConfig
from agent.sandbox import resolve_within_sandbox
from agent.tools.registry import ToolSpec

SCHEMA = {
    "type": "object",
    "properties": {
        "caminho": {
            "type": "string",
            "description": "Diretório a listar (deve estar dentro dos diretórios permitidos).",
        },
    },
    "required": ["caminho"],
    "additionalProperties": False,
}

MAX_ENTRIES = 200


def make_handler(config: AgentConfig):
    def listar_diretorio(caminho: str) -> dict:
        resolved = resolve_within_sandbox(caminho, config.allowed_dirs)
        if not resolved.exists():
            return {"ok": False, "error": f"Diretório não existe: {resolved}"}
        if not resolved.is_dir():
            return {"ok": False, "error": f"Não é um diretório: {resolved}"}

        entradas = []
        for i, p in enumerate(sorted(resolved.iterdir())):
            if i >= MAX_ENTRIES:
                break
            try:
                tamanho = p.stat().st_size if p.is_file() else None
            except OSError:
                tamanho = None
            entradas.append(
                {
                    "nome": p.name,
                    "tipo": "diretorio" if p.is_dir() else "arquivo",
                    "tamanho_bytes": tamanho,
                }
            )

        return {"ok": True, "caminho": str(resolved), "entradas": entradas}

    return listar_diretorio


def build_spec(config: AgentConfig) -> ToolSpec:
    return ToolSpec(
        name="listar_diretorio",
        description="Lista os arquivos e subdiretórios imediatos de um diretório permitido.",
        parameters=SCHEMA,
        handler=make_handler(config),
    )
