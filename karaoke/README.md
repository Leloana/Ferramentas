# 🎤 Karaoke AI Premium — Multi-Dispositivo & Sincronia IA

Um ecossistema moderno, de alto desempenho e alta fidelidade para Karaokê, projetado para rodar localmente com **transcrição fonética em tempo real (Whisper GPU/CPU)**, **cálculo de pontuação difuso por timing**, e uma arquitetura inovadora **Multi-Dispositivo** (use a TV da sala como tela/display e qualquer Celular conectado como microfone sem fios via WebSockets e QR Code!).

O projeto é altamente modular, limpo e com 100% de separação de responsabilidades.

---

## 🌟 Recursos de Destaque (Premium)

### 📺🎙️ Arquitetura Multi-Dispositivo
* **Modo TV (Tela/Display):** Um dispositivo com tela grande (TV ou Notebook) atua como console de exibição. Toca a faixa instrumental (`backing_track.mp3`), renderiza as letras dinâmicas e exibe as parciais e médias de pontuação enviadas pelo servidor.
* **Modo Microfone (Celular):** Qualquer smartphone na mesma rede Wi-Fi escaneia o **QR Code** gerado na TV e se transforma instantaneamente em um microfone de baixíssima latência. Utiliza a API nativa de `AudioWorklet` do navegador para capturar e enviar pacotes binários PCM Float32 diretamente ao servidor.

### 🎥 Dupla Importação e Download Inteligente
* **Download Paralelo de Alta Velocidade:** Insira a **URL do Vídeo Vocal (Original)** e a **URL do Vídeo Instrumental (Karaokê)**. O servidor faz os downloads em concorrência paralela via `asyncio.gather` e `yt-dlp`, poupando tempo de rede.
* **Resiliência Windows-Locked:** Totalmente tolerante a falhas do Windows no encerramento e remoção de arquivos temporários, com conversão profissional de áudio via `pydub` (MP3 192kbps) e expurgo automático de resíduos (`.webm`, `.m4a`, `.part`).

### ⚙️ Alinhamento Fino & Tratamento de Latência
* **Silêncio de Preparação (Padding):** Adicione um atraso de silêncio no início das faixas para dar tempo de inicializar os fluxos de áudio e preparar o cantor.
* **Ajuste LRC da IA (LRC Offset):** Use a diretriz **"Início vocal na letra"** para deslocar de forma inteligente todas as marcações de tempo em introduções instrumentais longas, evitando atrasos acumulados de pontuação.

### ⚖️ Motor de Pontuação Avançado
* **Comparação Fonética (Fuzzy matching):** Baseada no algoritmo `rapidfuzz` (`fuzz.token_sort_ratio`) para identificar a canção mesmo sob pequenas distorções de captura.
* **Ajustes Fonéticos por Idioma:** Mapas acústicos dedicados para Inglês e Português para evitar colisões fonéticas inter-idiomas (ex: `"a" -> "ah"` em português, contrações em inglês).
* **Perdão de Vazamento (Leakage Forgiveness):** O motor de pontuação detecta se o final do verso anterior vazou para a janela atual e remove automaticamente esse ruído para garantir avaliação justa.
* **Sandwich Recovery**: Recupera automaticamente uma ou duas palavras falhadas/não capturadas se estiverem circundadas por palavras cantadas corretamente.

---

## 📂 Estrutura de Diretórios e Guias do Desenvolvedor

A base de código está dividida em camadas perfeitamente desacopladas. Para detalhes completos de engenharia, consulte nossos guias internos dedicados:
*   📖 **Guia Mestre de Arquitetura e Contratos**: Veja em [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md) as especificações de rede, modelo do segments.json e restrições.
*   📖 **Arquitetura Técnica do Client (Frontend)**: Veja em [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) o padrão de ES Modules, estado mutável compartilhado e controle CSS de estados.
*   📖 **Histórico de Refatoração do Backend**: Veja em [docs/BACKEND_REFACTOR_NOTES.md](docs/BACKEND_REFACTOR_NOTES.md) como o monolito do servidor foi decomposto em routers assíncronos.

---

## 🛠️ Guia de Instalação e Execução (Passo a Passo)

Siga os passos abaixo para preparar o ambiente virtual do Python, instalar as dependências necessárias (com suporte a CPU ou GPU NVIDIA/CUDA) e executar o projeto.

### Passo 1: Criar o Ambiente Virtual (venv)
Na pasta raiz do projeto (`karaoke`), execute o comando para criar um ambiente virtual isolado para as dependências do Python:

