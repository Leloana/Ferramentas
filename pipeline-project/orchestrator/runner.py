"""
Orquestrador principal.
Uso: python runner.py "adicione autenticação JWT no endpoint de usuários"
"""
from __future__ import annotations
import sys
import json
import os
import subprocess
import yaml
from pathlib import Path
from datetime import datetime

# Garante que o root do projeto está no path
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.state import PipelineState
from orchestrator.validators import ValidationError_
from agents import planner, coder, implementer
from mcps.client import MCPClient

# Carrega a configuração global
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)


RUNS_DIR = Path(__file__).parent.parent / "runs"


def save_run(state: PipelineState):
    """Salva estado final em runs/<id>/"""
    if not state.run_dir:
        return
    run_dir = Path(state.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    with open(run_dir / "final_state.json", "w") as f:
        f.write(state.model_dump_json(indent=2))

    print(f"\n  [runner] estado salvo em {run_dir}/final_state.json")


def run_pipeline(prompt: str, codebase_path: str = ".", stage: int = 3) -> PipelineState:
    if stage not in (1, 2, 3):
        raise ValueError("Estágio inválido. Escolha entre 1 (Planejamento), 2 (Pseudocódigo) ou 3 (Implementação).")

    state = PipelineState(prompt=prompt, codebase_path=codebase_path)
    run_date = datetime.now().strftime('%Y-%m-%d')
    state.run_dir = str(RUNS_DIR / f"{run_date}_{state.run_id}")

    print(f"\n{'='*60}")
    print(f"Pipeline iniciado — run_id: {state.run_id}")
    print(f"Prompt: {prompt} (Estágio Limite: {stage})")
    print(f"{'='*60}")

    try:
        # --- Pré-pipeline: retrieval real via busca híbrida srclight ---
        print("\n[Retrieval]")
        # Garante que outros modelos foram descarregados para liberar a GPU para o embedding
        from orchestrator.utils import unload_ollama_models
        unload_ollama_models(except_model=CONFIG["retrieval"]["embedding_model"])

        codebase_abs = Path(state.codebase_path).resolve()
        db_path = (codebase_abs / ".srclight" / "index.db").resolve()
        
        # Indexa/reindexa a base de código a cada execução para garantir que as alterações mais recentes sejam capturadas
        print(f"  [retrieval] Garantindo indexação atualizada da base de código em: {codebase_abs}...")
        
        cmd_index = [
            sys.executable,
            "-m", "srclight.cli",
            "index",
            "--db", str(db_path),
            "--embed", CONFIG["retrieval"]["embedding_model"],
            str(codebase_abs)
        ]
        print(f"  [index] Executando indexação: {' '.join(cmd_index)}")
        try:
            subprocess.run(cmd_index, capture_output=True, text=True, check=True)
            print("  [index] Base de código indexada/atualizada com sucesso!")
        except subprocess.CalledProcessError as e:
            raise ValidationError_("R", f"Falha ao indexar a base de código: {e.stderr or e.stdout}")
        
        # Inicializa cliente MCP srclight
        server_cmd = [
            sys.executable,
            "-m", "srclight.cli",
            "serve",
            "-t", "stdio",
            "--db", str(db_path)
        ]
        print("  [retrieval] Inicializando cliente MCP srclight...")
        client = MCPClient(server_cmd, cwd=str(codebase_abs))
        try:
            print(f"  [retrieval] Executando busca híbrida (top {CONFIG['retrieval']['top_k']}) para o prompt...")
            search_args = {
                "query": prompt,
                "limit": CONFIG["retrieval"]["top_k"]
            }
            raw_search = client.call_tool("hybrid_search", search_args)
            search_res = json.loads(raw_search)
            
            chunks = []
            results = search_res.get("results", [])
            for r in results:
                name = r.get("name")
                file_path = r.get("file")
                if not name:
                    continue
                
                # Busca os detalhes do símbolo para obter o código-fonte real
                raw_symbol = client.call_tool("get_symbol", {"name": name})
                if not raw_symbol:
                    continue
                symbol_data = json.loads(raw_symbol)
                
                # Trata múltiplas ocorrências do símbolo
                symbol = None
                if "symbols" in symbol_data:
                    r_file = Path(file_path).as_posix()
                    for s in symbol_data["symbols"]:
                        s_file = Path(s.get("file", "")).as_posix()
                        if s_file == r_file:
                            symbol = s
                            break
                    if not symbol and symbol_data["symbols"]:
                        symbol = symbol_data["symbols"][0]
                else:
                    symbol = symbol_data
                    
                if symbol and symbol.get("content"):
                    chunk = (
                        f"# Symbol: {symbol.get('name')} ({symbol.get('kind', 'unknown')})\n"
                        f"# File: {symbol.get('file')} (Lines {symbol.get('start_line')}-{symbol.get('end_line')})\n"
                        f"# Signature: {symbol.get('signature', '')}\n"
                        f"{symbol.get('content')}"
                    )
                    chunks.append(chunk)
                    
            state.retrieved_chunks = chunks
            print(f"  [OK] {len(state.retrieved_chunks)} chunks reais recuperados com sucesso via busca híbrida srclight!")
        finally:
            client.close()

        # --- Agente 1: Planejamento ---
        planner.run(state)
        if stage == 1:
            print("\n  [runner] Etapa 1 finalizada (Apenas Planejamento/Análise). Interrompendo fluxo.")
            state.set_status("done")
            return state

        # HITL opcional: descomente para pausar e esperar aprovação humana
        # _hitl_checkpoint(state)

        # --- Agente 2: Pseudocódigo ---
        coder.run(state)
        if stage == 2:
            print("\n  [runner] Etapa 2 finalizada (Até Pseudocódigo). Interrompendo fluxo.")
            state.set_status("done")
            return state

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
    import argparse

    parser = argparse.ArgumentParser(description="Orquestrador principal do pipeline.")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="adicione autenticação JWT no endpoint de usuários",
        help="O prompt/instrução para o pipeline"
    )
    parser.add_argument(
        "stage",
        nargs="?",
        type=int,
        choices=[1, 2, 3],
        default=None,
        help="Etapa limite (1: Planejamento, 2: Pseudocódigo, 3: Implementação)"
    )
    parser.add_argument(
        "--stage",
        "-s",
        dest="stage_flag",
        type=int,
        choices=[1, 2, 3],
        default=None,
        help="Etapa limite (sobrescreve posicional)"
    )

    args = parser.parse_args()

    prompt = args.prompt
    stage = 3  # Padrão

    # Caso 1: Usuário chamou `python runner.py 1` ou similar
    if prompt in ("1", "2", "3") and args.stage is None:
        stage = int(prompt)
        prompt = "adicione autenticação JWT no endpoint de usuários"
    else:
        if args.stage is not None:
            stage = args.stage

    # Caso 2: A flag explícita --stage ou -s foi passada
    if args.stage_flag is not None:
        stage = args.stage_flag

    run_pipeline(prompt, stage=stage)
