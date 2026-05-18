# Backend Refactor Notes — Handoff

Documento de transferência para a próxima IA/dev que pegar este projeto.
Resume **o que mudou no backend (`karaoke/server/`)** em 3 commits sequenciais
no branch `main` (HEAD: `500f88f`).

Antes: 1 arquivo `main.py` de 1056 linhas + `score_engine.py` + `stt_engine.py`
+ `song_manager.py`.
Agora: `main.py` ≈ 905 linhas, lógica utilitária extraída para package
`server/utils/`, vários bugs corrigidos.

---

## Estrutura atual

```
karaoke/server/
├── main.py              # FastAPI app, rotas HTTP e WebSocket (ainda gordo — ver "TODO")
├── score_engine.py      # Scoring fuzzy palavra-a-palavra + sandwich recovery
├── stt_engine.py        # Wrapper sobre faster-whisper (CUDA→CPU fallback)
├── song_manager.py      # Listagem/leitura de pastas de músicas
└── utils/
    ├── __init__.py
    ├── ffmpeg_bootstrap.py   # Localiza ffmpeg.exe via Winget no Windows
    ├── lrc.py                # read_lrc_meta(): parser de header [ti:]/[ar:]
    ├── text.py               # slugify() + parse_time_to_seconds()
    └── youtube.py            # download_youtube_audio() via yt-dlp
```

`tools/prepare_song.py` é importado dinamicamente em 3 lugares de `main.py`
(`sys.path.append` em runtime). **Não foi alterado** mas merece virar
package próprio (`tools/__init__.py`) — ver TODO.

---

## Commits (do mais antigo para o mais novo)

### `7dd646a` — Batch 1: bugfixes + cleanups

**Bugs reais corrigidos:**

1. **Cálculo de média da pontuação errado.** `room.total_score / (seg_idx + 1)`
   subestimava/superestimava a média porque tasks de transcrição terminam
   fora de ordem (seg 5 pode finalizar antes do seg 3). Agora há um contador
   `room.scored_count` incrementado quando cada segmento é efetivamente
   pontuado, e a média usa esse contador.

2. **Endpoint WebSocket duplicado.** `main.py` tinha duas funções
   `websocket_endpoint` — a de `/ws/{song_id}` era código morto (a segunda
   sobrescrevia a primeira por mesmo nome). Removida.

3. **STT fallback CUDA→CPU quebrava parâmetros.** Quando `cublas`/`cudnn`
   falhava no meio de uma transcrição, o código recarregava
   `WhisperModel("medium", ...)` com tamanho hardcoded e chamava
   `self.transcribe(audio_data, language)` perdendo `initial_prompt`.
   Agora usa `self.model_size` e repassa todos os parâmetros.

4. **Tasks coletáveis pelo GC.** `asyncio.create_task(...)` sem referência
   forte. Agora ficam em `room.pending_tasks: set` com
   `task.add_done_callback(room.pending_tasks.discard)`.

5. **Race no `audio_ended`.** Finalizava o jogo sem esperar transcrições em
   voo, então a média final podia não incluir os últimos segmentos. Agora
   `await asyncio.wait_for(asyncio.gather(*pending_tasks), timeout=10.0)`.

**Cleanups:**

- Regex de alucinações do Whisper compilada **uma vez** como `_HALLUCINATION_RE`
  no escopo de módulo (antes recompilava por segmento e por palavra).
- `ACOUSTIC_NORMALIZATION` separado em `_ACOUSTIC_EN` e `_ACOUSTIC_PT`.
  Antes colidiam: `"a" → "ah"` quebrava inglês, `"know" → "no"` quebrava
  português. Função `clean_text(text, language)` escolhe o mapa correto.
  `calculate_score(..., language=...)` recebe e propaga.
- Thresholds (`70`, `50`, `80`, `0.4`, `1.0`, `2.5`, `0.85`, `0.65`...)
  extraídos para constantes nomeadas no topo do `score_engine.py`.
- Helper `KaraokeRoom.broadcast(msg)` substitui ~10 ocorrências do padrão
  `if room.display: try: send_json(); if room.mic: try: send_json()`.
- Todos os `except: pass` silenciosos viraram
  `except Exception as e: logger.debug(...)` (antes engoliam
  `KeyboardInterrupt`/`SystemExit`).
- Imports inline (`re`, `math`, `scipy.signal`, `socket`, `logging`) movidos
  para o topo dos respectivos módulos. `yt_dlp`, `prepare_song`, `difflib`,
  `uvicorn` permanecem lazy (são pesados/opcionais).

### `085c5e3` — Batch 2: extract `utils/` package

- **`utils/ffmpeg_bootstrap.py`**: função `bootstrap()` idempotente que
  localiza `ffmpeg.exe` em `%LOCALAPPDATA%\Microsoft\WinGet\Packages` (ou
  `\Links`), injeta no `PATH` e configura `pydub.AudioSegment.converter` /
  `.ffprobe`. Em Linux/macOS retorna `None` (no-op). Substitui ~30 linhas
  soltas no topo do `main.py`.
- **`utils/text.py`**:
  - `slugify(text)` agora usa `unicodedata.normalize("NFKD", ...)` em vez
    da tabela manual de acentos PT — funciona para qualquer idioma.
  - `parse_time_to_seconds(time_str)` aceita `"4:30"`, `"04:30.5"`,
    `"1:02:03"`, `"10"`. Sentinela: `"-1"`/`""` → `-1.0`.
- **`utils/lrc.py`**: `read_lrc_meta(lrc_path, fallback_title, fallback_artist)
  -> (title, artist)`. Substitui o mesmo bloco try/for/break duplicado em
  `SongManager.list_songs` e `SongManager.get_song_data`.
