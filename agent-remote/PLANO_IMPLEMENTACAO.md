# 📋 Plano de Implementação — Agent-Remote

Este plano estabelece o passo a passo para a construção do **Agent-Remote**, priorizando a filosofia de **código enxuto, direto e funcional** ("não quero nada complexo").

---

## 🧭 Princípios de Desenvolvimento
1. **Zero Over-engineering:** Sem contêineres Docker aninhados, sem Redis, sem bancos de dados pesados e sem frameworks JavaScript que precisem de compilação (npm/webpack).
2. **Dependências Mínimas:** `fastapi`, `uvicorn`, `websockets`, `requests`, `qrcode` (opcional para exibir no terminal).
3. **Segurança por Padrão:** Autenticação obrigatória antes de qualquer tela ou websocket e terminal protegido por whitelist rígida.

---

## 🧱 Fases de Execução

### Fase 1: Configuração e Camada de Autenticação
* Criar [`config.example.json`](config.example.json) e `config.py` para carregar:
  * Porta local do Agent-Remote (padrão: `8765`).
  * Senha mestra (lida de arquivo ou variável de ambiente).
  * Mapeamento de aplicações e portas locais:
    * `Plataforma TTS & Vídeos`: `http://127.0.0.1:8011`
    * `ComfyUI`: `http://127.0.0.1:8188`
    * `Karaoke AI`: `http://127.0.0.1:8000`
  * Whitelist de comandos do terminal.
* Implementar autenticação via cookie assinado (HMAC-SHA256) com endpoint `/api/login` e `/api/logout`.

### Fase 2: Mecanismo de Chat (Ollama Streaming)
* Criar módulo `chat_engine.py`:
  * Conecta no endpoint local do Ollama (`http://127.0.0.1:11434/api/chat`).
  * Suporta streaming de respostas token por token via WebSocket ou Server-Sent Events (SSE).
  * Mantém histórico simples de conversa durante a sessão do usuário.
  * System Prompt voltado a orientar o usuário sobre o status das ferramentas do repositório.

### Fase 3: Terminal Seguro com Whitelist
* Criar módulo `terminal_engine.py`:
  * Validador de comandos baseado nas regras de [`COMANDOS_WHITELIST.md`](COMANDOS_WHITELIST.md).
  * Rejeição imediata de operadores perigosos (`;`, `&&`, `|`, `>`, etc.).
  * Execução assíncrona com `asyncio.create_subprocess_exec` (sem `shell=True`).
  * Streaming de saída (`stdout` e `stderr`) em tempo real através do WebSocket `/ws/terminal`.

### Fase 4: Frontend Responsivo (Split View & Mobile Tabs)
* Interface construída em um único arquivo HTML/CSS/JS (`templates/index.html` ou pasta `static/`):
  * **Tela de Login:** Campo de senha simples + botão de conectar.
  * **Header:** Seletor de aplicação ativa (troca a URL do iframe), indicador de status e leitura de VRAM (`nvidia-smi`).
  * **Desktop Split:** 
    * Esquerda (50%): Chat interativo com a IA.
    * Direita (50%): Iframe apontando para a aplicação selecionada (ex: `http://localhost:8011`).
  * **Gaveta Inferior:** Terminal retrátil com botões de atalho (*Chips* para `git status`, `nvidia-smi`, `executar_projeto`).
  * **Mobile:** Abas na barra inferior que alternam a visão entre Chat, App e Terminal com toque suave.

### Fase 5: Integração com Cloudflare Tunnel (`run.py`)
* Criar o script mestre `run.py`:
  1. Verifica se as dependências Python estão instaladas.
  2. Verifica se o binário `cloudflared` está disponível no sistema.
  3. Inicia o servidor Uvicorn em background.
  4. Lança `cloudflared tunnel --url http://127.0.0.1:8765` e captura a URL pública temporária.
  5. Imprime a URL colorida e o QR Code no terminal.
  6. Trata encerramento gracioso via `Ctrl+C` matando ambos os processos.

---

## 🧪 Critérios de Aceite
1. Subir o `run.py` com apenas 1 comando.
2. Acessar a URL HTTPS do Cloudflare pelo celular.
3. Fazer login com a senha configurada.
4. Enviar uma mensagem para a IA e receber resposta por streaming.
5. Ver a tela do `tts_platform_pt` (ou outra aplicação ativa) renderizada no iframe lateral.
6. Clicar no botão `[git status]` ou `[nvidia-smi]` no terminal web e ver o resultado imediato na tela.
