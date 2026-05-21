# Plano de Implementação Detalhado

Este documento contém o plano de ação detalhado para executar o **Passo 2** e **Passo 3** do projeto de agentes com pipeline MCP.

---

## Passo 2 — MCP read_file

Criaremos um servidor MCP local que expõe a ferramenta `read_file` de forma segura, comunicando-se via stdio através do protocolo JSON-RPC standard.

### Objetivos:
1. Criar um servidor MCP stdio nativo em Python (`mcps/readonly_server.py`).
2. Criar um cliente MCP genérico (`mcps/client.py`) para gerenciar o ciclo de vida do subprocesso.
3. Configurar o ambiente virtual `.venv` para o projeto com todas as dependências (`pyyaml`, `requests`, `pydantic`).

### Arquitetura de Comunicação MCP:
```
+---------------------------+                +-------------------------+
| Pipeline (Runner/Agentes) | -- stdio stdin --> | readonly_server.py      |
|                           | <-- stdio stdout - | (MCP JSON-RPC Server)   |
+---------------------------+                +-------------------------+
```

---

## Passo 3 — Agente 1 Real (Planejador)

Substituiremos a chamada mock do planejador por uma integração real com o Ollama local, injetando o prompt de sistema, os chunks recuperados do retrieval e a árvore de arquivos reais do repositório.

### Objetivos:
1. Criar o prompt de sistema estruturado em `prompts/planner.system.md` com 2-3 exemplos few-shot de saída JSON.
2. Ler a URL do Ollama e o nome do modelo diretamente do `config.yaml`.
3. Substituir a lógica de `call_model()` em `planner.py` por uma chamada HTTP real.
4. Mapear dinamicamente a estrutura de arquivos da codebase e injetar no prompt do planejador.
5. Rodar o pipeline orquestrado por `runner.py` e validar que as camadas de validação A e B aceitam e analisam o retorno JSON real.

---

## Cronograma de Ações e Arquivos Afetados

### Fase 1: Configuração do Ambiente
- **[NEW]** `setup_venv.ps1` — Cria e configura a venv local.
- **[MODIFY]** `.gitignore` — Adiciona `.venv` para evitar commit indesejado de dependências.

### Fase 2: Camada de Comunicação MCP (Passo 2)
- **[NEW]** `mcps/readonly_server.py` — Código do servidor MCP stdio.
- **[NEW]** `mcps/client.py` — Cliente para inicialização e controle do subprocesso.
- **[NEW]** `scratch/test_mcp.py` — Script rápido de validação para testar a leitura de arquivos via MCP.

### Fase 3: Integração do Agente 1 (Passo 3)
- **[NEW]** `prompts/planner.system.md` — Prompt de sistema mestre e few-shots.
- **[MODIFY]** `agents/planner.py` — Integração real com Ollama e montagem da árvore de arquivos.
- **[MODIFY]** `orchestrator/runner.py` — Ajustes para leitura de configurações.

---

## Próximos Passos
1. Aguardar aprovação do plano pelo usuário.
2. Iniciar a execução e criar o arquivo `task.md` para monitoramento.
