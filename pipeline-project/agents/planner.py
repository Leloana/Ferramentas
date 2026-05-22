from __future__ import annotations
import json
import os
import requests
import yaml
from pathlib import Path
from orchestrator.state import PipelineState, Plan, AgentLog
from orchestrator.validators import (
    validate_json_parseable,
    validate_plan_schema,
    validate_plan_structure,
    validate_physical_paths,
    ValidationError_,
)
from orchestrator.retries import with_retry

# Carrega a configuração global
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

OLLAMA_URL = f"{CONFIG['ollama']['base_url']}/api/chat"
MODEL = CONFIG['models']['planner']


def get_file_tree(root_dir: str) -> str:
    """Gera uma árvore de diretórios textual excluindo pastas irrelevantes."""
    lines = []
    root_path = Path(root_dir).resolve()
    
    # Ignora pastas de cache, dependências e relatórios temporários
    exclude_dirs = {".git", "__pycache__", ".venv", "runs", ".idea", ".vscode", "docx_to_pdf_converter", "karaoke", "youtube_music_playlist_organizer"}
    
    for root, dirs, files in os.walk(root_path):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        try:
            rel_path = Path(root).relative_to(root_path)
        except ValueError:
            continue
            
        level = len(rel_path.parts)
        indent = "  " * level
        
        if rel_path != Path("."):
            lines.append(f"{indent}📁 {rel_path.name}/")
        
        sub_indent = "  " * (level + 1)
        for f in files:
            # Ignora arquivos de sistema e de cache
            if f.endswith((".pyc", ".pyo", ".pyd")) or f in {".gitignore", "LICENSE"}:
                continue
            lines.append(f"{sub_indent}📄 {f}")
            
    return "\n".join(lines)


def call_model(prompt: str, chunks: list[str], file_tree: str, attempt: int = 0, last_error=None) -> str:
    """
    Faz requisição POST para o Ollama local usando o system prompt e os dados da run.
    """
    print(f"  [agent1] enviando requisição para o modelo {MODEL} no Ollama...")

    # Carrega o system prompt correspondente
    system_prompt_path = Path(__file__).parent.parent / "prompts" / "planner.system.md"
    with open(system_prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    # Monta a mensagem do usuário
    user_content = (
        f"SOLICITAÇÃO DO USUÁRIO:\n{prompt}\n\n"
        f"TRECHOS DE CÓDIGO RECUPERADOS (RETRIEVAL):\n"
    )

    if last_error:
        user_content += (
            f"\n\nPREVIOUS ATTEMPT FAILED. Your last response was rejected.\n"
            f"Error: {last_error.message}\n"
            f"You MUST return ONLY a JSON object with a 'steps' array. "
            f"No other keys. No prose. Example: {{\"steps\": [{{\"id\": \"step_1\", ...}}]}}"
        )

    if chunks:
        for i, chunk in enumerate(chunks, 1):
            user_content += f"\n--- Chunk {i} ---\n{chunk}\n"
    else:
        user_content += "Nenhum trecho de código recuperado.\n"
        
    user_content += f"\nESTRUTURA DE ARQUIVOS DA BASE DE CÓDIGO:\n{file_tree}\n"



    # Garante que outros modelos foram descarregados para liberar a GPU
    from orchestrator.utils import unload_ollama_models
    unload_ollama_models(except_model=MODEL)

    num_ctx = CONFIG.get("ollama", {}).get("planner_num_ctx", 8192)

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
        raise ValidationError_("A", f"Falha na chamada ao Ollama: {e}")


def run(state: PipelineState) -> Plan:
    """Executa o Agente 1 com retry."""
    state.set_status("planning")
    print(f"\n[Agente 1 — Planejador]")
    print(f"  prompt: {state.prompt[:80]}...")

    def attempt_fn(attempt: int, last_error):
        # Gera o file tree com base no codebase_path
        file_tree = get_file_tree(state.codebase_path)
        
        raw = call_model(state.prompt, state.retrieved_chunks, file_tree, attempt, last_error)

        # Salva o log bruto da saída
        if state.run_dir:
            planner_log_dir = Path(state.run_dir) / "planner"
            planner_log_dir.mkdir(parents=True, exist_ok=True)
            with open(planner_log_dir / f"attempt_{attempt + 1}.json", "w", encoding="utf-8") as f:
                f.write(raw)

        # Camada A
        data = validate_json_parseable(raw)
        plan = validate_plan_schema(data)

        # Camada B
        validate_plan_structure(plan)

        # Camada C: Validação física
        validate_physical_paths(plan, state.codebase_path)

        return plan

    log = AgentLog(agent="planner", model=MODEL)
    plan = with_retry(attempt_fn, state, agent_name="agent1", max_retries=3)

    state.plan = plan
    state.logs.append(log)
    print(f"  [OK] Plano gerado: {len(plan.steps)} passos")
    return plan
