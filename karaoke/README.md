# 🎤 Karaoke AI Premium — Multi-Device & Sincronia IA

Um ecossistema de alto desempenho para Karaokê projetado para rodar localmente com transcrição fonética em tempo real (Whisper GPU/CPU), cálculo de pontuação difuso por timing e uma arquitetura multi-dispositivo. Use a TV da sala como console de exibição (Display) e qualquer celular conectado na mesma rede Wi-Fi como microfone sem fio via WebSockets e QR Code.

---

## 🏛️ Visão Geral da Arquitetura

O sistema é dividido em camadas perfeitamente desacopladas:
- **Frontend (Console/Mobile):** Desenvolvido em HTML5/CSS3 e Vanilla JavaScript (ES Modules, Web Audio API e AudioWorklet Processor). Sem build step — arquivos servidos diretamente pelo FastAPI.
- **Backend (FastAPI):** Gerencia conexões WebSocket, roteamento de áudio PCM, transcrição Whisper, alinhamento forçado MMS_FA e pontuação. Inclui um sistema de fila de processamento de GPU para downloads e separação de stems.
- **Armazenamento:** Músicas são salvas no disco local sob `server/songs/`, e perfis de cantores ficam salvos sob `players/`.

Para especificações detalhadas, diagramas de componentes e contratos, consulte os guias em:
- [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) (Arquitetura Completa e Contratos do Sistema)
- [docs/architecture/FLOW.md](docs/architecture/FLOW.md) (Fluxos de Upload, Edição e Sincronização)
- [docs/architecture/MULTIPLAYER_FLOW.md](docs/architecture/MULTIPLAYER_FLOW.md) (Handshake Multi-player e WebSocket Game Loop)
- [docs/guides/PROJECT_GUIDE.md](docs/guides/PROJECT_GUIDE.md) (Guia do Projeto & Fonte da Verdade de Engenharia)
- [docs/guides/LRC_ALIGNMENT_TUNING.md](docs/guides/LRC_ALIGNMENT_TUNING.md) (Playbook de Solução de Timestamps e Ajuste LRC)

---

## 📋 Pré-requisitos

- **Sistema Operacional:** Windows (preferencial) / Linux / macOS.
- **Runtime:** Python 3.10 ou superior (3.11 / 3.12 recomendados).
- **Ferramentas Externas:** FFmpeg (injetado no PATH automaticamente no Windows se instalado via Winget).
- **Hardware (Opcional, mas altamente recomendado):** Placa de vídeo NVIDIA (RTX 30/40 series) com CUDA 12.4 para acelerar a separação (Demucs) e transcrição (Faster-Whisper).

---

## 🔧 Instalação Passo a Passo

Siga as etapas para criar o ambiente virtual, instalar dependências e inicializar os módulos:

### 1. Criar o Ambiente Virtual (venv)
Na raiz do projeto (`karaoke`), execute:
```powershell
# No Windows (PowerShell/CMD)
python -m venv venv
```
```bash
# No Linux / macOS
python3 -m venv venv
```

### 2. Ativar o Ambiente Virtual
- **Windows PowerShell:**
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
- **Windows Prompt de Comando (CMD):**
  ```cmd
  .\venv\Scripts\activate.bat
  ```
- **Linux / macOS:**
  ```bash
  source venv/bin/activate
  ```

### 3. Instalar Dependências
- **Opção A: Instalação Padrão (CPU)**
  ```bash
  pip install -r requirements.txt
  ```
- **Opção B: Instalação Acelerada por GPU (NVIDIA CUDA 12.4)**
  ```bash
  # 1. Instala dependências do requirements.txt
  pip install -r requirements.txt

  # 2. Força instalação do PyTorch e Torchaudio compilados com CUDA 12.4
  pip install --force-reinstall torch torchaudio --index-url https://download.pytorch.org/whl/cu124
  ```

---

## ⚙️ Configurações

O backend suporta as seguintes variáveis de ambiente:

