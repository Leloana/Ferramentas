# 👥 Multiplayer & Multi-Device Flow

This document details the architecture and step-by-step flow of the multi-player, multi-device Karaoke AI system.

---

## 🏗️ Architectural Overview

The system operates on a client-server-client layout:
1. **Display (TV/Console):** Serves as the central display. Renders lyrics, plays instrumental tracks, manages playback state (seeking/time), and displays real-time score updates.
2. **Microphones (Phones):** Connect as wireless micro controllers that record and stream PCM Float32 audio bytes in real time and display lyrics/scores.
3. **Server (FastAPI):** Coordinates WebSocket rooms, queues registrations, routes incoming audio buffers, transcribes segments, and evaluates scores.

```mermaid
sequenceDiagram
    autonumber
    actor Display as TV (Display)
    actor Mic1 as Mobile Mic 1 (Player 1)
    actor Mic2 as Mobile Mic 2 (Player 2)
    participant Server as FastAPI Server (ws/room)
    database Profiles as Disk (players/name/profile.json)

    Note over Display, Server: 1. Room Initialization
    Display->>Server: Connect WS (role=display, song_id=song-slug)
    Server-->>Display: pairing_status: unpaired, singing_state: inactive

    Note over Mic1, Server: 2. Registration & Queue Handshake
    Mic1->>Server: Connect WS (role=mic)
    Server-->>Mic1: register_request (First in queue)
    
    Mic2->>Server: Connect WS (role=mic)
    Server-->>Mic2: register_wait (position=1)

    Mic1->>Server: Send register_name {name: "Alice"}
    Server->>Profiles: Load/Create profile.json for "Alice"
    Server-->>Mic1: registration_success {name: "Alice"}
    Server-->>Display: players_update {players: ["Alice"]}
    
    Note over Mic2, Server: Mic 2 gets promoted to registration
    Server-->>Mic2: register_request
    Mic2->>Server: Send register_name {name: "Bob"}
    Server->>Profiles: Load/Create profile.json for "Bob"
    Server-->>Mic2: registration_success {name: "Bob"}
    Server-->>Display: players_update {players: ["Alice", "Bob"]}

    Note over Display, Server: 3. Game Start
    Display->>Server: start_game {game_mode: "1v1", active_players: ["Alice", "Bob"]}
    Server-->>Display: game_started {active_players: ["Alice", "Bob"]}
    Server-->>Mic1: game_started {active_players: ["Alice", "Bob"]}
    Server-->>Mic2: game_started {active_players: ["Alice", "Bob"]}

    Note over Display, Server: 4. Real-Time Singing Loop
    Display->>Server: playback_time {current_time: 2.5}
    Server-->>Display: singing_state: active (segment 1 is playing)
    Server-->>Mic1: singing_state: active
    Server-->>Mic2: singing_state: active
    
    Mic1->>Server: Stream Audio (binary bytes)
    Note right of Mic1: Bytes appended to Alice's Segment 1 buffer
    Mic2->>Server: Stream Audio (binary bytes)
    Note right of Mic2: Bytes appended to Bob's Segment 1 buffer

    Note over Display, Server: 5. Segment Scoring (Async)
    Display->>Server: playback_time {current_time: 6.0} (Past segment end)
    Server-->>Display: singing_state: inactive
    Note right of Server: Spawns asyncio task for Segment 1 transcription
    Server->>Server: Whisper transcribe (Alice) & (Bob) in threads
    Server->>Server: Calculate phonetic scores (Fuzz/Metaphone)
    Server-->>Display: segment_result {Alice: 88%, Bob: 91%}
    Server-->>Mic1: segment_result {Alice: 88%}
    Server-->>Mic2: segment_result {Bob: 91%}

    Note over Display, Server: 6. End Game & Persistence
    Display->>Server: audio_ended
    Server->>Profiles: Save Alice score 88% & Bob score 91%
    Server-->>Display: game_over {Alice: 88%, Bob: 91%}
    Server-->>Mic1: game_over {Alice: 88%}
    Server-->>Mic2: game_over {Bob: 91%}
```

---

## 🎬 Detailed Step-by-Step Flow

