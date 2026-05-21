"""
Agente 2 — Coder (MOCK)
Para cada step do plano, retorna pseudocódigo JSON fixo.
Quando for real: substituir `call_model()` por chamada ao Ollama.
"""
from __future__ import annotations
import json
from orchestrator.state import PipelineState, Plan, PseudocodeStep, AgentLog
from orchestrator.validators import (
    validate_json_parseable,
    validate_pseudocode_schema,
    validate_pseudocode_coverage,
    ValidationError_,
)
from orchestrator.retries import with_retry

MODEL = "qwen2.5-coder:7b-q4_k_m"


def mock_pseudocode_for(step_id: str, description: str) -> dict:
    """Gera pseudocódigo mock baseado no step."""
    return {
        "step_id": step_id,
        "inputs": ["context: dict"],
        "outputs": ["result: bool"],
        "pseudocode": (
            f"FUNCTION execute_{step_id}(context):\n"
            f"  # {description}\n"
            f"  SET result = CALL do_work(context)\n"
            f"  IF result IS None:\n"
            f"    RETURN False\n"
            f"  RETURN True"
        ),
        "external_calls": []
    }


def call_model(step_id: str, description: str, file_content: str, attempt: int, last_error) -> str:
    """
    MOCK: retorna pseudocódigo fixo.
    REAL: POST para Ollama com system prompt do Agente 2 + step JSON + file_content.
    """
    print(f"  [agent2] gerando pseudocódigo para {step_id} (mock)...")
    return json.dumps(mock_pseudocode_for(step_id, description))


def run(state: PipelineState) -> dict[str, PseudocodeStep]:
    """Executa o Agente 2: uma chamada por step."""
    print(f"\n[Agente 2 — Coder]")
    assert state.plan is not None, "Agente 2 precisa do plano do Agente 1"

    pseudocode: dict[str, PseudocodeStep] = {}
    log = AgentLog(agent="coder", model=MODEL)

    for step in state.plan.steps:
        print(f"  → processando {step.id}: {step.description[:50]}")

        def attempt_fn(attempt: int, last_error, _step=step):
            # Aqui você leria o arquivo real via MCP read_file
            file_content = f"# conteúdo mock de {_step.file}"

            raw = call_model(_step.id, _step.description, file_content, attempt, last_error)

            # Camada A
            data = validate_json_parseable(raw)
            ps = validate_pseudocode_schema(data)

            # Camada B: pseudocódigo não pode ser trivial
            if len(ps.pseudocode.strip().splitlines()) < 2:
                raise ValidationError_("B", f"{_step.id}: pseudocódigo trivial (< 2 linhas)")

            return ps

        ps = with_retry(attempt_fn, state, agent_name=f"agent2_{step.id}", max_retries=3)
        pseudocode[step.id] = ps

    # Camada B: cobertura total
    validate_pseudocode_coverage(state.plan, pseudocode)

    state.pseudocode = pseudocode
    state.logs.append(log)
    print(f"  ✓ Pseudocódigo gerado para {len(pseudocode)} steps")
    return pseudocode
