# 🎤 Karaoke AI Premium — Multi-Device & Sincronia IA

Um ecossistema de alto desempenho para Karaokê projetado para rodar localmente com transcrição fonética em tempo real (Whisper GPU/CPU), cálculo de pontuação difuso por timing e uma arquitetura multi-dispositivo. Use a TV da sala como console de exibição (Display) e qualquer celular conectado na mesma rede Wi-Fi como microfone sem fio via WebSockets e QR Code.

---

## 🏛️ Visão Geral da Arquitetura

O sistema é dividido em camadas perfeitamente desacopladas:
- **Frontend (Console/Mobile):** Desenvolvido em HTML5/CSS3 e Vanilla JavaScript (ES Modules, Web Audio API, e AudioWorklet Processor).
- **Backend (FastAPI):** Gerencia conexões WebSocket, roteamento de áudio PCM, transcrição Whisper, alinhamento forçado MMS_FA e pontuação.
- **Armazenamento:** Músicas são salvas no disco local sob `server/songs/`, e perfis de cantores ficam salvos sob `players/`.

Para especificações detalhadas, diagramas de componentes e contratos, consulte os guias em:
- [docs/architecture/ARCHITECTURE.md](file:///c:/Users/mf827/Documents/Ferramentas/karaoke/docs/architecture/ARCHITECTURE.md) (Arquitetura Completa e Contratos do Sistema)
- [docs/architecture/FLOW.md](file:///c:/Users/mf827/Documents/Ferramentas/karaoke/docs/architecture/FLOW.md) (Fluxos de Upload, Edição e Sincronização)
- [docs/architecture/MULTIPLAYER_FLOW.md](file:///c:/Users/mf827/Documents/Ferramentas/karaoke/docs/architecture/MULTIPLAYER_FLOW.md) (Handshake Multi-player e WebSocket Game Loop)
- [docs/guides/PROJECT_GUIDE.md](file:///c:/Users/mf827/Documents/Ferramentas/karaoke/docs/guides/PROJECT_GUIDE.md) (Guia do Projeto & Fonte da Verdade de Engenharia)
- [docs/guides/LRC_ALIGNMENT_TUNING.md](file:///c:/Users/mf827/Documents/Ferramentas/karaoke/docs/guides/LRC_ALIGNMENT_TUNING.md) (Playbook de Solução de Timestamps e Ajuste LRC)

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
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }; .\venv\Scripts\Activate.ps1; uvicorn server.main:app --host 192.168.15.6 --port 8000 --reload --ssl-keyfile "C:\Users\mf827\Documents\Ferramentas\karaoke\server\key.pem" --ssl-certfile "C:\Users\mf827\Documents\Ferramentas\karaoke\server\cert.pem"
```

Acesse `https://192.168.15.6:8000` nos dispositivos da rede para conectar.

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
├── client/                     # Código estático do frontend
│   ├── index.html              # Interface principal do Karaokê
│   ├── js/                     # Scripts modulares Vanilla JS
│   │   ├── main.js             # Ponto de entrada do cliente
│   │   ├── ws-display.js       # WebSocket da TV
│   │   ├── ws-mic.js           # WebSocket do Celular
│   │   └── worklets/
│   │       └── audio-processor.js # Coleta de áudio do AudioWorklet
│   └── styles/
│       └── main.css            # Estilos visuais e Neon Glow
├── docs/                       # Documentação técnica e operacional
│   ├── architecture/           # Especificações de arquitetura e fluxos de rede
│   ├── guides/                 # Manuais e playbooks (Guia do Projeto, LRC Tuning)
│   └── archive/                # Documentos arquivados, históricos e rascunhos antigos
├── players/                    # Perfis e histórico persistidos de cantores
├── server/                     # Código do Backend FastAPI
│   ├── routes/                 # Rotas REST HTTP (songs, lyrics, upload)
│   ├── utils/                  # Utilitários (MMS_FA alignment, youtube, audio)
│   ├── ws/
│   │   └── room.py             # WebSocket das salas (handshake e game loop)
│   ├── main.py                 # Ponto de entrada do Servidor
│   └── state.py                # Singletons compartilhados
├── tests/                      # Suíte de Testes
└── requirements.txt            # Dependências Python
```

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