```powershell
# No Windows (PowerShell ou CMD)
python -m venv venv
```

```bash
# No Linux / macOS
python3 -m venv venv
```

### Passo 2: Ativar o Ambiente Virtual
Ative o ambiente virtual para garantir que todos os comandos `pip` e `python` subsequentes operem dentro do escopo do projeto:

* **Windows PowerShell:**
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
  *(Se você receber um erro de permissão de scripts no PowerShell, execute primeiro `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` e tente ativar novamente).*

* **Windows Prompt de Comando (CMD):**
  ```cmd
  .\venv\Scripts\activate.bat
  ```

* **Linux / macOS:**
  ```bash
  source venv/bin/activate
  ```

### Passo 3: Instalar as Dependências
Com o ambiente virtual ativado, prossiga com a instalação dos pacotes. 

#### Opção A: Instalação Padrão (CPU)
Para rodar em modo CPU (indicado para computadores sem GPU NVIDIA dedicada):
```bash
pip install -r requirements.txt
```

#### Opção B: Instalação Acelerada por GPU (NVIDIA CUDA - Recomendado)
Se você possui uma GPU NVIDIA (ex: RTX 4070) e deseja aceleração por hardware para a separação de voz (Demucs) e transcrição (Faster-Whisper), instale as wheels oficiais do PyTorch com suporte para CUDA 12.4:
```bash
# 1. Instala todas as dependências base do requirements.txt
pip install -r requirements.txt

# 2. Força a instalação do PyTorch e Torchaudio compilados com CUDA 12.4
pip install --force-reinstall torch torchaudio --index-url https://download.pytorch.org/whl/cu124
```

*Nota: Certifique-se de que os drivers da sua placa NVIDIA e o kit de ferramentas CUDA correspondente estejam instalados e atualizados no seu sistema operacional.*

---

## 🚀 Como Executar o Servidor

Para que dispositivos móveis (como celulares) conectados na rede Wi-Fi consigam acessar a página e capturar o áudio do microfone, os navegadores modernos exigem que o servidor rode obrigatoriamente sob **HTTPS** (Contexto Seguro).

Fornecemos os certificados de desenvolvimento `key.pem` e `cert.pem` na pasta `server/`.

### 1. Subir o Servidor Uvicorn
Com o ambiente virtual ativado, suba o servidor FastAPI:

* **No Windows (PowerShell) - Libera a porta 8000 automaticamente e inicia o servidor:**
  ```powershell
  Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }; .\venv\Scripts\python.exe -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --ssl-keyfile server/key.pem --ssl-certfile server/cert.pem
  ```

* **No Linux / macOS:**
  ```bash
  python -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --ssl-keyfile server/key.pem --ssl-certfile server/cert.pem
  ```

### 2. Acessar o Sistema
* **Na TV ou Computador Principal:** Abra o navegador e acesse [https://localhost:8000](https://localhost:8000).
* **Alerta de Segurança (Autoassinado):** Por se tratar de um certificado de testes local, clique em **"Avançado"** e em **"Prosseguir para localhost (inseguro)"**. Isso é necessário apenas no primeiro acesso para liberar a transmissão de áudio.
* **Pareamento do Celular (Microfone):** O display exibirá um **QR Code**. Escaneie-o com a câmera do seu celular (conectado na mesma rede Wi-Fi) para pareá-lo instantaneamente como microfone!

---

## 🎵 Gerenciamento de Canções via CLI

Você também pode reinstalar e reprocessar músicas diretamente pela linha de comando usando a ferramenta `reinstall_song.py`.

### 1. Transcrição Direta (Whisper Puro - Padrão)
Gera o arquivo `lyrics.lrc` com a transcrição direta feita pela inteligência artificial sem forçar o alinhamento com a letra textual em `plain_lyrics`.
```bash
python tools/reinstall_song.py server/songs/lift-radiohead
```

### 2. Alinhamento de Letra Plana
Cruza a letra salva em `meta.json` / `lyrics.txt` com as posições de tempo da voz utilizando alinhamento fonético avançado:
```bash
python tools/reinstall_song.py server/songs/lift-radiohead --align-lyrics
```

---

## 🧠 Tecnologias Utilizadas
* **Backend:** FastAPI (APIRouter desacoplado), Uvicorn SSL, Faster-Whisper, RapidFuzz, Demucs.
* **Frontend:** Vanilla JS nativo (ES Modules, Web Audio API, AudioWorkletProcessor de PCM em baixa latência), HTML5, CSS3.
* **Processamento Acústico:** PyAV, Pydub, Scipy (Downsampling de microfone em tempo real).
