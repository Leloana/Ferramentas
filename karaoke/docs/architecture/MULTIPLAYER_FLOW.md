# 👥 Multiplayer & Multi-Device Flow

This document details the architecture and step-by-step flow of the multi-player, multi-device Karaoke AI system.

---

## 🏗️ Architectural Overview

The system operates on a client-server-client layout:
1. **Display (TV/Console):** Serves as the central display. Renders lyrics, plays instrumental tracks, manages playback state (seeking/time), and displays real-time score updates.
2. **Microphones (Phones):** Connect as wireless micro controllers that record and stream `KM01` packets (Int16 16 kHz) in real time and display lyrics/scores.
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
    Server->>Server: Calculate scores (fuzzy + language normalization) and pitch (YIN)
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
- **Display Connection:** The display connects to `/ws/room/{room_id}?role=display&song_id={song_id}`. Connecting resets the room's scores, active segments, and playback indicators (and bumps `room.game_id`, so late Whisper results from the previous game are dropped).
- **Display reconnect mid-song:** the game socket reconnects with `&resume=1`; the server keeps scores, recording and the current verse, and the client does not resend `start_game`.
- **Display replaced:** a new display in the same room closes the previous one with close code **4001**; a client that receives 4001 does not reconnect (two tabs would otherwise kick each other forever).
- **Microphone Connection:** Microphone devices connect to `/ws/room/{room_id}?role=mic` and are placed into the `room.unregistered_mics` queue.

### 2. Nickname Registration Queue
- To prevent nickname conflicts and clutter, only **one microphone** registers at a time.
- The server checks the queue:
  - The first connection receives `{"type": "register_request"}`.
  - All subsequent connections receive `{"type": "register_wait", "position": X}`.
- When the first microphone sends `{"type": "register_name", "name": "..."}`, the server:
  - Trims it to 15 printable characters and derives the profile key (alphanumeric, hyphens, underscores).
  - Checks if the name (or its case-insensitive profile key) is already in use or reserved (`solo`, `local`, `tv`, `pc_local`).
  - Creates the player profile directory on the server disk (`players/<sanitized_name>/profile.json`) if it does not exist.
  - Returns `{"type": "registration_success", "name": "..."}` and broadcasts a `players_update` list to the Display.
  - Automatically pops the queue and sends a `register_request` to the next microphone.

### 3. Lobby, Teams and Game Mode
There is no game-mode picker any more. The display shows a **lobby** (`client/js/lobby/lobby.js`): one seat per singer, added with "+". Each seat picks **its own microphone** (a registered phone or `PC_Local`, shown as "Local") and a **team** (A–D, the team button only shows with 2+ seats).
- **Everyone on their own team:** free-for-all — `game_mode` is `solo`, `1v1`, `1v1v1` or `1v1v1v1` (one per team).
- **Two or more seats on the same team:** duo/trio — `game_mode` is `teams`.

**Turns ("Revezar versos"):** with 2+ teams the lobby can alternate verses. `start_game` then carries `"turns": true, "turn_order": [[mics of team 1], [mics of team 2], ...]`; the k-th verse with lyrics belongs to team `k % n` (`ws/room.turn_owner`, mirrored in `client/js/game/turns.js`). Only the owner is scored, each player's final average is over their own verses, and `segment_start` carries `"turn": [...]` so phones show "Sua vez" / "Vez de ...".

**GPU mutex:** if a song is generating lyrics (`queue_manager.alignment_busy()`), the server answers `start_game` with `{"type": "start_blocked", "reason": "..."}` and does not start; the TV already disables INICIAR while `/api/queue/status` reports `alignment_busy`.

The display sends `{"type": "start_game", "game_mode": "...", "active_players": [...], "scoring_mode": "...", "transpose": 0}` with **one entry per microphone** (seat order, grouped by team). The server scores each microphone independently, exactly as before; it only stores `game_mode`. **Team scores are computed on the client**: `client/js/game/score-bars.js` shows one edge bar per team (up to 4: bottom, top, left, right) with the team average highlighted and a discreet bar per member, and the game-over podium ranks teams by the average of their members. The server resets game-wide aggregates, registers the active singers, and broadcasts `game_started` containing the active player list to all connected websockets.

