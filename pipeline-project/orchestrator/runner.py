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

    with open(run_dir / "final_state.json", "w", encoding="utf-8") as f:
        f.write(state.model_dump_json(indent=2))

    print(f"\n  [runner] estado salvo em {run_dir}/final_state.json")

import re
import unicodedata

# Verbos/substantivos que indicam síntese/documentação (PT-BR + EN).
# Normalizados (sem acento, lower) para casar variações morfológicas.
_SYNTHESIS_TERMS = {
    "resum", "descrev", "descric", "documenta", "sintetiz", "sintese",
    "overview", "summary", "summariz", "explain", "describe",
    "html", "site", "card", "landing", "apresent", "exibir",
    "readme", "doc", "docs", "pagina", "page",
}


def _normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _detect_synthesis_mode(prompt: str) -> bool:
    """Heurística: prompt pede para descrever/sintetizar/documentar conteúdo do repo."""
    norm = _normalize(prompt)
    tokens = re.findall(r"\w+", norm)
    for tok in tokens:
        for term in _SYNTHESIS_TERMS:
            if tok.startswith(term):
                return True
    return False


BRAIN_DIRNAME = "brain"


def _safe_brain_filename(symbol: str) -> str:
    """Slug seguro derivado do nome do símbolo."""
    s = re.sub(r"[^a-zA-Z0-9_.-]+", "_", symbol).strip("_")
    return s or "symbol"


def _load_brain_index(codebase_path: str) -> str | None:
    """Lê o índice de brain/ (listagem de dossiês existentes) para alimentar o Planner."""
    brain = Path(codebase_path) / BRAIN_DIRNAME
    if not brain.exists():
        return None
    entries = []
    for md in sorted(brain.glob("*.md")):
        try:
            first_line = md.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        except Exception:
            first_line = ""
        entries.append(f"- {md.name}: {first_line[:120]}")
    if not entries:
        return None
    return "# BRAIN INDEX (dossiês de análise pré-existentes em brain/)\n" + "\n".join(entries)


def _format_srclight_section(title: str, raw: str | None) -> str:
    """Formata uma seção de markdown a partir de uma resposta JSON do srclight."""
    if not raw:
        return f"## {title}\n\n_(não disponível)_\n"
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return f"## {title}\n\n```\n{str(raw)[:2000]}\n```\n"
    # Heurística genérica: se for lista, vira bullets; se dict com 'results', usa results.
    items = data if isinstance(data, list) else data.get("results") or data.get("callers") \
        or data.get("callees") or data.get("symbols") or data.get("dependents") \
        or data.get("imports") or data.get("tests") or data.get("changes")
    if items is None:
        return f"## {title}\n\n```json\n{json.dumps(data, indent=2)[:2000]}\n```\n"
    if not items:
        return f"## {title}\n\n_(vazio)_\n"
    lines = [f"## {title}\n"]
    for it in items[:30]:
        if isinstance(it, dict):
            name = it.get("name") or it.get("symbol") or it.get("path") or "?"
            file = it.get("file") or ""
            line = it.get("line") or it.get("start_line") or ""
            extra = f"  — `{file}{':' + str(line) if line else ''}`" if file else ""
            lines.append(f"- **{name}**{extra}")
        else:
            lines.append(f"- {it}")
    if len(items) > 30:
        lines.append(f"- _(+{len(items) - 30} omitidos)_")
    return "\n".join(lines) + "\n"


