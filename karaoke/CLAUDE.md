# Guia de Desenvolvimento - Karaoke AI Premium (`CLAUDE.md`)

Este arquivo resume os detalhes técnicos específicos do subprojeto **Karaoke AI Premium**. Consulte este documento antes de realizar modificações nesta pasta para entender fluxos de arquivos, APIs, schemas e restrições arquiteturais.

---

## 📂 1. Estrutura de Diretórios Relevante

| Diretório/Arquivo | Função Principal | O que saber antes de editar |
| :--- | :--- | :--- |
| **`client/`** | Frontend da aplicação (Vanilla HTML/CSS/JS) | Sem build step. Mantenha compatibilidade direta com ES Modules. |
| ├─ `index.html` | Markup principal, modais e templates HTML | Contém todos os modais da aplicação. |
| ├─ `styles/main.css` | Folha de estilos monolítica (Neon Glow, BEM) | **Não mude styles inline no JS.** Crie classes de estado CSS e alterne-as com `classList`. |
| └─ `js/` | Módulos JavaScript (ES Modules) | Centralize as variáveis compartilhadas em `state.js`. |
| &emsp;&emsp;├─ `state.js` | Objeto central de estado mutável compartilhado | **Nunca exporte `let` locais.** Adicione propriedades ao objeto `state`. |
| &emsp;&emsp;├─ `main.js` | Bootstrap da aplicação (identifica display vs mic) | Define o ponto de entrada. |
| &emsp;&emsp;├─ `game-view.js` | Renderização da letra e animações de gameplay | Controla o acendimento progressivo das sílabas/palavras. |
| &emsp;&emsp;├─ `ws-display.js` / `ws-mic.js` | WebSockets do Display (TV) / Microfone (Celular) | Tratam reconexões e recebimento de blobs binários PCM. |
| &emsp;&emsp;└─ `worklets/audio-processor.js` | AudioWorklet para captura e fluxo de áudio PCM | Roda em thread separada. Envia pacotes PCM Float32 brutos. |
| **`server/`** | Backend FastAPI e motores de IA | Orquestrado por managers de estado singletons. |
| ├─ `main.py` | Entrada Uvicorn e registro de middlewares/routers | Inicializa o servidor. Mantém logs em console. |
| ├─ `state.py` | Singletons compartilhados (`room_manager`, etc.) | **Use para evitar imports circulares** entre routers e websockets. |
| ├─ `rooms.py` | Modelo da sala de canto (`KaraokeRoom`) | Gerencia buffers em memória por jogador e por segmento. |
| ├─ `queue_manager.py` | Fila de downloads/processamento da GPU | Garante que processos pesados de IA aguardem ocioso da GPU. |
| ├─ `score_engine.py` | Motor de cálculo de notas do cantor | Contém fuzzy tokens, Double Metaphone e penalidades de tempo. |
| ├─ `stt_engine.py` | Instanciação e controle do Faster-Whisper | Tem fallback CUDA -> CPU automático e limpa silêncio (VAD). |
| ├─ `routes/` | Handlers REST HTTP (`songs`, `lyrics`, `upload`, `queue`) | Retornam estritamente JSON (ou `FileResponse` para áudio). |
| ├─ `ws/room.py` | Canal WebSocket bidirecional da sala | Processa áudio PCM, gerencia turnos e persiste perfis. |
| └─ `utils/` | Helpers (Download YouTube, parsing LRC, alinhadores) | Modifique `lrc_align.py` / `lrc_pro.py` para alterar o alinhamento da letra. |
| **`tools/`** | Ferramentas offline e scripts CLI | Utilizados no processamento de mídia e reinstalação. |
| └─ `prepare_song.py` | Fatiador de áudio e alinhador word-level | Gera o `segments.json` crucial para o frontend. |
| **`players/`** | Diretório local de perfis persistidos | Estruturado por pasta contendo nickname -> `profile.json`. |

---

## 🔑 2. Arquivos-Chave por Função