### 1. Connection & Pairing
- **Display Connection:** The display connects to `/ws/room/{room_id}?role=display&song_id={song_id}`. Connecting resets the room's scores, active segments, and playback indicators.
- **Microphone Connection:** Microphone devices connect to `/ws/room/{room_id}?role=mic` and are placed into the `room.unregistered_mics` queue.

### 2. Nickname Registration Queue
- To prevent nickname conflicts and clutter, only **one microphone** registers at a time.
- The server checks the queue:
  - The first connection receives `{"type": "register_request"}`.
  - All subsequent connections receive `{"type": "register_wait", "position": X}`.
- When the first microphone sends `{"type": "register_name", "name": "..."}`, the server:
  - Sanitizes the name (allowing only alphanumeric, hyphens, and underscores).
  - Checks if the name is already in use or is a reserved keyword (`solo`, `local`, `tv`).
  - Creates the player profile directory on the server disk (`players/<sanitized_name>/profile.json`) if it does not exist.
  - Returns `{"type": "registration_success", "name": "..."}` and broadcasts a `players_update` list to the Display.
  - Automatically pops the queue and sends a `register_request` to the next microphone.

### 3. Game Mode Configurations
The display sets the active singers for the round:
- **Solo:** Single microphone, scoring tracks standard session stats.
- **1v1 (Duels):** Active players are listed. Each microphone streams audio, and individual segments are scored and rendered in real time.
- **Duos (2v2):** Averages scores from dual player pairs.

Once configured, the display sends `{"type": "start_game", "game_mode": "...", "active_players": [...]}`. The server resets game-wide aggregates, registers the active singers, and broadcasts `game_started` containing the active player list to all connected websockets.

### 4. Audio Routing & Buffering
- Microphones stream raw PCM Float32 audio bytes through WebSocket binary messages.
- The display continually streams Uvicorn-synced playback updates `{"type": "playback_time", "current_time": X}`.
- The server maps the current time against the loaded song segments:
  - If the player is within the active singing window of a segment (plus preparation margins: `PRE_SING_BUFFER_SEC` and `POST_SING_BUFFER_SEC`), the server appends the incoming audio bytes to that player's segment-specific buffer:
    `room.player_segment_buffers[player_name][segment_idx]`
  - If no active players are registered (e.g. guest mode), the server defaults to appending audio to a global segment buffer `room.segment_buffers[segment_idx]`.

### 5. Asynchronous Transcription & Scoring
- Once the playback time exceeds the segment's singing duration (`current_time >= seg["sing_end"] + POST_SING_BUFFER_SEC`):
  1. The server extracts the accumulated PCM Float32 buffer for the segment.
  2. Spawns an asynchronous task using `asyncio.create_task` to run the transcription and scoring pipeline.
  3. The task resamples the microphone input from its source rate (typically 48kHz) to Whisper's 16kHz rate using `scipy.signal.resample_poly`.
  4. Transcription is executed off the main FastAPI event loop via `asyncio.to_thread` to maintain loop responsiveness.
  5. The `score_engine.py` cleanses the expected lyrics and transcription (e.g. applying contractions, stripping vocalize particles like *ah/oh*).
  6. Evaluates a matching score (`0.0` to `100.0`) based on RapidFuzz ratio, penalizes latency errors, applies sandwich recovery to repair missing words, and filters previous verse audio leakage.
  7. Broadcasts the final segment evaluation `{"type": "segment_result", "score": ..., "player_scores": {...}}` to the display and players.

### 6. Seeking & Rewinding
- If a user seeks backward on the Display timeline, the display broadcasts the new `playback_time`.
- The server detects the backward time jump (`new_playback_time < room.last_client_time`).
- To prevent duplicate or corrupt stats:
  - Deletes all cached segment audio buffers starting from the new playback point.
  - Wipes segment scores from that index forward.
  - Recalculates total scoring averages for the room and all active players.
  - Broadcasts the reset score update to keep client interfaces aligned.

### 7. Session Teardown
- Once the backing track ends, the display sends `{"type": "audio_ended"}`.
- The server halts inputs, awaits all running background transcription tasks, and calculates the final average score.
- For each active player, the server appends the round's results to `profile.json` under `songs_sung` (storing song metadata, score, and timestamps).
- Broadcasts the final average report `{"type": "game_over", "player_scores": {...}}` to all websockets.
