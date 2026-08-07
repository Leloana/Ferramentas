"""Cliente LLM: abstrai o endpoint OpenAI-compatível do Ollama.

O loop do agente (agent/loop.py) depende só da interface `LLMClient.chat(...)`
e das dataclasses `AssistantMessage`/`ToolCallRequest` — isso permite
substituir por um cliente fake nos testes unitários, sem precisar de GPU
nem de um servidor Ollama rodando (ver tests/test_loop.py).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from agent.config import AgentConfig


@dataclass(frozen=True)
class ToolCallRequest:
    id: str
    name: str
    # args_raw preserva o texto original (pode ser JSON malformado vindo do
    # modelo); args é o dict já parseado, ou None se o parse falhou.
    args_raw: str
    args: dict[str, Any] | None


@dataclass(frozen=True)
class AssistantMessage:
    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)


class LLMClient(Protocol):
    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AssistantMessage: ...


class OllamaLLMClient:
    """Implementação real, via SDK `openai` apontando para o Ollama local."""

    def __init__(self, config: AgentConfig) -> None:
        # import local: evita exigir o pacote `openai` para quem só quer
        # rodar os testes unitários com um cliente fake.
        from openai import OpenAI

        self._config = config
        self._client = OpenAI(base_url=config.ollama_base_url, api_key="ollama")

    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AssistantMessage:
        resp = self._client.chat.completions.create(
            model=self._config.model,
            messages=messages,
            tools=tools,
            temperature=self._config.temperature,
            top_p=self._config.top_p,
        )
        msg = resp.choices[0].message

        tool_calls: list[ToolCallRequest] = []
        for call in msg.tool_calls or []:
            raw = call.function.arguments or "{}"
            try:
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    parsed = None
            except json.JSONDecodeError:
                parsed = None
            tool_calls.append(
                ToolCallRequest(
                    id=call.id, name=call.function.name, args_raw=raw, args=parsed
                )
            )

        return AssistantMessage(content=msg.content, tool_calls=tool_calls)
