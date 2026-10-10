# Guia de Desenvolvimento - Karaoke AI Premium (`CLAUDE.md`)

Este arquivo resume os detalhes técnicos específicos do subprojeto **Karaoke AI Premium**. Consulte este documento antes de realizar modificações nesta pasta para entender fluxos de arquivos, APIs, schemas e restrições arquiteturais.

---

## 📂 1. Estrutura de Diretórios Relevante

| Diretório/Arquivo | Função Principal | O que saber antes de editar |
| :--- | :--- | :--- |
| **`client/`** | Frontend da aplicação (Vanilla HTML/CSS/JS) | Sem build step. Mantenha compatibilidade direta com ES Modules. |
| ├─ `index.html` | Esqueleto da página (`<!-- @include partials/... -->`) | O `GET /` monta os parciais (`server/utils/html_includes.py`) e entrega uma página só — bom para TV. Cada tela/modal é um arquivo em `partials/`. IDs são contrato com o JS. |
| ├─ `partials/` | Um arquivo por área/modal | Mudou um ID? Procure-o em `js/`. |
| ├─ `assets/art/` | Artes SVG (desenhadas pelo Codex) | Paleta de `styles/tokens.css`. |
| ├─ `styles/*.css` | Tema "partitura antiga" em tons pastéis, cantos retos. `tokens.css` (cores/fontes), um arquivo por área, `states.css` (visibilidade por `data-state`), `tv.css` (foco do controle remoto) | **Não mude styles inline no JS.** Crie classes de estado CSS e alterne-as com `classList`. Cores só por `var(--...)`. Fontes: `--font-ui` (sans simples) para tudo que se lê — letra, títulos de música, notas, listas, formulários; `--font-display` (serifada) só no estético — marca, títulos de seção/modal, letra do rank. Sem `inset`/`:has()` (TV antiga). |
| └─ `js/` | Módulos JavaScript (ES Modules), uma pasta por área | Centralize as variáveis compartilhadas em `core/state.js`. Arquivo novo vai na pasta da área; nada solto na raiz além do `main.js`. |
| &emsp;&emsp;├─ `main.js` | Bootstrap (identifica TV ou celular) | Ponto de entrada do `index.html`. Importa `core/compat.js` primeiro. |
| &emsp;&emsp;├─ `core/` | Estado, config, DOM, ícones, tema, toast, endereço público, wake lock | `core/state.js`: **nunca exporte `let` locais**, adicione propriedades ao objeto `state`. `core/icons.js`: **sem emojis e sem biblioteca de ícones**, use `<i data-icon="nome">` ou `iconSvg('nome')`; ícone novo = novo path ali. |
| &emsp;&emsp;├─ `ui/` | Modal único, select personalizado, abas, controle remoto, painel de saúde | Todo `<select>` é aprimorado no bootstrap (`ui/select.js`); troque valor com `select.value = x`. Controle remoto em `ui/tv-nav.js`. |
| &emsp;&emsp;├─ `audio/` | `AudioLifecycleManager`, pitch shifter, microfone, voz guia, prévia do refrão, ouvir a apresentação | A voz guia passa pelo mesmo tom do instrumental (`audio/audio-lifecycle-manager.js`). |
| &emsp;&emsp;├─ `net/` | WebSocket da TV no lobby (`ws-display.js`) e sincronia de tempo (`sync.js`) | O WebSocket da partida é o de `game/session.js`. |
| &emsp;&emsp;├─ `game/` | Tela de jogo da TV: `session` (início, fim, reconexão), `server-messages` (uma função por mensagem), `highlight-loop` (laço da letra), `lyrics-carousel`, `hud`, `transcription`, `game-over`, `controls`; e as peças `score-bars`, `verse-stamp`, `turns`, `lyrics-script`, `game-events`, `share-card` (cartão do fim, que É o placar do fim de jogo na TV — um por cantor, lado a lado, `mountShareCards`; ouvir a própria voz só no celular — e da tela final de quem cantou, com quadradinhos sem texto para trocar o estilo — `mountShareCard`; caderno/neon/vidro no esqueleto comum; ingresso, cupom, vinil, pôster, mosaico e letreiro em `share-card-styles.js` + `styles/share-card-styles.css`; código de barras vem de `player_stats[p].verses`), `combo` (selo e chips), `reactions` (plateia subindo na TV) | Mensagem nova do servidor para a TV = função nova em `server-messages.js`. Laço da letra: um passo nomeado por responsabilidade em `frame()`. Média do time é feita no front (`score-bars.js`); 2 times = barras na esquerda/direita e sem as configurações (`barOf`), 3–4 = baixo/topo/esquerda/direita. Celular só mostra nota de verso que foi dele (`myVerseScore`: no revezamento o servidor manda só a nota de quem cantou). `turns.js` espelha `turn_owner` em `ws/room.py`. Faixas do carimbo em `verseQuality` (85/70). O combo é contado no servidor (`server/combo.py`, mesma faixa de 85). A TV desliga animações, as reações são a exceção (`tv.css`). |
| &emsp;&emsp;├─ `lobby/` | Repertório, lobby (vagas + time A–D), fila de processamento, fila da noite, capa, busca no YouTube e os modais da biblioteca (pareamento, adicionar música, editor) | Não existe seletor de modo: mesmo time = dupla/trio. Fila da noite: `song_requests.py` no servidor. Capa: `utils/cover.py`. |
| &emsp;&emsp;├─ `players/` | Ranking, perfil, modal "Cantores" e anotação dos versos | Lê `/api/players`. |
| &emsp;&emsp;├─ `mobile/` | Celular-microfone: tela (`mobile-mic-view`), `mic-socket` (conexão), `mic-messages` (uma função por mensagem), `mic-final` (placar final), `mic-health` (vigia do áudio), `reactions-bar` (3 reações de quem assiste) | Mesmo formato da TV: conexão separada das mensagens. |
| &emsp;&emsp;└─ `worklets/audio-processor.js` | AudioWorklet para captura e fluxo de áudio PCM | Roda em thread separada. Reamostra para 16 kHz Int16 e envia pacotes `KM01` de 100 ms com o índice da 1ª amostra. Mudou o formato? Mude também `server/mic_stream.py` e a versão em `WORKLET_URL`. |
| **`server/`** | Backend FastAPI e motores de IA | Orquestrado por managers de estado singletons. |
| ├─ `main.py` | Entrada Uvicorn e registro de middlewares/routers | Inicializa o servidor. Mantém logs em console. |
| ├─ `state.py` | Singletons compartilhados (`room_manager`, etc.) | **Use para evitar imports circulares** entre routers e websockets. |
| ├─ `rooms.py` | Modelo da sala de canto (`KaraokeRoom`) | Gerencia buffers em memória por jogador e por segmento. |
| ├─ `queue_manager.py` | Fila de downloads/processamento da GPU | Garante que processos pesados de IA aguardem ocioso da GPU. |
| ├─ `score_engine.py` | Motor de cálculo de notas do cantor | Fuzzy tokens (rapidfuzz), normalização por idioma (contrações, números, hífen) e penalidades de tempo. Pronúncia (`phonetic.py`: Double Metaphone no inglês, regras de som no português) e emendas de até 3 palavras contra 1 ("belly shot"×"Belisha") — fora do japonês. Mexeu? Meça também o canto de um verso contra a letra de outro (falso positivo). |
| ├─ `pitch.py` | Afinação: YIN em numpy, `pitch.json` da voz separada, nota de tom por verso | Informativa (fora da nota) até calibrar; oitava livre; nota mostrada já desconta o acaso (~30). |
| ├─ `song_requests.py` | Fila da noite por sala (pedidos "quero cantar") | Limites: 30 pedidos, 3 por cantor. Some quando a sala fecha. |
| ├─ `players.py` | Perfis dos cantores (`players/<apelido>/profile.json`), recordes, ranking | `KARAOKE_PLAYERS_DIR` troca a pasta (os testes usam uma temporária via `tests/conftest.py`). |
| ├─ `mic_stream.py` | Linha do tempo do áudio dos microfones | Formato do pacote `KM01`, relógio da música (`SongClock`) e janelas disjuntas por verso. |
| ├─ `stt_engine.py` | Instanciação e controle do Faster-Whisper | Tem fallback CUDA -> CPU automático e limpa silêncio (VAD). Modelo padrão `large-v3-turbo` (float16 na GPU, int8 na CPU), trocável por `KARAOKE_WHISPER_*`. Os limiares de confiança foram calibrados no `medium`: recalibrar com canto real. |
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
*   **Fila de processamento em segundo plano:** `server/routes/queue.py` (adiciona tarefas ao `queue_manager.py`). Até 60 itens (cabe uma playlist); baixa 2 por vez (`queue_eta.DOWNLOAD_SLOTS`), separa uma por vez e gera uma letra por vez. O `eta_sec` da fila já conta a espera pelos da frente (`SongQueueManager.etas`, simulação em `queue_eta.pipeline_finish`). Médias em `server/queue_stats.json`: a separação é cronometrada a partir do lock (`separate_stems(on_start=...)`), não da espera; a letra só entra na média se nenhuma separação rodou junto (dividem a GPU).
*   **Playlist inteira:** link com `list=` no "Adicionar música" abre o passo `playlist` (`client/js/lobby/playlist-import.js`): álbum (≥ 60% com o mesmo artista) abre antes o passo `playlist-artist`, só para confirmar o artista de todas (o palpite vem do canal, ex. "Official Arctic Monkeys"; botão "Artista" reabre); depois marcar/desmarcar, corrigir título e artista de cada uma, tempo total estimado; envia um `/api/queue/add` por música (cada uma busca a própria letra; modo rápido).
*   **Tratamento de áudio/resampling:** ao vivo o celular já manda 16 kHz (`worklets/audio-processor.js`). Offline, `server/utils/audio.py` converte arquivos para 16kHz Mono.
*   **Áudio ao vivo → verso:** `server/mic_stream.py` (âncora por jogador, `segment_window`, tempos do Whisper relativos à janela).
*   **Cálculo da Pontuação:** `server/score_engine.py` (fuzzy matching, normalização e atrasos). Letra × transcrição casadas em ordem (`match_in_order`, programação dinâmica): palavra fora de ordem não pontua.
*   **Separação voz × instrumental:** `server/utils/separation.py` (uma separação por vez, MP3 em `KARAOKE_MP3_BITRATE`=320k). `KARAOKE_SEPARATOR`=auto usa o BS-RoFormer (`audio-separator`, opcional, `KARAOKE_ROFORMER_MODEL`) se instalado, senão o Demucs (`python -m demucs.separate`, `KARAOKE_DEMUCS_MODEL`=htdemucs). RoFormer só com GPU e sem partida em andamento; falha ou timeout cai no Demucs. Fila e reinstall usam só ele.
*   **Letra de outra versão do áudio:** `utils/lyrics_fetcher.py` escolhe no LRCLIB (`/api/search`) a versão de duração mais próxima (o reinstall busca de novo com a duração real). `utils/lrc_sync.sync_lrc` decide o LRC deste áudio: `lrc_fit` (escala + offset pela voz do stem) e `lrc_structure` (Whisper do stem × letra: pula verso cortado, repete refrão a mais). Vale no modo rápido e no PRO (que alinha os dois candidatos e fica com o melhor).
*   **Tempos dos versos:** `server/utils/segment_timing.py` — `match_words_in_order` (letra × Whisper sem inverter a ordem) e `finalize_segments` (sing_end cobre a última palavra e não invade o próximo verso; também aplicado na leitura pelo `song_manager`).
*   **Qualidade do alinhamento:** `server/utils/alignment_quality.py` grava `meta.json["alignment_quality"]` e `["needs_review"]` (nota < 70); a lista mostra "Revisar". Volume do instrumental: `utils/loudness.py` (~−16 LUFS, `meta.json["loudness"]`).
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
    },
    "alignment_quality": {"score": 88, "flags": ["..."], "lines": [{"idx": 0, "confidence": 0.8, "flags": []}]},
    "needs_review": false,              // nota < 70 → "Revisar" na lista
    "loudness": {"lufs_before": -21.3, "gain_db": 5.3}
}
```
Outros arquivos opcionais na pasta: `cover.jpg` (+ `cover.options.json`, `cover.choice.json`), `pitch.json` (melodia de referência, 10 ms/quadro), `.lyrics_edited` (letra revisada no editor).

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
    "confidence": 0.82,       // opcional (PRO): confiança média do verso
    "align": "window",        // opcional (PRO): window | fallback | global
    "lyrics_timed": [         // Palavras individuais mapeadas (PRO acrescenta "confidence" por palavra)
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
      "song_id": "titulo-da-musica-artista",
      "score": 85.5,
      "pitch": 71.0,          // opcional: afinação média da partida
      "mode": "solo",
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
| `GET` | `/api/songs/{song_id}/cover` | — | Capa do álbum (JPEG). 1ª vez escolhe o melhor candidato (iTunes/Deezer/YouTube, nota por artista+título, tributo/karaokê/ao vivo perdem); guarda em `songs/<slug>/cover.jpg` (`cover.none` = sem capa). Baixa a versão grande (iTunes 1200 px, YouTube `maxresdefault`, cai na pequena se faltar); capas antigas de 600 px: `python tools/upgrade_covers.py` |
| `GET` · `POST` | `/api/songs/{song_id}/cover/options` · `/api/songs/{song_id}/cover` | `{"url"}` (POST) | Opções de capa (`cover.options.json`) · escolher uma delas (só URLs da lista) |
| `GET` | `/songs/{song_id}/vocal` | — | Voz separada (voz guia) |
| `GET` | `/api/players` · `/api/players/{nome}` | — | Ranking · perfil (resumo, recordes por música, últimas) |
| `GET` | `/api/songs/{song_id}/leaderboard` | — | Melhores da sala na música |
| `GET` | `/api/recordings/{id}/audio/{jogador}` | — | Voz gravada (WAV 16 kHz no tempo da música) |
| `GET` | `/api/status` | — | Painel de saúde: GPU, fila, salas (tempo até a nota), disco |
| `GET` | `/api/youtube-search` | `q: str`, `limit: int` (Query) | `{"results": [{"url", "title", "channel", "duration", "thumbnail", "artist_guess", "title_guess"}]}` |
| `POST` | `/api/upload-song` | Form (`title`, `artist`, `language`, files/URLs) | `{"success": true, "lyrics_status": "draft", "draft_lrc": "...", "slug": "..."}` |
| `GET` | `/api/youtube-playlist` | `url: str` (Query, link com `list=`) | `{"title", "truncated", "results": [... como a busca, + "status": "new"\|"library"\|"queue"]}` (até 50; `utils/youtube.PLAYLIST_LIMIT`) |
| `POST` | `/api/queue/estimate` | JSON `{"durations": [seg\|null], "align_lyrics"}` | `{"total_sec", "own_sec", "queued"}` — tempo até a fila atual + estas ficarem prontas (`queue_eta.pipeline_finish`) |
| `POST` | `/api/queue/add` | Form (`title`, `artist`, `youtube_url`, etc.) | `{"success": true, "item": {...}}` (Entra na fila) |
| `GET` | `/api/queue/status` | — | `{"queue": [...], "gpu_busy": bool}` |
| `DELETE`| `/api/queue/remove/{item_id}`| — | `{"success": true, "message": "..."}` |
| `WS` | `/ws/room/{room_id}` | Query (`role`, `song_id`) | Loop de WebSocket bidirecional para áudio/dados |

---

## ⚙️ 5. Padrões de Código e Convenções

1.  **State Management (Frontend):**
    *   Sempre use o objeto global `state` importado de `js/core/state.js` para ler ou escrever dados entre os módulos.
    *   **Proibido:** Declarar variáveis soltas no topo dos módulos (como `let ws;` ou `let activeSong;`) que guardem estado interativo.
2.  **No-Build Frontend:**
    *   O frontend deve permanecer estritamente em Vanilla ES Modules.
    *   Sintaxe até ES2018 (navegador de TV antigo): sem `?.`, `??` nem `catch {}`. Polyfills em `js/core/compat.js`.
    *   Controle remoto: `js/ui/tv-nav.js` (setas, OK, Voltar, Play/Pause). `?tv=1` força o modo TV.
    *   Preview sem GPU: `python tools/preview_front.py [--host 0.0.0.0]` (dados de exemplo, sem WebSocket; busca no YouTube e capas funcionam se o `yt-dlp` estiver instalado).
    *   Interface: sem textos explicativos; no celular os toasts são só de erro (validação usa `'error'`); trocar de tela/aba/modal volta ao topo; toda tela tem voltar.
    *   Histórico do redesign do front: `docs/archive/FRONT_REDESIGN_2026-09.md`.
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
*   **Mutex de GPU (gerar letra × partida):** trabalhos longos de Whisper/MMS fora da partida usam `async with queue_manager.gpu_job("nome")` (pega o `whisper_lock` e aparece em `alignment_busy()`). Enquanto houver um, o INICIAR fica bloqueado na TV ("GPU ocupada · Gerando a letra de X", via `/api/queue/status`) e o servidor responde `start_blocked` a um `start_game`. A etapa 1 (download + Demucs) continua rodando durante a partida.
*   **Monotonicidade dos Timestamps Word-Level:**
    *   No arquivo `segments.json`, a lista `lyrics_timed` **deve possuir tempos de expected_start estritamente crescentes**. Nunca permita que duas palavras seguidas no JSON comecem no mesmo segundo (ex.: 0.0s e 0.0s). O frontend calcula gradientes de cor com base no avanço de tempo; tempos iguais causam divisão por zero e quebram a animação visual.
*   **Vazamento Instrumental:**
    *   O Whisper é sensível a ruído. Se o microfone capturar a caixa de som da TV (backing track), o Whisper transcreverá o segmento anterior ou alucinará. Use o `score_engine.py` com o mecanismo de remoção de vazamento de versos anteriores (`leakage removal`).
    *   Desde o P0 as janelas dos versos são disjuntas (`mic_stream.segment_window`), então o mesmo áudio não cai mais em dois versos. O `leakage removal` ficou só para voz que vaza de verdade, e não remove palavras que também abrem o verso atual (versos que repetem o anterior eram zerados).
*   **Mudou o score? Rode as partidas reais:**
    *   `tests/unit/test_recorded_sessions.py` repontua o que o Whisper ouviu em partidas reais (`tests/fixtures/recorded_sessions/`) contra o gabarito anotado pelo cantor. Canto certo tem que continuar alto e cantarolar, baixo.
    *   As partidas ficam gravadas por padrão em `karaoke/recordings/` (fora do git; `KARAOKE_RECORD=0` desliga). `tools/replay_recording.py` roda o Whisper de novo nelas com outro modelo ou constante (`--set modulo.NOME=valor`).
    *   Gravação formato 3 (`server/recorder.py`): configuração, linha do tempo da TV (`player_event`), aparelhos (`client_info`), rede e ruído de fundo por celular, dados crus do Whisper, afinação e tempo por verso, versões (commit + constantes), resultado final e cópia da música. Anotação também pelo celular ("Anotar meus versos").
    *   `tools/export_recordings.py` vira as partidas anotadas em fixtures (`tests/fixtures/recorded_sessions/exported/`, com `baseline` = erro médio contra o gabarito) e `--zip` faz backup. `test_exported_sessions_do_not_regress` barra piora. Lógica de repontuar em `server/calibration.py`.
*   **Referencial de tempo do Whisper:**
    *   O Whisper devolve `start` relativo ao início da JANELA, que começa até 1,5 s antes do `sing_start`. Compare com `expected_start` só depois de `_shift_words(words, t0 - sing_start)` em `ws/room.py`. Sem isso o canto perfeito tira 85.
*   **Slug de música vindo do cliente:** sempre `utils/song_paths.safe_song_dir(SONGS_DIR, slug)`, nunca `SONGS_DIR / slug` direto (rotas apagam/renomeiam pastas).
*   **Texto de usuário no front:** apelidos, títulos e transcrições nunca vão crus para `innerHTML` — use `textContent` ou `escapeHtml` (`js/core/html.js`). `showToast` já é texto puro.
*   **Reconexão da TV:** o jogo reconecta com `resume=1` (o servidor não reseta a sala) e o código de fechamento 4001 (`DISPLAY_REPLACED_CODE`) significa "outra tela assumiu" — não reconectar. Resultados de Whisper conferem `room.game_id` antes de gravar.
*   **Letra revisada à mão:** o `save-lyrics` grava `songs/<slug>/.lyrics_edited`; o reinstall sem alinhamento forçado mantém esse `lyrics.lrc` em vez do backup/LRCLIB.
*   **Tela de cantar nunca rola:** cabe na janela em qualquer tela (notebook baixo, TV 960×540) e nº de cantores. Sempre ficam a nota de quem canta (mesmo mínima) e a letra legível com a próxima linha; para caber, sacrifique o resto (ajustes, "Ouvi:", linha anterior, espaçamentos). Layout em `states.css` §14 (altura da janela, palco `flex: 1`, fonte por `vh`) e `tv.css`. Mexeu? `tests/ui/test_screens.py::test_singing_screen_fits`.
*   **Testes das telas:** `tests/ui/test_screens.py` (Playwright sobre o preview; pulado sem Playwright). Mexeu em tela? Rode `python -m pytest tests/ui`.
*   **Hallucinações no Silêncio:**
    *   Trechos silenciosos longos fazem o Whisper gerar alucinações repetitivas. Garanta que o gate de áudio de RMS (`rms_threshold` em `stt_engine.py`) rejeite transcrição abaixo de `0.0018` de energia média.

## Fluxo Git Obrigatório

- Todo commit deve ser feito a partir da raiz do repositório (`Ferramentas/`)
- Nunca rodar `git commit` de dentro de um subprojeto
- Mensagem no formato: `feat(karaoke): descrição` / `fix(karaoke): descrição`
- Sempre `git add` com path relativo à raiz: `git add karaoke/client/js/lobby/selection-view.js`
- Push imediato após commit