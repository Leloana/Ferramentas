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
- [docs/guides/PLANO_SERVIDOR.md](docs/guides/PLANO_SERVIDOR.md) (Roteiro no servidor: preparar, reprocessar o acervo, sessões de teste gravadas e anotadas)
- [docs/guides/AUDIO_PIPELINE_MELHORIAS.md](docs/guides/AUDIO_PIPELINE_MELHORIAS.md) (Revisão do pipeline de áudio: o que já foi feito e o que calibrar no servidor)
- [docs/archive/FRONT_REDESIGN_2026-09.md](docs/archive/FRONT_REDESIGN_2026-09.md) (Histórico do redesign do front e dos recursos de festa)

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
| `KARAOKE_PUBLIC_URL` | URL pública usada nos QR Codes (atrás do túnel). Sem ela, o QR usa o IP da rede local quando a TV está em `localhost`/IP, ou o próprio domínio. | `https://karaoke.myall.net.br` | — |
| `KARAOKE_HOST` / `KARAOKE_PORT` | Endereço e porta de escuta ao rodar `python server/main.py`. Atrás do túnel, use `127.0.0.1`. | `127.0.0.1` / `8000` | `0.0.0.0` / `8000` |
| `KARAOKE_WHISPER_MODEL` | Modelo do faster-whisper usado ao vivo e no preparo. | `small` | `large-v3-turbo` |
| `KARAOKE_WHISPER_DEVICE` | `auto` tenta CUDA e cai na CPU. `cpu` força o perfil leve. | `cpu` | `auto` |
| `KARAOKE_WHISPER_COMPUTE` | Força o compute_type. Sem ela: `float16` na GPU, `int8` na CPU. | `int8_float16` | — |
| `KARAOKE_DEMUCS_MODEL` | Modelo do Demucs na separação voz × instrumental. | `htdemucs_ft` | `htdemucs` |
| `KARAOKE_MP3_BITRATE` | Bitrate dos MP3 de voz e instrumental. | `256k` | `320k` |
| `KARAOKE_RECORD` / `KARAOKE_RECORD_DIR` | Grava as partidas (voz de cada celular + o que o Whisper ouviu) para calibrar a nota. `0` desliga. | `0` / `D:/gravacoes` | ligado / `recordings/` |
| `KARAOKE_PLAYERS_DIR` | Pasta dos perfis dos cantores (os testes usam uma temporária). | `D:/perfis` | `players/` |

Servidor final via Cloudflare Tunnel (`karaoke.myall.net.br`): checklist pendente em [docs/guides/TODO_SERVIDOR_FINAL.md](docs/guides/TODO_SERVIDOR_FINAL.md).

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

Suíte completa (unitários, integração HTTP/WebSocket e partidas gravadas):
```bash
.\venv\Scripts\python.exe -m pytest -q tests
```
`tests/test_escolta_vagalumes.py` precisa do áudio real de uma música e de CUDA. Os testes das telas
(`tests/ui/`) usam Playwright sobre o preview e são pulados sem ele:
```bash
pip install playwright && python -m playwright install chromium
python -m pytest tests/ui
```

## 👀 Ver o front sem GPU

`python tools/preview_front.py --host 0.0.0.0` serve o front em `http://<ip>:8765` com dados de exemplo
(músicas de `server/songs/*/meta.json`, perfis fictícios, fila fictícia). Não há WebSocket: serve para
ver telas, abas, modais, navegação por controle remoto (`/?tv=1`) e o celular-microfone (`/?role=mic&room=1234`).

---

## 📂 Estrutura do Projeto

