# Pipeline de Agentes Automatizados com MCP, Ollama e Srclight

Este projeto implementa um pipeline de desenvolvimento de software automatizado composto por 3 agentes inteligentes (Planejador, Coder e Implementador) que cooperam de forma isolada para planejar, estruturar e aplicar modificações de código diretamente no repositório local. Ele utiliza a especificação do **Model Context Protocol (MCP)** para operações de busca híbrida, leitura e escrita e se integra com LLMs locais via **Ollama**.

---

## 🎯 O que o projeto faz

O pipeline recebe uma solicitação de desenvolvimento em linguagem natural (prompt) e a executa em duas trilhas dependendo da intenção detectada:

### Detecção de intenção
Antes do retrieval, o runner classifica o prompt em **`code-edit`** (default) ou **`synthesis`** (descrever / documentar / gerar HTML / cards / overview / README / etc.). A detecção é morfológica (normaliza acentos via NFKD e usa prefix-match em termos como `resum`, `descrev`, `documenta`, `sintetiz`, `html`, `site`, `card`, `landing`, `overview`, ...). O modo escolhido fica em `state.synthesis_mode` e altera o retrieval.

### Fases

1. **Retrieval**:
   - **Modo `code-edit`**: indexa a base via `srclight` e faz **busca híbrida** (FTS5 + vetorial) com `top_k` símbolos via `hybrid_search`, extraindo o código-fonte de cada um via `get_symbol`. Bom quando o prompt tem sinal semântico (nome de função, conceito técnico).
   - **Modo `synthesis`**: pula a busca híbrida (sinal fraco para prompts genéricos como "resuma o repo") e carrega diretamente: `codebase_map()` do srclight + `README.md` + `config.yaml` + `PLANO.md` + `prompts/*.md` + **todos os `.py` de `orchestrator/`, `agents/`, `mcps/` sem truncar**. É o que o Planner/Coder precisam para falar com precisão sobre o projeto.

2. **Planejador (Agente 1)**: Analisa a árvore de arquivos e os chunks recuperados para gerar um plano JSON. Cada step inclui um campo **`mode`** (`patch` ou `direct` — ver abaixo). A **Camada C** previne path traversal e impede `modify`/`delete` em arquivos inexistentes.

3. **Coder (Agente 2)**: Comportamento depende do `mode` do step:
   - **`mode: "patch"`** (default — edições de código): lê o arquivo alvo via MCP read-only e gera **pseudocódigo JSON** estruturado, que o Implementer traduzirá em diff/escrita.
   - **`mode: "direct"`** (síntese de artefato fechado — HTML, CSS, JS, MD, JSON): **produz o conteúdo final do arquivo inteiro** no campo `file_content`. Usa `coder_num_ctx_synthesis` (32K) para caber a saída.

4. **Implementador (Agente 3)**: Também depende do `mode`:
   - **`mode: "patch"`**: chama o LLM para emitir `write_file` ou `apply_patch` a partir do pseudocódigo.
   - **`mode: "direct"`**: **passthrough puro, sem LLM** — embrulha `ps.file_content` num `write_file` e envia ao MCP de escrita. Elimina o "telefone sem fio" entre dois LLMs locais quantizados que destrói animações, CSS e JS em tarefas criativas.

5. **Validação Git (MCP Write)**: O servidor de escrita aplica patches de forma tolerante a hunks, gera o diff em memória e roda `git apply --check` antes de gravar no disco.

6. **Logging**: `runs/<data>_<id>/` guarda `final_state.json` + saídas brutas por agente (`planner/`, `coder/`, `implementer/`).

### Quando o Planner escolhe `direct` vs `patch`?
Regra no system prompt: **`direct` para `create` de artefato auto-contido** (HTML page, doc MD, JSON config, CSS/JS standalone); **`patch` para edições incrementais** (modificar função, adicionar rota, corrigir bug). Em caso de dúvida em `create`, preferir `direct`.

---

## 🔒 Isolamento de Contexto (Limitação de Escopo)

Para garantir precisão máxima e reduzir custos com a janela de contexto da GPU, **não há compartilhamento de histórico de chat ou conversação entre os agentes**:
* Cada chamada ao Ollama é iniciada com uma nova lista de mensagens (system prompt + prompt do usuário formatado com JSON).
* O **Coder** e o **Implementador** rodam em loops isolados por passo. Eles nunca veem o prompt original do usuário, nem os diálogos dos outros passos ou agentes. Eles operam estritamente no escopo das propriedades do passo que estão processando no momento, reduzindo a chance de alucinações.

