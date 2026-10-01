# 🏛️ System Architecture Guide

This document describes the high-level architecture, module contracts, data flow pipelines, configurations, and external dependencies of the Karaoke AI system.

---

## 1. System Overview & Purpose

Karaoke AI is a multi-device local singing and scoring system. It allows:
1. **Large Screen Console (Display / TV):** Renders lyrics, plays high-fidelity backing track audio, and renders score updates.
2. **Mobile Microphones (Phones):** Connect as wireless micro-controllers that capture audio, resample it to 16 kHz Int16 and stream `KM01` packets (100 ms, first-sample index in the header).
3. **AI Backend Server (FastAPI):** Orchestrates WebSocket rooms, manages pairing queues, places the 16 kHz audio on a per-player song timeline, transcribes vocals using faster-whisper, performs forced alignment using Torchaudio's MMS_FA model (line by line, with confidence), evaluates lyrics with RapidFuzz plus language normalization, and pitch with YIN (`server/pitch.py`). Party features (night queue, turns, profiles/records, shareable end card) run on the same room socket.

---

## 2. Component Diagram

```mermaid
graph TD
    subgraph Client Layer (Web Browser)
        TV[Display Console - TV]
        Mic1[Mobile Mic - Player 1]
        Mic2[Mobile Mic - Player 2]
    end

    subgraph Service Layer (FastAPI Server)
        API[HTTP REST Router]
        WS[WebSocket Room Server]
        SM[Song Manager]
        RM[Room Manager]
    end

    subgraph Processing Engine
        STT[STT Engine - faster-whisper]
        MMS[Forced Aligner - MMS_FA]
        SC[Score Engine - RapidFuzz]
    end

    subgraph Storage Layer
        DB[(Disk Database - songs/)]
        PROF[(Player Profiles - players/)]
    end

    TV -->|HTTP GET/POST| API
    Mic1 -->|WebSockets| WS
    Mic2 -->|WebSockets| WS
    TV -->|WebSockets| WS
    
    API --> SM
    WS --> RM
    
    SM --> DB
    RM --> STT
    RM --> SC
    
    API -->|align_lyrics| MMS
    API -->|reinstall| STT
    
    WS -->|game_over| PROF
```

---

## 3. Module & Service Specifications

### A. FastAPI Server (`server/main.py` & `server/routes/`)
- **Responsibility:** Pave HTTP endpoints for static assets, metadata listing, saving lyrics, uploading songs, and orchestrating the WebSocket game loop.
- **REST Endpoints:**
  - `GET /api/songs`: Lists all local songs scanned by `SongManager` (returns title, artist, ready status).
  - `GET /songs/{song_id}/audio`: Serves the backing track file (`backing_track.mp3`).
  - `GET /api/get-lyrics`: Retrieves the LRC content, plain text lyrics, and metadata for a song.
  - `POST /api/save-lyrics`: Saves manually edited LRC/metadata and triggers segment preparation.
  - `POST /api/upload-song`: Accepts files/URLs and starts background download and alignment.
  - `POST /api/reinstall-song/{song_id}`: Cleans the song folder and regenerates all tracks and alignments.
  - `GET /api/youtube-metadata`: Retrieves title/artist from a YouTube URL.
  - `GET /api/youtube-search`: Search YouTube by name (add-song step 1).
  - `POST /api/queue/add` · `GET /api/queue/status`: processing queue; status includes `alignment_busy` (GPU mutex: TV blocks INICIAR).
  - `GET /api/songs/{id}/cover` · `GET /api/songs/{id}/cover/options` · `POST /api/songs/{id}/cover`: album art (auto best candidate from iTunes/Deezer/YouTube, or a chosen option).
  - `GET /songs/{id}/vocal`: separated vocal (guide vocal).
  - `GET /api/players` · `GET /api/players/{name}` · `GET /api/songs/{id}/leaderboard`: ranking, profile, room bests.
  - `GET /api/recordings/{id}` · `GET /api/recordings/{id}/audio/{player}` · `POST /api/recordings/{id}/gabarito`: recorded games (calibration and replay).
  - `GET /api/status`: health panel (GPU, queue, per-room verse latency, disk).
  - Every song id/slug from the client goes through `utils/song_paths.safe_song_dir` (never leaves `songs/`).

### B. Room Manager (`server/rooms.py`)
- **Responsibility:** Manages room instances (`KaraokeRoom`), maps display/mic WebSockets, and handles the lifetime of room objects.
- **Properties:**
  - `display`: WebSocket reference to the active display.
  - `players`: Dict of `player_name` mapping to WebSocket references.
  - `unregistered_mics`: Waiting queue for connecting microphones.
  - `mic_timelines` + `song_clock`: per-player audio indexed by song time (`mic_stream.py`); each verse cuts its own disjoint window.
  - `segment_scores`: Cached scores per segment.
  - `game_id`: bumped per game/reset; late Whisper results from an older game are dropped.
  - `turn_order`: teams alternating verses (or `None`).
  - `song_requests`: night queue ("quero cantar").
  - `pitch_reference`, `transpose`, `player_pitch_scores`: pitch scoring against `pitch.json`.
  - `verse_latencies`: last 30 dispatch→result times (health panel).

