"""
Agente 1 — Planejador (MOCK)
Retorna um plano JSON fixo para testar o pipeline.
Quando for real: substituir `call_model()` por chamada ao Ollama.
"""
from __future__ import annotations
import json
from orchestrator.state import PipelineState, Plan, AgentLog
from orchestrator.validators import (
    validate_json_parseable,
    validate_plan_schema,
    validate_plan_structure,
    ValidationError_,
)
from orchestrator.retries import with_retry

# Modelo que será usado quando implementar de verdade
MODEL = "qwen3:14b-q4_k_m"

# --- Mock: plano fixo que sempre retorna ---
MOCK_PLAN = {
    "steps": [
        {
            "id": "step_1",
            "description": "Criar modelo User com campos id, email, hashed_password",
            "file": "src/models/user.py",
            "location": "módulo raiz",
            "action": "create",
            "depends_on": []
        },
        {
            "id": "step_2",
            "description": "Implementar função create_access_token em auth.py",
            "file": "src/auth.py",
            "location": "função create_access_token",
            "action": "modify",
            "depends_on": ["step_1"]
        },
        {
            "id": "step_3",
            "description": "Adicionar endpoint POST /login que retorna JWT",
            "file": "src/api/users.py",
            "location": "função login_endpoint",
            "action": "modify",
            "depends_on": ["step_2"]
        }
    ]
}


def call_model(prompt: str, chunks: list[str], attempt: int, last_error) -> str:
    """
    MOCK: retorna JSON fixo.
    REAL: fazer POST para Ollama com o system prompt + prompt + chunks.
    """
    print(f"  [agent1] chamando modelo (mock)...")

    # Simula falha na primeira tentativa para testar retry (descomente para testar):
    # if attempt == 0:
    #     raise ValidationError_("A", "JSON inválido simulado")

    return json.dumps(MOCK_PLAN)


def run(state: PipelineState) -> Plan:
    """Executa o Agente 1 com retry."""
    state.set_status("planning")
    print(f"\n[Agente 1 — Planejador]")
    print(f"  prompt: {state.prompt[:80]}...")

    def attempt_fn(attempt: int, last_error):
        raw = call_model(state.prompt, state.retrieved_chunks, attempt, last_error)

        # Camada A
        data = validate_json_parseable(raw)
        plan = validate_plan_schema(data)

        # Camada B
        validate_plan_structure(plan)

        return plan

    log = AgentLog(agent="planner", model=MODEL)
    plan = with_retry(attempt_fn, state, agent_name="agent1", max_retries=3)

    state.plan = plan
    state.logs.append(log)
    print(f"  ✓ Plano gerado: {len(plan.steps)} passos")
    return plan
