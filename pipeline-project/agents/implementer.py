"""
Agente 3 — Implementador (MOCK)
Para cada step, retorna uma tool call estruturada.
Quando for real: substituir `call_model()` por chamada ao Ollama com tool calling nativo.
"""
from __future__ import annotations
import json
from orchestrator.state import PipelineState, ToolCall, AgentLog
from orchestrator.validators import (
    validate_json_parseable,
    validate_tool_call_schema,
    validate_tool_whitelist,
    ValidationError_,
)
from orchestrator.retries import with_retry

MODEL = "qwen2.5-coder:7b-q4_k_m"

# Apenas estas tools são permitidas para o Agente 3
TOOL_WHITELIST = ["apply_patch", "write_file"]


def mock_tool_call_for(step_id: str, file_path: str, action: str) -> dict:
    """Gera tool call mock."""
    if action == "create":
        return {
            "tool": "write_file",
            "arguments": {
                "file_path": file_path,
                "content": f"# Arquivo criado pelo {step_id}\n# TODO: implementar\n"
            }
        }
    else:
        return {
            "tool": "apply_patch",
            "arguments": {
                "file_path": file_path,
                "unified_diff": (
                    f"--- a/{file_path}\n"
                    f"+++ b/{file_path}\n"
                    f"@@ -1,0 +1,3 @@\n"
                    f"+# Patch aplicado por {step_id}\n"
                    f"+# TODO: código real aqui\n"
                )
            }
        }


def call_model(step_id: str, pseudocode: str, file_path: str, file_content: str,
               location: str, attempt: int, last_error) -> str:
    """
    MOCK: retorna tool call fixo.
    REAL: POST para Ollama com tool calling nativo (Qwen suporta).
          O modelo deve retornar tool_calls estruturado, não prosa.
    """
    print(f"  [agent3] gerando tool call para {step_id} (mock)...")

    # Descobre action a partir do step (mock usa write_file para novos, apply_patch para resto)
    action = "create" if "criar" in pseudocode.lower() or "create" in pseudocode.lower() else "modify"
    return json.dumps(mock_tool_call_for(step_id, file_path, action))


def execute_tool_call(tool_call: ToolCall) -> str:
    """
    MOCK: simula execução da tool call.
    REAL: chama o servidor MCP correspondente (write_mcp ou readonly_mcp).
    """
    print(f"  [mcp] executando {tool_call.tool}({list(tool_call.arguments.keys())}) (mock)...")
    return f"ok: {tool_call.tool} aplicado"


def run(state: PipelineState) -> list[str]:
    """Executa o Agente 3: uma chamada por step, em ordem topológica."""
    print(f"\n[Agente 3 - Implementador]")
    assert state.plan is not None
    assert state.pseudocode

    # Ordena por dependências (topológica simples)
    steps_by_id = {s.id: s for s in state.plan.steps}
    ordered = _topological_sort(state.plan.steps)

    applied = []
    log = AgentLog(agent="implementer", model=MODEL)

    for step in ordered:
        ps = state.pseudocode[step.id]
        print(f"  -> aplicando {step.id}: {step.description[:50]}")

        def attempt_fn(attempt: int, last_error, _step=step, _ps=ps):
            # Leria arquivo real via MCP read_file
            file_content = f"# conteúdo mock de {_step.file}"

            raw = call_model(
                _step.id, _ps.pseudocode, _step.file,
                file_content, _step.location, attempt, last_error
            )

            # Camada A
            data = validate_json_parseable(raw)
            tool_call = validate_tool_call_schema(data)

            # Camada B: whitelist
            validate_tool_whitelist(tool_call, TOOL_WHITELIST)

            # Executa (mock)
            result = execute_tool_call(tool_call)
            return result

        result = with_retry(attempt_fn, state, agent_name=f"agent3_{step.id}", max_retries=2)
        applied.append(f"{step.id}: {result}")

    state.applied_patches = applied
    state.logs.append(log)
    print(f"  [OK] {len(applied)} patches aplicados")
    return applied


def _topological_sort(steps):
    """Ordena steps por dependências (Kahn's algorithm)."""
    from collections import deque
    in_degree = {s.id: 0 for s in steps}
    adj = {s.id: [] for s in steps}
    by_id = {s.id: s for s in steps}

    for s in steps:
        for dep in s.depends_on:
            adj[dep].append(s.id)
            in_degree[s.id] += 1

    queue = deque([s.id for s in steps if in_degree[s.id] == 0])
    result = []

    while queue:
        node = queue.popleft()
        result.append(by_id[node])
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return result
