# Agente de IA Local

Implementação do plano em [PLANO.md](PLANO.md): agente local com tool
calling, rodando 100% na máquina (Ollama + Qwen 3.5 9B), escopado para
tarefas curtas — sem autonomia longa multi-passo.

## 1. Pré-requisitos

- [Ollama](https://ollama.com) instalado e rodando.
- Modelo `qwen3.5:9b-instruct` já baixado (`ollama pull qwen3.5:9b-instruct`).
- Python 3.11+.
- GPU com ≥12 GB de VRAM (validado em RTX 4070).

## 2. Setup

```powershell
.\setup.ps1
```

Isso vai:
1. Definir `OLLAMA_FLASH_ATTENTION=1` e `OLLAMA_KV_CACHE_TYPE=q8_0` (variáveis
   de usuário, persistentes).
2. Criar o modelo customizado `local-agent` a partir do [Modelfile](Modelfile)
   (`num_ctx=24576`, `temperature=0.3`, `top_p=0.9`).
3. Instalar as dependências Python (`requirements.txt`).

**Depois de rodar o script, reinicie o app do Ollama** (bandeja do sistema →
Quit → abrir de novo) para que as variáveis de ambiente tenham efeito.

Copie `.env.example` para `.env` e ajuste se necessário (em especial
`LOCAL_AGENT_MODEL=local-agent` e `LOCAL_AGENT_ALLOWED_DIRS`, a whitelist de
diretórios que as ferramentas de arquivo podem tocar — por padrão é a pasta
do usuário).

## 3. Rodar o agente

```powershell
# pergunta única
python -m agent.cli "quanto é 47 * 12?"

# modo interativo
python -m agent.cli
```

## 4. Ferramentas disponíveis

| Ferramenta         | O que faz                                              |
|---------------------|---------------------------------------------------------|
| `buscar_arquivo`    | Busca arquivos por padrão glob dentro de um diretório.  |
| `ler_arquivo`       | Lê o conteúdo (texto) de um arquivo, com corte de tamanho. |
| `listar_diretorio`  | Lista entradas imediatas de um diretório.               |
| `calcular`          | Avalia expressão aritmética simples (sem `eval` arbitrário). |
| `data_hora_atual`   | Retorna data/hora local atual.                          |

Todas as ferramentas de arquivo são restritas a `LOCAL_AGENT_ALLOWED_DIRS`
(sandbox — ver `agent/sandbox.py`).

## 5. Guardrails implementados (PLANO.md secão 7)

- Limite de iterações (`LOCAL_AGENT_MAX_ITERS`, default 6) — ao estourar, falha
  limpa (`"FALHA: tarefa excedeu o limite de passos do agente local."`).
- Timeout por tool call (`LOCAL_AGENT_TOOL_TIMEOUT`) e timeout global da tarefa
  (`LOCAL_AGENT_TASK_TIMEOUT`).
- Validação de argumentos contra o schema JSON antes de executar qualquer
  ferramenta.
- Whitelist: só ferramentas registradas em `agent/tools/__init__.py` são
  executáveis.
- Sandbox de sistema de arquivos (`agent/sandbox.py`).
- Detecção de loop: mesma tool call (nome + args) repetida aborta a tarefa.
- Nunca alucina sucesso — falhas retornam mensagem explícita, não silêncio.

## 6. Testes

```powershell
# suíte unitária (rápida, não precisa de GPU nem de Ollama rodando)
pytest

# suíte live — critérios de aceitação da secão 8 do PLANO.md, contra o
# modelo real. Precisa do Ollama rodando com o modelo carregado.
pytest -m live
```

A suíte unitária (`tests/`) cobre guardrails, sandbox e ferramentas com um
`LLMClient` fake — determinística, roda em CI sem GPU.

A suíte live (`tests/live/`) implementa os 6 critérios da secão 8 contra o
modelo real (smoke test, 1 tool call, seleção de ferramenta ≥8/10, cadeia
curta, guardrail de tarefa impossível, VRAM sob carga). É pulada
automaticamente se o Ollama não estiver acessível em
`LOCAL_AGENT_OLLAMA_BASE_URL`.

## 7. Estrutura

```
agent/
  config.py       # variáveis de ambiente / defaults
  sandbox.py       # whitelist de diretórios para ferramentas de FS
  guardrails.py     # limite de iterações, timeout, detecção de loop
  llm_client.py     # wrapper do endpoint OpenAI-compatível do Ollama
  loop.py           # loop ReAct principal
  cli.py            # entrada de linha de comando
  tools/            # 5 ferramentas + registry central (whitelist)
tests/              # suíte unitária (fake LLM client)
tests/live/         # suíte contra o modelo real (secão 8 do PLANO.md)
Modelfile           # num_ctx / temperature / top_p do modelo customizado
setup.ps1           # setup do runtime (env vars + modelo + deps)
```

## 8. Escopo

Este agente é para tarefas **pontuais e de cadeia curta**. Ele não tenta
orquestração longa nem autocorreção em muitos passos — ao invés disso, falha
de forma limpa (ver secão 7 do PLANO.md). Escalonamento para APIs frontier
(Claude/GPT) está fora de escopo, tanto do plano quanto desta implementação.
