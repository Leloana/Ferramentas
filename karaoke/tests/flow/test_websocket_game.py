# tests/flow/test_websocket_game.py
"""Flow/Integration tests for Karaoke WebSocket game loop and pairing."""

import unittest
import sys
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root and server to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from fastapi.testclient import TestClient

class TestWebsocketGameFlow(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Create temporary songs directory
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="karaoke_test_ws_"))
        
        # Prepopulate with a mock song
        cls.song_slug = "ws-test-song"
        cls.song_dir = cls.temp_dir / cls.song_slug
        cls.song_dir.mkdir(parents=True, exist_ok=True)
        
        cls.meta_data = {
            "meta": {
                "title": "WS Song",
                "artist": "WS Artist",
                "language": "en",
                "slug": cls.song_slug
            }
        }
        with open(cls.song_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(cls.meta_data, f, indent=4)
            
        cls.segments = [
            {
                "id": 1,
                "label": "Parte 1",
                "sing_start": 1.0,
                "sing_end": 5.0,
                "pause_start": 5.0,
                "pause_end": 6.0,
                "language": "en",
                "lyrics": "hello world",
                "lyrics_timed": [
                    {"word": "hello", "expected_start": 0.5, "expected_end": 1.0},
                    {"word": "world", "expected_start": 1.1, "expected_end": 2.0}
                ]
            }
        ]
        with open(cls.song_dir / "segments.json", "w", encoding="utf-8") as f:
            json.dump(cls.segments, f, indent=4)

        with open(cls.song_dir / "backing_track.mp3", "w", encoding="utf-8") as f:
            f.write("mock backing track")

        # Patch state singletons
        cls.patcher_dir = patch("state.SONGS_DIR", cls.temp_dir)
        cls.patcher_dir.start()

        from song_manager import SongManager
        cls.mock_song_manager = SongManager(cls.temp_dir)
        cls.patcher_mgr = patch("state.song_manager", cls.mock_song_manager)
        cls.patcher_mgr.start()
        
        cls.patcher_room_songs = patch("server.ws.room.song_manager", cls.mock_song_manager)
        cls.patcher_room_songs.start()

        from main import app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.patcher_dir.stop()
        cls.patcher_mgr.stop()
        cls.patcher_room_songs.stop()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    @patch("ws.room.get_stt_engine")
    def test_websocket_full_game_loop(self, mock_get_stt):
        # Mock Whisper Engine
        mock_stt = MagicMock()
        # Mock transcription return: (text, words)
        mock_stt.transcribe.return_value = ("hello world", [
            {"word": "hello", "start": 0.6, "end": 0.9, "probability": 0.95},
            {"word": "world", "start": 1.2, "end": 1.8, "probability": 0.99}
        ])
        mock_get_stt.return_value = mock_stt

        room_id = "testroom123"

        # 1. Connect Display client first
        with self.client.websocket_connect(f"/ws/room/{room_id}?role=display&song_id={self.song_slug}") as ws_display:
            msg_pairing = ws_display.receive_json()
            self.assertEqual(msg_pairing["type"], "pairing_status")

            msg_players = ws_display.receive_json()
            self.assertEqual(msg_players["type"], "players_update")

            msg = ws_display.receive_json()
            # Initial singing state update
            self.assertEqual(msg["type"], "singing_state")
            self.assertFalse(msg["active"])

            # 2. Connect Mic client (Player 1)
            with self.client.websocket_connect(f"/ws/room/{room_id}?role=mic") as ws_mic:
                # Mic receives registration request
                msg_mic = ws_mic.receive_json()
                self.assertEqual(msg_mic["type"], "register_request")

                # Mic receives singing_state next
                msg_mic_sing = ws_mic.receive_json()
                self.assertEqual(msg_mic_sing["type"], "singing_state")

                # Register nickname
                ws_mic.send_json({"type": "register_name", "name": "PlayerOne"})
                msg_mic_reg = ws_mic.receive_json()
                self.assertEqual(msg_mic_reg["type"], "registration_success")
                self.assertEqual(msg_mic_reg["name"], "PlayerOne")

                # Display should receive pairing_status and players_update from registration
                msg_disp_pair = ws_display.receive_json()
                self.assertEqual(msg_disp_pair["type"], "pairing_status")
                msg_disp_update = ws_display.receive_json()
                self.assertEqual(msg_disp_update["type"], "players_update")
                self.assertIn("PlayerOne", msg_disp_update["players"])

                # Send client info from display
                ws_display.send_json({"type": "client_info", "sample_rate": 48000})
                
                # Display and mic receive segment_start for the first segment
                msg_disp_seg = ws_display.receive_json()
                self.assertEqual(msg_disp_seg["type"], "segment_start")
                self.assertEqual(msg_disp_seg["id"], 1)

                # 3. Start game
                ws_display.send_json({
                    "type": "start_game",
                    "game_mode": "solo",
                    "active_players": ["PlayerOne"]
                })
                
                # Both receive game_started notification
                msg_game_start = ws_display.receive_json()
                self.assertEqual(msg_game_start["type"], "game_started")
                self.assertEqual(msg_game_start["active_players"], ["PlayerOne"])

                # 4. Stream PCM Audio bytes from Mic
                # Send mock audio with some energy (Float32 values of 0.1) so that RMS > 0.0018 noise gate threshold
                import numpy as np
                mock_audio_bytes = np.full(1000, 0.1, dtype=np.float32).tobytes()
                
                # Set playback time in singing range
                # Segment 1: sing_start=1.0, sing_end=5.0
                ws_display.send_json({"type": "playback_time", "current_time": 2.0})
                msg_active = ws_display.receive_json()
                self.assertEqual(msg_active["type"], "singing_state")
                self.assertTrue(msg_active["active"])

                # Mic streams bytes
                ws_mic.send_bytes(mock_audio_bytes)

                # Move playback time past the segment end to trigger transcription
                ws_display.send_json({"type": "playback_time", "current_time": 6.0})
                
                # The display should receive outro_start first (since segment index check runs first)
                msg_outro = ws_display.receive_json()
                self.assertEqual(msg_outro["type"], "outro_start")

                # And then it should receive singing_state: inactive
                msg_inactive = ws_display.receive_json()
                self.assertEqual(msg_inactive["type"], "singing_state")
                self.assertFalse(msg_inactive["active"])

                # And then it receives the segment score result
                msg_score = ws_display.receive_json()
                self.assertEqual(msg_score["type"], "segment_result")
                self.assertGreaterEqual(msg_score["score"], 80.0) # High score expected for matching words
                self.assertEqual(msg_score["transcription"], "hello world")

                # 5. End Audio
                ws_display.send_json({"type": "audio_ended"})
                msg_game_over = ws_display.receive_json()
                self.assertEqual(msg_game_over["type"], "game_over")
                self.assertGreaterEqual(msg_game_over["player_scores"]["PlayerOne"], 80.0)

if __name__ == "__main__":
    unittest.main()