---

## ⚡ Otimização de GPU (referência: RTX 4070 12GB)

Os contextos foram dimensionados para caber em **12 GB de VRAM** mantendo execução 100% na GPU. KV cache do Qwen2.5-7B (GQA, q4 com KV fp16) gira em ~115 KB/token, então:
- 7B-q4 weights ≈ 4.5 GB
- 16K ctx ≈ 1.9 GB de KV → total ~6.5 GB (folga grande)
- 32K ctx ≈ 3.8 GB de KV → total ~8.5 GB (cabe com margem)

### 1. Modelo de embedding personalizado
O `qwen3-embedding:8b` default aloca 40.960 tokens (~15 GB de VRAM). Criamos `qwen3-embedding-gpu` com **8192** tokens (≈7.3 GB):
```dockerfile
FROM qwen3-embedding:8b
PARAMETER num_ctx 8192
```
```bash
ollama create qwen3-embedding-gpu -f Modelfile
```

### 2. Contextos no `config.yaml`
- `planner_num_ctx: 16384`
- `coder_num_ctx: 16384` (modo `patch`)
- `coder_num_ctx_synthesis: 32768` (modo `direct` — precisa caber o arquivo inteiro na saída)
- `implementer_num_ctx: 16384`

### 3. Descarregamento ativo
O utilitário `unload_ollama_models(except_model=...)` em `orchestrator/utils.py` é chamado antes de cada etapa (Retrieval, Planner, Coder, Implementer) garantindo que **apenas um modelo resida na VRAM por vez**. Isso permite alternar embedding ↔ LLM sem swap pra CPU.

---

## ⚙️ Como configurar e trocar os modelos

Toda a configuração global do projeto está no arquivo `config.yaml` na raiz do projeto.

### `config.yaml` atual
```yaml
models:
  planner: "qwen2.5-coder:7b-instruct-q4_K_M"
  coder: "qwen2.5-coder:7b-instruct-q4_K_M"
  implementer: "qwen2.5-coder:7b-instruct-q4_K_M"

ollama:
  base_url: "http://localhost:11434"
  planner_num_ctx: 16384
  coder_num_ctx: 16384
  coder_num_ctx_synthesis: 32768   # usado em steps mode=direct (saída do arquivo inteiro)
  implementer_num_ctx: 16384
  request_timeout: 300             # síntese gera respostas grandes; 90s era apertado

retrieval:
  top_k: 5
  embedding_model: "ollama:qwen3-embedding-gpu"

paths:
  runs_dir: "runs/"
  codebase: "."

validation:
  max_plan_steps: 30
  min_pseudocode_lines: 2

tool_whitelist:
  - apply_patch
  - write_file
```

**Dicas de tuning** (modelo / VRAM):
- Para tarefas de síntese visualmente ricas (HTML/CSS com animações), considere usar um modelo não-coder no `coder` (ex.: `qwen2.5:14b-instruct` ou `llama3.1:8b-instruct`) — modelos coder-tuned q4 tendem a gerar CSS genérico.
- Se subir o modelo para 14B, reduza `coder_num_ctx_synthesis` para `16384` ou `24576` pra caber na VRAM.

---

## 🛠️ Como adicionar ferramentas (Tools)

As ferramentas expostas aos agentes residem nos servidores MCP em `mcps/`.

