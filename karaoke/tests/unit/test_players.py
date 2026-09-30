import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
import players  # noqa: E402


class PlayersTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.patch = patch.object(players, "PLAYERS_DIR", self.dir)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_record_and_personal_best(self):
        first = players.record_game("Ana", "geni", "Geni - Chico", 70.0, pitch=55.0)
        self.assertTrue(first["is_record"])
        self.assertIsNone(first["best_before"])
        second = players.record_game("Ana", "geni", "Geni - Chico", 65.0)
        self.assertFalse(second["is_record"])
        self.assertEqual(second["best_before"], 70.0)
        self.assertEqual(second["times_sung"], 2)
        third = players.record_game("Ana", "geni", "Geni - Chico", 88.0)
        self.assertTrue(third["is_record"])

    def test_summary_detail_list_and_leaderboard(self):
        players.record_game("Ana", "geni", "Geni", 80.0, pitch=60.0)
        players.record_game("Ana", "ze", "Zé", 90.0)
        players.record_game("Bia", "geni", "Geni", 85.0)
        detail = players.profile_detail(players.load_profile("Ana"))
        self.assertEqual(detail["games"], 2)
        self.assertEqual(detail["best"], 90.0)
        self.assertEqual(detail["best_song"], "Zé")
        self.assertEqual(detail["avg_pitch"], 60.0)
        self.assertEqual([r["song_id"] for r in detail["records"]], ["ze", "geni"])
        self.assertEqual([p["name"] for p in players.list_profiles()], ["Ana", "Bia"])
        self.assertEqual(players.song_leaderboard("geni", "Geni"), [{"name": "Bia", "best": 85.0}, {"name": "Ana", "best": 80.0}])

    def test_names_cannot_escape_the_folder(self):
        self.assertEqual(players.get_player_profile_path("../../etc").parent.parent, self.dir)
        self.assertIsNone(players.load_profile("ninguem"))


if __name__ == "__main__":
    unittest.main()
