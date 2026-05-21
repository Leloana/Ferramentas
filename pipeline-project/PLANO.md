# Pipeline Multi-Agente Local — Plano de Implementação

> Setup caseiro de IAs generativas com pipeline fixo de 3 agentes (planejador → coder → implementador), executando 100% local com modelos pequenos (Qwen3, Gemma 3, etc.) e MCPs próprios.

---

## 1. Ferramentas a serem utilizadas

### Runtime de modelos
- **Ollama** — servidor local para os 3 modelos. Permite alternar modelos entre agentes. Suporta JSON Schema forçado via formato `json` ou GBNF.
- **llama.cpp / llama-server** (alternativa) — mais controle, melhor performance, suporta speculative decoding. Curva de aprendizado maior.
- **vLLM** — só se tiver GPU robusta e quiser throughput máximo. Provavelmente overkill para uso local.

### Orquestração
- **Python 3.11+** — linguagem do orquestrador (qualquer linguagem serve, Python tem o melhor ecossistema MCP).
- **Pydantic** — validação de schemas entre agentes. Não-negociável.
- **httpx** ou **openai-python** (apontando para Ollama) — cliente para chamadas aos modelos.
- **(Opcional) LangGraph** — se quiser modelar o pipeline como grafo de estados. Comece sem.

### MCPs (Model Context Protocol)
- **mcp Python SDK** (`mcp` no PyPI) — para escrever seus servidores MCP.
- MCPs próprios a construir:
  - `read_file`, `list_directory`, `search_codebase` (read-only, para Agentes 1 e 2)
  - `apply_patch` (diff-based, idempotente) (para Agente 3)
  - `write_file` (fallback quando patch não serve) (para Agente 3)
  - `run_tests`, `run_linter` (validação pós-aplicação)
  - `git_commit`, `git_diff` (versionamento)

### Embeddings e retrieval
- **nomic-embed-text** via Ollama — modelo de embedding default (768 dims, 8k contexto, leve).
- **tree-sitter** — parser universal para chunking AST-based de código.
- **ChromaDB** ou **sqlite-vec** — vector store local embarcado (sem servidor).
- **(Avançado) Qdrant** — vector store em Docker quando passar de ~50k chunks.
- **bge-reranker-base** — reranker leve, opcional para melhorar precision.

### Validação de saídas
- **JSON Schema** + gramática forçada (GBNF no llama.cpp/Ollama) — garante output estruturado.
- **ast** (Python stdlib), **tree-sitter** (outras linguagens) — parse de código gerado.
- **ruff** / **mypy** / **eslint** / **tsc --noEmit** — linters/type-checkers por linguagem.
- **pytest** ou test runner do projeto — gate final.

### Observabilidade
- **structlog** ou **loguru** — logging estruturado JSON.
- **sqlite** — armazenar logs de runs (queries fáceis: "quantas vezes Agente 3 falhou esse mês?").
- **(Opcional) Langfuse self-hosted** — UI para inspecionar runs. Overkill no início.

---

## 2. Arquitetura exemplificada

### Visão geral do fluxo

```
                    ┌─────────────────────┐
                    │   PROMPT HUMANO     │
                    └──────────┬──────────┘
                               │
                               ▼
              ┌────────────────────────────────┐
              │     ORQUESTRADOR (Python)      │
              │  - Carrega PipelineState       │
              │  - Roteia entre agentes        │
              │  - Aplica validações           │
              │  - Gerencia retries            │
              └────────────────┬───────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        ▼                      ▼                      ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│   AGENTE 1    │      │   AGENTE 2    │      │   AGENTE 3    │
│  Planejador   │ ───► │     Coder     │ ───► │ Implementador │
│  (reasoning)  │      │ (pseudocódigo)│      │  (tool-use)   │
└───────┬───────┘      └───────┬───────┘      └───────┬───────┘
        │                      │                      │
        ▼                      ▼                      ▼
   [Plano JSON]         [Pseudocódigo          [Tool calls MCP
   validado por          por step_id]           aplicados na
   schema +              validado por           codebase]
   HITL opcional]        cobertura
        │                      │                      │
        └──────────────────────┴──────────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  VALIDAÇÃO FINAL    │
                    │  - Linter           │
                    │  - Type-check       │
                    │  - Testes           │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   GIT COMMIT (MCP)  │
                    └─────────────────────┘
```