| Variável | Descrição | Exemplo | Padrão |
| :--- | :--- | :--- | :--- |
| `KARAOKE_HTTP` | Desativa a verificação de arquivos SSL key.pem/cert.pem locais, forçando inicialização puramente em HTTP. Ideal para túneis reverso (ex. Cloudflare Tunnel). | `true` | `false` |

---

## 🚀 Como Executar

No Windows (PowerShell), execute o comando único abaixo para rodar o projeto. Ele irá encerrar qualquer processo ativo na porta 8000, ativar a `venv` e iniciar o servidor em HTTPS no IP `192.168.15.6:8000`:

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }; .\venv\Scripts\Activate.ps1; uvicorn server.main:app --host 192.168.15.6 --port 8000 --reload --ssl-keyfile "server/key.pem" --ssl-certfile "server/cert.pem"
```

> Troque `192.168.15.6` pelo IP da sua máquina na rede Wi-Fi (use `ipconfig` no Windows ou `hostname -I` no Linux).

Acesse `https://192.168.15.6:8000` nos dispositivos da rede para conectar. Para o guia operacional completo (Linux/macOS, modo HTTP, túnel e troubleshooting), veja [.claude/karaoke/Executar.md](.claude/karaoke/Executar.md).

---

## 🧪 Como Executar os Testes

