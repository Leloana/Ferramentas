# 🗄️ Archived Backend Refactor Notes

> [!NOTE]
> **HISTÓRICO DO REFACTOR DO BACKEND / ARCHIVED REFACTOR HISTORY**
> Este documento serviu como nota de handoff para descrever a reorganização do backend do `main.py` monolítico para a estrutura modular de APIRouters atual.
> Para a documentação de referência atualizada, consulte:
> - [Guia do Projeto (PROJECT_GUIDE.md)](../guides/PROJECT_GUIDE.md)
> - [Manual de Arquitetura (ARCHITECTURE.md)](../architecture/ARCHITECTURE.md)

---

# Backend Refactor Notes — Handoff

Documento de transferência para a próxima IA/dev. Resume **o que mudou no backend (`karaoke/server/`)** ao longo de 8 commits no branch `main` (HEAD: `502eab9`).

**Antes:** 1 `main.py` de 1056 linhas + `score_engine.py` + `stt_engine.py` + `song_manager.py`.
**Agora:** `main.py` 52 linhas (só bootstrap). Cada handler num módulo; maior arquivo do projeto é `ws/room.py` com 339 linhas.

---

## Estrutura final

```
karaoke/server/
├── main.py              52   FastAPI app + monta 4 routers
├── state.py             16   Singletons: room_manager, song_manager, ffmpeg_bin_dir
├── rooms.py             61   KaraokeRoom + RoomManager
├── song_manager.py      50   Listagem/leitura de pastas de músicas
├── score_engine.py     181   Scoring fuzzy + sandwich recovery + leakage forgiveness
├── stt_engine.py       137   Wrapper faster-whisper com fallback CUDA→CPU
├── routes/
│   ├── __init__.py
│   ├── songs.py         74   GET / + list/audio/delete/get-ip
│   ├── lyrics.py        80   GET/POST lyrics.lrc + roda prepare_song
│   └── upload.py       209   POST /api/upload-song (3 caminhos: LRC pronto / letra plana / só Whisper)
├── ws/
│   ├── __init__.py
│   └── room.py         339   Handler /ws/room/{room_id} + process_and_score
└── utils/
    ├── __init__.py
    ├── ffmpeg_bootstrap.py   66   Localiza ffmpeg.exe via Winget no Windows
    ├── text.py               44   slugify + parse_time_to_seconds
    ├── lrc.py                34   read_lrc_meta (parser de header [ti:]/[ar:])
    ├── lrc_align.py         181   Alinha letra plana ↔ Whisper (função pura)
    ├── youtube.py            66   download_youtube_audio via yt-dlp
    └── prepare.py            16   run_prepare_song (wrapper para tools/prepare_song.py)
```

`tools/prepare_song.py` continua sendo importado dinamicamente (agora via `utils/prepare.run_prepare_song`, que checa `sys.path` antes de estender — evita crescimento ilimitado). **Não foi alterado** mas merece virar package próprio. Ver TODO.

---

## Histórico (do mais antigo para o mais novo)

### `7dd646a` — Batch 1: bugfixes + cleanups iniciais
- **Cálculo de média errado** corrigido (`room.scored_count` em vez de `seg_idx + 1` — tasks terminam fora de ordem).
- **WebSocket endpoint duplicado** removido (código morto em `/ws/{song_id}`).
- **STT fallback CUDA→CPU** preservava `model_size` e `initial_prompt`.
- **Regex de alucinações do Whisper** compilada uma vez como módulo-level.
- **Normalização acústica EN/PT** separada (antes colidiam: `"a"→"ah"` quebrava inglês, `"know"→"no"` quebrava português).
- **Thresholds extraídos** para constantes nomeadas em `score_engine.py`.
- **Helper `KaraokeRoom.broadcast(msg)`** substitui ~10 padrões de `if room.display: ...; if room.mic: ...`.
- **`except: pass`** silenciosos → `except Exception: logger.debug(...)`.
- **`pending_tasks` + `done_callback`** evita GC prematuro de tasks de transcrição.
- **`audio_ended` aguarda transcrições pendentes** (10s timeout) antes da pontuação final.

### `085c5e3` — Batch 2: extract `utils/`
- `utils/ffmpeg_bootstrap.py` — `bootstrap()` idempotente
- `utils/text.py` — `slugify()` agora usa `unicodedata.NFKD` (qualquer idioma) + `parse_time_to_seconds()`
- `utils/lrc.py` — `read_lrc_meta()` compartilhado com `song_manager`
- `song_manager.py` reescrito (93 → 50 linhas)

### `500f88f` — Batch 3: extract `utils/youtube.py`
- `download_youtube_audio()` movido; `ffmpeg_bin_dir` é parâmetro explícito em vez de captura de escopo

### `5c52ab7` — fix: último `except: pass` em `get_lyrics`

### `4da4456` — Refactor estrutural Parte 1: extract WebSocket layer
- `rooms.py` — `KaraokeRoom` + `RoomManager`
- `state.py` — singletons compartilhados (evita import circular)
- `ws/room.py` — handler WS via `APIRouter`, `process_and_score`, `_send_segment_start`, com constantes mágicas nomeadas (`PRE_SING_BUFFER_SEC`, `WHISPER_TARGET_SR`, `VOCALIZE_HIGH_RMS`...)
- `main.py`: 912 → 553

