# Diretrizes de Desenvolvimento e Resumo do Projeto (CLAUDE.md)

Este documento serve como guia rápido para desenvolvedores e agentes de IA sobre a arquitetura do repositório, comandos frequentes, regras de código e fluxo de trabalho.

---

## 🛠️ Resumo do Repositório (Ferramentas)

Este repositório (`Ferramentas`) agrupa scripts, automações e ecossistemas independentes voltados à produtividade, automação local e uso de Inteligência Artificial.

### 1. 🎤 Karaoke AI Premium (`/karaoke`)
* **Descrição:** Ecossistema de karaokê de alta performance rodando localmente com separação de faixas (Demucs), transcrição e alinhamento fonético em tempo real (Whisper GPU/CPU + MMS_FA), e suporte multi-dispositivo (TV como tela principal e celulares como microfones via WebSockets).
* **Stack:** FastAPI (Python), Vanilla JS (ES Modules, Web Audio API, AudioWorklets), WebSockets, PyTorch (CUDA).
* **Documentação:** Copiada em `.claude/karaoke/` (dividida entre `onboarding/` para guias e arquitetura, e `resolucoes/` para resoluções de problemas, históricos e notas).

### 2. 🤖 Pipeline de Agentes Automatizados (`/pipeline-project`)
* **Descrição:** Pipeline de desenvolvimento composto por 3 agentes autônomos (Planner, Coder e Implementer) que colaboram para propor, validar e escrever código localmente. Integra com **Ollama** e utiliza o **Model Context Protocol (MCP)** para I/O e a ferramenta **Srclight** para busca híbrida e geração de dossiês semânticos.
* **Stack:** Python, SQLite, Ollama, MCP.

### 3. ▶️ YouTube Music Playlist Organizer (`/youtube_music_playlist_organizer`)
* **Descrição:** Classificador inteligente de playlists do YouTube Music por vibe, gênero ou clima usando IA local (Ollama). Possui interface CLI retrô-cyberpunk com equalizadores ASCII, cache de faixas e gerenciamento inteligente da cota da API oficial do YouTube.
* **Stack:** Python (Rich, Questionary), YouTube Data API v3, Ollama.

### 4. 📄 DOCX to PDF Converter (`/docx_to_pdf_converter`)
* **Descrição:** Conversor em lote ou individual de documentos Microsoft Word (`.docx`) para PDF utilizando a API nativa do Word no Windows.
* **Stack:** Python (`pywin32`).

---

## 🚀 Comandos Frequentes por Projeto

### Karaoke AI Premium
* **Ambiente:** `cd karaoke; .\venv\Scripts\Activate.ps1`
* **Executar Servidor (HTTPS com rede local):**
  ```powershell
  Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }; .\venv\Scripts\Activate.ps1; uvicorn server.main:app --host 192.168.15.6 --port 8000 --reload --ssl-keyfile "server/key.pem" --ssl-certfile "server/cert.pem"
  ```
* **Executar Testes Unitários:**
  ```powershell
  .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
  ```

### Pipeline de Agentes
* **Ambiente:** `cd pipeline-project; .venv\Scripts\Activate.ps1`
* **Executar Pipeline (Modo Completo):**
  ```powershell
  python orchestrator/runner.py "sua solicitação de desenvolvimento aqui"
  ```
* **Executar Pipeline por Etapas (Fase 1 - Planejamento / Fase 2 - Pseudocódigo):**
  ```powershell
  python orchestrator/runner.py "solicitação" --stage 1
  python orchestrator/runner.py "solicitação" --stage 2
  ```

### YouTube Music Playlist Organizer
* **Ambiente:** `cd youtube_music_playlist_organizer; .\venv\Scripts\activate`
* **Configuração Inicial OAuth:**
  ```powershell
  python setup_oauth.py
  ```
* **Executar Interface CLI:**
  ```powershell
  python main.py
  ```

### DOCX to PDF Converter
* **Ambiente:** Instalar `pip install -r requirements.txt` (com MS Word instalado no Windows).
* **Converter arquivo:**
  ```powershell
  python converter.py "caminho/do/documento.docx"
  ```
* **Converter pasta inteira:**
  ```powershell
  python converter.py "caminho/da/pasta"
  ```

---

## 📜 Regras de Código e Diretrizes de Desenvolvimento

1. **Regra de Localização de Arquivos (Strict):**
   * Toda nova ferramenta ou script deve seguir a estrutura `raiz/pasta_da_ferramenta/ferramenta`.
   * **NÃO** crie arquivos soltos na raiz do repositório (com exceção de `README.md`, `.gitignore`, `CLAUDE.md`, `.ai_instructions.md`).
2. **Ambientes Virtuais (venv):**
   * Cada pasta de projeto Python deve gerenciar suas dependências dentro de seu próprio `venv` ou `.venv`.
3. **Fluxo Git Obrigatório (Continuous Sync):**
   * **Commit Automatizado e Descritivo:** Qualquer alteração no código deve ser commitada imediatamente com uma mensagem clara e descritiva.
   * **Push Imediato:** O comando `git push` deve ser chamado logo após o commit para garantir que o repositório remoto esteja sincronizado.
   * **Branch Principal:** Todas as edições são feitas diretamente na branch ativa (usualmente `main`).
4. **Tratamento Especial do Karaoke:**
   * Sempre que for alterar o projeto de Karaoke, consulte primeiro o guia mestre: [karaoke/.claude/karaoke/onboarding/PROJECT_GUIDE.md](karaoke/.claude/karaoke/onboarding/PROJECT_GUIDE.md) (cópia oficial em [karaoke/docs/guides/PROJECT_GUIDE.md](karaoke/docs/guides/PROJECT_GUIDE.md)). Ele contém os contratos de dados e fluxos de áudio. A base de conhecimento completa do karaokê está indexada em [karaoke/.claude/karaoke/README.md](karaoke/.claude/karaoke/README.md).