### Componentes laterais

```
┌─────────────────────────────────────────────────────────┐
│                  VECTOR STORE (ChromaDB)                │
│   - Chunks AST da codebase (função/classe)              │
│   - Atualizado incrementalmente por hash                │
│   - Consultado pelo Agente 1 (hybrid: dense + BM25)     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                  SERVIDORES MCP PRÓPRIOS                │
│   - read_only_mcp (read_file, list, search)             │
│   - write_mcp (apply_patch, write_file)                 │
│   - validation_mcp (run_tests, run_linter)              │
│   - git_mcp (commit, diff, revert)                      │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                  PIPELINE STATE                         │
│   {                                                     │
│     run_id, prompt, codebase_path,                      │
│     retrieved_chunks: [...],                            │
│     plan: {...} | None,                                 │
│     pseudocode: {...} | None,                           │
│     applied_patches: [...],                             │
│     errors: [...], retries: {...},                      │
│     status: "pending|planning|coding|applying|done|fail"│
│   }                                                     │
└─────────────────────────────────────────────────────────┘
```

### Estrutura de pastas sugerida

```
pipeline-project/
├── orchestrator/
│   ├── runner.py          # loop principal
│   ├── state.py           # PipelineState (Pydantic)
│   ├── validators.py      # camadas A-E de validação
│   └── retries.py         # política de retry
├── agents/
│   ├── planner.py         # Agente 1
│   ├── coder.py           # Agente 2
│   └── implementer.py     # Agente 3
├── prompts/
│   ├── planner.system.md
│   ├── planner.fewshot.md
│   ├── coder.system.md
│   └── implementer.system.md
├── mcps/
│   ├── readonly_server.py
│   ├── write_server.py
│   ├── validation_server.py
│   └── git_server.py
├── retrieval/
│   ├── chunker.py         # tree-sitter
│   ├── embedder.py        # nomic via Ollama
│   ├── store.py           # ChromaDB wrapper
│   └── search.py          # hybrid search
├── schemas/
│   ├── plan.schema.json
│   ├── pseudocode.schema.json
│   └── tool_call.schema.json
├── runs/                  # logs de cada execução
│   └── 2026-05-21_<id>/
│       ├── input.json
│       ├── agent1_output.json
│       ├── agent2_output.json
│       ├── agent3_calls.jsonl
│       └── final_state.json
├── config.yaml            # modelos, paths, thresholds
└── README.md
```

### Fluxo detalhado de uma run

1. Usuário invoca `pipeline run "adicione autenticação JWT no endpoint de usuários"`.
2. Orquestrador cria `PipelineState` com `run_id` único.
3. **Pre-pipeline**: hash-diff incremental atualiza vector store.
4. **Retrieval**: prompt é embedado, hybrid search retorna top-5 chunks. Salvos no state.
5. **Agente 1**: recebe prompt + chunks + file tree resumida. Produz plano JSON.
   - Validação A-C aplicada. Se falha, retry (máx 3).
   - HITL opcional: humano aprova/edita plano.
6. **Agente 2**: para cada step do plano, chamada separada produzindo pseudocódigo.
   - Validação de cobertura: todo `step_id` tem pseudocódigo.
7. **Agente 3**: para cada step (ordem topológica por `depends_on`):
   - Recebe **somente**: pseudocódigo do step + conteúdo atual do arquivo alvo + lista de MCPs disponíveis.
   - Faz tool call estruturado. Orquestrador valida whitelist + aplica.
   - Em falha de patch, retry com erro específico (máx 2).
8. **Validação final**: roda linter + type-check + testes via MCPs.
9. Se tudo passou: `git_commit` com mensagem gerada a partir do plano.
10. Estado final salvo em `runs/<id>/final_state.json`.

---

## 3. Agentes (descrição, prompt, modelos)

### Agente 1 — Planejador

**Descrição.** Recebe o prompt humano e contexto da codebase (chunks recuperados via embeddings + file tree). Decompõe a tarefa em passos atômicos, descritos com `id`, `descrição`, `arquivos_afetados`, `localização_específica`, `tipo_de_mudança`, `dependências`. É o agente onde mais vale gastar capacidade de reasoning.