*   **Listar músicas no disco:** `server/routes/songs.py` (usa o `song_manager` de `server/song_manager.py`).
*   **Loop de Jogo & Handshake (WebSockets):** `server/ws/room.py` (Display + Mics na mesma sala).
*   **Adicionar música (Upload / YouTube):** `server/routes/upload.py` (inicia pipeline de download e alinhamento).
*   **Fila de processamento em segundo plano:** `server/routes/queue.py` (adiciona tarefas ao `queue_manager.py`).
*   **Tratamento de áudio/resampling:** `server/utils/audio.py` (converte PCM Float32 para 16kHz Mono).
*   **Cálculo da Pontuação:** `server/score_engine.py` (fuzzy matching, Double Metaphone e atrasos).
*   **Alinhamento de letras com áudio:** `server/utils/lrc_align.py` (Whisper) e `server/utils/lrc_pro.py` (MMS_FA PyTorch).
*   **Criação de segmentos de canto:** `tools/prepare_song.py` (gera metadados de jogabilidade no arquivo final).

---

## 📊 3. Schemas de Dados Principais

### A. Metadados da Música (`server/songs/<slug>/meta.json`)
Armazena links de origem, letras brutas e status de arquivos físicos.
```json
{
    "meta": {
        "title": "Nome da Música",
        "artist": "Artista",
        "language": "pt",
        "slug": "nome-da-musica-artista"
    },
    "audio": {
        "youtube_vocal_url": "URL ou null",
        "youtube_backing_url": "URL ou null"
    },
    "lyrics": {
        "plain_lyrics": "Letra linha por linha..."
    },
    "status": {
        "has_vocal_file": true,
        "has_backing_file": true,
        "has_lrc_file": true
    }
}
```

### B. Arquivo de Gameplay (`server/songs/<slug>/segments.json`)
Lido pelo frontend para renderizar e temporizar a letra durante a reprodução.
```json
[
  {
    "id": 1,
    "label": "Parte 1",
    "sing_start": 26.681,     // Início do canto (segundos absolutos)
    "sing_end": 31.061,       // Fim do canto (segundos absolutos)
    "pause_start": 31.061,    // Início da pausa instrumental subsequente
    "pause_end": 31.161,      // Fim da pausa instrumental
    "language": "en",         // Idioma usado na transcrição
    "lyrics": "This is the place",
    "lyrics_timed": [         // Palavras individuais mapeadas
      {
        "word": "This",
        "expected_start": 0.0,  // Offset relativo ao sing_start do segmento (segundos)
        "expected_end": 1.32    // Offset relativo ao sing_start do segmento (segundos)
      },
      {
        "word": "is",
        "expected_start": 2.42,
        "expected_end": 2.54
      }
    ]
  }
]
```

### C. Histórico do Cantor (`players/<sanitized_nickname>/profile.json`)
Armazena a nota histórica de cada sessão.
```json
{
  "name": "Apelido",
  "songs_sung": [
    {
      "name": "Título da Música - Artista",
      "score": 85.5,
      "date": "2026-05-25T23:50:00Z"
    }
  ]
}
```

---

## 📡 4. Endpoints da API REST

| Método | Endpoint | Parâmetros | Retorno Esperado |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | — | HTML principal (`index.html`) |
| `GET` | `/api/songs` | — | Lista de dicionários com metadados e status das músicas |
| `GET` | `/songs/{song_id}/audio` | — | Streaming binário do áudio `backing_track.mp3` |
| `DELETE`| `/api/delete-song/{song_id}` | — | `{"success": true}` (remove pasta do disco) |
| `POST` | `/api/reinstall-song/{song_id}` | `align_lyrics: bool` (Query) | `{"success": true, "message": "..."}` |
| `GET` | `/api/get-ip` | — | `{"ip": "192.168.x.x"}` (IP local do servidor na rede) |
| `GET` | `/api/get-lyrics` | `slug: str` (Query) | `{"success": true, "lyrics": "LRC", "language": "pt", "meta_json": "{}"}` |
| `POST` | `/api/save-lyrics` | Form (`slug`, `language`, `lyrics_lrc`, `meta_json`) | `{"success": true}` (Salva e gera os segmentos) |
| `GET` | `/api/youtube-metadata` | `url: str` (Query) | `{"title": "...", "artist": "..."}` |
| `POST` | `/api/upload-song` | Form (`title`, `artist`, `language`, files/URLs) | `{"success": true, "lyrics_status": "draft", "draft_lrc": "...", "slug": "..."}` |
| `POST` | `/api/queue/add` | Form (`title`, `artist`, `youtube_url`, etc.) | `{"success": true, "item": {...}}` (Entra na fila) |
| `GET` | `/api/queue/status` | — | `{"queue": [...], "gpu_busy": bool}` |
| `DELETE`| `/api/queue/remove/{item_id}`| — | `{"success": true, "message": "..."}` |
| `WS` | `/ws/room/{room_id}` | Query (`role`, `song_id`) | Loop de WebSocket bidirecional para áudio/dados |