```
karaoke/
├── client/                         # Código estático do frontend (sem build step)
│   ├── index.html                  # Esqueleto; parciais em client/partials/ (montados pelo servidor)
│   ├── partials/                   # Uma tela/modal por arquivo
│   ├── assets/art/                 # Artes SVG próprias
│   ├── js/                         # Módulos ES Modules Vanilla JS (até ES2018, TV antiga)
│   │   ├── main.js                 # Bootstrap: identifica display vs microfone
│   │   ├── state.js                # Objeto central de estado compartilhado
│   │   ├── config.js               # Constantes de configuração do cliente
│   │   ├── dom.js                  # Helpers de manipulação do DOM
│   │   ├── toast.js                # Notificações toast de UI
│   │   ├── modal.js                # Gerenciador único de modais (abrir/fechar, ESC, clique fora, botão voltar)
│   │   ├── tabs.js                 # Helper declarativo de abas (reaproveitado em todos os seletores)
│   │   ├── modals.js               # "Adicionar música" (busca no YouTube), editor e pareamento
│   │   ├── youtube-search.js       # Busca no YouTube pelo nome
│   │   ├── lobby.js                # Lobby: vagas com microfone + time (dupla/trio)
│   │   ├── score-bars.js           # Placar por time nas bordas da TV
│   │   ├── verse-stamp.js          # Carimbo por verso (Na mosca · Quase · Fora)
│   │   ├── turns.js                # Revezar versos (duelo)
│   │   ├── requests.js             # Fila da noite ("quero cantar") e próxima automática
│   │   ├── share-card.js           # Cartão 4:5 para print no fim de jogo
│   │   ├── replay.js               # Ouvir a própria apresentação
│   │   ├── profile-view.js         # Ranking e perfil dos cantores
│   │   ├── players-modal.js        # Modal "Cantores" da TV
│   │   ├── cover-picker.js         # Trocar a capa entre as opções encontradas
│   │   ├── song-preview.js         # Ouvir 12 s do refrão na lista
│   │   ├── guide-vocal.js          # Voz guia (vocal separado baixinho)
│   │   ├── wake-lock.js            # Tela sempre acesa (celular e TV)
│   │   ├── status-panel.js         # Painel de saúde (clique no "Online")
│   │   ├── html.js                 # escapeHtml (texto de usuário nunca vai cru para o HTML)
│   │   ├── icons.js                # Ícones próprios em SVG
│   │   ├── select.js               # Select personalizado
│   │   ├── tv-nav.js               # Navegação por controle remoto
│   │   ├── compat.js               # Polyfills para TV antiga
│   │   ├── selection-view.js       # Repertório e lobby da música (capa + cantor)
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
│       └── *.css                   # Estilos por área (partitura antiga, tons pastéis)
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
│   ├── score_engine.py             # Motor de pontuação (fuzzy, normalização por idioma, timing)
│   ├── stt_engine.py               # Faster-Whisper (fallback CUDA → CPU, VAD, duas passadas)
│   ├── pitch.py                    # Afinação (YIN): pitch.json e "tom X%" por verso
│   ├── players.py                  # Perfis, recordes e ranking dos cantores
│   ├── song_requests.py            # Fila da noite por sala
│   ├── recorder.py                 # Gravação das partidas (calibração da nota)
│   ├── routes/                     # Rotas REST HTTP
│   │   ├── songs.py                # Listagem, deleção e reinstalação de músicas
│   │   ├── lyrics.py               # Leitura e salvamento de letras LRC
│   │   ├── upload.py               # Upload de arquivo ou URL YouTube
│   │   ├── queue.py                # Gerenciamento da fila de processamento
│   │   ├── players.py              # /api/players (ranking e perfil)
│   │   ├── recordings.py           # Gravações: anotar versos e ouvir a voz gravada
│   │   └── status.py               # /api/status (painel de saúde)
│   ├── utils/                      # Helpers internos
│   │   ├── audio.py                # Conversão de PCM Float32 para 16kHz Mono
│   │   ├── lrc_align.py            # Alinhamento de letras via Whisper
│   │   ├── lrc_pro.py              # Alinhamento forçado via MMS_FA, linha por linha, com confiança
│   │   ├── alignment_quality.py    # Nota da sincronia → needs_review ("Revisar")
│   │   ├── segment_timing.py       # Casamento letra × Whisper e ajuste dos versos
│   │   ├── separation.py           # Demucs (uma separação por vez) + MP3
│   │   ├── loudness.py             # Volume do instrumental (~−16 LUFS)
│   │   ├── cover.py                # Capa (iTunes + Deezer + YouTube, escolhível)
│   │   ├── song_paths.py           # Slug seguro (nunca sai de songs/)
│   │   └── youtube.py              # Download e extração de metadados do YouTube
│   └── ws/
│       └── room.py                 # WebSocket bidirecional (handshake e game loop)
├── tools/                          # Scripts CLI e ferramentas offline
│   ├── prepare_song.py             # Fatiador de áudio e alinhador word-level (gera segments.json)
│   ├── replay_recording.py         # Repassa uma partida gravada pelo Whisper com outros parâmetros
│   └── preview_front.py            # Front sem GPU, com dados de exemplo
├── tests/                          # Suíte de Testes (unittest/pytest; tests/ui com Playwright)
└── requirements.txt                # Dependências Python
```

---

## 🎮 Funcionalidades Principais

| Funcionalidade | Descrição |
| :--- | :--- |
| **Multi-dispositivo** | TV como display, celular como microfone sem fio via QR Code |
| **Transcrição em Tempo Real** | Faster-Whisper com VAD, fallback automático CUDA → CPU |
| **Pontuação IA** | Fuzzy matching + normalização (acentos, contrações, números, hífen) + penalidades de timing; carimbo "Na mosca · Quase · Fora" por verso |
| **Afinação** | "Tom X%" por verso comparando a voz com a melodia do vocal separado (informativo, fora da nota até calibrar) |
| **Festa** | Lobby com vagas e times (dupla/trio), revezar versos (duelo), sortear cantor, fila da noite ("quero cantar") com próxima automática |
| **Perfis e recordes** | Ranking "Cantores", perfil com recordes por música, recorde pessoal e melhor da sala no fim de jogo |
| **Fim de jogo** | Cartão 4:5 para print (TV e celular), ouvir a própria apresentação |
| **Voz guia** | Vocal separado tocando baixinho junto do instrumental, no mesmo tom |
| **Alinhamento Word-Level** | MMS_FA (PyTorch) linha por linha na janela do LRC, com confiança por palavra; música fraca aparece como "Revisar" |
| **Fila de Processamento GPU** | Download e Demucs durante a partida; gerar a letra espera o fim, e enquanto gera o INICIAR fica bloqueado (mutex de GPU) |
| **Capas** | Automáticas (iTunes + Deezer + YouTube, nota por artista/título) e escolhíveis no lobby |
| **Busca Automática de Letras** | Integração com LRCLIB e Lyrics.ovh para buscar LRC sincronizado |
| **Gerenciamento de Músicas** | Upload por arquivo ou URL YouTube, reinstalação e edição de letras |
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
  - *Solução:* Use o botão "Destravar GPU" na interface de fila, ou reinicie o servidor. O painel de saúde (clique no "Online" do cabeçalho) mostra se a GPU está ocupada e o tempo até a nota.
- **INICIAR bloqueado com "GPU ocupada":**
  - *Causa:* uma música está na etapa de gerar a letra (mutex de GPU, de propósito).
  - *Solução:* aguardar; o botão libera sozinho quando termina.
- **Hallucinações do Whisper em silêncio:**
  - *Causa:* Trechos silenciosos longos fazem o Whisper gerar texto repetitivo.
  - *Solução:* O gate de áudio RMS em `stt_engine.py` rejeita segmentos abaixo de `0.0018` de energia média.