**Modelo sugerido.**
- Primário: **Qwen3 14B** (Q4_K_M) com modo "thinking" ativado.
- Alternativa: **DeepSeek-R1-Distill-Qwen-14B** (Q4_K_M).
- Fallback (VRAM apertada): **Qwen3 8B** com prompting muito estruturado.
- Temperatura: 0.2-0.3.
- Contexto efetivo: até ~8k tokens.

**System prompt (esqueleto).**

```
Você é um planejador técnico. Sua função é decompor o pedido do usuário
em uma lista de passos atômicos e executáveis sobre uma codebase real.

REGRAS RÍGIDAS:
1. Cada passo modifica UM arquivo e tem UM objetivo claro.
2. Use APENAS arquivos que aparecem no contexto fornecido (chunks ou
   file tree). Se um arquivo necessário não aparece, declare-o com
   action="create" e justifique.
3. Cada passo deve ter localização específica: função, classe ou linha.
4. Marque dependências entre passos via "depends_on".
5. Responda APENAS em JSON conforme o schema. Sem prosa, sem markdown.

SCHEMA DE SAÍDA:
{
  "steps": [
    {
      "id": "step_1",
      "description": "uma frase curta, ação clara",
      "file": "caminho/relativo.py",
      "location": "função nome_da_função | classe NomeDaClasse | linha N",
      "action": "create" | "modify" | "delete",
      "depends_on": ["step_0"] ou []
    }
  ]
}

CONTEXTO DA CODEBASE:
{chunks_recuperados}

ÁRVORE DE ARQUIVOS RELEVANTES:
{file_tree}

EXEMPLOS:
{few_shot_examples}

PEDIDO DO USUÁRIO:
{user_prompt}
```

**Notas.**
- Force gramática JSON (Ollama format=json ou GBNF).
- Inclua 2-3 few-shot examples curtos. Para modelos 8-14B isso é o que mais melhora qualidade.
- Limite o número de chunks (top-5) para não estourar atenção.
- HITL pode entrar aqui: orquestrador pausa, mostra o plano, espera aprovação/edição.

---

### Agente 2 — Coder (pseudocódigo)

**Descrição.** Recebe o plano do Agente 1 e, **para cada step separadamente**, produz pseudocódigo de alto nível. Não escreve código real — descreve a lógica em pseudocódigo estruturado (entradas, saídas, controle de fluxo, chamadas de funções). Itera por step para não sobrecarregar o modelo pequeno.

**Modelo sugerido.**
- Primário: **Qwen2.5-Coder 7B** (Q4_K_M) ou **Qwen3-Coder 7B** se disponível.
- Alternativa: **DeepSeek-Coder-V2-Lite** (Q4_K_M).
- Temperatura: 0.3-0.4.
- Contexto efetivo: ~6k tokens.

**System prompt (esqueleto).**

```
Você é um engenheiro de software que produz pseudocódigo de alto nível.

REGRAS:
1. Você recebe UM passo do plano por vez.
2. Produza pseudocódigo claro, com nomes de variáveis significativos.
3. Declare explicitamente: INPUTS, OUTPUTS, fluxo de controle.
4. NÃO escreva código executável. Use sintaxe de pseudocódigo
   (FUNCTION, IF, FOR, RETURN, CALL).
5. Se o passo depende de saída de outro step, referencie pelo step_id.
6. Responda APENAS em JSON conforme o schema.

SCHEMA DE SAÍDA:
{
  "step_id": "step_1",
  "inputs": ["nome: tipo", ...],
  "outputs": ["nome: tipo", ...],
  "pseudocode": "linha 1\nlinha 2\n...",
  "external_calls": ["função_x", "biblioteca.metodo_y"]
}

CONTEXTO DO ARQUIVO ATUAL (se modify):
{file_content}

PASSO A IMPLEMENTAR:
{step_json}

PSEUDOCÓDIGO:
```

**Notas.**
- Uma chamada por step. Não tente fazer batch — modelos pequenos degradam.
- Forneça o conteúdo atual do arquivo alvo (lido via MCP) para o modelo "ver" o contexto.
- Validação posterior: todos os `step_id` do plano têm pseudocódigo correspondente.

---

### Agente 3 — Implementador