### `a3dbb47` — Refactor estrutural Parte 2: slim main.py
- `utils/lrc_align.py` — `align_plain_lyrics()` pura + `draft_lrc_from_whisper()`
- `utils/prepare.py` — `run_prepare_song()` evita duplicação de `sys.path.append`
- `routes/songs.py`, `routes/lyrics.py`, `routes/upload.py` — 3 routers via `APIRouter`
- `upload_song` decomposto em helpers (`_slice_with_padding`, `_vocal_to_float32_mono_16k`, `_acquire_sources`, `_build_meta`); fluxo principal ~60 linhas com 3 branches explícitos
- `state.py` também expõe `ffmpeg_bin_dir`
- `main.py`: 553 → **52**

### `bcb91cb` / `502eab9` — Documentação de handoff
- Este arquivo: criado em `bcb91cb`, atualizado em `502eab9` com a estrutura final pós-refactor estrutural.

---

## Invariantes / contratos importantes

- **`segments.json`** (gerado por `tools/prepare_song.py`) — cada segmento precisa de: `id`, `label`, `sing_start`, `sing_end`, `pause_end`, `lyrics`, `lyrics_timed` (lista de dicts com `word` e `expected_start`), `language`.
- **Mensagens WebSocket cliente→servidor:** `client_info`, `playback_time`, `audio_ended`, blobs binários PCM Float32.
- **Mensagens servidor→cliente:** `pairing_status`, `singing_state`, `segment_start`, `segment_result`, `outro_start`, `game_over`. Todas via `room.broadcast(...)`.
- **Sample rate do cliente** vem em `client_info` (default 48000). Resampling para 16 kHz (Whisper) usa `scipy.signal.resample_poly`.
- **RMS thresholds** (em `ws/room.py`): `VOCALIZE_HIGH_RMS=0.008`, `VOCALIZE_LOW_RMS=0.002`. STT silence gate em `stt_engine.py`: `0.0002`.
- **`KaraokeRoom.segment_buffers: dict[int, bytearray]`** — buffers dedicados por segmento, populados nas janelas `[sing_start - PRE_SING_BUFFER_SEC, sing_end + POST_SING_BUFFER_SEC]` (1.5s antes, 0.5s depois).
- **Singletons:** `room_manager` e `song_manager` vivem in `state.py`. Sempre importe de lá (não instancie de novo).

---

## TODO / próximos passos para a próxima IA

Em ordem de impacto:

1. **`tools/` virar package** (criar `tools/__init__.py`) e importar `from tools.prepare_song import prepare_song` no topo de `utils/prepare.py`, eliminando o `sys.path.append` runtime que sobrou.
2. **Modelar com dataclasses/Pydantic.** `KaraokeRoom`, `Segment`, mensagens WS — elimina dicts soltos e dá validação. FastAPI já está aí.
3. **Testes** — `tests/` ainda não existe. Começar pelas funções puras:
   - `score_engine.calculate_score` (match, leakage, sandwich, timing)
   - `utils.text.parse_time_to_seconds` / `slugify`
   - `utils.lrc.read_lrc_meta`
   - `utils.lrc_align.align_plain_lyrics` (já bem testável — pura)
4. **`ws/room.py` ainda é grande (339 linhas).** O loop principal do `while True:` poderia ser decomposto em `_handle_bytes`, `_handle_client_info`, `_handle_playback_time`, `_handle_audio_ended`. `process_and_score` poderia virar método de `KaraokeRoom`.
5. **Concorrência em `room.total_score`/`scored_count`.** Múltiplas `create_task` mutam. O GIL salva em CPython, mas se rodar `--workers > 1` ou interpretador free-threaded, vira bug. Usar `asyncio.Lock`.
6. **CORS `allow_origins=["*"]`** aberto. Restringir em produção.
7. **Config via env**: `WHISPER_MODEL` (hardcoded `"medium"` em `stt_engine.py`), `WHISPER_DEVICE`, porta do uvicorn, diretório de songs.
8. **Logging único.** `logging.basicConfig` chamado em `main.py` E `stt_engine.py`. Configurar uma vez no entrypoint.
9. **Lifespan handler.** Migrar do uvicorn ad-hoc para `lifespan=` context manager do FastAPI — boas práticas modernas.

---

## Como rodar

```bash
cd karaoke/server
python -m venv .venv
.venv/Scripts/activate   # ou source .venv/bin/activate
pip install fastapi uvicorn numpy scipy faster-whisper rapidfuzz pydub yt-dlp
python main.py            # serve em 0.0.0.0:8000
# ou:
# uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Em Windows com ffmpeg instalado via Winget (`winget install ffmpeg`), `utils/ffmpeg_bootstrap.bootstrap()` localiza o binário automaticamente (chamado uma vez no import de `state.py`). Em Linux/macOS, `ffmpeg` precisa estar no `PATH`.

---

## O que **não foi** alterado

- `client/` (frontend) — totalmente intocado.
- `tools/prepare_song.py` e `tools/generate_lrc.py` — intocados.
- Formato dos arquivos persistidos (`segments.json`, `lyrics.lrc`, `meta.json`, `backing_track.mp3`, `vocal.mp3`) — intactos.
- Protocolo WebSocket cliente↔servidor — todas as mensagens preservadas.
- `karaoke/server/songs/` — apenas dados, nada tocado.

---

## Como ler o código pela primeira vez

Sugestão de ordem para a próxima IA:

1. `main.py` (52 linhas) — entende a montagem.
2. `state.py` (16 linhas) — vê os singletons.
3. `rooms.py` (61 linhas) — modelo da sala.
4. `routes/songs.py` — rotas mais simples.
5. `routes/upload.py` — fluxo complexo, mas decomposto em helpers.
6. `ws/room.py` — o coração: loop WS + scoring.
7. `score_engine.py` — função pura `calculate_score`.
8. `utils/*` — helpers isolados, leitura linear.
