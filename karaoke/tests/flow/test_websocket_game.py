# tests/flow/test_websocket_game.py
"""Flow/Integration tests for Karaoke WebSocket game loop and pairing."""

import unittest
import sys
import time
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
        
        cls.patcher_room_songs = patch("ws.room.song_manager", cls.mock_song_manager, create=True)
        cls.patcher_room_songs.start()
        
        import sys
        for name in ["ws.room", "server.ws.room"]:
            if name in sys.modules:
                sys.modules[name].song_manager = cls.mock_song_manager

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
        # Canto no tempo exato. A janela do verso começa em 0.0 (sing_start 1.0 - 1.5,
        # limitado a 0), então o Whisper mede +1.0 s em relação ao lyrics_timed.
        mock_stt.transcribe.return_value = ("hello world", [
            {"word": "hello", "start": 1.5, "end": 1.9, "probability": 0.95},
            {"word": "world", "start": 2.1, "end": 2.8, "probability": 0.99}
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
                # Pacote KM01 (Int16 16 kHz) com energia 0.1, acima do gate de RMS 0.0018
                import numpy as np
                from mic_stream import build_packet
                mock_audio_bytes = build_packet(0, np.full(1000, 0.1, dtype=np.float32))
                
                # Set playback time in singing range
                # Segment 1: sing_start=1.0, sing_end=5.0
                ws_display.send_json({"type": "playback_time", "current_time": 2.0})
                msg_active = ws_display.receive_json()
                self.assertEqual(msg_active["type"], "singing_state")
                self.assertTrue(msg_active["active"])

                # Mic streams bytes
                ws_mic.send_bytes(mock_audio_bytes)

                # Move playback time past the segment end + grace to trigger transcription
                ws_display.send_json({"type": "playback_time", "current_time": 6.2})
                
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
                self.assertEqual(msg_score["score"], 100.0)  # sem o deslocamento da janela daria 85
                self.assertEqual(msg_score["transcription"], "hello world")

                # 5. End Audio
                ws_display.send_json({"type": "audio_ended"})
                msg_game_over = ws_display.receive_json()
                self.assertEqual(msg_game_over["type"], "game_over")
                self.assertGreaterEqual(msg_game_over["player_scores"]["PlayerOne"], 80.0)

    @patch("ws.room.get_stt_engine")
    def test_last_verse_is_scored_when_audio_ends_inside_grace(self, mock_get_stt):
        """Música acaba entre o fim da janela e a folga de pacote atrasado: o verso ainda pontua."""
        import numpy as np
        from mic_stream import build_packet

        mock_stt = MagicMock()
        mock_stt.transcribe.return_value = ("hello world", [
            {"word": "hello", "start": 1.5, "end": 1.9, "probability": 0.95},
            {"word": "world", "start": 2.1, "end": 2.8, "probability": 0.99}
        ])
        mock_get_stt.return_value = mock_stt

        # Relógio do servidor avança junto com a música (sem isso 2.0 → 5.6 vira seek).
        server_clock = {"now": 100.0}
        clock_patch = patch("mic_stream._monotonic", lambda: server_clock["now"])
        clock_patch.start()
        self.addCleanup(clock_patch.stop)
        # Folga larga: o pacote pós-audio_ended depende de escalonamento real de threads.
        grace_patch = patch("ws.room._late_packet_grace", lambda room: 1.5)
        grace_patch.start()
        self.addCleanup(grace_patch.stop)

        with self.client.websocket_connect(f"/ws/room/graceroom?role=display&song_id={self.song_slug}") as ws_display:
            for expected_type in ("pairing_status", "players_update", "singing_state"):
                self.assertEqual(ws_display.receive_json()["type"], expected_type)

            with self.client.websocket_connect("/ws/room/graceroom?role=mic") as ws_mic:
                self.assertEqual(ws_mic.receive_json()["type"], "register_request")
                self.assertEqual(ws_mic.receive_json()["type"], "singing_state")
                ws_mic.send_json({"type": "register_name", "name": "PlayerTwo"})
                self.assertEqual(ws_mic.receive_json()["type"], "registration_success")
                self.assertEqual(ws_display.receive_json()["type"], "pairing_status")
                self.assertEqual(ws_display.receive_json()["type"], "players_update")

                ws_display.send_json({"type": "start_game", "game_mode": "solo", "active_players": ["PlayerTwo"]})
                self.assertEqual(ws_display.receive_json()["type"], "game_started")

                ws_display.send_json({"type": "playback_time", "current_time": 2.0})
                self.assertEqual(ws_display.receive_json()["type"], "singing_state")
                ws_mic.send_bytes(build_packet(0, np.full(1000, 0.1, dtype=np.float32)))

                # Janela do verso fecha em 5.5 s; 5.6 s ainda está dentro da folga.
                server_clock["now"] += 3.6
                ws_display.send_json({"type": "playback_time", "current_time": 5.6})
                self.assertEqual(ws_display.receive_json()["type"], "outro_start")
                self.assertEqual(ws_display.receive_json()["type"], "singing_state")

                # Pacote atrasado pela rede: amostras de 5.4 s (dentro da janela) chegando em 5.6 s.
                # Âncora = 2.0 - 1000/16000 = 1.9375, então o índice de 5.4 s é 55400.
                ws_mic.send_bytes(build_packet(55400, np.full(1000, 0.1, dtype=np.float32)))
                # Ida e volta no mesmo socket garante que o pacote já foi processado.
                ws_mic.send_json({"type": "register_name", "name": "PlayerTwo"})
                mic_types = []
                while "registration_error" not in mic_types and len(mic_types) < 20:
                    mic_types.append(ws_mic.receive_json()["type"])  # drena os broadcasts da sala
                self.assertIn("registration_error", mic_types)

                # audio_ended logo depois do último playback_time crescente.
                ws_display.send_json({"type": "audio_ended"})
                # Outro pacote do fim do verso (5.3 s) chegando 450 ms depois. Sem congelar
                # o relógio no audio_ended, a extrapolação o jogaria para fora da janela.
                from state import room_manager
                deadline = time.monotonic() + 2.0
                while not room_manager.rooms["graceroom"].song_clock.ended and time.monotonic() < deadline:
                    time.sleep(0.01)  # espera o servidor processar o audio_ended
                self.assertTrue(room_manager.rooms["graceroom"].song_clock.ended)
                server_clock["now"] += 0.45
                ws_mic.send_bytes(build_packet(53800, np.full(1000, 0.1, dtype=np.float32)))
                msg_score = ws_display.receive_json()
                self.assertEqual(msg_score["type"], "segment_result")
                self.assertEqual(msg_score["score"], 100.0)
                self.assertEqual(ws_display.receive_json()["type"], "game_over")

                audio = mock_stt.transcribe.call_args.args[0]
                self.assertEqual(int(np.count_nonzero(audio)), 3000)



    def test_replaced_display_closing_keeps_new_display(self):
        """TV troca de página: o display antigo fecha depois que o novo assumiu.

        Antes o `finally` do antigo zerava room.display (o placar sumia da TV) e
        mandava "unpaired" para os celulares ("TV Desconectada").
        """
        from state import room_manager

        with self.client.websocket_connect(f"/ws/room/swaproom?role=display&song_id={self.song_slug}") as ws_old:
            for expected_type in ("pairing_status", "players_update", "singing_state"):
                self.assertEqual(ws_old.receive_json()["type"], expected_type)

            with self.client.websocket_connect("/ws/room/swaproom?role=mic") as ws_mic:
                self.assertEqual(ws_mic.receive_json()["type"], "register_request")
                self.assertEqual(ws_mic.receive_json()["type"], "singing_state")
                ws_mic.send_json({"type": "register_name", "name": "Swapper"})
                self.assertEqual(ws_mic.receive_json()["type"], "registration_success")

                with self.client.websocket_connect(f"/ws/room/swaproom?role=display&song_id={self.song_slug}") as ws_new:
                    for expected_type in ("pairing_status", "players_update", "singing_state"):
                        self.assertEqual(ws_new.receive_json()["type"], expected_type)
                    # O servidor fecha o display antigo ao aceitar o novo; ler dele
                    # completa o fechamento e roda o `finally` do handler antigo.
                    from starlette.websockets import WebSocketDisconnect
                    with self.assertRaises(WebSocketDisconnect):
                        for _ in range(20):
                            ws_old.receive_json()
                    ws_old.close()
                    room = room_manager.rooms["swaproom"]
                    deadline = time.monotonic() + 1.0
                    while room.display is not None and time.monotonic() < deadline:
                        time.sleep(0.02)
                    self.assertIsNotNone(room.display)
                    self.assertIn("Swapper", room.players)

                    # Nenhum "unpaired" de display chegou ao celular.
                    ws_mic.send_json({"type": "register_name", "name": "Swapper"})
                    mic_msgs = []
                    while not any(m["type"] == "registration_error" for m in mic_msgs) and len(mic_msgs) < 20:
                        mic_msgs.append(ws_mic.receive_json())
                    self.assertFalse(any(
                        m["type"] == "pairing_status" and m.get("status") == "unpaired" for m in mic_msgs
                    ), mic_msgs)


if __name__ == "__main__":
    unittest.main()