**Descrição.** Recebe **contexto minimizado**: apenas o pseudocódigo de UM step + conteúdo atual do arquivo + lista das MCPs disponíveis. Converte pseudocódigo em código real e chama MCPs para aplicar. É puramente mecânico — não planeja, não decide arquitetura. Modelo pequeno e rápido é ideal.

**Modelo sugerido.**
- Primário: **Qwen2.5-Coder 7B** (Q4_K_M) — mesmo do Agente 2 (compartilha VRAM).
- Alternativa leve: **Qwen2.5-Coder 3B** (Q4_K_M) — se quiser mais velocidade.
- Temperatura: 0.1 (determinismo na aplicação).
- Contexto efetivo: ~4k tokens (entrada bem enxuta).

**System prompt (esqueleto).**

```
Você é um implementador. Sua ÚNICA função é converter pseudocódigo
em código real e aplicar via tool calls.

REGRAS ABSOLUTAS:
1. Você SÓ pode modificar a codebase usando as ferramentas listadas
   abaixo. NÃO sugira comandos shell. NÃO descreva edições em prosa.
   NÃO use nenhuma outra ferramenta.
2. Se a operação necessária não tem ferramenta correspondente,
   responda com erro estruturado: {"error": "no_tool_for_<descrição>"}.
3. Use a linguagem do arquivo alvo (Python, TypeScript, etc).
4. Mantenha estilo e convenções visíveis no conteúdo atual do arquivo.
5. Modifique APENAS o que o pseudocódigo determina. Não refatore
   código adjacente.

FERRAMENTAS DISPONÍVEIS:
- apply_patch(file_path, unified_diff): aplica diff unificado.
- write_file(file_path, content): sobrescreve arquivo (use só para create).

ARQUIVO ALVO: {file_path}
CONTEÚDO ATUAL:
{file_content}

PSEUDOCÓDIGO A IMPLEMENTAR:
{pseudocode}

LOCALIZAÇÃO: {location}

Execute a tool call apropriada agora.
```

**Notas críticas.**
- **NÃO passe lista completa de MCPs** — só as 2-3 que esse agente precisa. Menos opções, menos confusão.
- Use **tool calling nativo do modelo** (Qwen tem bom suporte), nunca tool calling baseado em prompt.
- O orquestrador valida a tool call contra whitelist ANTES de executar.
- Se o modelo responder em prosa em vez de tool call, é falha — retry com prompt mais firme, depois desiste.

---

### Resumo comparativo dos agentes

| Aspecto | Agente 1 (Planejador) | Agente 2 (Coder) | Agente 3 (Implementador) |
|---------|----------------------|------------------|--------------------------|
| Modelo | Qwen3 14B (reasoning) | Qwen2.5-Coder 7B | Qwen2.5-Coder 7B/3B |
| Temperatura | 0.2-0.3 | 0.3-0.4 | 0.1 |
| Contexto típico | 6-8k tokens | 3-6k tokens | 2-4k tokens |
| Chamadas por run | 1 (com retries) | N (1 por step) | N (1 por step) |
| Saída | JSON (plano) | JSON (pseudocódigo) | Tool call MCP |
| HITL | Sim (recomendado) | Opcional | Não (mecânico) |
| Tem acesso a MCPs? | Read-only | Read-only | Write (whitelisted) |

---

## 4. Como capturar falhas no fluxo

### Taxonomia de falhas

Em ordem de fácil → difícil de detectar:

1. **Falha de execução** — timeout, crash, sem resposta.
2. **Falha de formato** — JSON inválido, schema errado, tool call malformada.
3. **Falha de contrato** — formato certo, regras violadas (passos vazios, tool fora da whitelist).
4. **Falha semântica leve** — output coerente mas incompleto ou inconsistente.
5. **Falha semântica profunda** — código compila e roda mas faz a coisa errada.

Pipelines amadores detectam 1 e 2. Pipelines de produção detectam 1-4 e aceitam vazamento de 5 com testes/HITL como rede de segurança.

### Validação em camadas (defense in depth)

Cada saída de agente passa por uma sequência de checks, do mais barato ao mais caro. **Se uma camada falha, não passa para a próxima — retry ou abort.**

**Camada A — Sintática (instantâneo)**
- Output é JSON parseável?
- Schema (Pydantic / JSON Schema) valida?
- Tipos corretos em cada campo?

