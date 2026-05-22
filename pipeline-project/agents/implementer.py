"""
Agente 3 — Implementador
Para cada step, lê o arquivo existente via MCP read_file,
chama o Ollama para obter a tool call estruturada em JSON e executa via write_server.py.
"""
from __future__ import annotations
import json
import os
import sys
import requests
import yaml
from pathlib import Path
from orchestrator.state import PipelineState, ToolCall, AgentLog
from orchestrator.validators import (
    validate_json_parseable,
    validate_tool_call_schema,
    validate_tool_whitelist,
    ValidationError_,
)
from orchestrator.retries import with_retry
from mcps.client import MCPClient

# Carrega a configuração global
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

OLLAMA_URL = f"{CONFIG['ollama']['base_url']}/api/chat"
MODEL = CONFIG['models']['implementer']

# Apenas estas tools são permitidas para o Agente 3
TOOL_WHITELIST = CONFIG.get("tool_whitelist", ["apply_patch", "write_file"])


def call_model(step_id: str, pseudocode: str, file_path: str, file_content: str,
               location: str, attempt: int, last_error, action: str = "modify") -> str:
    """
    POST para Ollama com a tool calling estruturada JSON.
    """
    print(f"  [agent3] enviando requisição para o modelo {MODEL} no Ollama...")

    # Carrega o system prompt correspondente
    system_prompt_path = Path(__file__).parent.parent / "prompts" / "implementer.system.md"
    with open(system_prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    # Monta a mensagem do usuário
    tool_hint = (
        "TOOL OBRIGATÓRIA: use write_file com o conteúdo completo do arquivo."
        if action == "create"
        else "Prefira apply_patch para modificações cirúrgicas. Use write_file só se necessário."
    )

    user_content = (
        f"PASSO A SER EXECUTADO:\n"
        f"ID: {step_id}\n"
        f"Arquivo: {file_path}\n"
        f"Localização: {location}\n"
        f"Action: {action}\n\n"
        f"INSTRUÇÃO DE TOOL: {tool_hint}\n\n"
        f"PSEUDOCÓDIGO DO PASSO:\n"
        f"{pseudocode}\n\n"
        f"CONTEÚDO DO ARQUIVO ALVO:\n"
        f"{file_content if file_content else '(Arquivo vazio ou novo)'}\n"
    )

    # Garante que outros modelos foram descarregados para liberar a GPU
    from orchestrator.utils import unload_ollama_models
    unload_ollama_models(except_model=MODEL)

    num_ctx = CONFIG.get("ollama", {}).get("implementer_num_ctx", 8192)

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "format": "json",
        "options": {
            "num_ctx": num_ctx
        },
        "stream": False
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=90)
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]
    except Exception as e:
        raise ValidationError_("A", f"Falha na chamada ao Ollama para o Implementador: {e}")


def execute_tool_call(tool_call: ToolCall, codebase_path: str) -> str:
    """
    Chama o servidor MCP de escrita (mcps/write_server.py).
    """
    print(f"  [mcp] executando {tool_call.tool} via write_server.py...")
    import sys
    from mcps.client import MCPClient
    
    server_path = Path(codebase_path) / "mcps" / "write_server.py"
    client = MCPClient([sys.executable, str(server_path)])
    try:
        result = client.call_tool(tool_call.tool, tool_call.arguments)
        return result
    except Exception as e:
        raise ValidationError_("A", f"Erro na execução da tool pelo write_server: {e}")
    finally:
        client.close()


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
            # Lendo arquivo real via MCP read_file
            file_path = _step.file
            full_path = os.path.join(state.codebase_path, file_path)
            file_content = ""
            if os.path.exists(full_path):
                client = MCPClient([sys.executable, str(Path(state.codebase_path) / "mcps" / "readonly_server.py")])
                try:
                    file_content = client.call_tool("read_file", {"path": os.path.abspath(full_path)})
                except Exception as e:
                    print(f"  [agent3] aviso: erro ao ler {_step.file} via MCP: {e}")
                    file_content = ""
                finally:
                    client.close()
            else:
                file_content = ""

            raw = call_model(
                _step.id, _ps.pseudocode, _step.file,
                file_content, _step.location, attempt, last_error,
                action=_step.action
            )

            # Salva o log bruto da saída
            if state.run_dir:
                impl_log_dir = Path(state.run_dir) / "implementer"
                impl_log_dir.mkdir(parents=True, exist_ok=True)
                with open(impl_log_dir / f"{_step.id}_attempt_{attempt + 1}.json", "w", encoding="utf-8") as f:
                    f.write(raw)

            # Camada A
            data = validate_json_parseable(raw)
            tool_call = validate_tool_call_schema(data)

            # Camada B: whitelist
            validate_tool_whitelist(tool_call, TOOL_WHITELIST)

            # Executa
            result = execute_tool_call(tool_call, state.codebase_path)
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
