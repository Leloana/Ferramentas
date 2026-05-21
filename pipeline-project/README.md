# Pipeline de Agentes Automatizados com MCP, Ollama e Srclight

Este projeto implementa um pipeline de desenvolvimento de software automatizado composto por 3 agentes inteligentes (Planejador, Coder e Implementador) que cooperam de forma isolada para planejar, estruturar e aplicar modificações de código diretamente no repositório local. Ele utiliza a especificação do **Model Context Protocol (MCP)** para operações de busca híbrida, leitura e escrita e se integra com LLMs locais via **Ollama**.

---

## 🎯 O que o projeto faz

O pipeline recebe uma solicitação de desenvolvimento em linguagem natural (prompt) e a executa através das seguintes fases:

1. **Retrieval Dinâmico e Real (via Srclight)**:
   - Se a pasta `.srclight/` não existir na base de código, o pipeline inicia automaticamente o processo de indexação da base de código usando o modelo de embedding.
   - Conecta ao servidor MCP do `srclight` e faz uma **Busca Híbrida** (combinando busca textual FTS5 com busca vetorial semântica) para identificar os símbolos (funções, classes, arquivos) mais relevantes.
   - Extrai o código-fonte exato dos símbolos encontrados usando a ferramenta `get_symbol` do `srclight` e os fornece como chunks de contexto para o Planejador.
2. **Planejador (Agente 1)**: Analisa a árvore de arquivos e o contexto do retrieval para gerar um plano de passos JSON estruturado. A **Camada C de Validação** previne ataques de Path Traversal e impede alterações em arquivos que não existem no disco físico para ações de modificação/exclusão.
3. **Coder (Agente 2)**: Lê os arquivos originais reais via servidor MCP de Leitura (`readonly_server.py`) e projeta a lógica de cada alteração em pseudocódigo estruturado JSON.
4. **Implementador (Agente 3)**: Executa as alterações de código gerando chamadas de ferramenta estruturadas JSON (`write_file` ou `apply_patch`) e enviando-as ao servidor MCP de Escrita (`write_server.py`).
5. **Validação Git (MCP Write)**: O servidor de escrita aplica os patches de forma tolerante a hunks, gera um diff em memória e roda `git apply --check` na raiz do repositório antes de gravar fisicamente no disco.
6. **Logging e Histórico**: Salva os metadados do run na pasta `runs/` juntamente com as saídas brutas (raw JSON) de cada agente segmentadas em pastas separadas por agente (`planner/`, `coder/`, `implementer/`).

---

## 🔒 Isolamento de Contexto (Limitação de Escopo)

Para garantir precisão máxima e reduzir custos com a janela de contexto da GPU, **não há compartilhamento de histórico de chat ou conversação entre os agentes**:
* Cada chamada ao Ollama é iniciada com uma nova lista de mensagens (system prompt + prompt do usuário formatado com JSON).
* O **Coder** e o **Implementador** rodam em loops isolados por passo. Eles nunca veem o prompt original do usuário, nem os diálogos dos outros passos ou agentes. Eles operam estritamente no escopo das propriedades do passo que estão processando no momento, reduzindo a chance de alucinações.

---

## ⚡ Otimização de GPU (VRAM de 12GB ou menor)

Para garantir que a execução ocorra **100% na GPU** sem transbordar para a CPU (offloading que torna o processo muito lento), aplicamos as seguintes configurações:

### 1. Modelo de Embedding Personalizado
O modelo `qwen3-embedding:8b` por padrão aloca uma janela de contexto de 40.960 tokens, consumindo cerca de 15 GB de VRAM. Criamos o modelo personalizado `qwen3-embedding-gpu` com contexto limitado para **8192** tokens (consome apenas **7.3 GB** de VRAM).

Para criar este modelo no seu Ollama local:
1. Crie um arquivo chamado `Modelfile` contendo:
   ```dockerfile
   FROM qwen3-embedding:8b
   PARAMETER num_ctx 8192
   ```
2. No terminal, execute o comando:
   ```bash
   ollama create qwen3-embedding-gpu -f Modelfile
   ```

### 2. Configurações de Contexto no `config.yaml`
Configuramos janelas de contexto limitadas de `8192` tokens no arquivo de configuração global para manter o consumo de KV Cache controlado.
Além disso, implementamos um utilitário de **Descarregamento Ativo** (`unload_ollama_models`) que limpa automaticamente os modelos inativos da VRAM do Ollama antes de cada etapa importante (Retrieval, Planejador, Coder, Implementador), garantindo que apenas um modelo resida na GPU por vez.

---

## ⚙️ Como configurar e trocar os modelos

Toda a configuração global do projeto está no arquivo `config.yaml` na raiz do projeto.

### Visualizando o [config.yaml](file:///C:/Users/mf827/Documents/Ferramentas/pipeline-project/config.yaml):
```yaml
models:
  planner: "qwen2.5-coder:7b-instruct-q4_K_M"       # Modelo usado pelo Agente 1 (Planner)
  coder: "qwen2.5-coder:7b-instruct-q4_K_M"         # Modelo usado pelo Agente 2 (Coder)
  implementer: "qwen2.5-coder:7b-instruct-q4_K_M"     # Modelo usado pelo Agente 3 (Implementer)

ollama:
  base_url: "http://localhost:11434"                 # URL do Ollama local
  planner_num_ctx: 8192                             # Limites de contexto para evitar uso de CPU
  coder_num_ctx: 8192
  implementer_num_ctx: 8192

retrieval:
  top_k: 5
  embedding_model: "ollama:qwen3-embedding-gpu"      # Modelo de embedding customizado

paths:
  runs_dir: "runs/"
  codebase: "."
```

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
Após adicionar uma ferramenta de escrita, adicione o nome dela na lista `tool_whitelist` do [config.yaml](file:///C:/Users/mf827/Documents/Ferramentas/pipeline-project/config.yaml) para que ela seja validada na Camada B de segurança do Implementador.

---

## 📝 Como alterar os prompts de cada modelo

Os prompts do sistema definem o comportamento e as regras de saída dos agentes. Eles estão localizados na pasta `prompts/`:

* **Agente 1 (Planejador)**: [prompts/planner.system.md](file:///C:/Users/mf827/Documents/Ferramentas/pipeline-project/prompts/planner.system.md)
* **Agente 2 (Coder)**: [prompts/coder.system.md](file:///C:/Users/mf827/Documents/Ferramentas/pipeline-project/prompts/coder.system.md)
* **Agente 3 (Implementador)**: [prompts/implementer.system.md](file:///C:/Users/mf827/Documents/Ferramentas/pipeline-project/prompts/implementer.system.md)

Edite diretamente o arquivo Markdown correspondente para ajustar diretrizes, adicionar exemplos de poucos disparos (few-shot learning) ou impor novas regras estruturais de saída.

---

## 🚀 Como executar o pipeline

Certifique-se de que o **Ollama** esteja rodando localmente com os modelos especificados no `config.yaml` carregados.

### Executar o pipeline principal
Execute o arquivo `runner.py` passando o prompt desejado entre aspas como argumento:

```powershell
# Ativar o ambiente virtual
.venv\Scripts\Activate.ps1

# Executar o runner
python orchestrator\runner.py "adicione um comentário na primeira linha de config.yaml"
```

A execução imprimirá o progresso de cada agente e validará as alterações. O resultado final estará gravado no arquivo alvo e o log completo de estado e respostas brutas estará salvo na pasta `runs/`.
