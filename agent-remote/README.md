# 🌐 Agent-Remote — Controle Web Remoto do PC & Central de Aplicações

O **Agent-Remote** é uma interface web minimalista, ágil e segura para controlar o seu computador e interagir com o agente de IA local à distância (via celular, tablet ou outro computador), utilizando um túnel criptografado **Cloudflare Tunnel**.

O objetivo central é transformar o ecossistema de ferramentas locais em uma central unificada: você escolhe a ferramenta alvo, digita uma senha de acesso e tem em mãos uma visão em **duas abas / split-screen** — de um lado o **chat com o agente**, do outro a **aplicação funcionando em tempo real**.

---

## 🎯 Por que foi criado?

1. **Acesso Móvel sem Complicação:** Controlar execuções de scripts (ex: geração de vídeos do `tts_platform_pt`, checagem de VRAM, status do git) direto da tela do smartphone, sem precisar ficar na frente do PC.
2. **Duas Abas / Split View Integrado:** Inspirado em plataformas modernas como *Bolt.new* e *OpenHands*, reúne a conversa com o agente e o iframe da aplicação ativa em uma única interface.
3. **Segurança por Padrão (Sem Abrir Portas no Roteador):** Utiliza o Cloudflare Tunnel (`cloudflared`), fornecendo uma URL pública HTTPS gratuita (`.trycloudflare.com`) sem expor IP, sem redirecionamento de portas (port forwarding) e com proteção por senha.
4. **Terminal Web Seguro (Whitelist):** Um terminal leve embutido no navegador, restrito estritamente a comandos pré-aprovados (evitando riscos de injeção de comandos arbitrários pela web).
5. **Zero Complexidade:** Nada de dezenas de containers Docker ou frameworks pesados. É uma aplicação Python única (FastAPI) com frontend em HTML/CSS/JS puro, rápida para carregar em redes móveis 4G/5G.

---

## 🏛️ Visão Geral da Interface

```
+---------------------------------------------------------------------------------+
| [🌐 Agent-Remote]   [Projeto: tts_platform_pt ▼]   [VRAM: 8.2/12 GB]   [Sair]  |
+----------------------------------------+----------------------------------------+
| 💬 ABA 1: CHAT COM O AGENTE (Ollama)   | 🖥️ ABA 2: APLICAÇÃO ATIVA (Preview)    |
|                                        |                                        |
| [Usuário]: Gere o vídeo do Musashi.    |  +----------------------------------+  |
|                                        |  | Preview do App (ex: porta 8011)   |  |
| [Agente]: Iniciando produção em lote   |  |                                  |  |
| com o script executar_projeto.py.      |  |  [Interface Web do TTS / Vídeos] |  |
| Acompanhe pelo terminal abaixo!        |  |  Status: Renderizando cena 3/10  |  |
|                                        |  +----------------------------------+  |
|                                        |                                        |
+----------------------------------------+----------------------------------------+
| ⌨️ TERMINAL EMBUTIDO (Comandos permitidos: git, executar_projeto, nvidia-smi...)  |
| $ python scripts/executar_projeto.py Projetos/Video_11/musashi_duelo_ganryujima |
| [OK] Áudio XTTS sintetizado com sucesso. Submetendo prompts ao ComfyUI...       |
+---------------------------------------------------------------------------------+
```

> 📱 **No Celular:** A interface se adapta automaticamente em abas deslizantes de toque único: `[ 💬 Chat ]`, `[ 🖥️ App ]` e `[ ⌨️ Terminal ]`.

---

## 🚀 Como Funciona (Fluxo de Uso)

1. **Na máquina do PC:**
   Execute o inicializador único:
   ```bash
   python run.py
   ```
2. **Geração do Acesso Remoto:**
   O script inicia o servidor local FastAPI e o Cloudflare Tunnel em segundo plano, imprimindo no terminal:
   * A URL pública HTTPS temporária gerada (ex: `https://alpha-beta-gamma.trycloudflare.com`).
   * Um **QR Code ASCII** no próprio terminal para escanear direto com a câmera do celular.
3. **No Navegador / Celular:**
   * Abra a URL ou escaneie o QR Code.
   * Digite a senha configurada no `config.json` ou `.env`.
   * Escolha a ferramenta que deseja acompanhar (ex: `tts_platform_pt`, `karaoke`, etc.).
   * Converse com o agente e veja a aplicação rodando lado a lado.

---

## 📂 Documentação Completa

| Documento | Descrição |
| --- | --- |
| [**ARQUITETURA.md**](./ARQUITETURA.md) | Detalhamento da arquitetura técnica, lições de projetos existentes (OpenHands, Bolt.new, ttyd) e modelo de segurança. |
| [**GUIA_CLOUDFLARE.md**](./GUIA_CLOUDFLARE.md) | Passo a passo de instalação do `cloudflared`, uso de Quick Tunnels gratuitos e túneis permanentes. |
| [**COMANDOS_WHITELIST.md**](./COMANDOS_WHITELIST.md) | Catálogo e regras de segurança da whitelist de comandos do terminal web. |
| [**PLANO_IMPLEMENTACAO.md**](./PLANO_IMPLEMENTACAO.md) | Roteiro prático passo a passo para a codificação leve do sistema. |

---

## 🛠️ Stack Tecnológica Recomendada

* **Backend:** Python 3.10+ com **FastAPI** + **Uvicorn** (suporte nativo a WebSockets assíncronos e SSE).
* **IA Local:** Integração direta com a API do **Ollama** local (`http://127.0.0.1:11434`), aproveitando modelos com bom raciocínio e tool calling como `qwen3.5:9b`.
* **Túnel Seguro:** **Cloudflare Tunnel (`cloudflared`)** oficial.
* **Frontend:** Vanilla HTML5, CSS3 flexbox moderno e JavaScript moderno (ES6 modules). Zero bundlers, zero compilação (npm/webpack), carregamento instantâneo.