**Camada B — Estrutural (microssegundos)**
- Tamanhos razoáveis: `1 ≤ len(steps) ≤ 30`, descrições não-vazias.
- Referências internas consistentes (`depends_on` aponta para passos reais).
- Sem ciclos no grafo de dependências.
- Sem duplicatas de `step_id`.

**Camada C — Contextual (milissegundos)**
- Arquivos referenciados existem na codebase (`os.path.exists`), exceto se `action: create`.
- Tools chamadas estão na whitelist registrada.
- Funções/classes mencionadas em `location` existem no arquivo (via AST).
- Para Agente 3: o diff aplica limpo (`git apply --check`).

**Camada D — Executável (segundos)**
- Código gera AST válida (`ast.parse` / `tree-sitter`).
- Linter passa (`ruff`, `eslint`).
- Type-check passa (`mypy`, `tsc --noEmit`).
- Testes da codebase passam (se existirem).

**Camada E — Semântica (LLM-as-judge ou humano)**
- LLM-judge com rubrica binária ("pseudocódigo cobre todos os passos? sim/não").
- Diff review humano antes de merge.
- Reservada para casos críticos ou confiança baixa.

### Detecção de falhas por agente

#### Agente 1 — Planejador

| Falha | Como detectar | Camada |
|-------|---------------|--------|
| JSON inválido | JSON Schema validator | A |
| Lista vazia ou >30 passos | Regra de tamanho | B |
| Passos não-atômicos | Heurística: descrição > N palavras, ou contém "e também" / "depois" / "além disso" | B |
| `depends_on` quebrado | Verificação de grafo | B |
| Arquivo inventado | `os.path.exists` (exceto `create`) | C |
| Ciclo em dependências | DFS no grafo | B |
| Plano sistematicamente ruim | Sintoma indireto: Agente 3 falha muito → logar e revisar prompts | E |

#### Agente 2 — Coder

| Falha | Como detectar | Camada |
|-------|---------------|--------|
| Cobertura incompleta | Para cada `step_id` do plano, deve existir pseudocódigo | B |
| Pseudocódigo trivial | Heurística: < N linhas, ou só comentários, ou repete descrição do passo | B |
| Símbolos não-declarados | `external_calls` referencia coisas que não existem nos imports do arquivo (AST) | C |
| APIs alucinadas | Difícil de pegar aqui; deixar Agente 3 falhar e fazer feedback loop | D |

#### Agente 3 — Implementador

| Falha | Como detectar | Camada |
|-------|---------------|--------|
| Nenhuma tool call (respondeu em prosa) | Verificar se mensagem tem `tool_calls` estruturadas | A |
| Tool fora da whitelist | Lista de nomes permitidos | C |
| Argumentos inválidos | Schema da tool | A |
| Código não-parseável | `ast.parse` no resultado | D |
| Patch não aplica | `git apply --check` | C |
| Linter/type-check falha | `ruff` / `mypy` / `eslint` | D |
| Modificou função/arquivo errado | Comparar diff resultante com `file` e `location` do plano | C |
| Mudança fora do escopo | AST diff: nodes alterados ⊆ nodes mencionados no plano | C |
| Testes quebram | `pytest` ou runner do projeto via MCP | D |

### Sinais comportamentais (modelo "se denunciando")

Modelos pequenos têm padrões reconhecíveis de falha:

- **Repetição** — mesma linha/bloco repetido. Detecte com hash de janelas deslizantes ou n-gram repetition score.
- **Truncamento** — `finish_reason == "length"` quase sempre indica falha. Frase termina no meio.
- **Recusa/hedge** — frases como "Eu não tenho certeza...", "Como modelo de linguagem...", "Talvez você queira...". Lista de gatilhos → falha automática em pipeline de execução.
- **Tool inventada** — sinal mais comum de Agente 3 perdido. Whitelist resolve.
- **Latência anormal** — inferência levou 10x o normal. Métrica de logging.
- **Output idêntico à entrada** — modelo só ecoou. Falha.
- **Output muito mais curto que esperado** — truncou ou desistiu.
- **Output muito maior que esperado** — provavelmente em loop.

### Política de retry

