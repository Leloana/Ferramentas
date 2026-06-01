# Testes desta etapa

Roteiro para validar tudo que foi implementado. Marque `[x]` o que passar.
Todos os testes assumem `run.bat` rodando no Windows com Ollama ativo e um
modelo já puxado (ideal: `qwen3:8b` para testar thinking).

---

## 0. Setup

- [ ] `setup.bat` cria `.venv` e instala dependências sem erro.
- [ ] `run.bat` lista os modelos numerados e aceita seleção.
- [ ] Painel inicial mostra: model, WINCLI loaded/not, persist path, mode,
      contagem de skills, lista de comandos.

---

## 1. Prompt enriquecido (item 7)

- [ ] Prompt do shell aparece no formato `[<cwd> | <model> | normal/ask_edits | 0 t] >`.
- [ ] Após o primeiro turno, o contador de tokens incrementa.
- [ ] Trocar `/mode bypass` muda o segmento do meio para `normal/bypass`.

---

## 2. `.persist` (item 5+8)

- [ ] Após o primeiro prompt, existe `.persist/<sessionid>.json`.
- [ ] O JSON contém `session_id`, `started_at`, `model`, `turns`,
      `session_totals`.
- [ ] Em um turno com cadeia de tools, cada step aparece em `turns[N].chain[]`
      com `prompt_tokens`, `gen_tokens`, `elapsed_s`, `tps`, e o
      `tool_call` + `tool_result` correto.
- [ ] `turns[N].totals` soma corretamente os steps do turno.
- [ ] `session_totals` soma todos os turnos.

---

## 3. `/context` (item 8)

- [ ] `/context` imprime tabela com session_id, modo, WINCLI status,
      variante de patch ativa, turnos, mensagens, tokens Σ, elapsed Σ.
- [ ] Lista todas as 6 skills descobertas (init, plan, debug, reflect,
      add_skill, add_tool).
- [ ] Após dar `a` (always allow) em um gate, `/context` mostra a tool no
      campo `always-allow tools`.

---

## 4. `/mode` e permissões (item 14)

- [ ] `/mode` sem args mostra estado atual.
- [ ] `/mode bypass` faz write/patch/run_command rodarem sem confirmação.
- [ ] `/mode ask_all` faz até `read_file` pedir confirmação.
- [ ] `/mode ask_edits` (padrão) só pede em write/patch/run_command.
- [ ] Em `ask_edits`, antes de `write_file`, aparece um painel com o
      conteúdo do arquivo novo.
- [ ] Em `ask_edits`, antes de `patch_file`, aparece `old_str`/`new_str`
      (ou range de linhas para v3) em painel amarelo.
- [ ] Em `ask_edits`, antes de `run_command`, aparece o comando em painel
      vermelho.
- [ ] Responder `n` no gate: o agente recebe "denied by user" e adapta.
- [ ] Responder `a`: a tool inteira fica liberada na sessão.
- [ ] Responder `p`: só aquele path fica liberado para aquela tool.
- [ ] `/mode op plan` muda apenas o op_mode (sem mudar perm).

---

## 5. Variantes de patch_file (item 1)

Repetir o mesmo prompt complexo de edição **em três sessões diferentes**,
trocando `ACTIVE_PATCH` em [tools.py](tools.py) linha ~14 entre execuções.

Prompt sugerido: peça para adicionar uma função nova em `agent.py` e
modificar um trecho com indentação no meio de outro arquivo.

- [ ] **v1** (default): funciona em casos simples. Quando falha, retorna
      `hint` com 3 linhas próximas (fuzzy).
- [ ] **v2**: aceita `context_before` / `context_after`. Quando old_str
      aparece 2x, anchors desambiguam.
- [ ] **v3**: usa `start_line`/`end_line` + `new_content` (pega os
      números de `read_file.numbered`). Anote qual variante errou menos.

Anote no final qual variante o modelo X usou melhor: __________

---

## 6. Erros ricos de tool (item 6)

- [ ] `read_file` em path inexistente → mensagem com sugestão "did you mean".
- [ ] `patch_file` com old_str ausente → hint mostra linhas similares.
- [ ] `patch_file` com old_str ambíguo (2+ matches) → erro pede mais contexto.
- [ ] `run_command` com timeout > 30s → erro claro de timeout.
- [ ] `write_file` sem `content` → erro `"missing 'content' arg"`.

---

## 7. Circuit breaker + reflect (item 13)

- [ ] Provocar 3 falhas idênticas de `patch_file` (ex: passar old_str que
      não existe três vezes seguidas).