### 1. Adicionar uma ferramenta no servidor MCP correspondente
Abra o arquivo do servidor (ex: [write_server.py](file:///C:/Users/mf827/Documents/Ferramentas/pipeline-project/mcps/write_server.py) para ferramentas de escrita, ou [readonly_server.py](file:///C:/Users/mf827/Documents/Ferramentas/pipeline-project/mcps/readonly_server.py) para leitura).

1. Implemente a função em Python que realiza a ação.
2. Adicione a especificação da ferramenta na lista dentro do método `tools/list` da comunicação JSON-RPC:
   ```json
   {
     "name": "nome_da_sua_tool",
     "description": "Explicação detalhada da finalidade da ferramenta.",
     "inputSchema": {
       "type": "object",
       "properties": {
         "argumento1": { "type": "string", "description": "Descrição do argumento" }
       },
       "required": ["argumento1"]
     }
   }
   ```
3. No manipulador do método `tools/call`, chame a sua função passando os argumentos recebidos e estruture o retorno da chamada JSON-RPC.

### 2. Liberar na Whitelist do Agente 3 (Implementador)
Após adicionar uma ferramenta de escrita, adicione o nome dela na lista `tool_whitelist` do `config.yaml` para que ela seja validada na Camada B de segurança do Implementador.

### Tools disponíveis hoje

**ReadOnly server** (`mcps/readonly_server.py`):
| Tool | Função |
|---|---|
| `read_file` | conteúdo completo de 1 arquivo |
| `read_many_files` | batch read; retorna `{path: {ok, content\|error}}` |
| `list_directory` | listagem com `recursive`, `max_depth`, `glob`, skip de `.git`/`.venv`/`.srclight`/`runs` |
| `search_text` | grep regex recursivo com filtro de `glob` |
| `file_exists` | `{exists, kind}` |
| `file_stat` | tamanho, mtime, line_count |

**Write server** (`mcps/write_server.py`) — todas com safety check (path dentro do git root, fora de `.git`/`.venv`/`.srclight`/`node_modules`):
| Tool | Função |
|---|---|
| `write_file` | escreve/sobrescreve arquivo completo |
| `apply_patch` | unified diff com validação `git apply --check` |
| `append_to_file` | append (cria se não existir) |
| `delete_file` | remove um arquivo (recusa diretórios) |
| `move_file` | rename/move; falha se destino existir |
| `create_directory` | `mkdir -p` idempotente |

---

## 📝 Como alterar os prompts de cada modelo

Os prompts do sistema definem o comportamento e as regras de saída dos agentes. Eles estão localizados na pasta `prompts/`:

* **Agente 1 (Planejador)**: [prompts/planner.system.md](file:///C:/Users/mf827/Documents/Ferramentas/pipeline-project/prompts/planner.system.md)
* **Agente 2 (Coder)**: [prompts/coder.system.md](file:///C:/Users/mf827/Documents/Ferramentas/pipeline-project/prompts/coder.system.md)
* **Agente 3 (Implementador)**: [prompts/implementer.system.md](file:///C:/Users/mf827/Documents/Ferramentas/pipeline-project/prompts/implementer.system.md)

Edite diretamente o arquivo Markdown correspondente para ajustar diretrizes, adicionar exemplos de poucos disparos (few-shot learning) ou impor novas regras estruturais de saída.

---

## 🧠 `action: "analyze"` e a pasta `brain/`

Além de edições de código (`create`/`modify`/`delete`), o Planner pode emitir steps com `action: "analyze"` que **produzem dossiês de contexto sobre símbolos** (funções, classes, módulos). Esses dossiês ficam em `brain/<slug>.md` e são executados pelo runner **sem LLM** — os dados vêm direto do call graph do `srclight`.

### O que cada dossiê contém
Para o `target_symbol` declarado no step, o runner consulta o srclight e formata:
- **Definition** — arquivo, linhas, assinatura, conteúdo do símbolo (`get_symbol`)
- **Callers** — quem chama (`get_callers`)
- **Callees** — o que ele chama (`get_callees`)
- **Imports** — módulos importados pelo símbolo (`find_imports`)
- **Dependents** — módulos que dependem dele (`get_dependents`)
- **Tests** — cobertura conhecida (`get_tests_for`)
- **Blame / Recent Changes** — histórico git (`blame_symbol`)

Ferramentas indisponíveis no servidor srclight viram seções `_(não disponível)_` — a execução não falha.

### Como o contexto se propaga
Quando um step posterior tem `depends_on: ["<analyze_step_id>"]`, o runner lê transitivamente todos os dossiês upstream e **injeta o markdown como chunks adicionais** no prompt do Coder. Resultado: um `modify` que vem depois de um `analyze` tem conhecimento real de quem usa a função antes de mudá-la.

### Conhecimento persistente entre runs
`brain/` fica versionada no projeto. Em runs futuras, o índice de dossiês existentes é injetado no contexto do Planner — ele é instruído a **reaproveitar dossiês recentes** em vez de reanalisar.

### Exemplos de prompt que ativam analyze
- `"analise a função apply_patch_tolerant"` → 1 step analyze
- `"refatore run_pipeline para suportar HITL"` → Planner provavelmente emite analyze de run_pipeline + modify
- `"qual o impacto de mudar a assinatura de write_file?"` → 1 step analyze + 1 step direct create do relatório

### Schema do step
```json
{
  "id": "step_1",
  "action": "analyze",
  "target_symbol": "apply_patch_tolerant",
  "file": "brain/apply_patch_tolerant.md",
  "location": "brain dossier",
  "mode": "patch",
  "depends_on": []
}
```

---

## 🧬 `mode: "patch"` vs `mode: "direct"`

Este campo no `PlanStep` define como o conteúdo do step trafega entre os agentes.

| Aspecto | `patch` (default) | `direct` |
|---|---|---|
| Quando | Edições de código existente (modify/add função, fix bug) | Criar artefato completo (HTML, CSS, JS, MD, JSON) em um shot |
| Coder produz | Pseudocódigo descritivo (`pseudocode`) | Conteúdo final do arquivo (`file_content`) |
| Implementer | Chama LLM para emitir `apply_patch`/`write_file` | **Passthrough sem LLM** — escreve `file_content` direto |
| Num ctx Coder | 16K | 32K |
| Risco de perda | Baixo (pseudocódigo → código é tradução natural) | Zero (sem segundo LLM) |

**Por que existe o modo `direct`?** Em testes anteriores, pedir "crie um site HTML com cards e animações descrevendo o projeto" gerava CSS genérico e JS quebrado — porque o pseudocódigo do Coder ("crie um card com hover animation") era reescrito pelo Implementer (outro LLM 7B-q4) com perda de fidelidade. No modo `direct` o Coder escreve o HTML/CSS/JS final e o Implementer só faz I/O.

O Planner decide o `mode` automaticamente (regra no `prompts/planner.system.md`). Para forçar manualmente, edite o plano em `runs/<id>/planner/attempt_N.json` e reinicie a partir do estágio 2.

---

## 🚀 Como executar o pipeline

Certifique-se de que o **Ollama** esteja rodando localmente com os modelos especificados no `config.yaml` carregados.

### Execução Completa (Padrão)
Execute o arquivo `runner.py` passando o prompt desejado:

```powershell
# Ativar o ambiente virtual
.venv\Scripts\Activate.ps1

# Executar o runner (completo - estágio 3)
python orchestrator\runner.py "adicione um comentário na primeira linha de config.yaml"
```

### Execução por Etapas (Interrupção Controlada)
Você pode escolher executar o pipeline apenas até uma determinada fase passando o número da etapa (`1`, `2` ou `3`) como argumento posicional ou via flag:

* **Estágio 1 — Planejamento/Análise**: Executa apenas o Retrieval e o Agente 1 (Planner), gerando o plano de ação sem propor pseudocódigo ou aplicar patches.
* **Estágio 2 — Pseudocódigo**: Executa até o Agente 2 (Coder), gerando o plano de ação e estruturando as modificações em pseudocódigo (sem aplicar alterações no disco).
* **Estágio 3 — Implementação/Escrita (Padrão)**: Executa todo o pipeline, aplicando fisicamente os patches através do Agente 3 (Implementer), executando validações do Git e lint.

#### Exemplos de Uso por Etapa:

**Usando argumentos posicionais:**
```powershell
# Executar apenas o Planejamento (Estágio 1)
python orchestrator\runner.py "adicione um comentário no README" 1

# Executar até o Pseudocódigo (Estágio 2)
python orchestrator\runner.py "adicione um comentário no README" 2

# Executar com prompt padrão do sistema apenas o Planejamento (Estágio 1)
python orchestrator\runner.py 1
```

**Usando flags (`--stage` ou `-s`):**
```powershell
# Executar apenas o Planejamento
python orchestrator\runner.py "adicione um comentário no README" --stage 1

# Executar até o Pseudocódigo
python orchestrator\runner.py "adicione um comentário no README" -s 2
```

A execução imprimirá o progresso até o estágio limite. O estado final e as respostas brutas de cada agente executado estarão salvos na pasta `runs/`.

### Exemplos por tipo de tarefa

**Edição de código (modo `patch`):**
```powershell
python orchestrator\runner.py "adicione validação de email no endpoint /register"
```
Logs esperados: `[retrieval] Executando busca híbrida...` → Planner emite steps com `mode: "patch"` → Coder gera pseudocódigo → Implementer chama LLM para `apply_patch`.

**Síntese / documentação (modo `direct`):**
```powershell
python orchestrator\runner.py "crie um site HTML com cards descrevendo cada arquivo Python, com hover animations e click para expandir"
```
Logs esperados: `[intent] modo SÍNTESE detectado` → `[retrieval-synth] carregando codebase_map + arquivos-chave + fontes` → Planner emite 1+ steps com `mode: "direct"` → Coder produz `file_content` final → Implementer loga `[direct] docs/... escrito (N chars)` **sem chamar LLM**.
