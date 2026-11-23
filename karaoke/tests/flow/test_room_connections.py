"""Conexões da sala com celular bloqueado, reconexão e tela congelada.

Partidas reais: celular com a tela bloqueada (JS congelado, mas o navegador
responde ao ping) travava a fila de registro e quem chegava depois não aparecia;
celular que reconectava perdia o controle da sala; tela congelada segurava a sala.
"""
import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

SLUG = "conn-test-song"


def until(ws, kind, limit=30):
    """Recebe até chegar `kind`; devolve (mensagem, tipos que vieram antes)."""
    seen = []
    for _ in range(limit):
        msg = ws.receive_json()
        if msg["type"] == kind:
            return msg, seen
        seen.append(msg["type"])
    raise AssertionError(f"{kind} não chegou (vieram {seen})")


class RoomConnectionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="karaoke_test_conn_"))
        song_dir = cls.temp_dir / SLUG
        song_dir.mkdir()
        (song_dir / "meta.json").write_text(json.dumps({"meta": {"title": "T", "artist": "A", "language": "en",
                                                                  "slug": SLUG}}), encoding="utf-8")
        (song_dir / "segments.json").write_text(json.dumps([{
            "id": 1, "label": "Parte 1", "sing_start": 1.0, "sing_end": 5.0, "pause_start": 5.0,
            "pause_end": 6.0, "language": "en", "lyrics": "hello world",
            "lyrics_timed": [{"word": "hello", "expected_start": 0.5, "expected_end": 1.0},
                             {"word": "world", "expected_start": 1.1, "expected_end": 2.0}]}]), encoding="utf-8")
        (song_dir / "backing_track.mp3").write_text("x", encoding="utf-8")

        cls.patchers = [patch("state.SONGS_DIR", cls.temp_dir),
                        patch.dict("os.environ", {"KARAOKE_RECORD_DIR": str(cls.temp_dir / "_rec")})]
        for p in cls.patchers:
            p.start()
        from song_manager import SongManager
        cls.songs = SongManager(cls.temp_dir)
        cls.patchers += [patch("state.song_manager", cls.songs),
                         patch("ws.room.song_manager", cls.songs, create=True)]
        for p in cls.patchers[2:]:
            p.start()
        if "ws.room" in sys.modules:
            sys.modules["ws.room"].song_manager = cls.songs
        from main import app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        for p in reversed(cls.patchers):
            p.stop()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def tv(self, room, device="tv-1"):
        return self.client.websocket_connect(f"/ws/room/{room}?role=display&device={device}&seq=1")

    def mic(self, room, name="", device=""):
        q = f"&name={name}&device={device}" if name else ""
        return self.client.websocket_connect(f"/ws/room/{room}?role=mic{q}")

    def register(self, ws, name, device):
        until(ws, "register_request")
        ws.send_json({"type": "register_name", "name": name, "device": device})
        until(ws, "registration_success")

    # 1) sem fila de registro
    def test_frozen_phone_does_not_block_the_others(self):
        from state import room_manager
        with self.tv("r-frozen") as tv:
            with self.mic("r-frozen") as frozen:
                until(frozen, "register_request")  # tela bloqueada: nunca responde
                with self.mic("r-frozen") as ana:
                    _, before = until(ana, "register_request")
                    self.assertNotIn("register_wait", before)
                    ana.send_json({"type": "register_name", "name": "Ana", "device": "cel-ana"})
                    until(ana, "registration_success")
                    msg, _ = until(tv, "players_update")
                    while "Ana" not in msg["players"]:
                        msg, _ = until(tv, "players_update")
                    self.assertEqual(msg["queue_count"], 1)  # o congelado segue sem apelido
                    self.assertIn("Ana", room_manager.rooms["r-frozen"].players)

    # 2) reconexão pela URL, sem passar pelo registro
    def test_phone_back_with_name_in_url_skips_registration(self):
        with self.tv("r-url"):
            with self.mic("r-url") as old:
                self.register(old, "Eu", "cel-eu")
                with self.mic("r-url", "Eu", "cel-eu") as new:
                    msg, before = until(new, "registration_success")
                    self.assertEqual(msg["name"], "Eu")
                    self.assertNotIn("register_request", before)
                    with self.assertRaises(WebSocketDisconnect) as closed:
                        for _ in range(30):
                            old.receive_json()
                    self.assertEqual(closed.exception.code, 4002)

    def test_name_in_url_taken_by_another_phone_asks_again(self):
        with self.tv("r-taken"):
            with self.mic("r-taken") as ana:
                self.register(ana, "Ana", "cel-ana")
                with self.mic("r-taken", "Ana", "outro-cel") as other:
                    err, _ = until(other, "registration_error")
                    self.assertIn("em uso", err["message"])
                    until(other, "register_request")

    # 3) estado da sala para todos e celular que perdeu o registro
    def test_unregistered_phone_gets_room_state_and_is_asked_to_register(self):
        with self.tv("r-state") as tv:
            tv.send_json({"type": "lobby_state", "screen": "idle", "seats": []})
            with self.mic("r-state") as ws:
                state, _ = until(ws, "remote_state")
                self.assertTrue(state["has_display"])
                ws.send_json({"type": "remote", "action": "turns", "value": True})
                err, _ = until(ws, "remote_error")
                self.assertIn("Reconectando", err["message"])
                until(ws, "register_request")

    # 4) tela que parou de dar sinal de vida
    def test_silent_display_lets_another_screen_take_the_room(self):
        from rooms import DISPLAY_SILENT_SEC
        from state import room_manager
        with self.tv("r-silent", "tv-velha") as old:
            until(old, "singing_state")
            # outra tela com a tela atual viva: sala em uso
            with self.tv("r-silent", "tv-nova") as refused:
                with self.assertRaises(WebSocketDisconnect) as closed:
                    refused.receive_json()
                self.assertEqual(closed.exception.code, 4004)

            room = room_manager.rooms["r-silent"]
            with self.mic("r-silent") as phone:
                self.register(phone, "Bia", "cel-bia")
                room.display_seen = time.monotonic() - DISPLAY_SILENT_SEC - 1
                # o ping do celular leva "TV fora" para a aba Sala
                phone.send_json({"type": "ping"})
                state, _ = until(phone, "pong")
                for _ in range(5):  # remote_state do registro ainda pode estar na fila
                    state, _ = until(phone, "remote_state")
                    if not state["has_display"]:
                        break
                self.assertFalse(state["has_display"])
                phone.send_json({"type": "remote", "action": "turns", "value": True})
                self.assertIn("TV", until(phone, "remote_error")[0]["message"])

                with self.tv("r-silent", "tv-nova") as new:
                    until(new, "singing_state")
                    with self.assertRaises(WebSocketDisconnect) as closed:
                        for _ in range(30):
                            old.receive_json()
                    self.assertEqual(closed.exception.code, 4001)
                    # a nova dá sinal de vida e volta a receber os comandos
                    new.send_json({"type": "alive"})
                    phone.send_json({"type": "remote", "action": "turns", "value": True})
                    cmd, _ = until(new, "remote")
                    self.assertEqual((cmd["action"], cmd["value"]), ("turns", True))

    # 5) voltar ao lobby pelo celular
    def test_back_to_lobby_only_without_song_playing(self):
        with self.client.websocket_connect(f"/ws/room/r-lobby?role=display&device=tv-1&seq=1&song_id={SLUG}") as tv:
            with self.mic("r-lobby") as phone:
                self.register(phone, "Caio", "cel-caio")
                phone.send_json({"type": "remote", "action": "lobby"})
                self.assertEqual(until(tv, "remote")[0]["action"], "lobby")

                tv.send_json({"type": "start_game", "game_mode": "solo", "active_players": ["Caio"]})
                until(tv, "game_started")
                phone.send_json({"type": "remote", "action": "lobby"})
                self.assertIn("acabar", until(phone, "remote_error")[0]["message"])
                phone.send_json({"type": "remote", "action": "stop"})
                self.assertEqual(until(tv, "remote")[0]["action"], "stop")


if __name__ == "__main__":
    unittest.main()
