"""Ferramenta: data_hora_atual — retorna a data/hora local atual."""
from __future__ import annotations

from datetime import datetime

from agent.config import AgentConfig
from agent.tools.registry import ToolSpec

SCHEMA = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


def make_handler(_config: AgentConfig):
    def data_hora_atual() -> dict:
        agora = datetime.now()
        return {
            "ok": True,
            "iso": agora.isoformat(timespec="seconds"),
            "data": agora.strftime("%d/%m/%Y"),
            "hora": agora.strftime("%H:%M:%S"),
        }

    return data_hora_atual


def build_spec(config: AgentConfig) -> ToolSpec:
    return ToolSpec(
        name="data_hora_atual",
        description="Retorna a data e hora atuais do sistema local.",
        parameters=SCHEMA,
        handler=make_handler(config),
    )
