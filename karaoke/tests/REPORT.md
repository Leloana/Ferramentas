# Codebase Audit & Test Report

This report summarizes the results of the Karaoke AI system codebase audit, the bugs identified and resolved, and the test suite executions.

---

## 📊 Test Suite Execution Summary

The test suite consists of **23 tests** covering unit calculations, individual modules, and end-to-end integration flows. All 23 tests executed successfully and passed.

| Flow Name / Test Domain | Test File | Result | Notes |
| :--- | :--- | :---: | :--- |
| **Forced Alignment (PRO)** | [test_escolta_vagalumes.py](file:///c:/Users/mf827/Documents/Ferramentas/karaoke/tests/test_escolta_vagalumes.py) | **PASS** | Validates Torchaudio MMS_FA forced alignment on GPU (CUDA 12.4 / RTX 4070) with 32 segments, including hyphen/accent normalization, CTC tokenization, and monotonicity logic. |
| **Fuzzy Scoring Engine** | [test_score_engine.py](file:///c:/Users/mf827/Documents/Ferramentas/karaoke/tests/unit/test_score_engine.py) | **PASS** | Verifies text cleaning (PT/EN contractions, accent preservation), fuzz token ratio scoring, leakage removal, timing penalties, sandwich recovery, and vocal fragment filtering. |
| **LRC Text Alignment** | [test_lrc_alignment.py](file:///c:/Users/mf827/Documents/Ferramentas/karaoke/tests/unit/test_lrc_alignment.py) | **PASS** | Tests the cursor forward-only fuzzy matching algorithm (`lrc_align.py`) and MMS_FA pre-tokenization (`lrc_pro.py`). |
| **STT Confidence Gate** | [test_stt_engine.py](file:///c:/Users/mf827/Documents/Ferramentas/karaoke/tests/unit/test_stt_engine.py) | **PASS** | Verifies adaptive confidence threshold checks against segment background noise levels. |
| **FastAPI HTTP APIs** | [test_http_api.py](file:///c:/Users/mf827/Documents/Ferramentas/karaoke/tests/flow/test_http_api.py) | **PASS** | Validates song listing, retrieve/serve audio backing, get/save lyrics, deleting, and local IP resolution endpoints under a isolated temporary directory sandbox. |
| **YouTube Metadata** | [test_youtube_metadata.py](file:///c:/Users/mf827/Documents/Ferramentas/karaoke/tests/flow/test_youtube_metadata.py) | **PASS** | Tests YouTube video information extractor heuristics and cleans off tags like (Official Video) or (Lyric Video). |
| **Upload & Reinstall** | [test_upload_pipeline.py](file:///c:/Users/mf827/Documents/Ferramentas/karaoke/tests/flow/test_upload_pipeline.py) | **PASS** | Verifies upload parameter verification, file saving to disk, structure of meta.json, and mocked reinstall pipeline execution. |
| **WebSocket Game Loop** | [test_websocket_game.py](file:///c:/Users/mf827/Documents/Ferramentas/karaoke/tests/flow/test_websocket_game.py) | **PASS** | Simulates a full room: display connects, microphone client registers, display sends start_game, mic streams non-silent PCM Float32 bytes, playback seek, segment boundaries transcription task, and game over final calculations. |

---

## 🐛 Bugs Found & Fixed

During Phase 1 (Codebase Exploration) and Phase 2 (Active Flow Testing), three critical bugs were identified and successfully resolved:

1. **CPU/GPU-Intensive Event Loop Blocking**
   - *Description:* Routes `/api/save-lyrics`, `/api/upload-song`, and `/api/reinstall-song/{song_id}` executed heavy transcription/separation pipelines synchronously on the main thread. This completely blocked the FastAPI async loop, freezing the server and dropping active WebSockets.
   - *File(s):* [server/routes/lyrics.py](file:///c:/Users/mf827/Documents/Ferramentas/karaoke/server/routes/lyrics.py), [tools/reinstall_song.py](file:///c:/Users/mf827/Documents/Ferramentas/karaoke/tools/reinstall_song.py).
   - *Severity:* **Critical**
   - *Fix Applied:* Yes. Offloaded all heavy CPU/GPU operations (MMS_FA alinhamento, Whisper transcription, Demucs execution, prepare_song, and generate_lrc) to background worker threads using `asyncio.to_thread`.
2. **Unassigned `room.mic` & Silent Disconnection**
   - *Description:* When the TV/Display disconnected, cleanup logic attempted to notify ONLY `room.mic` of the unpairing. However, `room.mic` was never populated at runtime (all microphones are stored under `room.players` or `room.unregistered_mics`). As a result, active players never knew the display disconnected.
   - *File(s):* [server/ws/room.py](file:///c:/Users/mf827/Documents/Ferramentas/karaoke/server/ws/room.py).
   - *Severity:* **Major**
   - *Fix Applied:* Yes. The finally block was rewritten to loop through `list(room.players.values()) + room.unregistered_mics` and send `pairing_status: unpaired` to all of them.
3. **Empty Nickname Path Traversal**
   - *Description:* Name sanitization allowed names to filter down to empty strings (e.g. if the user registered with `"???"`). This caused player profiles to resolve directly to the root `players/profile.json` file, corrupting files and violating folder isolation.
   - *File(s):* [server/ws/room.py](file:///c:/Users/mf827/Documents/Ferramentas/karaoke/server/ws/room.py).
   - *Severity:* **Minor**
   - *Fix Applied:* Yes. Added check during name registration to reject any nickname that sanitizes to empty. Also, `get_player_profile_path` now returns `"default_player"` as a fallback if the sanitized result is empty.

---

## 🕳️ Testing Gaps
- **Real YouTube Audio Download:** Because tests must run quickly and isolated from external networks, the yt-dlp downloader was mocked in `test_upload_pipeline.py`.
- **GPU Fallback to CPU:** Test suite does not manually trigger a PyTorch CUDA memory corruption crash to verify Whisper's dynamic fallback to CPU. This is handled at runtime via a broad `RuntimeError` block in `stt_engine.py` and has been validated by code review.

---

## 💡 Recommendations for Future Expansion
1. **Concurrency Load Testing:** Simulate 4 active players streaming PCM Float32 audio bytes simultaneously to verify that Python's GIL does not cause audio buffer stutters.
2. **Client-Side Latency Compensation tests:** Write automated checks for mic-side audio timestamps once latency calibration headers are introduced into the WebSocket protocol.