- [ ] Após 3ª falha aparece painel vermelho "circuit breaker tripped".
- [ ] `/skill reflect` roda automaticamente (painel magenta "Reflection").
- [ ] Reflexão é injetada no histórico e o controle volta ao usuário.
- [ ] `/skill reflect <hint>` manual funciona em qualquer momento.

---

## 8. Thinking tag (item 10)

Usar um modelo com thinking (ex.: `qwen3:8b` com `/set parameter` ou
`deepseek-r1`).

- [ ] Conteúdo entre `<think>...</think>` aparece em painel cinza
      "💭 thinking" separado.
- [ ] Tool calls dentro do `<think>` **não** são executados (o parser
      ignora a região).
- [ ] A resposta final visível não contém o conteúdo do thinking.
- [ ] No `.persist`, o campo `content` do step armazena a versão sem o
      thinking.

---

## 9. Skills com lazy load (item 15)

- [ ] `/skills` lista as 6 skills com descrições.
- [ ] System prompt do modelo (verificar via `.persist` turno 1) **NÃO**
      contém menções a plan/debug/reflect/add_skill/add_tool — só core tools.
- [ ] `/skill <nome inexistente>` retorna erro limpo.

---

## 10. Plan mode multi-agent (item 9+11)

`/plan adicionar logging estruturado ao agent.py`

### 10a. Planner
- [ ] Linha de progresso "planner" aparece com spinner.
- [ ] Ao terminar mostra `✓ planner | N calls | M t | Ts (ok)`.
- [ ] Plano gerado tem seções: `# Plan:`, `## Goal`, `## Tasks`, `## Verification`.

### 10b. Reviewer
- [ ] Linha "reviewer" aparece logo depois do planner.
- [ ] Output revisado é o que vai ao painel + arquivo.

### 10c. Aprovação
- [ ] Painel azul mostra o plano em `plans/<slug>.md`.
- [ ] Prompt `[a]pprove / [e]dit / [r]eject / [c]ancel` aparece.
- [ ] `a` segue para executors.
- [ ] `e` abre notepad/$EDITOR, salva, e re-renderiza o plano editado.
- [ ] `c` cancela tudo e volta ao prompt principal.
- [ ] Após `e`, tarefas editadas (incluindo deletadas/reordenadas) são respeitadas.

### 10d. Parser de tasks
- [ ] Tarefas com `(id:N, deps:X,Y, tools:a,b)` parseiam todos os campos.
- [ ] Tarefas sem metadata recebem id automático e seguem ordem do arquivo.
- [ ] Tarefas em `## Verification` também entram no pipeline.

### 10e. Executors em ordem topológica
- [ ] Tarefas rodam em ordem respeitando `deps:`.
- [ ] Cada executor mostra `executor N/T (id=X)` em linha compacta.
- [ ] Cada executor só pode chamar as tools listadas em `tools:` da task.
- [ ] Após cada executor, o arquivo de plano é atualizado: `[ ]` → `[x]` +
      linha `→ <summary>`.
- [ ] Se um executor sai com `FAILED: <motivo>`, marca como `[✗]`.
- [ ] Se um executor estoura 15 tool calls, marca como `[✗]` com `max_calls`.
- [ ] Se um executor trip 3 strikes no mesmo erro, marca como `[✗] stuck`.

### 10f. Deps em cascata
- [ ] Quando uma task falha, suas dependentes saem como `[⊘ skipped]` sem rodar.
- [ ] Skip aparece com summary `skipped: dep(s) [X] did not complete`.

### 10g. Verifier
- [ ] Verifier roda após todos os executors (mesmo se todos OK).
- [ ] Painel magenta "verifier" mostra o veredito.
- [ ] Verifier chama `read_file` em arquivos de `files_touched` antes de
      confirmar (ver `.persist` para conferir).
- [ ] Verifier não pode chamar write/patch/run_command (whitelist read-only).

### 10h. Relatório final
- [ ] Tabela com colunas id / status / description / summary aparece.
- [ ] Linha de totais: ✓ done / ✗ failed / ⊘ skipped + elapsed total.
- [ ] Mensagem `[PLAN COMPLETED]` é injetada no histórico principal — o
      agente principal sabe que houve um plano.

### 10i. Custo / latência (anote)
- Tempo total: ______ s
- Tokens total: ______
- Latência por executor (média): ______ s
- Comparar com tempo que o single-agent levaria: ______

---

## 11. Debug mode multi-round (item 12)