Execute a suíte completa de testes unitários e de integração com o comando:
```bash
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

---

## 📂 Estrutura do Projeto

```
karaoke/
├── client/                         # Código estático do frontend (sem build step)
│   ├── index.html                  # Interface principal (modais e templates HTML)
│   ├── js/                         # Módulos ES Modules Vanilla JS
│   │   ├── main.js                 # Bootstrap: identifica display vs microfone
│   │   ├── state.js                # Objeto central de estado compartilhado
│   │   ├── config.js               # Constantes de configuração do cliente
│   │   ├── dom.js                  # Helpers de manipulação do DOM
│   │   ├── toast.js                # Notificações toast de UI
│   │   ├── modal.js                # Gerenciador único de modais (abrir/fechar, ESC, clique fora, botão voltar)
│   │   ├── tabs.js                 # Helper declarativo de abas (reaproveitado em todos os seletores)
│   │   ├── modals.js               # Lógica de todos os modais da aplicação
│   │   ├── selection-view.js       # Tela de seleção de músicas
│   │   ├── game-view.js            # Renderização da letra e animações de gameplay
│   │   ├── queue-view.js           # Interface da fila de processamento de músicas
│   │   ├── mobile-mic-view.js      # Interface do microfone no celular
│   │   ├── audio-lifecycle-manager.js # Gerenciamento do ciclo de vida do áudio
│   │   ├── mic-stream.js           # Captura e streaming de áudio do microfone
│   │   ├── mic-status.js           # Indicador de status do microfone
│   │   ├── sync.js                 # Sincronização de tempo display ↔ microfone
│   │   ├── jungle.js               # Pitch shifter (Web Audio API)
│   │   ├── ws-display.js           # WebSocket do Display (TV)
│   │   ├── ws-mic.js               # WebSocket do Microfone (Celular)
│   │   └── worklets/
│   │       └── audio-processor.js  # AudioWorklet: coleta PCM Float32 bruto
│   └── styles/
│       └── main.css                # Estilos visuais (Neon Glow, BEM)
├── docs/                           # Documentação técnica e operacional
│   ├── architecture/               # Especificações de arquitetura e fluxos de rede
│   ├── guides/                     # Manuais e playbooks (Guia do Projeto, LRC Tuning)
│   └── archive/                    # Documentos arquivados, históricos e rascunhos antigos
├── players/                        # Perfis e histórico persistidos de cantores
├── server/                         # Código do Backend FastAPI
│   ├── main.py                     # Ponto de entrada do Servidor (Uvicorn)
│   ├── state.py                    # Singletons compartilhados (evita imports circulares)
│   ├── rooms.py                    # Modelo da sala de canto (KaraokeRoom, buffers por jogador)
│   ├── song_manager.py             # Gerenciador de músicas no disco
│   ├── queue_manager.py            # Fila de downloads/processamento GPU (async)
│   ├── score_engine.py             # Motor de pontuação (fuzzy, Double Metaphone, timing)
│   ├── stt_engine.py               # Faster-Whisper (fallback CUDA → CPU, VAD)
│   ├── routes/                     # Rotas REST HTTP
│   │   ├── songs.py                # Listagem, deleção e reinstalação de músicas
│   │   ├── lyrics.py               # Leitura e salvamento de letras LRC
│   │   ├── upload.py               # Upload de arquivo ou URL YouTube
│   │   └── queue.py                # Gerenciamento da fila de processamento
│   ├── utils/                      # Helpers internos
│   │   ├── audio.py                # Conversão de PCM Float32 para 16kHz Mono
│   │   ├── lrc_align.py            # Alinhamento de letras via Whisper
│   │   ├── lrc_pro.py              # Alinhamento forçado via MMS_FA (PyTorch)
│   │   └── youtube.py              # Download e extração de metadados do YouTube
│   └── ws/
│       └── room.py                 # WebSocket bidirecional (handshake e game loop)
├── tools/                          # Scripts CLI e ferramentas offline
│   └── prepare_song.py             # Fatiador de áudio e alinhador word-level (gera segments.json)
├── tests/                          # Suíte de Testes (unittest)
└── requirements.txt                # Dependências Python
```

---

## 🎮 Funcionalidades Principais

| Funcionalidade | Descrição |
| :--- | :--- |
| **Multi-dispositivo** | TV como display, celular como microfone sem fio via QR Code |
| **Transcrição em Tempo Real** | Faster-Whisper com VAD, fallback automático CUDA → CPU |
| **Pontuação IA** | Fuzzy matching + Double Metaphone + penalidades de timing por palavra |
| **Alinhamento Word-Level** | MMS_FA (PyTorch) para sincronização precisa sílaba a sílaba |
| **Fila de Processamento GPU** | Downloads e separação Demucs enfileirados, sem conflito de VRAM |
| **Busca Automática de Letras** | Integração com LRCLIB e Lyrics.ovh para buscar LRC sincronizado |
| **Gerenciamento de Músicas** | Upload por arquivo ou URL YouTube, reinstalação e edição de letras |
| **Perfis de Cantores** | Histórico persistido de notas por música e sessão |
| **HTTPS Automático** | Suporte a SSL local ou Cloudflare Tunnel para acesso seguro no mobile |

---

## ❌ Erros Comuns & Resolução

- **Erro `AttributeError: module 'routes.songs' has no attribute 'reinstall_song'` nos testes:**
  - *Causa:* Importações locais no router geravam caminhos de mock conflitantes.
  - *Solução:* Use a diretiva `@patch("tools.reinstall_song.reinstall_song")` nos testes.
- **WebSockets caindo ou áudio travando em conexões móveis:**
  - *Causa:* Conexão HTTP não-segura bloqueia a API `getUserMedia` em dispositivos móveis.
  - *Solução:* Garanta que o servidor está rodando em HTTPS (`key.pem` e `cert.pem` criados) ou utilize o Cloudflare Tunnel.
- **`ModuleNotFoundError: No module named 'rapidfuzz'`:**
  - *Causa:* Execução de testes usando o Python global em vez do executável da venv.
  - *Solução:* Use sempre `.\venv\Scripts\python.exe` para rodar scripts e testes.
- **Travamento da GPU / status preso em `busy`:**
  - *Causa:* Processo de reinstalação de música rodando em paralelo com o servidor pode travar o lock da GPU.
  - *Solução:* Use o botão "Destravar GPU" na interface de fila, ou reinicie o servidor.
- **Hallucinações do Whisper em silêncio:**
  - *Causa:* Trechos silenciosos longos fazem o Whisper gerar texto repetitivo.
  - *Solução:* O gate de áudio RMS em `stt_engine.py` rejeita segmentos abaixo de `0.0018` de energia média.
