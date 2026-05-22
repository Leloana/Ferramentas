"""
Agente 2 — Coder
Para cada step do plano, lê o arquivo existente via MCP read_file,
chama o Ollama para obter pseudocódigo JSON estruturado e valida as camadas A e B.
"""
from __future__ import annotations
import json
import os
import sys
import requests
import yaml
from pathlib import Path
from orchestrator.state import PipelineState, Plan, PseudocodeStep, AgentLog
from orchestrator.validators import (
    validate_json_parseable,
    validate_pseudocode_schema,
    validate_pseudocode_coverage,
    validate_direct_content,
    ValidationError_,
)
from orchestrator.retries import with_retry
from mcps.client import MCPClient

# Carrega a configuração global
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

OLLAMA_URL = f"{CONFIG['ollama']['base_url']}/api/chat"
MODEL = CONFIG['models']['coder']


def call_model(step_id: str, description: str, file_content: str, attempt: int, last_error,
               state_chunks=None, mode: str = "patch", target_file: str = "") -> str:
    """
    Faz requisição POST para o Ollama local usando o system prompt do Coder.
    """
    print(f"  [agent2] enviando requisição para o modelo {MODEL} no Ollama...")

    # Carrega o system prompt correspondente
    system_prompt_path = Path(__file__).parent.parent / "prompts" / "coder.system.md"
    with open(system_prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    # Monta a mensagem do usuário
    user_content = (
        f"PASSO A SER PROCESSADO:\n"
        f"ID: {step_id}\n"
        f"Mode: {mode}\n"
        f"File: {target_file}\n"
        f"Descrição: {description}\n\n"
        f"CONTEÚDO DO ARQUIVO ALVO:\n"
        f"{file_content if file_content else '(Arquivo vazio ou novo)'}\n"
    )

    if mode == "direct":
        user_content += (
            "\nIMPORTANT: This step is mode='direct'. Output JSON with the keys "
            "'step_id' and 'file_content' ONLY. 'file_content' must contain the COMPLETE, "
            "FINAL, ready-to-write content of the file. No pseudocode, no placeholders.\n"
        )

    if state_chunks:
        user_content += "\nADDITIONAL CONTEXT (codebase files for synthesis):\n"
        for chunk in state_chunks:
            user_content += f"\n{chunk}\n"

    # Garante que outros modelos foram descarregados para liberar a GPU
    from orchestrator.utils import unload_ollama_models
    unload_ollama_models(except_model=MODEL)

    if mode == "direct":
        num_ctx = CONFIG.get("ollama", {}).get("coder_num_ctx_synthesis", 32768)
    else:
        num_ctx = CONFIG.get("ollama", {}).get("coder_num_ctx", 16384)

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
        timeout = CONFIG.get("ollama", {}).get("request_timeout", 300)
        response = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]
    except Exception as e:
        raise ValidationError_("A", f"Falha na chamada ao Ollama para o Coder: {e}")


def run(state: PipelineState) -> dict[str, PseudocodeStep]:
    """Executa o Agente 2: uma chamada por step."""
    print(f"\n[Agente 2 - Coder]")
    assert state.plan is not None, "Agente 2 precisa do plano do Agente 1"

    pseudocode: dict[str, PseudocodeStep] = {}
    log = AgentLog(agent="coder", model=MODEL)

    # Importa aqui para evitar ciclo no momento do carregamento do módulo.
    from orchestrator.runner import _collect_brain_context

    for step in state.plan.steps:
        # Steps de análise foram executados pelo runner antes do Coder; nada a fazer aqui.
        if step.action == "analyze":
            continue

        print(f"  -> processando {step.id}: {step.description[:50]}")

        # Contexto extra: dossiês brain/ de upstream analyze steps (via depends_on).
        brain_chunks = _collect_brain_context(state, step)
        step_chunks = list(state.retrieved_chunks) + brain_chunks

        def attempt_fn(attempt: int, last_error, _step=step, _chunks=step_chunks):
            # Lendo arquivo real via MCP read_file
            file_path = _step.file
            full_path = os.path.join(state.codebase_path, file_path)
            file_content = ""
            if os.path.exists(full_path):
                client = MCPClient([sys.executable, str(Path(state.codebase_path) / "mcps" / "readonly_server.py")])
                try:
                    file_content = client.call_tool("read_file", {"path": os.path.abspath(full_path)})
                except Exception as e:
                    print(f"  [agent2] aviso: erro ao ler {_step.file} via MCP: {e}")
                    file_content = ""
                finally:
                    client.close()
            else:
                file_content = ""

            raw = call_model(_step.id, _step.description, file_content, attempt, last_error,
                             state_chunks=_chunks,
                             mode=_step.mode, target_file=_step.file)

            # Salva o log bruto da saída
            if state.run_dir:
                coder_log_dir = Path(state.run_dir) / "coder"
                coder_log_dir.mkdir(parents=True, exist_ok=True)
                with open(coder_log_dir / f"{_step.id}_attempt_{attempt + 1}.json", "w", encoding="utf-8") as f:
                    f.write(raw)

            # Camada A
            data = validate_json_parseable(raw)
            # Garante que step_id esteja presente (modelo às vezes esquece em direct mode).
            data.setdefault("step_id", _step.id)
            ps = validate_pseudocode_schema(data)

            # Camada B
            if _step.mode == "direct":
                validate_direct_content(ps)
            else:
                min_lines = CONFIG.get("validation", {}).get("min_pseudocode_lines", 2)
                if len(ps.pseudocode.strip().splitlines()) < min_lines:
                    raise ValidationError_("B", f"{_step.id}: pseudocódigo trivial (< {min_lines} linhas)")

            return ps

        ps = with_retry(attempt_fn, state, agent_name=f"agent2_{step.id}", max_retries=3)
        pseudocode[step.id] = ps

    # Camada B: cobertura total
    validate_pseudocode_coverage(state.plan, pseudocode)

    state.pseudocode = pseudocode
    state.logs.append(log)
    print(f"  [OK] Pseudocódigo gerado para {len(pseudocode)} steps")
    return pseudocode
