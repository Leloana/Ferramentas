# Contexto de Transição: Próximos Passos do Pipeline de Agentes

Este documento serve para guiar o assistente de IA na próxima sessão sobre o estado atual do projeto e os próximos passos de desenvolvimento.

---

## 📌 Estado Atual do Projeto

1. **Passo 2 (MCP read_file) — Concluído:**
   - **Servidor MCP:** [readonly_server.py](file:///C:/Users/mf827/.gemini/antigravity/worktrees/pipeline-project/implement-mcp-real-agents/pipeline-project/mcps/readonly_server.py) expõe a tool `read_file` via stdio JSON-RPC.
   - **Cliente MCP:** [client.py](file:///C:/Users/mf827/.gemini/antigravity/worktrees/pipeline-project/implement-mcp-real-agents/pipeline-project/mcps/client.py) gerencia o subprocesso e requisições síncronas.
   - **Teste de Leitura:** Validado com sucesso via [test_mcp.py](file:///C:/Users/mf827/.gemini/antigravity/worktrees/pipeline-project/implement-mcp-real-agents/pipeline-project/scratch/test_mcp.py).

2. **Passo 3 (Agente 1 Real - Planejador) — Concluído:**
   - **System Prompt:** [planner.system.md](file:///C:/Users/mf827/.gemini/antigravity/worktrees/pipeline-project/implement-mcp-real-agents/pipeline-project/prompts/planner.system.md) configurado com poucas tentativas (few-shots).
   - **Código do Agente:** [planner.py](file:///C:/Users/mf827/.gemini/antigravity/worktrees/pipeline-project/implement-mcp-real-agents/pipeline-project/agents/planner.py) atualizado para ler configurações do [config.yaml](file:///C:/Users/mf827/.gemini/antigravity/worktrees/pipeline-project/implement-mcp-real-agents/pipeline-project/config.yaml), mapear a árvore física da base de código e fazer requisições POST HTTP ao Ollama usando o modelo `qwen2.5-coder:7b-instruct-q4_K_M`.

3. **Compatibilidade com Windows (CP1252):**
   - Todos os console logs do [runner.py](file:///C:/Users/mf827/.gemini/antigravity/worktrees/pipeline-project/implement-mcp-real-agents/pipeline-project/orchestrator/runner.py), [state.py](file:///C:/Users/mf827/.gemini/antigravity/worktrees/pipeline-project/implement-mcp-real-agents/pipeline-project/orchestrator/state.py), [planner.py](file:///C:/Users/mf827/.gemini/antigravity/worktrees/pipeline-project/implement-mcp-real-agents/pipeline-project/agents/planner.py), [coder.py](file:///C:/Users/mf827/.gemini/antigravity/worktrees/pipeline-project/implement-mcp-real-agents/pipeline-project/agents/coder.py) e [implementer.py](file:///C:/Users/mf827/.gemini/antigravity/worktrees/pipeline-project/implement-mcp-real-agents/pipeline-project/agents/implementer.py) foram limpos de caracteres não-ASCII (como `✓`, `✗`, `→`, `—`) para evitar quebras de codificação.

---

## 🚀 Próximas Ordens de Execução

### Passo 4 — Agente 2 Real (Coder)
* **Objetivo:** Tornar o [coder.py](file:///C:/Users/mf827/.gemini/antigravity/worktrees/pipeline-project/implement-mcp-real-agents/pipeline-project/agents/coder.py) real.
* **Ações:**
  1. Criar o system prompt em `prompts/coder.system.md` detalhando a geração do pseudocódigo JSON.
  2. Substituir `call_model()` por chamada HTTP POST ao Ollama com formato JSON.
  3. No loop de passos, instanciar o `MCPClient` para ler o conteúdo real do arquivo alvo usando o servidor `mcps/readonly_server.py` e a tool `read_file`.

### Passo 5 — Agente 3 Real + MCPs de Escrita
* **Objetivo:** Tornar o [implementer.py](file:///C:/Users/mf827/.gemini/antigravity/worktrees/pipeline-project/implement-mcp-real-agents/pipeline-project/agents/implementer.py) real e criar as tools de escrita.
* **Ações:**
  1. Criar o servidor `mcps/write_server.py` com as ferramentas `write_file` e `apply_patch` (geração tolerante a hunk headers).
  2. Atualizar o Agente 3 para usar tool-calling do Qwen ou chamadas estruturadas JSON.
  3. Executar as chamadas instanciando o `MCPClient` apontando para o servidor de escrita.

### Passo 6 — Camada C de Validação
* **Objetivo:** Integrar proteções de segurança física.
* **Ações:**
  1. Adicionar validação de arquivos no `orchestrator/validators.py` (checar caminhos do plano com `os.path.exists`).
  2. Implementar `git apply --check` no `write_server.py` antes de aplicar qualquer patch unificado permanentemente.

---

## 🛠️ Como rodar o pipeline atual
O pipeline com o planejador real rodando no Ollama e os demais agentes em modo mock pode ser executado via terminal PowerShell:
```powershell
.\.venv\Scripts\python orchestrator\runner.py "sua solicitação aqui"
```