| Tipo de falha | Estratégia | Máx tentativas |
|---------------|-----------|----------------|
| Camada A (sintática) | Retry com erro específico do validador | 3 |
| Camada B (estrutural) | Retry com mensagem do que violou | 3 |
| Camada C (contextual) | Retry com contexto adicional (ex: lista de arquivos reais, lista de tools válidas) | 2 |
| Camada D (executável) | Retry com erro do compilador/linter colado no prompt | 2 |
| Camada E (semântica) | NÃO retry automático. Escalona para humano ou marca run como falho | 0 |

**Critério de desistência:** se um único step falhou todas as tentativas, **pare o pipeline inteiro**. Não pule steps — vai gerar inconsistência. Salve estado, deixe humano olhar.

### LLM-as-judge: cuidados

- **Nunca** use o mesmo modelo que produziu a saída para julgá-la.
- Juiz pequeno = juiz fraco. Use o maior modelo disponível como juiz.
- Use **rubricas binárias**, não avaliações abertas: "o código modifica apenas a função `foo`? sim/não".
- Trate como sanity check, não como verdade absoluta.

### Logging estruturado (essencial desde o dia 1)

Por chamada de agente, logar:

```json
{
  "run_id": "...",
  "timestamp": "...",
  "agent": "planner|coder|implementer",
  "model": "qwen3:14b-q4_k_m",
  "tokens_in": 2341,
  "tokens_out": 892,
  "latency_ms": 4123,
  "finish_reason": "stop|length|error",
  "validation_layer_failed": null,
  "retry_count": 0,
  "output_hash": "sha256:..."
}
```

Por run completa, logar:

```json
{
  "run_id": "...",
  "user_prompt": "...",
  "total_duration_ms": 87234,
  "status": "success|partial|failed",
  "agent1_retries": 0,
  "agent2_retries": 1,
  "agent3_retries": 4,
  "failed_step_id": "step_5",
  "files_changed": ["src/auth.py", "src/api/users.py"],
  "final_validation": "passed|failed"
}
```

Armazene em SQLite. Depois de 20-30 runs você detecta padrões: "Agente 3 inventa tool em 15% dos casos quando plano tem >10 passos" → ajusta o limite no Agente 1.

### Gates de segurança (camadas externas ao pipeline)

- **Diff em staging**: aplicações do Agente 3 NÃO vão direto para arquivos finais. Vão para uma branch ou stash, e o orquestrador valida tudo antes de promover.
- **Commits granulares**: cada step do Agente 3 = um commit. Revert fácil se algo passar.
- **Não auto-merge para main** nos primeiros tempos. Sempre revisão humana antes do merge.
- **Testes como gate final obrigatório**: se quebrou teste, `git revert` automático e marca run como falho.

### Resumo operacional

Ordem de implementação dos checks:

1. **JSON Schema + gramática forçada** — resolve 80% das falhas óbvias.
2. **Whitelist de tools + rejeição automática** — fecha o Agente 3.
3. **Parser/linter na saída do Agente 3** — pega código quebrado.
4. **Logging estruturado de tudo** — sem isso, você está cego.
5. **Retry com erro específico no prompt** — modelos coder respondem bem a feedback de compilador.
6. **LLM-judge ou humano** — para casos suspeitos.
7. **Testes da codebase como gate final** — última linha de defesa.

Sem os passos 1-4 você não está rodando pipeline. Está rezando.

---

## Apêndice: ordem prática de implementação

Quando for implementar de verdade (não agora):

1. Orquestrador "burro" com mocks dos 3 agentes — pipeline ponta-a-ponta sem inteligência.
2. Um MCP simples: `read_file`.
3. Agente 1 real com modelo pequeno + JSON Schema + few-shots.
4. Agente 2 real, uma chamada por step.
5. Agente 3 real + MCP `apply_patch` + `write_file`.
6. Camadas de validação A-C.
7. Retrieval básico: tree-sitter + nomic + ChromaDB.
8. Camada D: linter + type-check via MCP.
9. Retry estruturado com feedback de erro.
10. Logging estruturado em SQLite.
11. HITL após Agente 1.
12. Testes como gate final.
13. Hybrid search (BM25 + dense).
14. LLM-judge opcional para casos críticos.

Construir end-to-end com pouca qualidade primeiro é melhor que perfeccionar o Agente 1 e nunca chegar no Agente 3.