- `song_manager.py` reescrito: 93 → 50 linhas, comportamento idêntico.

### `500f88f` — Batch 3: extract `utils/youtube.py`

- `download_youtube_audio(url, output_path, ffmpeg_bin_dir=None)` movido
  para módulo próprio. `ffmpeg_bin_dir` agora é **parâmetro explícito** em
  vez de captura do escopo global — sem acoplamento implícito ao bootstrap.
- Lógica de limpeza de arquivos residuais (`.webm`/`.m4a`/`.part`) e import
  lazy de `yt_dlp` preservados.

---

## Invariantes / contratos importantes

- **`segments.json`** (gerado por `tools/prepare_song.py`) — cada segmento
  precisa de: `id`, `label`, `sing_start`, `sing_end`, `pause_end`,
  `lyrics`, `lyrics_timed` (lista de dicts com `word` e `expected_start`),
  `language`.
- **Mensagens WebSocket cliente→servidor:** `client_info` (sample_rate),
  `playback_time` (current_time do `<audio>`), `audio_ended`, e blobs
  binários PCM Float32 com áudio do mic.
- **Mensagens servidor→cliente:** `pairing_status`, `singing_state`,
  `segment_start`, `segment_result`, `outro_start`, `game_over`. Todas vão
  pelo helper `room.broadcast(...)`.
- **Sample rate do cliente** vem em `client_info` (default 48000).
  Resampling para 16 kHz (Whisper) usa `scipy.signal.resample_poly`.
- **RMS thresholds** (no `process_and_score`): vocalize → `>0.008` = 100,
  `>0.002` = 50, senão 0. STT silence gate: `rms < 0.0002` curto-circuita.
- **`KaraokeRoom.segment_buffers: dict[int, bytearray]`** — buffers
  dedicados por segmento, populados nas janelas
  `[sing_start - 1.5, sing_end + 0.5]`. O buffer global `audio_buffer`
  ainda existe para retrocompatibilidade mas não é mais a fonte da verdade.

---

## TODO / próximos passos sugeridos para a próxima IA

Em ordem de impacto:

1. **Extrair o alinhamento Whisper↔letra plana** (~150 linhas dentro de
   `upload_song`, a partir de `if plain_lyrics and plain_lyrics.strip()`)
   para `utils/lrc_align.py`. Função pura: recebe `plain_lyrics`,
   `whisper_segments`, `lyrics_start_val`, `total_duration` e devolve o
   conteúdo LRC + flag `fallback_used`.

2. **Quebrar `main.py` em routers.** Criar `routes/songs.py` (list/get
   audio/delete), `routes/upload.py` (`upload_song`), `routes/lyrics.py`
   (`get_lyrics`/`save_lyrics`), `routes/system.py` (`get_ip`),
   `ws/room.py` (handler `/ws/room/{room_id}` + `process_and_score`).
   Montar com `APIRouter` em `main.py`. Alvo: `main.py` < 100 linhas.

3. **`tools/` virar package** (criar `tools/__init__.py`) e importar
   `from tools.prepare_song import prepare_song` no topo de `main.py`,
   eliminando os 3 `sys.path.append` em runtime.

4. **Modelar com dataclasses/Pydantic.** `KaraokeRoom`, `Segment`,
   mensagens WS (`SegmentStartMsg`, `SegmentResultMsg`...) — elimina dicts
   soltos e dá validação. Considere `pydantic.BaseModel` já que FastAPI
   está disponível.

5. **Testes** — `tests/` ainda não existe. Começar por unidades puras:
   - `score_engine.calculate_score` (vários casos: match exato, leakage,
     sandwich recovery, timing penalty)
   - `utils.text.parse_time_to_seconds` (formatos válidos e inválidos)
   - `utils.text.slugify` (PT/EN/CJK)
   - `utils.lrc.read_lrc_meta`

6. **Concorrência em `room.total_score`/`scored_count`.** Múltiplas
   `create_task` mutam. O GIL salva em CPython, mas se um dia o servidor
   rodar com `--workers > 1` ou interpretador free-threaded, será bug.
   Considerar `asyncio.Lock`.

7. **CORS `allow_origins=["*"]`** está aberto. Restringir em produção.

8. **Configuração via env**: `WHISPER_MODEL` (atualmente hardcoded
   `"medium"`), `WHISPER_DEVICE` (atualmente `"auto"`), porta do uvicorn,
   diretório de songs.

9. **Logging único.** `logging.basicConfig` é chamado em `main.py` **e**
   `stt_engine.py`. Configurar uma vez no entrypoint.

---

## Como rodar

```bash
cd karaoke/server
python -m venv .venv
.venv/Scripts/activate   # ou source .venv/bin/activate
pip install fastapi uvicorn numpy scipy faster-whisper rapidfuzz pydub yt-dlp
python main.py            # serve em 0.0.0.0:8000
```

Em Windows com ffmpeg instalado via Winget (`winget install ffmpeg`), o
`utils/ffmpeg_bootstrap.bootstrap()` localiza o binário automaticamente.
Em Linux/macOS, `ffmpeg` precisa estar no `PATH`.

---

## O que **não foi** alterado

- `client/` (frontend) — totalmente intocado.
- `tools/prepare_song.py` e `tools/generate_lrc.py` — intocados.
- Formato dos arquivos persistidos (`segments.json`, `lyrics.lrc`,
  `meta.json`, `backing_track.mp3`, `vocal.mp3`) — intactos.
- Protocolo WebSocket cliente↔servidor — todas as mensagens preservadas.
- A árvore `karaoke/server/songs/` — apenas dados, nada tocado.
