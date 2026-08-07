"""Ferramenta: ler_arquivo — lê o conteúdo (texto) de um arquivo, com corte de tamanho."""
from __future__ import annotations

from agent.config import AgentConfig
from agent.sandbox import resolve_within_sandbox
from agent.tools.registry import ToolSpec

SCHEMA = {
    "type": "object",
    "properties": {
        "caminho": {
            "type": "string",
            "description": "Caminho completo do arquivo a ler (deve estar dentro dos diretórios permitidos).",
        },
        "max_chars": {
            "type": "integer",
            "description": "Número máximo de caracteres a retornar (padrão 4000).",
            "minimum": 1,
            "maximum": 20000,
        },
    },
    "required": ["caminho"],
    "additionalProperties": False,
}

DEFAULT_MAX_CHARS = 4000


def make_handler(config: AgentConfig):
    def ler_arquivo(caminho: str, max_chars: int = DEFAULT_MAX_CHARS) -> dict:
        resolved = resolve_within_sandbox(caminho, config.allowed_dirs)
        if not resolved.exists():
            return {"ok": False, "error": f"Arquivo não existe: {resolved}"}
        if not resolved.is_file():
            return {"ok": False, "error": f"Não é um arquivo: {resolved}"}

        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return {"ok": False, "error": f"Falha ao ler arquivo: {exc}"}

        truncado = len(text) > max_chars
        return {
            "ok": True,
            "caminho": str(resolved),
            "truncado": truncado,
            "conteudo": text[:max_chars],
        }

    return ler_arquivo


def build_spec(config: AgentConfig) -> ToolSpec:
    return ToolSpec(
        name="ler_arquivo",
        description="Lê o conteúdo de um arquivo de texto dentro de um diretório permitido.",
        parameters=SCHEMA,
        handler=make_handler(config),
    )
