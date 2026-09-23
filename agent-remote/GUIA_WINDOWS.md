# 🪟 Guia Oficial: Agent-Remote no Windows Nativo

O **Agent-Remote** foi projetado para rodar de forma **100% nativa no Windows** (Windows 10 e Windows 11), sem necessidade de WSL, Docker ou configurações manuais complexas.

---

## ⚡ Início Rápido (2 Cliques)

1. Entre na pasta `agent-remote` no Explorador de Arquivos do Windows.
2. Dê **dois cliques** no arquivo:
   ```cmd
   run.bat
   ```
3. O script cuidará de tudo automaticamente:
   * Cria o ambiente virtual `venv` (se ainda não existir).
   * Instala as dependências (`FastAPI`, `uvicorn`, `pywinpty`, etc.).
   * Se o `cloudflared.exe` não estiver instalado, faz o download oficial automático.
   * Inicia o servidor e exibe o **QR Code** no terminal para você escanear com a câmera do celular.

---

## 🛠️ Como Funciona o Terminal no Windows

* **ConPTY Oficial da Microsoft:** O Agent-Remote usa a API de pseudoterminal nativa do Windows (através do pacote `pywinpty`). Isso permite rodar aplicações de terminal interativo com cores ANSI, autocomplete e controle de cursor (exatamente igual ao Windows Terminal).
* **Shell Padrão:** Por padrão, o terminal abre no **PowerShell** (com política de execução desbloqueada para scripts). Você também pode usar PowerShell 7 (`pwsh`), Git Bash ou `cmd.exe`.
* **Seus Agentes no Windows:**
  * O **`claude` (Claude Code)** instalado via npm (`npm install -g @anthropic-ai/claude-code`) funciona diretamente no PowerShell.
  * O **`agy` (Antigravity CLI)** funciona diretamente pelo terminal.
  * O **`git`** funciona nativamente para `git status`, `git commit` e `git push`.

---

## 🤖 Conectando o Servidor MCP no Windows

Ao iniciar o `run.bat` ou `python run.py`, o Agent-Remote atualiza automaticamente o arquivo `.mcp.json` com os caminhos corretos do Windows (`C:\...`).

Para registrar no Claude Code no Windows:
```powershell
claude mcp add agent-remote .\venv\Scripts\python.exe C:\caminho\para\agent-remote\mcp_server.py
```
Ou simplesmente deixe o arquivo `.mcp.json` na raiz da sua pasta de trabalho.

---

## 🔒 Segurança & Dicas no Windows

1. **Firewall do Windows:** Se o Windows Defender exibir um pop-up perguntando sobre o Python ou Cloudflared, marque as caixas de rede e clique em *"Permitir Acesso"*.
2. **IP Whitelist para o Celular:**
   * Abra a interface no celular pelo link da Cloudflare.
   * Vá até a aba **Status & IP**.
   * Clique em **"Autorizar meu IP Atual na Whitelist"**.
   * Pronto! Somente o seu smartphone poderá acessar o seu computador a partir de então.
3. **Se quiser instalar o Cloudflare Tunnel globalmente:**
   Abra o PowerShell como Administrador e execute:
   ```powershell
   winget install --id Cloudflare.cloudflared
   ```
