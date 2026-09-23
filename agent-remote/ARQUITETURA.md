# 🏛️ Arquitetura do Sistema — Agent-Remote

Este documento detalha as decisões técnicas, a análise de projetos semelhantes da comunidade e as estratégias de segurança adotadas para o **Agent-Remote**.

---

## 🔍 1. Análise de Projetos Existentes e Lições Aprendidas

Para projetar uma ferramenta simples, eficiente e segura, analisamos as soluções open-source mais relevantes do mercado:

| Projeto | O que faz bem | Por que não usamos diretamente | O que aproveitamos / adaptamos |
|---|---|---|---|
| **OpenHands** *(antigo OpenDevin)* | Layout modular completo: Chat + Navegador/Preview + Terminal em tempo real. | Excessivamente complexo e pesado. Exige múltiplos contêineres Docker, Docker-in-Docker, consome 2GB a 4GB de RAM só para subir o ambiente. | **O Layout**: A divisão visual entre conversa, visualização do app e terminal é o formato perfeito para desenvolvimento assistido. |
| **Bolt.new / Lovable** | Experiência de desenvolvimento com **Live Preview**: você vê o app sendo construído em tempo real enquanto fala com a IA. | Fechado / focado apenas em stacks web Node.js em containers WebContainers no navegador, sem acesso ao hardware da máquina local. | **O Split View com Iframe**: Ter a aba do aplicativo em execução lado a lado com a janela de diálogo com a IA. |
| **ttyd / Gotty** | Servidores web consagrados para expor terminais (PTY) via WebSockets. | Abrem uma shell aberta completa (`bash`/`powershell`) para a internet. Qualquer falha de autenticação expõe o computador inteiro. | **WebSockets para I/O**: Usamos WebSockets bidirecionais para o terminal, mas **substituímos a shell aberta por um Dispatcher com Whitelist rígida**. |
| **Gradio (`share=True`)** | Criação de túneis remotos públicos temporários sem configuração manual de portas. | Amarrado ao ecossistema Gradio de Data Science, com UIs pré-definidas e engessadas. | **O conceito de túnel sob demanda**: Adotamos o binário oficial do **Cloudflare Tunnel (`cloudflared`)** direto pelo Python. |

---

## 🧱 2. Diagrama de Arquitetura

```
 [📱 Celular / Navegador Externo]
               │  (HTTPS Seguro - Criptografia TLS de ponta a ponta)
               ▼
   [Cloudflare Edge Network]
               │  (Túnel Reverso Outbound - Zero portas abertas no roteador)
               ▼
   [cloudflared (Daemon Local)]
               │  (HTTP Local: 127.0.0.1:8765)
               ▼
 ┌─────────────────────────────────────────────────────────────┐
 │                      AGENT-REMOTE (FastAPI)                 │
 ├─────────────────┬─────────────────────────┬─────────────────┤
 │  Módulo de Auth │  Ollama Chat Engine     │ Terminal Engine │
 │  - Validação PIN│  - Streaming SSE / WS   │ - Whitelist Rígida│
 │  - Sessão HMAC  │  - Contexto de Conversa │ - Sem shell=True │
 └────────┬────────┴────────────┬────────────┴────────┬────────┘
          │                     │                     │
          ▼                     ▼                     ▼
   [Frontend Web]     [Ollama Local :11434]    [Comandos do PC]
   (Chat + Preview    (Modelo qwen3.5:9b       (git, python,
    Iframe + Console)  na GPU RTX 4070)         nvidia-smi, etc.)
          │
          ▼
   [Aplicações Locais em Execução]
   (TTS Web :8011 | ComfyUI :8188 | Karaoke :8000 | etc.)
```

---

## 🔐 3. Modelo de Segurança

Por ser uma aplicação acessível via internet através de um túnel público, a segurança é construída em três camadas intransponíveis:

### A. Autenticação por Senha / PIN
* O usuário define uma senha mestra no `config.json` ou variável de ambiente `AGENT_REMOTE_PASSWORD`.
* Ao acessar a raiz, qualquer requisição sem cookie assinado (HMAC-SHA256) é redirecionada para a tela de login.
* Proteção contra força bruta (rate-limiting de 5 tentativas por minuto por IP).

### B. Terminal Seguro com Whitelist (Anti-Shell Injection)
Ao contrário de soluções como `ttyd`, o Agent-Remote **não inicia um interpretador de comandos arbitrário** (`powershell.exe` ou `/bin/bash` solto).

* Cada comando submetido passa pelo `CommandValidator`:
  1. Quebra a string em tokens usando `shlex.split()`.
  2. Verifica se o primeiro token (binário/comando) está explicitamente na lista de permissões (`ALLOWED_COMMANDS`).
  3. Bloqueia operadores de concatenação e redirecionamento de shell (`|`, `&`, `;`, `>`, `<`, `` ` ``, `$()`).
  4. Executa usando `asyncio.create_subprocess_exec()` diretamente com a lista de argumentos, **nunca usando `shell=True`**.
* A saída (stdout/stderr) é transmitida em tempo real via WebSocket linha por linha para a interface web.

### C. Túnel Reverso Seguro (Cloudflare)
* Não há necessidade de IP fixo, DDNS ou redirecionamento de portas (port forwarding) no modem da operadora.
* A conexão é sempre iniciada de **dentro para fora** (outbound connection na porta 443 para os servidores da Cloudflare).
* As URLs do Quick Tunnel (`.trycloudflare.com`) são temporárias e rotativas.

---

## 🎨 4. Estrutura da Interface do Usuário (Frontend)

O frontend foi desenhado para ser **ultrarrápido, moderno e responsivo**:
* **Sem Frameworks Pesados:** Construído em HTML5 semântico, CSS flexbox/grid com suporte nativo a Dark Theme e JavaScript Vanilla.
* **Componentes Principais:**
  1. **Barra Superior (Header):**
     * Indicador de status (Conectado / Desconectado).
     * Seletor do Projeto Ativo (ex: `tts_platform_pt`, `karaoke`, `comfyui`).
     * Widget rápido de telemetria da GPU (ex: `VRAM: 6.8 / 12.0 GB`).
     * Botão de logout.
  2. **Área Dividida (Split View Desktop):**
     * **Painel Esquerdo (50%):** Histórico de chat com o modelo de IA, renderização markdown de código e campo de mensagem com suporte a envio por `Enter`.
     * **Painel Direito (50%):** Iframe carregando a aplicação web selecionada no seletor (com botões de reload e abrir em nova aba).
  3. **Gaveta de Terminal (Drawer Inferior):**
     * Terminal em estilo monospace preto com botões de atalho de 1 toque (ex: `[git status]`, `[nvidia-smi]`, `[status serviços]`).
     * Campo para digitar comandos manuais permitidos pela whitelist.
  4. **Modo Mobile (Smartphones):**
     * Os painéis se convertem automaticamente em abas acessíveis no rodapé (`Tabs`):
       * `[ 💬 Chat ]`
       * `[ 🖥️ App Preview ]`
       * `[ ⌨️ Terminal ]`