### 11a. Round único (caso fácil)
- [ ] `/debug python -c "import main" ||| returncode 0`:
  - [ ] Painel "🐛 multi-round debug" mostra command/criterion/rounds.
  - [ ] Painel "starting round 1/3" aparece.
  - [ ] Linha compacta "✓ debugger round 1 | N calls | M t | Ts (ok)".
  - [ ] Painel verde "DEBUG SUCCESS on round 1".
  - [ ] Rounds 2/3 NÃO rodam (interrupção correta no sucesso).

### 11b. Múltiplos rounds com handoff
- [ ] `/debug` com bug intencional difícil (ex.: import circular):
  - [ ] Round 1 termina sem sucesso, mostra painel cinza "handoff round 1"
        contendo TRIED / LAST_ERROR / FILES_TOUCHED / HYPOTHESIS / NEXT.
  - [ ] Painel "starting round 2/3" diz "1 handoff(s) in context".
  - [ ] Round 2 NÃO repete as approaches do round 1 (verificar nos
        `.persist` que ele lê o handoff antes de agir).
  - [ ] Se sucesso no round 2, encerra; senão produz handoff 2 e segue.
  - [ ] Round 3 recebe ambos os handoffs.

### 11c. Falha esgotando rounds
- [ ] `/debug` com erro insolúvel (ex.: comando que sempre falha):
  - [ ] 3 rounds rodam até o fim.
  - [ ] Painel vermelho "DEBUG STUCK" lista os 3 handoffs.
  - [ ] Mensagem `[DEBUG STUCK]` é injetada no histórico principal.

