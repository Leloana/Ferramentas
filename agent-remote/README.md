# 🌐 Agent-Remote — Controle Web Remoto do PC & Central de Aplicações

O **Agent-Remote** é uma ferramenta feita para você programar no seu PC com **`agy` (Antigravity CLI)** ou **`claude` (Claude Code)**, ir para a academia (ou qualquer lugar fora de casa) e **continuar exatamente de onde parou pelo celular**, com um terminal interativo real e uma aba de aplicação controlada pelo agente via **MCP**.

A interface é focada em **fazer apenas uma coisa por vez**, otimizada para toque no smartphone:
1. ⌨️ **Aba Terminal:** Terminal Linux PTY real (`xterm.js`) com barra de atalhos touch (`Tab`, `Ctrl+C`, `Esc`, setas, chips para `agy`, `claude`, `git push`, etc.).
2. 📱 **Aba Aplicação (Live Preview):** O agente coloca o site que criou na aba via MCP (`show_in_remote_preview`). O preview atualiza na hora e contorna problemas de HTTPS com proxy reverso automático.
3. ⚙️ **Aba Status & Segurança:** IP Whitelist com detecção real do celular via Cloudflare (`CF-Connecting-IP`), telemetria de VRAM/GPU (`nvidia-smi`) e link do túnel.
4. 💬 **Aba Chat IA:** Interface opcional para conversar diretamente com modelos (Ollama, Gemini, Claude, OpenAI).

---

## 🏋️‍♂️ O Cenário Real de Uso

> *"Estou fazendo código com o agy ou claude no meu PC via terminal, vou para a academia e quero continuar. Abro o celular: lá tem o terminal na pasta que eu quero, escolho se continuo com o agy ou claude mandando prompts normalmente. Quando finalizamos, digo: 'beleza, agora me mostra a aplicação usando o mcp do agent-remote', e ela aparece na aba Aplicação para eu testar no celular. Se precisar dar push, volto na aba Terminal e dou git push."*

---

## 🏛️ Arquitetura das Abas

```
+---------------------------------------------------------------------------------+
| 🌐 Agent-Remote         [⌨️ Terminal]  [📱 Aplicação]  [⚙️ Status]  [💬 Chat]     |
+---------------------------------------------------------------------------------+
|                                                                                 |
|  [📱 VISÃO 1: TERMINAL (PTY)]                                                   |
|  +---------------------------------------------------------------------------+  |
|  | [Tab] [Ctrl+C] [Esc] [↑] [↓] [←] [→] [↵] | [agy] [claude] [git push]      |  |
|  +---------------------------------------------------------------------------+  |
|  | marcelo@pc:~/marcelo/Ferramentas$ agy                                     |  |
|  | Antigravity CLI v1.1.27                                                   |  |
|  | > Faça um dashboard de vendas em React na porta 3000                      |  |
|  | Criando aplicação... Servidor rodando em http://localhost:3000            |  |
|  +---------------------------------------------------------------------------+  |
|                                                                                 |
|  [📱 VISÃO 2: APLICAÇÃO (Preview acionado via MCP)]                             |
|  +---------------------------------------------------------------------------+  |
|  | Aplicação: Dashboard de Vendas (porta 3000)  [🔄 Recarregar] [↗️ Abrir]    |  |
|  +---------------------------------------------------------------------------+  |
|  |  +---------------------------------------------------------------------+  |  |
|  |  |  [Interface Web da aplicação gerada pelo agente rodando 100%]       |  |  |
|  |  +---------------------------------------------------------------------+  |  |
|  +---------------------------------------------------------------------------+  |
|                                                                                 |
+---------------------------------------------------------------------------------+
```

---

## 🚀 Como Executar

### 1. Iniciar no PC

#### 🪟 No Windows Nativo (2 Cliques):
Dê dois cliques no arquivo:
```cmd
run.bat
```
*(ou execute no PowerShell: `.\run.bat` ou `python run.py`). Veja o [**GUIA_WINDOWS.md**](./GUIA_WINDOWS.md) para detalhes.*

#### 🐧 No Linux / WSL:
```bash
./run.py
```

O inicializador automático:
* Configura a `venv` e instala dependências (`pywinpty` no Windows, `FastAPI`, etc.).
* Sincroniza o arquivo `.mcp.json` com os caminhos nativos do SO.
* Localiza ou baixa o executável oficial do **Cloudflare Tunnel**.
* Inicia o servidor e exibe no terminal o **QR Code ASCII** para escanear com a câmera do celular.

### 2. No Celular
1. Escaneie o QR Code ou acerte a URL gerada pelo Cloudflare Tunnel.
2. Digite sua senha de acesso.
3. Na aba **Status & IP**, clique em **"Autorizar meu IP Atual na Whitelist"** se quiser restringir o acesso apenas para o seu smartphone.
4. Na aba **Terminal**, use o bash, lance o `agy` ou `claude`, e trabalhe normalmente!

---

## 🤖 Como os Agentes Interagem via MCP

O **Agent-Remote** inclui um MCP Server pronto para ser consumido pelo `claude` (Claude Code) e `agy` (Antigravity CLI):

### Ferramenta `show_in_remote_preview`
* **Nome:** `show_in_remote_preview`
* **Parâmetros:**
  * `url`: URL completa (ex: `http://localhost:3000`) ou apenas a porta (ex: `3000`).
  * `title`: Título descritivo opcional (ex: `Dashboard de Métricas`).
* **Efeito:** Grava o estado de visualização e despacha um evento WebSocket em tempo real para a tela do celular, que carrega o iframe e notifica o usuário!

### Como Registrar o MCP no Claude Code
No terminal:
```bash
claude mcp add agent-remote python /home/marcelo/marcelo/Ferramentas/agent-remote/mcp_server.py
```
Ou no arquivo de configuração do projeto `.mcp.json`:
```json
{
  "mcpServers": {
    "agent-remote": {
      "command": "/home/marcelo/marcelo/Ferramentas/agent-remote/venv/bin/python",
      "args": ["/home/marcelo/marcelo/Ferramentas/agent-remote/mcp_server.py"]
    }
  }
}
```

---

## 🛡️ Segurança

1. **IP Whitelist com `CF-Connecting-IP`:** Quando ativada, bloqueia qualquer visitante cujo IP não seja o do seu celular, mesmo que saiba a senha.
2. **Sessão HMAC Segura:** Cookies assinados criptograficamente.
3. **Sem Port Forwarding:** O túnel Cloudflare estabelece conexões de saída criptografadas com a rede da Cloudflare, sem abrir portas no roteador de casa.
4. **Proxy Reverso Automático:** Aplicativos rodando em portas locais (ex: 3000, 5173, 8000) são roteados por `/proxy/port/{porta}/`, contornando problemas de *Mixed Content* em conexões móveis HTTPS.
