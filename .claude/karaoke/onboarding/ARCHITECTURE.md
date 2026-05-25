# 🏛️ System Architecture Guide

This document describes the high-level architecture, module contracts, data flow pipelines, configurations, and external dependencies of the Karaoke AI system.

---

## 1. System Overview & Purpose

Karaoke AI is a multi-device local singing and scoring system. It allows:
1. **Large Screen Console (Display / TV):** Renders lyrics, plays high-fidelity backing track audio, and renders score updates.
2. **Mobile Microphones (Phones):** Connect as wireless micro-controllers that capture and stream PCM Float32 audio bytes in real-time.
3. **AI Backend Server (FastAPI):** Orchestrates WebSocket rooms, manages pairing queues, resamples and processes audio streams, transcribes vocals using faster-whisper, performs forced alignment using Torchaudio's MMS_FA model, and evaluates performance using RapidFuzz/Double Metaphone.

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

### B. Room Manager (`server/rooms.py`)
- **Responsibility:** Manages room instances (`KaraokeRoom`), maps display/mic WebSockets, and handles the lifetime of room objects.
- **Properties:**
  - `display`: WebSocket reference to the active display.
  - `players`: Dict of `player_name` mapping to WebSocket references.
  - `unregistered_mics`: Waiting queue for connecting microphones.
  - `player_segment_buffers`: Dual dictionary holding binary PCM Float32 audio bytes per player per segment index.
  - `segment_scores`: Cached scores per segment.

### C. Speech-to-Text Engine (`server/stt_engine.py`)
- **Responsibility:** Wraps the `faster-whisper` model. Performs voice detection, filters out training hallucinations (e.g. "thanks for watching"), and returns confidence metrics.
- **Inputs:** Audio buffer (16kHz Float32 mono numpy array), language code, and expected lyric prompt.
- **Outputs:** `(transcription_text, word_list)` where `word_list` contains start/end times and probability scores.

### D. Scoring Engine (`server/score_engine.py`)
- **Responsibility:** Compares transcribed lyrics with expected lyrics.
- **Parameters & Mechanics:**
  - **Fuzzy Token Matching:** Employs RapidFuzz token sorting metrics.
  - **Phonetic Checking:** Employs Double Metaphone for Portuguese and English phonetic approximations.
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

---

## 5. External Dependencies

1. **FastAPI & Uvicorn:** Core HTTP & WebSockets routing loop.
2. **faster-whisper:** Local CTranslate2 implementation of OpenAI's Whisper model (delivers high transcription speed and GPU execution).
3. **torchaudio & torch (CUDA 12.4):** Drives Forced Alignment (PRO mode) using the PyTorch-based MMS_FA pipeline.
4. **demucs:** Isolates vocals and backing tracks.
5. **pydub & PyAV:** Handles audio I/O, format conversion (e.g. webm/m4a to MP3), resampling, and slicing.
6. **yt-dlp:** Fast metadata retrieval and audio downloads from YouTube.
7. **rapidfuzz & DoubleMetaphone:** Fuzzy and phonetic string scoring.