### 11d. Handoff sintético quando agente não emite
- [ ] Forçar um round a estourar `max_tool_calls=6` sem emitir bloco
      ` ```handoff `:
  - [ ] Sistema gera handoff sintético com TRIED/LAST_ERROR baseado
        nos últimos tool_calls.
  - [ ] Próximo round ainda recebe contexto útil.

### 11e. Edge cases
- [ ] `/debug` sem `|||` → erro de uso.
- [ ] `/debug cmd |||` (criterion vazio) → erro.
- [ ] `/debug ||| crit` (command vazio) → erro.
- [ ] Cada round respeita whitelist (não tem write_file fora dos
      core tools — confirmar no `.persist`).

### 11f. Custo / latência (anote)
- Round 1 tempo médio: ______ s
- Round 2 tempo médio: ______ s (deve ser comparável a round 1 — KV
  cache de tamanho similar porque contexto é resetado)
- Round 3 tempo médio: ______ s
- Tokens por round: ______ / ______ / ______

---

## 12. Add skill (item 3)

- [ ] `/skill add_skill skill que mostra o calendário do mês usando run_command`:
  - [ ] Cria `skills/<nome>.py`.
  - [ ] Índice é invalidado e o novo nome aparece em `/skills` na hora
        (sem reiniciar a CLI).
  - [ ] `/skill <nome>` executa a nova skill.

---

## 13. Add tool (item 4)

- [ ] `/skill add_tool tool que retorna o tamanho de um arquivo em bytes`:
  - [ ] Cria/anexa em `extra_tools.py`.
  - [ ] Em seguida, peça ao agente: "use a nova tool para ver o tamanho
        de main.py" — ele deve conseguir chamar pela próxima requisição
        (reload dinâmico).

---

## 14. `/init` ainda funciona

- [ ] `/init` regenera `WINCLI.md`.
- [ ] System prompt da próxima mensagem (ver `.persist`) inclui o novo
      conteúdo de WINCLI.

---

## 15. Regressões

- [ ] `exit` / `quit` ainda saem.
- [ ] Ctrl+C ainda sai sem stacktrace.
- [ ] `read_file` retorna `numbered` (linhas com prefixo `N: `).
- [ ] PowerShell errors no `run_command` mostram returncode != 0.
- [ ] Histórico do prompt_toolkit (setas ↑↓) ainda navega comandos.

---

## 16. Truncamento de tool results

### 16a. read_file com arquivo grande
- [ ] Em arquivo de >300 linhas, `read_file` devolve só `head + omitted + tail`.
- [ ] Output contém `[... lines X..Y (N) omitted ...]`.
- [ ] Mensagem do tool result no histórico fica < 12k caracteres.

### 16b. read_file com offset/limit
- [ ] Peça ao agente: "read main.py linhas 50 a 80" — ele deve usar
      `{"path":"main.py","offset":50,"limit":31}`.
- [ ] Output mostra só esse range, com numeração começando em 50.
- [ ] Funciona com offset perto do fim do arquivo (returns < limit).

### 16c. run_command com output gigante
- [ ] `run_command` com `Get-ChildItem -Recurse` num diretório grande:
      stdout cortado em head+tail com `[... N lines of stdout omitted ...]`.
- [ ] Result tem campo `truncated: true`.

### 16d. Sumarização de tool results antigos
- [ ] Após 6+ turnos de conversa, abra `.persist/<id>.json` e confirme
      que tool results antigos no `chain` ainda têm conteúdo completo
      (persistência guarda tudo).
- [ ] Mas se você rodar um turno novo agora, o que vai pra Ollama
      (visível só por inspeção do código, não no disco) substituiu os
      tool results antigos por `[tool: ... — summarized away]`.
- [ ] Confirme que o consumo de tokens visível no prompt enriquecido
      não cresce linearmente com o número de turnos.

---

## 17. Cancelamento mid-turn (Ctrl+C)

- [ ] Durante geração do agente (streaming), aperte Ctrl+C:
  - [ ] CLI **NÃO** sai. Painel amarelo "turn cancelled by user".
  - [ ] Volta para o prompt principal.
  - [ ] Próximo turno funciona normalmente.
  - [ ] Mensagem `[USER INTERRUPTED THE PREVIOUS RESPONSE]` aparece no
        histórico.
- [ ] Ctrl+C **no prompt vazio** (esperando input) → sai normalmente.
- [ ] Ctrl+C **durante execução de tool** (raro, tools são rápidas) →
      painel "cancelled during tool execution".

---

## 18. /resume

### 18a. Listagem
- [ ] `/resume` sem argumento lista até 10 sessões recentes em tabela.
- [ ] Pickeando número, carrega a sessão.
- [ ] `c` cancela.

### 18b. Resume direto
- [ ] `/resume last` carrega a sessão mais recente.
- [ ] `/resume <prefix>` (ex.: `/resume 20260528`) carrega por prefix.
- [ ] `/resume bogus` mostra erro "no session matching".

### 18c. Continuidade
- [ ] Após /resume, o histórico tem todas as mensagens da sessão antiga.
- [ ] `/context` mostra `resumed_from: <id>` e o novo `session_id`.
- [ ] Próximo prompt funciona com contexto preservado (o agente
      lembra o que estava fazendo).
- [ ] Nova `.persist/<new_id>.json` é criada (antiga não é alterada).
- [ ] Snapshot manager começa do zero (não restaura undo stack antigo).

---

## 19. Snapshot / /undo

### 19a. Captura
- [ ] Cada write_file/patch_file gera um snapshot em
      `.persist/snapshots/<session>/<N>/<filename>`.
- [ ] `/context` mostra "undo stack depth" crescendo.

### 19b. Undo restaura
- [ ] Peça uma edição (ex.: trocar uma string em um arquivo).
- [ ] `/undo` reverte o arquivo ao estado anterior.
- [ ] Mensagem `↶ restored <path>` aparece.

### 19c. Undo de arquivo novo
- [ ] Peça pra criar `lixo.py` (write_file novo).
- [ ] `/undo` apaga o arquivo (não restaura — não existia antes).
- [ ] Mensagem `↶ deleted <path>`.

### 19d. Undo múltiplo
- [ ] Faça 3 edições em arquivos diferentes.
- [ ] `/undo 3` reverte os 3 em ordem reversa.
- [ ] `/context` mostra undo stack depth = 0.

### 19e. Stack vazia
- [ ] `/undo` quando não há nada → "nothing to undo".

---

## 20. Diff stats no /context

- [ ] Após algumas edições, `/context` mostra tabela "files modified
      this session" com colunas: file, +, -, note.
- [ ] Arquivos novos aparecem com note "new".
- [ ] Linhas + e - estão corretas (compare com `git diff` manual).
- [ ] Após `/undo` que reverte uma edição completamente, o arquivo
      ainda aparece com +0/-0 (snapshot ainda registrado).

---

## 21. Preview de run_command com syntax highlight

- [ ] Em `ask_edits` mode, antes de um `run_command`:
  - [ ] Painel mostra o comando com **syntax highlight de powershell**.
  - [ ] Título do painel inclui o working directory atual em texto cinza.
  - [ ] Funciona para comandos multi-linha.

---

## Bugs / observações encontrados

| # | Item | O que aconteceu | Severidade |
|---|------|-----------------|------------|
|   |      |                 |            |
|   |      |                 |            |