def _execute_analyze_step(state: PipelineState, step, mcp_client, project_name: str | None) -> str:
    """
    Executa um step action=analyze: chama srclight para target_symbol, formata markdown,
    escreve em brain/. Retorna o path relativo.
    Não usa LLM — os dados são estruturados e determinísticos.
    """
    symbol = (step.target_symbol or "").strip()
    if not symbol:
        raise ValidationError_("C", f"{step.id}: target_symbol vazio")

    print(f"  [analyze] {step.id} -> símbolo '{symbol}'")

    # Bateria de chamadas ao srclight. Tolerante a falhas: ferramenta indisponível vira "_(não disponível)_".
    def _try(tool: str, args: dict) -> str | None:
        try:
            return mcp_client.call_tool(tool, args)
        except Exception as e:
            print(f"    [analyze] {tool} indisponível: {e}")
            return None

    args_with_project = lambda extra: {**extra, **({"project": project_name} if project_name else {})}

    raw_symbol = _try("get_symbol", {"name": symbol})
    raw_callers = _try("get_callers", args_with_project({"symbol": symbol}))
    raw_callees = _try("get_callees", args_with_project({"symbol": symbol}))
    raw_imports = _try("find_imports", args_with_project({"symbol": symbol}))
    raw_deps = _try("get_dependents", args_with_project({"symbol": symbol}))
    raw_blame = _try("blame_symbol", args_with_project({"symbol": symbol}))
    raw_tests = _try("get_tests_for", args_with_project({"symbol": symbol}))

    # Definição/conteúdo do símbolo (resumido).
    def_section = "## Definition\n\n_(símbolo não localizado pelo srclight)_\n"
    if raw_symbol:
        try:
            sd = json.loads(raw_symbol)
            sym = sd if "content" in sd else (sd.get("symbols") or [{}])[0]
            if sym.get("content"):
                file = sym.get("file", "?")
                start = sym.get("start_line", "?")
                end = sym.get("end_line", "?")
                sig = sym.get("signature", "")
                content = sym.get("content", "")
                def_section = (
                    f"## Definition\n\n"
                    f"- **File**: `{file}` (lines {start}–{end})\n"
                    f"- **Signature**: `{sig}`\n\n"
                    f"```\n{content[:3000]}\n```\n"
                )
        except Exception:
            pass

    md = [
        f"# Analysis: `{symbol}`\n",
        f"_Gerado em {datetime.now().isoformat(timespec='seconds')} pelo runner (action=analyze, sem LLM)._\n",
        f"_Step: `{step.id}` — {step.description}_\n",
        "---\n",
        def_section,
        _format_srclight_section("Callers (quem chama este símbolo)", raw_callers),
        _format_srclight_section("Callees (o que este símbolo chama)", raw_callees),
        _format_srclight_section("Imports (módulos importados)", raw_imports),
        _format_srclight_section("Dependents (módulos que dependem deste)", raw_deps),
        _format_srclight_section("Tests (cobertura conhecida)", raw_tests),
        _format_srclight_section("Blame / Recent Changes", raw_blame),
    ]
    md_content = "\n".join(md)

    # Grava em brain/
    out_path = Path(state.codebase_path) / step.file
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md_content, encoding="utf-8")
    rel = out_path.relative_to(Path(state.codebase_path)).as_posix()
    state.brain_artifacts[step.id] = rel
    print(f"  [analyze] {rel} escrito ({len(md_content)} chars)")
    return rel


def _collect_brain_context(state: PipelineState, step) -> list[str]:
    """
    Para um step não-analyze, coleta o conteúdo dos brain/ files referenciados
    transitivamente via depends_on. Retorna lista de chunks formatados.
    """
    if not state.plan:
        return []
    steps_by_id = {s.id: s for s in state.plan.steps}
    visited: set[str] = set()
    stack = list(step.depends_on)
    chunks = []
    while stack:
        sid = stack.pop()
        if sid in visited:
            continue
        visited.add(sid)
        dep = steps_by_id.get(sid)
        if not dep:
            continue
        stack.extend(dep.depends_on)
        if dep.action == "analyze":
            rel = state.brain_artifacts.get(dep.id)
            if rel:
                try:
                    content = (Path(state.codebase_path) / rel).read_text(encoding="utf-8")
                    chunks.append(f"# BRAIN ARTIFACT ({rel}) — from upstream analyze step {dep.id}\n{content}")
                except Exception:
                    pass
    return chunks


def _load_synthesis_chunks(state: PipelineState, mcp_client) -> list[str]:
    """
    Para tarefas de síntese, busca híbrida é ruim (prompt sem sinal semântico).
    Em vez disso, carrega: codebase_map, README, config.yaml, prompts/*.md,
    e todos os .py de agents/orchestrator/mcps inteiros (sem truncar).
    """
    chunks: list[str] = []
    codebase = Path(state.codebase_path).resolve()

    # 1) Codebase map via srclight (overview estrutural).
    try:
        raw_map = mcp_client.call_tool("codebase_map", {})
        if raw_map:
            chunks.append(f"# CODEBASE MAP\n{raw_map}")
    except Exception as e:
        print(f"  [retrieval-synth] codebase_map indisponível: {e}")

    # 2) Arquivos-chave de descrição do projeto.
    key_files = [
        "README.md", "config.yaml", "PLANO.md",
        "prompts/planner.system.md",
        "prompts/coder.system.md",
        "prompts/implementer.system.md",
    ]
    for rel in key_files:
        fp = codebase / rel
        if fp.exists() and fp.is_file():
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
                chunks.append(f"# FILE: {rel}\n{content}")
            except Exception:
                pass

    # 3) Fontes principais (sem truncar).
    for folder in ("orchestrator", "agents", "mcps"):
        folder_path = codebase / folder
        if not folder_path.exists():
            continue
        for py_file in sorted(folder_path.rglob("*.py")):
            if py_file.name == "__init__.py" and py_file.stat().st_size == 0:
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
                rel = py_file.relative_to(codebase).as_posix()
                chunks.append(f"# FILE: {rel}\n{content}")
            except Exception:
                pass

    return chunks

