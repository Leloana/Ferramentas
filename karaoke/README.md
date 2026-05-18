# 🎤 Karaoke AI Premium — Multi-Dispositivo & Sincronia IA

Um ecossistema moderno, de alto desempenho e alta fidelidade para Karaokê, projetado para rodar localmente com **transcrição fonética em tempo real (Whisper GPU/CPU)**, **cálculo de pontuação difuso por timing**, e uma arquitetura inovadora **Multi-Dispositivo** (use a TV da sala como tela/display e qualquer Celular conectado como microfone sem fios via WebSockets e QR Code!).

O projeto foi totalmente refatorado, alcançando uma arquitetura altamente modular, limpa e com 100% de separação de responsabilidades.

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
*   📖 **Guia Mestre de Arquitetura e Contratos**: Veja em [PROJECT_GUIDE.md](PROJECT_GUIDE.md) as especificações de rede, modelo do segments.json e restrições.
*   📖 **Arquitetura Técnica do Client (Frontend)**: Veja em [client/ARCHITECTURE.md](client/ARCHITECTURE.md) o padrão de ES Modules, estado mutável compartilhado e controle CSS de estados.
*   📖 **Histórico de Refatoração do Backend**: Veja em [BACKEND_REFACTOR_NOTES.md](BACKEND_REFACTOR_NOTES.md) como o monolito do servidor foi decomposto em routers assíncronos.

---

## 🚀 Como Iniciar em 3 Passos

### 1. Preparar o Ambiente Virtual (venv)
O ecossistema utiliza um ambiente virtual dedicado contendo todas as dependências pré-instaladas. Para validar ou instalar novas dependências, utilize o terminal a partir da pasta raiz do repositório:
```bash
# Acessar a pasta do karaokê
cd karaoke

# Ativar o ambiente virtual (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Se preferir usar Prompt de Comando (CMD)
.\venv\Scripts\activate.bat

# Se preferir Linux/macOS
source venv/bin/activate
```

*(Caso precise reinstalar as dependências de raiz, execute `pip install fastapi uvicorn numpy scipy faster-whisper rapidfuzz pydub yt-dlp av python-multipart`)*

### 2. Rodar o Servidor Exposto na Rede (Modo HTTPS Seguro 🔒)
Para que os navegadores modernos nos dispositivos móveis e TV **permitam e liberem o uso de captura do microfone**, a página deve ser executada obrigatoriamente sob **HTTPS** (Contexto Seguro).

Nós já fornecemos certificados SSL de desenvolvimento (`key.pem` e `cert.pem`) prontos na pasta `server/`. Para subir o servidor na rede local utilizando o Python do ambiente virtual, execute:

* **No Windows (PowerShell/Prompt a partir da pasta `karaoke`):**
  ```powershell
  .\venv\Scripts\python.exe -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --ssl-keyfile server/key.pem --ssl-certfile server/cert.pem
  ```

* **No Linux / macOS (Terminal a partir da pasta `karaoke`):**
  ```bash
  ./venv/bin/python -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --ssl-keyfile server/key.pem --ssl-certfile server/cert.pem
  ```

* **Acesso seguro na TV/PC principal:** [https://localhost:8000](https://localhost:8000)
* **Acesso no Celular/Rede:** `https://<seu-ip-local>:8000` (ex: `https://192.168.1.15:8000`)
* **Ignorar Alerta de Certificado Local:** Por se tratar de um certificado autoassinado para desenvolvimento local, o navegador exibirá a tela "Sua conexão não é particular". Basta clicar em **"Avançado"** (Advanced) e em seguida em **"Ir para o site (inseguro)"** (Proceed) para liberar o acesso ao microfone e iniciar instantaneamente!

### 3. Pareamento Inteligente via QR Code
O servidor descobre automaticamente o IP de rede da sua máquina local. O **QR Code** gerado no Display principal (TV) conterá diretamente o endereço HTTPS correto de rede. Aponte a câmera do celular para o QR Code para conectar instantaneamente como microfone inteligente!

---

## 🧠 Tecnologias Utilizadas
* **Backend:** FastAPI (APIRouter desacoplado), Uvicorn SSL, Faster-Whisper, RapidFuzz.
* **Frontend:** Vanilla JS nativo (ES Modules, Web Audio API, AudioWorkletProcessor de PCM em baixa latência), HTML5, CSS3.
* **Processamento Acústico:** PyAV, Pydub, Scipy (Downsampling de microfone em tempo real).
