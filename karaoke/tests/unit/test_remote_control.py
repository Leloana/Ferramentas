"""Controle da sala pelo celular: travas (mutex) e validação dos comandos."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from remote_control import check_remote, clean_command, clean_seats, remote_state_payload  # noqa: E402


class CheckRemoteTest(unittest.TestCase):
    def test_locked_while_playing(self):
        for action in ("select_song", "seats", "turns", "scoring_mode", "start"):
            self.assertEqual(check_remote(action, True, None, True), "Espere a música acabar.")
        for action in ("transpose", "speed", "volume", "guide_volume", "pause", "stop"):
            self.assertIsNone(check_remote(action, True, None, True))

    def test_gpu_busy_blocks_only_start(self):
        self.assertIn("GPU ocupada", check_remote("start", False, "Reptilia", True))
        self.assertIsNone(check_remote("select_song", False, "Reptilia", True))
        self.assertIsNone(check_remote("seats", False, "Reptilia", True))

    def test_needs_tv_and_known_action(self):
        self.assertIn("TV desconectada", check_remote("start", False, None, False))
        self.assertEqual(check_remote("rm -rf", False, None, True), "Comando desconhecido.")
        self.assertEqual(check_remote("pause", False, None, True), "Nenhuma música tocando.")


class CleanCommandTest(unittest.TestCase):
    def test_seats_only_room_mics_once(self):
        players = ["Ana", "Lelo"]
        self.assertEqual(clean_seats([{"mic": "Ana", "team": "A"}, {"mic": "Lelo", "team": "B"}], players),
                         [{"mic": "Ana", "team": "A"}, {"mic": "Lelo", "team": "B"}])
        self.assertIsNone(clean_seats([{"mic": "Ana", "team": "A"}, {"mic": "Ana", "team": "B"}], players))
        self.assertIsNone(clean_seats([{"mic": "Estranho", "team": "A"}], players))
        self.assertIsNone(clean_seats([{"mic": "Ana", "team": "Z"}], players))
        self.assertIsNone(clean_seats("Ana", players))

    def test_select_song_must_be_ready(self):
        self.assertEqual(clean_command("select_song", {"song_id": "reptilia"}, [], {"reptilia"}),
                         ({"action": "select_song", "song_id": "reptilia"}, None))
        self.assertEqual(clean_command("select_song", {"song_id": "x"}, [], {"reptilia"})[1], "Música não encontrada.")

    def test_only_known_fields_reach_the_tv(self):
        cmd, err = clean_command("transpose", {"delta": 1, "evil": "<script>"}, [], set())
        self.assertEqual((cmd, err), ({"action": "transpose", "delta": 1}, None))
        self.assertIsNotNone(clean_command("speed", {"delta": 5}, [], set())[1])
        self.assertEqual(clean_command("guide_volume", {"delta": -1}, [], set())[0], {"action": "guide_volume", "delta": -1})
        self.assertEqual(clean_command("scoring_mode", {"value": "words"}, [], set())[0]["value"], "words")
        self.assertEqual(clean_command("turns", {"value": 1}, [], set())[0], {"action": "turns", "value": True})

    def test_state_payload_adds_server_locks(self):
        payload = remote_state_payload({"song": {"id": "x"}, "in_game": False}, True, "Reptilia", True)
        self.assertEqual(payload["type"], "remote_state")
        self.assertTrue(payload["in_game"])  # o servidor manda, não a TV
        self.assertEqual(payload["gpu_busy"], "Reptilia")
        self.assertEqual(remote_state_payload(None, False, None, False)["has_display"], False)


if __name__ == "__main__":
    unittest.main()
