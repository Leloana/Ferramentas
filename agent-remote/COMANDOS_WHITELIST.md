# 🛡️ Política de Whitelist de Comandos do Terminal Web

O terminal web do **Agent-Remote** foi projetado seguindo o princípio da **defesa em profundidade** e do **menor privilégio**. Ele não expõe um shell desprotegido (como `cmd.exe` ou `/bin/bash` cru), mas sim um **Dispatcher Controlado** de comandos.

---

## 🎯 Por que usar uma Whitelist?

Expor uma janela de terminal na internet — mesmo com senha — é um risco sério se houver brechas de autenticação ou se um terceiro obtiver acesso. 

Com a **Whitelist estrita**:
* Apenas ações previamente homologadas para o desenvolvimento do repositório podem ser executadas.
* Mesmo se alguém tentar injetar comandos como `rm -rf /` ou `format C:`, o comando é rejeitado na camada de validação antes de chegar ao sistema operacional.
* Torna o uso pelo celular extremamente confortável, pois os comandos homologados podem ser disparados com **um único toque** através de botões de atalho (*Quick Action Chips*).

---

## 📋 Comandos Permitidos por Padrão

A lista de comandos padrão é dividida por categoria e configurada em `config.json`:

### 1. Monitoramento de Hardware e Modelos
| Comando | O que faz |
|---|---|
| `nvidia-smi` | Exibe o consumo de VRAM e temperatura da GPU RTX 4070 em tempo real. |
| `ollama ps` | Lista os modelos de IA carregados atualmente na memória VRAM/RAM. |
| `ollama list` | Lista todos os modelos locais disponíveis na máquina. |

### 2. Controle de Versão (Git)
| Comando | O que faz |
|---|---|
| `git status` | Verifica branches, arquivos modificados e pendências de commit. |
| `git pull` | Puxa as atualizações mais recentes do repositório remoto. |
| `git log -n 5 --oneline` | Exibe os últimos 5 commits do repositório. |
| `git diff --stat` | Resumo estatístico das alterações locais. |

### 3. Execução e Produção de Vídeos (`tts_platform_pt`)
| Comando | O que faz |
|---|---|
| `python scripts/executar_projeto.py <projeto>` | Inicia a esteira automatizada de produção de vídeo (áudio + ComfyUI + montagem). |
| `python scripts/download_qwen_models.py` | Executa o download/verificação dos pesos INT8 do Qwen-Image-2.1. |
| `python scripts/gerar_imagens.py <args>` | Dispara jobs de geração de imagens direto para a API do ComfyUI. |

### 4. Navegação e Inspeção de Arquivos (Leitura Segura)
| Comando | O que faz |
|---|---|
| `ls` / `dir` | Lista os arquivos da pasta atual do projeto. |
| `pwd` | Exibe o diretório de trabalho corrente. |

---

## 🚫 Caracteres e Operadores Estritamente Proibidos

Para evitar vulnerabilidades de *Command Injection* ou encadeamento malicioso, qualquer entrada contendo os seguintes caracteres ou padrões é **imediatamente rejeitada**:

| Caractere / Padrão | Risco Mitigado |
|---|---|
| `;` e `&` e `&&` | Encadeamento e execução sequencial de comandos não autorizados. |
| `\|` e `\|\|` | Envio de saídas através de pipes ou execução condicional arbitrária. |
| `>`, `>>`, `<` | Sobrescrita ou corrupção de arquivos do sistema. |
| `` ` `` ou `$()` | Expansão e substituição de comandos embutidos. |
| `rm -rf`, `del /f` | Destruição involuntária de dados do repositório. |
| `sudo`, `runas` | Tentativa de elevação de privilégios. |

---

## ⚙️ Como Adicionar Novos Comandos à Whitelist

Você pode personalizar a lista de comandos permitidos editando o arquivo `config.json`:

```json
{
  "terminal": {
    "allowed_commands": [
      "git",
      "nvidia-smi",
      "ollama",
      "python",
      "uvicorn",
      "ls",
      "dir"
    ],
    "allowed_scripts": [
      "scripts/executar_projeto.py",
      "scripts/download_qwen_models.py",
      "scripts/gerar_imagens.py"
    ]
  }
}
```

> 💡 **Dica de Usabilidade:** No frontend do Agent-Remote, os comandos mais comuns aparecem como **botões de atalho** no topo do terminal. No smartphone, basta tocar em `[git status]` ou `[nvidia-smi]` para executar instantaneamente sem digitar nada.