### C. Speech-to-Text Engine (`server/stt_engine.py`)
- **Responsibility:** Wraps the `faster-whisper` model. Performs voice detection, filters out training hallucinations (e.g. "thanks for watching"), and returns confidence metrics.
- **Inputs:** Audio buffer (16kHz Float32 mono numpy array), language code, and expected lyric prompt.
- **Outputs:** `(transcription_text, word_list)` where `word_list` contains start/end times and probability scores. With `details={}` it also returns both runs (`prompted_words`, `unprompted_words`, `used`) — recorded for calibration.

### D. Scoring Engine (`server/score_engine.py`)
- **Responsibility:** Compares transcribed lyrics with expected lyrics.
- **Parameters & Mechanics:**
  - **Fuzzy Token Matching:** Employs RapidFuzz token sorting metrics.
  - **Language Normalization:** accents on both sides, Portuguese spoken forms (tá/está, tô/estou, cê/você, pra/para, à/a), numbers 0–20 spelled out, hyphen-split words ("Dá" + "-se"), low-probability ghost copies dropped. (Double Metaphone is used only in `utils/lrc_realign.py`, not in scoring.)
  - **Leakage Removal:** Trims text overlap leaking from previous segments.
  - **Sandwich Recovery:** Re-credits 1-2 missing words if surrounding words are correct.
  - **Timing Penalty:** Subtracts points if a word's start time diverges from the expected time (TIMING_TOLERANT_SEC, TIMING_LENIENT_SEC).
- **Inputs:** Expected lyric words, transcribed words, previous verse words, and language.
- **Outputs:** `{"score": float, "transcription": str, "matched_words": int, "total_expected": int}`.

---

## 4. Configuration Surface

The system can be configured using environment variables:

| Env Var | Description | Example Values | Default |
| :--- | :--- | :--- | :--- |
| `KARAOKE_HTTP` | Force server to run in HTTP mode (disabling key.pem/cert.pem checks). Useful for Cloudflare Tunneling. | `true`, `1`, `yes` | `false` |
| `PATH` | Server scans system PATH + localized directories to find `ffmpeg.exe` and Nvidia CUDA DLLs automatically. | — | — |
| `KARAOKE_PUBLIC_URL` | Public URL used in QR codes behind the tunnel. | `https://karaoke.example` | — |
| `KARAOKE_WHISPER_MODEL` / `_DEVICE` / `_COMPUTE` | faster-whisper model, device and compute type. | `small` / `cpu` / `int8` | `large-v3-turbo` / `auto` / per device |
| `KARAOKE_SEPARATOR` | Vocal separator: `roformer` (needs the optional `audio-separator` package), `demucs`, or `auto` (RoFormer when installed). | `demucs` | `auto` |
| `KARAOKE_ROFORMER_MODEL` / `_MODEL_DIR` | audio-separator model and its download folder. | `vocals_mel_band_roformer.ckpt` | `model_bs_roformer_ep_317_sdr_12.9755.ckpt` / `~/.cache/audio-separator-models` |
| `KARAOKE_DEMUCS_MODEL` | Demucs model for vocal separation. | `htdemucs_ft` | `htdemucs` |
| `KARAOKE_MP3_BITRATE` | Bitrate of vocal/backing MP3s. | `256k` | `320k` |
| `KARAOKE_RECORD` / `KARAOKE_RECORD_DIR` | Record games for calibration (`0` disables). | `0` | on / `recordings/` |
| `KARAOKE_PLAYERS_DIR` | Player profiles folder. | `/data/players` | `players/` |

---

## 5. External Dependencies

1. **FastAPI & Uvicorn:** Core HTTP & WebSockets routing loop.
2. **faster-whisper:** Local CTranslate2 implementation of OpenAI's Whisper model (delivers high transcription speed and GPU execution).
3. **torchaudio & torch (CUDA 12.4):** Drives Forced Alignment (PRO mode) using the PyTorch-based MMS_FA pipeline.
4. **demucs:** Isolates vocals and backing tracks.
5. **pydub & PyAV:** Handles audio I/O, format conversion (e.g. webm/m4a to MP3), resampling, and slicing.
6. **yt-dlp:** Fast metadata retrieval and audio downloads from YouTube.
7. **rapidfuzz & DoubleMetaphone:** Fuzzy scoring (Metaphone only in the LRC realigner).
8. **numpy:** YIN pitch tracking (`pitch.py`) and BS.1770 loudness (`utils/loudness.py`) — no scipy/librosa.
9. **iTunes Search / Deezer / LRCLIB / Lyrics.ovh (HTTP, no keys):** album art and lyrics lookup.
