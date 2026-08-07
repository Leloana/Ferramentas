"""Registro central de ferramentas — a única fonte de verdade sobre o que o
agente pode executar (guardrail 7.4: whitelist)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import jsonschema

from agent.guardrails import InvalidToolArguments, ToolNotWhitelisted


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    handler: Callable[..., dict[str, Any]]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Ferramenta '{spec.name}' já registrada.")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotWhitelisted(
                f"Ferramenta '{name}' não está registrada/whitelistada."
            ) from exc

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def openai_schemas(self) -> list[dict[str, Any]]:
        """Formato de tools esperado pela API OpenAI-compatível (Ollama)."""
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
            for spec in self._tools.values()
        ]

    def validate_args(self, name: str, args: dict[str, Any]) -> None:
        spec = self.get(name)
        try:
            jsonschema.validate(instance=args, schema=spec.parameters)
        except jsonschema.ValidationError as exc:
            raise InvalidToolArguments(
                f"Argumentos inválidos para '{name}': {exc.message}"
            ) from exc

    def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Valida e executa. Não captura exceções da própria ferramenta —
        quem chama decide como tratar timeout/erro (ver agent/loop.py)."""
        spec = self.get(name)
        self.validate_args(name, args)
        return spec.handler(**args)