def run_pipeline(prompt: str, codebase_path: str = ".", stage: int = 3) -> PipelineState:
    if stage not in (1, 2, 3):
        raise ValueError("Estágio inválido. Escolha entre 1 (Planejamento), 2 (Pseudocódigo) ou 3 (Implementação).")

    state = PipelineState(prompt=prompt, codebase_path=codebase_path)
    state.synthesis_mode = _detect_synthesis_mode(prompt)
    run_date = datetime.now().strftime('%Y-%m-%d')
    state.run_dir = str(RUNS_DIR / f"{run_date}_{state.run_id}")
    if state.synthesis_mode:
        print("  [intent] modo SÍNTESE detectado (descrever/documentar/HTML).")

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
            if state.synthesis_mode:
                print("  [retrieval-synth] carregando codebase_map + arquivos-chave + fontes...")
                state.retrieved_chunks = _load_synthesis_chunks(state, client)
                print(f"  [OK] {len(state.retrieved_chunks)} chunks de síntese carregados.")
            else:
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

        # --- Brain index: alimenta Planner com dossiês de análise pré-existentes ---
        brain_idx = _load_brain_index(state.codebase_path)
        if brain_idx:
            state.retrieved_chunks.insert(0, brain_idx)
            print(f"  [brain] índice carregado ({brain_idx.count(chr(10))} entradas).")

        # --- Agente 1: Planejamento ---
        planner.run(state)
        if stage == 1:
            print("\n  [runner] Etapa 1 finalizada (Apenas Planejamento/Análise). Interrompendo fluxo.")
            state.set_status("done")
            return state

        # --- Execução dos steps action=analyze (sem LLM, dados do srclight) ---
        analyze_steps = [s for s in state.plan.steps if s.action == "analyze"]
        if analyze_steps:
            print(f"\n[Analyze] {len(analyze_steps)} step(s) de análise — chamando srclight...")
            project_name = Path(state.codebase_path).resolve().name
            analyze_client = MCPClient(server_cmd, cwd=str(codebase_abs))
            try:
                for s in analyze_steps:
                    _execute_analyze_step(state, s, analyze_client, project_name)
                    if state.run_dir:
                        log_dir = Path(state.run_dir) / "analyze"
                        log_dir.mkdir(parents=True, exist_ok=True)
                        (log_dir / f"{s.id}.txt").write_text(
                            f"symbol={s.target_symbol}\nfile={state.brain_artifacts.get(s.id, '?')}\n",
                            encoding="utf-8",
                        )
            finally:
                analyze_client.close()

        # HITL opcional: descomente para pausar e esperar aprovação humana
        # _hitl_checkpoint(state)

        # --- Agente 2: Pseudocódigo ---
        coder.run(state)
        if stage == 2:
            print("\n  [runner] Etapa 2 finalizada (Até Pseudocódigo). Interrompendo fluxo.")
            state.set_status("done")
            return state

        print("\n[Merge de Steps]")
        merge_same_file_steps(state)

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

def merge_same_file_steps(state: PipelineState) -> None:
    """
    Colapsa steps consecutivos que tocam o mesmo arquivo em um único step sintético.
    O step colapsado usa action='write' (write_file completo) em vez de patches incrementais.
    Modifica state.plan.steps e state.pseudocode in-place.
    """
    from orchestrator.state import PlanStep, PseudocodeStep

    original_steps = state.plan.steps
    merged_steps = []
    merged_pseudocode = dict(state.pseudocode)
    skip = set()

    for i, step in enumerate(original_steps):
        if step.id in skip:
            continue

        # Steps analyze são materializados pelo runner; não passam por merge.
        if step.action == "analyze":
            merged_steps.append(step)
            continue

        # Steps em modo direct não são fundidos — o Coder já produz o arquivo final inteiro.
        if step.mode == "direct":
            merged_steps.append(step)
            continue

        # Encontra steps consecutivos no mesmo arquivo (apenas modo patch).
        group = [step]
        for j in range(i + 1, len(original_steps)):
            next_step = original_steps[j]
            if next_step.mode == "direct":
                break
            if next_step.file == step.file:
                group.append(next_step)
                skip.add(next_step.id)
            else:
                break  # só agrupa consecutivos

        if len(group) == 1:
            merged_steps.append(step)
            continue

        # Cria step sintético
        merged_id = f"{group[0].id}_merged"
        merged_desc = "; ".join(s.description for s in group)
        merged_pseudo = "\n\n".join(
            f"# === {s.id}: {s.description} ===\n{state.pseudocode[s.id].pseudocode}"
            for s in group
            if s.id in state.pseudocode
        )

        synthetic_step = PlanStep(
            id=merged_id,
            description=merged_desc,
            file=step.file,
            location="arquivo completo",
            action="create",  # força write_file
            depends_on=group[0].depends_on
        )

        synthetic_pseudo = PseudocodeStep(
            step_id=merged_id,
            inputs=[],
            outputs=["file_content: str"],
            pseudocode=merged_pseudo,
            external_calls=[]
        )

        # Remove pseudocódigos individuais, adiciona o merged
        for s in group:
            merged_pseudocode.pop(s.id, None)
        merged_pseudocode[merged_id] = synthetic_pseudo

        merged_steps.append(synthetic_step)
        print(f"  [merge] {len(group)} steps colapsados em {merged_id} ({step.file})")

    state.plan.steps = merged_steps
    state.pseudocode = merged_pseudocode

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
