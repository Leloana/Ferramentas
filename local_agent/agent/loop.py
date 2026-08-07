"""Loop ReAct do agente local (PLANO.md secão 6), com todos os guardrails da
secão 7 amarrados: limite de iterações, timeout por tool e global, validação
de argumentos, whitelist, sandbox (dentro das próprias ferramentas) e
detecção de loop. Nunca alucina sucesso — sempre falha limpo.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from agent.config import AgentConfig
from agent.guardrails import (
    CallSignatureTracker,
    InvalidToolArguments,
    LoopDetected,
    ToolNotWhitelisted,
    ToolTimeoutError,
    run_with_timeout,
)
from agent.llm_client import AssistantMessage, LLMClient, ToolCallRequest
from agent.tools.registry import ToolRegistry

DEFAULT_SYSTEM_PROMPT = """\
Você é um agente local com acesso a um conjunto pequeno de ferramentas.
Seu escopo é tarefas pontuais e de cadeia curta: chamadas de ferramenta
específicas, busca e leitura de arquivos, cálculos, e perguntas objetivas.

Regras:
- Use uma ferramenta apenas quando ela for realmente necessária para responder.
- Nunca invente resultado de ferramenta: só relate o que uma tool call retornou.
- Se a tarefa exigir muito mais passos do que o razoável, ou não puder ser
  concluída com as ferramentas disponíveis, PARE e explique o motivo em vez
  de insistir ou improvisar uma resposta não verificada.
- Você NÃO tem autonomia de longo prazo: não tente orquestrar cadeias longas.
"""

MAX_ITERS_MSG = "FALHA: tarefa excedeu o limite de passos do agente local."
TASK_TIMEOUT_MSG = "FALHA: tarefa excedeu o timeout global do agente local."


@dataclass
class AgentResult:
    status: str  # "ok" | "failed"
    content: str
    iterations: int
    trace: list[dict[str, Any]] = field(default_factory=list)


def _assistant_message_to_api_dict(msg: AssistantMessage) -> dict[str, Any]:
    out: dict[str, Any] = {"role": "assistant", "content": msg.content}
    if msg.tool_calls:
        out["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.args_raw},
            }
            for call in msg.tool_calls
        ]
    return out


def _execute_tool_call(
    call: ToolCallRequest,
    registry: ToolRegistry,
    tracker: CallSignatureTracker,
    config: AgentConfig,
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    entry: dict[str, Any] = {"tool": call.name, "args_raw": call.args_raw}
    trace.append(entry)

    if call.args is None:
        msg = f"Argumentos malformados (não é JSON válido): {call.args_raw!r}"
        entry["result"] = {"ok": False, "error": msg}
        return entry["result"]

    try:
        spec = registry.get(call.name)
    except ToolNotWhitelisted as exc:
        entry["result"] = {"ok": False, "error": str(exc)}
        return entry["result"]

    try:
        tracker.check_and_record(call.name, call.args)
    except LoopDetected as exc:
        entry["result"] = {"ok": False, "error": str(exc), "_abort": True}
        return entry["result"]

    try:
        registry.validate_args(call.name, call.args)
    except InvalidToolArguments as exc:
        entry["result"] = {"ok": False, "error": str(exc)}
        return entry["result"]

    try:
        result = run_with_timeout(spec.handler, call.args, config.tool_timeout_s)
    except ToolTimeoutError as exc:
        entry["result"] = {"ok": False, "error": str(exc)}
        return entry["result"]
    except Exception as exc:  # ferramenta pode levantar erro inesperado
        msg = f"Erro inesperado na ferramenta: {exc}"
        entry["result"] = {"ok": False, "error": msg}
        return entry["result"]

    entry["result"] = result
    return result


def run_agent(
    user_msg: str,
    *,
    registry: ToolRegistry,
    client: LLMClient,
    config: AgentConfig,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
) -> AgentResult:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]
    tools_schema = registry.openai_schemas()
    tracker = CallSignatureTracker()
    trace: list[dict[str, Any]] = []
    deadline = time.monotonic() + config.task_timeout_s

    for i in range(1, config.max_iters + 1):
        if time.monotonic() > deadline:
            return AgentResult(
                status="failed", content=TASK_TIMEOUT_MSG, iterations=i - 1, trace=trace
            )

        assistant_msg = client.chat(messages, tools_schema)
        messages.append(_assistant_message_to_api_dict(assistant_msg))

        if not assistant_msg.tool_calls:
            return AgentResult(
                status="ok",
                content=assistant_msg.content or "",
                iterations=i,
                trace=trace,
            )

        for call in assistant_msg.tool_calls:
            tool_result = _execute_tool_call(call, registry, tracker, config, trace)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(tool_result, ensure_ascii=False),
                }
            )
            if tool_result.get("_abort"):
                return AgentResult(
                    status="failed",
                    content=f"FALHA: {tool_result['error']}",
                    iterations=i,
                    trace=trace,
                )

    return AgentResult(
        status="failed", content=MAX_ITERS_MSG, iterations=config.max_iters, trace=trace
    )
