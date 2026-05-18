# 🎤 Karaoke AI Premium — Multi-Dispositivo & Sincronia IA

Um ecossistema moderno e de alta fidelidade para Karaokê, projetado para rodar localmente com **transcrição fonética em tempo real (Whisper GPU)**, **cálculo de pontuação difuso por timing**, e uma arquitetura inovadora **Multi-Dispositivo** (use a TV da sala como tela e o Celular como microfone sem fios via WebSockets e QR Code!).

---

## 🌟 Recursos de Destaque (Premium)

### 📺🎙️ Arquitetura de Pareamento Multi-Dispositivo
* **Modo TV (Tela/Display):** Um dispositivo com tela grande (TV com PC conectado ou Notebook) pode ser configurado apenas como tela de exibição. Ele toca o som instrumental (`backing_track.mp3`), exibe o progresso das letras e as pontuações em tempo real.
* **Modo Microfone (Celular):** Qualquer smartphone conectado na mesma rede WiFi lê o **QR Code** gerado na TV e se transforma instantaneamente em um microfone de baixa latência, enviando amostras de áudio de voz em tempo real via WebSockets para transcrição pesada de IA no servidor.

### 🎥 Dupla Importação Direta do YouTube
* **Download Concorrente de Alta Velocidade:** Insira a **URL do Vídeo Vocal (Original)** e a **URL do Vídeo Instrumental (Karaokê)**. O servidor realiza downloads simultâneos em paralelo via `asyncio.gather` e `yt-dlp`, reduzindo o tempo de espera pela metade.
* **Resiliência Windows-Locked:** Totalmente tolerante a falhas do Windows no encerramento de arquivos residuais, com conversão de áudio para MP3 (192kbps) e limpeza automática inteligente de arquivos órfãos (`.webm`, `.m4a`, `.part`).

### ⚙️ Alinhamento Fino & Tratamento de Latência
* **Silêncio Inicial (Padding):** Adicione um tempo de silêncio (ex: `1.5s`) no início das faixas para dar tempo de o navegador inicializar o fluxo de áudio e o cantor se preparar.
* **Ajuste LRC da IA (LRC Offset):** Se o Whisper transcrever uma música que começa direto com uma introdução instrumental longa, use o campo **"Início vocal na letra"** para empurrar de forma inteligente todas as marcações de tempo e evitar o efeito bola de neve de atraso na pontuação.

### 🔍 Busca em Tempo Real
* Interface administrativa elegante com pesquisa instantânea por **Título da Música** ou **Nome do Artista/Banda**.

### ⚖️ Motor de Pontuação Difuso & Timing Fino
* **Comparação Fonética:** Baseada na biblioteca `rapidfuzz` (`fuzz.ratio`) para identificar o canto mesmo com pequenas variações.
* **Penalidade Suave de Ritmo (Timing):** O motor de pontuação monitora a diferença absoluta de segundos do canto:
  * Diferença $< 0.5s$: Perfeito ($100\%$ de pontuação para a palavra).
  * Diferença $< 1.0s$: Tolerância leve ($30\%$ de penalidade na palavra).
  * Diferença $< 2.0s$: Tolerância limite ($60\%$ de penalidade na palavra).
* **Parciais Justas:** Removemos o bloqueio antigo de zerar a frase inteira por "muitas palavras perdidas". O usuário sempre ganha pontos proporcionais às palavras cantadas no ritmo, tornando o jogo muito mais divertido e gratificante!

---

## 🚀 Como Iniciar em 3 Passos

### 1. Instalar Dependências e FFmpeg
Certifique-se de que o Python 3.10+ e o FFmpeg (adicionado ao PATH) estão instalados:
```bash
pip install fastapi "uvicorn[standard]" faster-whisper rapidfuzz numpy pydub python-multipart scipy yt-dlp av
```

### 2. Rodar o Servidor Exposto na Rede (Modo HTTPS Seguro 🔒)
Para que os navegadores modernos (Chrome, Safari, Edge) no PC e no Celular **permitam o uso do microfone** em conexões de rede local (Wi-Fi), a página deve ser executada obrigatoriamente sob **HTTPS** (Contexto Seguro).

Nós já fornecemos os certificados locais `key.pem` e `cert.pem` prontos dentro da pasta `server/`. Para iniciar o servidor carregando as dependências do ambiente virtual `venv` e ativando a criptografia SSL, execute o comando correspondente ao seu sistema operacional:

* **No Windows (PowerShell ou Prompt de Comando):**
  ```powershell
  venv\Scripts\python.exe -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --ssl-keyfile server/key.pem --ssl-certfile server/cert.pem
  ```

* **No Linux / macOS (Terminal):**
  ```bash
  ./venv/bin/python -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --ssl-keyfile server/key.pem --ssl-certfile server/cert.pem
  ```
* **Acesso seguro na TV/PC principal:** [https://localhost:8000](https://localhost:8000) ou [https://127.0.0.1:8000](https://127.0.0.1:8000)
* **Acesso no Celular/Rede:** `https://<seu-ip-local>:8000` (ex: `https://192.168.15.6:8000`)
* **Nota sobre o Certificado Local:** Por ser um certificado autoassinado (de desenvolvimento local), o seu navegador exibirá uma tela de alerta na primeira entrada ("Sua conexão não é particular"). Basta clicar em **"Avançado"** (Advanced) e em seguida em **"Ir para o site (inseguro)"** (Proceed) para carregar o Karaokê e liberar o microfone instantaneamente!

### 3. Parear TV e Celular (Detecção Inteligente de IP)
* Nós criamos um sistema de **Detecção Inteligente de IP da Rede Local**: mesmo que você abra a TV usando `localhost`, o nosso sistema descobre automaticamente o IP real do seu computador na rede (ex: `192.168.15.5`).
* O **QR Code** gerado na tela da TV já conterá o link com o IP correto de rede. Basta apontar a câmera do celular para o QR Code para conectar o celular instantaneamente como microfone, sem precisar configurar nada manualmente!

---

## 📁 Estrutura Interna de Músicas (`server/songs/`)

Cada música criada fica alocada em sua respectiva pasta identificada pelo slug do título e artista, estruturada com arquivos limpos e organizados:
* `vocal.mp3`: Áudio de voz pura usado como base de comparação de espectro.
* `backing_track.mp3`: Trilha instrumental (karaokê) tocada na TV.
* `lyrics.lrc`: Arquivo de letras sincronizado contendo timestamps por linha.
* `segments.json`: Gerado automaticamente pelo Whisper GPU alinhando cada sílaba e palavra no tempo.

---

## 🧠 Tecnologias Utilizadas
* **Backend:** FastAPI, Faster-Whisper (GPU Medium), RapidFuzz (Phonetic matching).
* **Frontend Premium:** Vanilla JS (Conexão e gravação de áudio via AudioWorklet), HTML5 Web Audio API, WebSockets.
* **Processamento de Áudio:** PyAV, Pydub, Scipy (Downsampling de microfone em tempo real).
