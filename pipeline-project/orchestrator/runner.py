"""
Orquestrador principal.
Uso: python runner.py "adicione autenticação JWT no endpoint de usuários"
"""
from __future__ import annotations
import sys
import json
import os
from pathlib import Path
from datetime import datetime

# Garante que o root do projeto está no path
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.state import PipelineState
from orchestrator.validators import ValidationError_
from agents import planner, coder, implementer


RUNS_DIR = Path(__file__).parent.parent / "runs"


def save_run(state: PipelineState):
    """Salva estado final em runs/<id>/"""
    run_dir = RUNS_DIR / f"{datetime.now().strftime('%Y-%m-%d')}_{state.run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    with open(run_dir / "final_state.json", "w") as f:
        f.write(state.model_dump_json(indent=2))

    print(f"\n  [runner] estado salvo em {run_dir}/final_state.json")


def run_pipeline(prompt: str, codebase_path: str = ".") -> PipelineState:
    state = PipelineState(prompt=prompt, codebase_path=codebase_path)

    print(f"\n{'='*60}")
    print(f"Pipeline iniciado — run_id: {state.run_id}")
    print(f"Prompt: {prompt}")
    print(f"{'='*60}")

    try:
        # --- Pré-pipeline: retrieval (mock por enquanto) ---
        print("\n[Retrieval]")
        state.retrieved_chunks = [
            "# mock chunk 1: src/auth.py — função verify_token",
            "# mock chunk 2: src/api/users.py — endpoint GET /users",
        ]
        print(f"  [OK] {len(state.retrieved_chunks)} chunks recuperados (mock)")

        # --- Agente 1: Planejamento ---
        planner.run(state)

        # HITL opcional: descomente para pausar e esperar aprovação humana
        # _hitl_checkpoint(state)

        # --- Agente 2: Pseudocódigo ---
        coder.run(state)

        # --- Agente 3: Implementação ---
        implementer.run(state)

        # --- Validação final (mock) ---
        print("\n[Validação Final]")
        print("  [mock] linter: ok")
        print("  [mock] type-check: ok")
        print("  [mock] testes: ok")

        # --- Git commit (mock) ---
        print("\n[Git Commit]")
        print(f"  [mock] commit: 'feat: {prompt[:50]}'")

        state.set_status("done")

    except ValidationError_ as e:
        state.set_status("failed")
        state.add_error(str(e))
        print(f"\n  [FALHA] Pipeline falhou: {e}")

    except Exception as e:
        state.set_status("failed")
        state.add_error(f"Erro inesperado: {e}")
        print(f"\n  [FALHA] Erro inesperado: {e}")
        raise

    finally:
        save_run(state)
        _print_summary(state)

    return state


def _hitl_checkpoint(state: PipelineState):
    """Para e espera aprovação humana do plano."""
    print("\n[HITL] Plano gerado:")
    for step in state.plan.steps:
        print(f"  {step.id}: [{step.action}] {step.file} — {step.description}")
    resp = input("\nAprovar plano? (s/n): ").strip().lower()
    if resp != "s":
        raise ValidationError_("E", "Plano rejeitado pelo usuário")


def _print_summary(state: PipelineState):
    print(f"\n{'='*60}")
    print(f"Resumo - run_id: {state.run_id}")
    print(f"  Status:  {state.status}")
    print(f"  Steps:   {len(state.plan.steps) if state.plan else 0}")
    print(f"  Patches: {len(state.applied_patches)}")
    print(f"  Erros:   {len(state.errors)}")
    if state.errors:
        for e in state.errors:
            print(f"    [ERRO] {e}")
    retries = sum(state.retries.values())
    if retries:
        print(f"  Retries: {retries}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else "adicione autenticação JWT no endpoint de usuários"
    run_pipeline(prompt)
