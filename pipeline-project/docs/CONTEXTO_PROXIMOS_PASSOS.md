# Contexto de Transição: Estado Atual e Próximos Passos

Documento de handoff para a próxima sessão de desenvolvimento. Reflete o estado real do código.

---

## 📌 Estado Atual

Todo o backbone do pipeline está implementado e funcionando:

1. **MCPs** (`mcps/`):
   - `readonly_server.py` — tool `read_file` via stdio JSON-RPC.
   - `write_server.py` — tools `write_file` e `apply_patch` (tolerante a hunks, com `git apply --check` antes de gravar).
   - `client.py` — cliente síncrono que gerencia o subprocesso MCP.

2. **Agentes** (`agents/`):
   - `planner.py` (Agente 1) — chama Ollama, monta árvore de arquivos, emite plano JSON com `action` + `mode` por step. Recebe índice de `brain/` no contexto para reaproveitar dossiês existentes.
   - `coder.py` (Agente 2) — ramifica por `step.mode`: gera pseudocódigo (patch) ou conteúdo final (direct). Pula `action=analyze`. Injeta dossiês de `brain/` (via depends_on transitivo) como contexto.
   - `implementer.py` (Agente 3) — ramifica por `step.mode`: chama LLM para tool call (patch) ou passthrough (direct). Pula `action=analyze` (já materializado).
   - **`action=analyze`** é executado pelo runner sem LLM (`_execute_analyze_step`): chama srclight (`get_callers`/`get_callees`/`find_imports`/`get_dependents`/`blame_symbol`/`get_tests_for`/`get_symbol`), formata markdown estruturado e grava em `brain/<slug>.md`. Tolerante a tools indisponíveis (seções viram `_(não disponível)_`).

3. **Orquestração** (`orchestrator/`):
   - `runner.py` — detecta intenção (`_detect_synthesis_mode`), faz retrieval (híbrido ou de síntese), executa os 3 agentes, suporta execução por estágios (1/2/3).
   - `state.py` — schemas Pydantic (`PlanStep.mode`, `PseudocodeStep.file_content`).
   - `validators.py` — camadas A (sintaxe), B (estrutura, incluindo `validate_direct_content`), C (paths físicos).
   - `retries.py` — wrapper `with_retry` reaproveitado pelos 3 agentes.

4. **Retrieval de síntese**: quando o prompt é classificado como descritivo/documental, o runner pula `hybrid_search` (sinal semântico fraco em prompts genéricos) e carrega `codebase_map` + README + config + PLANO + `prompts/*.md` + todos os `.py` de `agents/`, `orchestrator/`, `mcps/`.

4b. **Pasta `brain/` (memória persistente)**: dossiês de análise por símbolo, versionados no projeto. Carregada como índice no contexto do Planner em toda run. Downstream steps que dependem de um analyze step recebem o markdown como chunk extra (`_collect_brain_context`, percorre `depends_on` transitivamente).

5. **Tuning de VRAM (RTX 4070 12GB)**:
   - Contextos: planner 16K, coder 16K (patch) / 32K (synthesis), implementer 16K.
   - `qwen3-embedding-gpu` com `num_ctx=8192` (≈7.3 GB).
   - `unload_ollama_models` rotaciona modelos na GPU entre etapas.

---

## 🚧 Próximos Passos Candidatos

Em ordem aproximada de impacto:

### 1. Reusar MCPClient entre steps no Coder/Implementer
Hoje cada step instancia um novo subprocesso MCP read-only (ver `coder.py:97-109` e `implementer.py:137-144`). Para planos com muitos steps isso é caro. Sugestão: criar o cliente uma vez no `run()` do agente e propagar.

### 2. Cache de indexação Srclight
`runner.py` reindexa em **toda execução** (`subprocess.run(cmd_index, ...)`). Para repos grandes isso é segundos a minutos a cada run. Sugestão: comparar `git rev-parse HEAD` + `git status --porcelain` com um marcador salvo em `.srclight/last_indexed_state` e pular se nada mudou.

### 3. Modelo dedicado para `mode: "direct"`
Qwen2.5-coder q4 é bom em código mas gera CSS/HTML genérico. Avaliar `qwen2.5:14b-instruct` ou `llama3.1:8b-instruct` apenas no caminho synthesis. Requer um campo `models.coder_synthesis` no `config.yaml` e branch no `coder.py:call_model`.

### 4. Mais cobertura no detector de intenção
`_detect_synthesis_mode` cobre PT-BR + EN básico. Adicionar termos: `mostr`, `gerar`, `gere`, `dashboard`, `relatori`, `tabela`, `chart`. Considerar fallback para classificação via LLM curto (1 token).

### 5. Limpeza de repo
- `errors.txt` versionado parece ser de debug — mover para gitignore.
- `runs/` deveria estar no gitignore.
- Arquivo fantasma `{config.yaml,README.md}` no diretório raiz (artefato de mv que falhou).

### 5b. Evolução do brain/
- TTL/refresh: dossiê fica desatualizado quando o símbolo muda. Adicionar `git log -1 --format=%H <file>` no header e o Planner decide se reanalisa.
- Sumarização: para repos grandes, o índice pode ficar enorme. Considerar agregar `brain/INDEX.md` curado em vez de listar tudo.
- Cross-symbol queries: hoje cada dossiê é um símbolo. Faltam dossiês de fluxo ("como funciona a indexação de ponta a ponta").

### 6. HITL real
O checkpoint `_hitl_checkpoint` em `runner.py` está comentado. Vale expor via flag CLI (`--review-plan`) para uso quando o usuário quiser inspecionar antes do Coder.

### 7. Validação semântica do `direct` output
Hoje `validate_direct_content` só checa ≥50 chars. Para HTML, poderia validar com `html.parser` que o documento fecha tags principais. Para JSON, `json.loads`. Cheap insurance.

---

## 🛠️ Como rodar
```powershell
.venv\Scripts\Activate.ps1
python orchestrator\runner.py "<prompt>"            # estágio 3 (completo)
python orchestrator\runner.py "<prompt>" --stage 1  # só Planner
python orchestrator\runner.py "<prompt>" --stage 2  # até Coder
```