### 4. Audio Routing & Buffering
- Microphones stream `KM01` packets (Int16 16 kHz + first-sample index) through WebSocket binary messages. The server anchors each player's sample counter to the song time.
- The display continually streams Uvicorn-synced playback updates `{"type": "playback_time", "current_time": X}`.
- Each packet goes into that player's `MicTimeline` (`server/mic_stream.py`), anchored to the song clock; with no registered players the stream key is `"Solo"`. Packets with a non-finite or negative first-sample index are rejected.
- The display also sends `{"type": "transpose", "semitones": n}` when the key changes, so the pitch reference follows the backing track.

### 5. Asynchronous Transcription & Scoring
- Once the playback time passes the end of the verse window: immediately if every scored player's audio already covers the window, otherwise after the late-packet grace (0.6–2 s):
  1. The server cuts the segment's disjoint window from the player's timeline (`mic_stream.segment_window`) — only for the verse owner in turns mode.
  2. Spawns an asynchronous task (strong reference in `room.pending_tasks`) to run transcription and scoring.
  3. Audio is already 16 kHz Int16 from the phone's AudioWorklet (no server resampling).
  4. Whisper runs off the event loop (`asyncio.to_thread`) under `queue_manager.whisper_lock`: prompted with the expected lyrics, retried without the prompt when the words are low-confidence (`pick_transcription`); both runs go to the recording.
  5. `score_engine.py` normalizes both sides (accents, contractions, numbers, hyphen-split words, vocalizations, low-probability ghost copies).
  6. Scores `0.0`–`100.0` (RapidFuzz, timing penalties, sandwich recovery, previous-verse leakage removal); `pitch.py` adds an informative pitch score from `pitch.json`.
  7. Broadcasts `{"type": "segment_result", "score", "pitch", "pitch_avg", "total_score", "combo", "player_scores": {name: {score, total_score, transcription, pitch, pitch_avg, combo}}}`. `combo` is the run of verses ≥ 85 in a row ending at the player's latest verse, in verse order (`server/combo.py`); the TV shows it from 2.

### 6. Seeking & Rewinding
- If a user seeks backward on the Display timeline, the display broadcasts the new `playback_time`.
- The server detects the backward time jump (`new_playback_time < room.last_client_time`).
- To prevent duplicate or corrupt stats:
  - Deletes all cached segment audio buffers starting from the new playback point.
  - Wipes segment scores from that index forward.
  - Recalculates total scoring averages for the room and all active players.
  - Broadcasts the reset score update with `"recalc": true` — clients update totals only (no verse stamp, no "Fora 0%").

### 7. Session Teardown
- Once the backing track ends, the display sends `{"type": "audio_ended"}`.
- The server halts inputs, awaits all running background transcription tasks, and calculates the final average score.
- For each active player, the server appends the round's results to `profile.json` under `songs_sung` (`server/players.py`: `song_id`, score, pitch, mode, date) and computes the personal record.
- Broadcasts `{"type": "game_over", "total_score", "player_scores", "player_pitch", "player_stats": {name: {good, ok, poor, best_combo}}, "records": {name: {is_record, best_before, times_sung}}, "leaderboard", "song_id", "song_title", "recording_id"}`. The TV and each phone build the shareable card and the "Ouvir" (replay) button from it.

### 7b. Audience Reactions
- A registered phone that is not singing this song shows three buttons and sends `{"type": "reaction", "kind": "heart" | "flame" | "star"}`.
- The server forwards `{"type": "reaction", "kind", "from"}` to the display only, while `room.in_game`, for players outside `active_players`, at most once per 0.4 s per phone (`REACTIONS`, `REACTION_MIN_INTERVAL_SEC` in `ws/room.py`). Anything else is dropped silently.
- The TV floats the icon with the sender's nickname (`game/reactions.js`, at most 12 on screen).

### 8. Night Queue ("quero cantar")
- A registered phone sends `{"type": "request_song", "song_id": "..."}` (the TV may send `"singer"` too); `{"type": "cancel_request", "id": "..."}` removes one (a phone only its own).
- The server keeps the list in `room.song_requests` (`server/song_requests.py`: max 30, 3 per singer) and broadcasts `{"type": "requests_update", "requests": [...]}`; errors come back as `request_error`.
- The TV shows "Próximas"; at game over it counts down 10 s and opens the next request in the lobby with the singer seated.