---

## ⚙️ 5. Padrões de Código e Convenções

1.  **State Management (Frontend):**
    *   Sempre use o objeto global `state` importado de `js/state.js` para ler ou escrever dados entre os módulos.
    *   **Proibido:** Declarar variáveis soltas no topo dos módulos (como `let ws;` ou `let activeSong;`) que guardem estado interativo.
2.  **No-Build Frontend:**
    *   O frontend deve permanecer estritamente em Vanilla ES Modules.
    *   Não introduza bundlers, compiladores de TypeScript ou dependências NPM de runtime.
3.  **Tratamento de Mídias e Line Endings:**
    *   Sempre filtre caracteres e line-endings (`\r\n` para `\n`) ao ler/salvar arquivos LRC. Use `normalize_lyrics_text` para evitar conflito de tags.
4.  **Isolamento de Erros de IA:**
    *   Falhas do Whisper não devem travar o loop de jogo WebSocket. Se um segmento gerar exceção na thread paralela, capture o erro e atribua score `0.0`.
5.  **Evitar Dependências Circulares no Backend:**
    *   Não faça imports diretos entre `ws/room.py` e `routes/`. Use singletons em `state.py` para desacoplar as instâncias.

---

## ⚠️ 6. Armadilhas Conhecidas e o que NÃO fazer

*   **Vazamento de Garbage Collector em WebSockets:**
    *   Ao disparar tarefas assíncronas de transcrição do Whisper via `asyncio.create_task`, **você deve salvar uma referência forte** das tarefas no conjunto da sala (`room.pending_tasks`). Caso contrário, o Python pode destruí-las antes da conclusão da transcrição.
*   **Limitação de VRAM e Threads da GPU:**
    *   Não execute processamento com Whisper ou Demucs fora de locks. Use `queue_manager.whisper_lock` no backend. O processamento concorrente da GPU pode estourar a VRAM no Windows e derrubar o servidor.
*   **Monotonicidade dos Timestamps Word-Level:**
    *   No arquivo `segments.json`, a lista `lyrics_timed` **deve possuir tempos de expected_start estritamente crescentes**. Nunca permita que duas palavras seguidas no JSON comecem no mesmo segundo (ex.: 0.0s e 0.0s). O frontend calcula gradientes de cor com base no avanço de tempo; tempos iguais causam divisão por zero e quebram a animação visual.
*   **Vazamento Instrumental:**
    *   O Whisper é sensível a ruído. Se o microfone capturar a caixa de som da TV (backing track), o Whisper transcreverá o segmento anterior ou alucinará. Use o `score_engine.py` com o mecanismo de remoção de vazamento de versos anteriores (`leakage removal`).
*   **Hallucinações no Silêncio:**
    *   Trechos silenciosos longos fazem o Whisper gerar alucinações repetitivas. Garanta que o gate de áudio de RMS (`rms_threshold` em `stt_engine.py`) rejeite transcrição abaixo de `0.0018` de energia média.

## Fluxo Git Obrigatório

- Todo commit deve ser feito a partir da raiz do repositório (`Ferramentas/`)
- Nunca rodar `git commit` de dentro de um subprojeto
- Mensagem no formato: `feat(karaoke): descrição` / `fix(karaoke): descrição`
- Sempre `git add` com path relativo à raiz: `git add karaoke/client/js/selection-view.js`
- Push imediato após commit