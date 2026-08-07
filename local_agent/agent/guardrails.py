"""Guardrails obrigatórios do agente local (PLANO.md secão 7).

Cada guardrail é uma peça pequena e testável isoladamente, sem depender do
modelo real, para que a suíte de testes cubra a secão 8 sem precisar de GPU.
"""
from __future__ import annotations

import concurrent.futures
import json
from dataclasses import dataclass, field


class ToolNotWhitelisted(Exception):
    """Ferramenta solicitada não está registrada (guardrail 7.4)."""


class InvalidToolArguments(Exception):
    """Argumentos da tool call não batem com o schema JSON (guardrail 7.3)."""


class ToolTimeoutError(Exception):
    """Ferramenta excedeu o timeout individual (guardrail 7.2)."""


class LoopDetected(Exception):
    """Mesma tool call (nome + args) repetida — aborta para evitar loop infinito (guardrail 7.6)."""


def run_with_timeout(fn, kwargs: dict, timeout_s: float):
    """Executa `fn(**kwargs)` com timeout. Levanta ToolTimeoutError se estourar."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn, **kwargs)
        try:
            return future.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError as exc:
            raise ToolTimeoutError(
                f"Ferramenta excedeu o timeout de {timeout_s}s."
            ) from exc


@dataclass
class CallSignatureTracker:
    """Rastreia (nome, args) de tool calls já executadas na tarefa atual."""

    seen: set[str] = field(default_factory=set)

    @staticmethod
    def _signature(name: str, args: dict) -> str:
        return name + "::" + json.dumps(args, sort_keys=True, ensure_ascii=False)

    def check_and_record(self, name: str, args: dict) -> None:
        sig = self._signature(name, args)
        if sig in self.seen:
            raise LoopDetected(
                f"A ferramenta '{name}' foi chamada novamente com os mesmos "
                f"argumentos — abortando para evitar loop infinito."
            )
        self.seen.add(sig)
