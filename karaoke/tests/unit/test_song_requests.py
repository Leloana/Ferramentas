import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
import song_requests as sr  # noqa: E402

SONG = {"id": "geni", "title": "Geni", "artist": "Chico"}


class SongRequestsTest(unittest.TestCase):
    def setUp(self):
        self.room = SimpleNamespace(song_requests=[])

    def test_add_list_and_remove(self):
        req, err = sr.add_request(self.room, SONG, "Ana")
        self.assertIsNone(err)
        self.assertEqual(sr.requests_payload(self.room)["requests"][0]["singer"], "Ana")
        self.assertFalse(sr.remove_request(self.room, req["id"], "Bia"))  # não é dela
        self.assertTrue(sr.remove_request(self.room, req["id"], "Ana"))
        self.assertEqual(self.room.song_requests, [])

    def test_limits(self):
        sr.add_request(self.room, SONG, "Ana")
        self.assertIsNotNone(sr.add_request(self.room, SONG, "Ana")[1])  # repetida
        for i in range(2):
            sr.add_request(self.room, {"id": f"s{i}"}, "Ana")
        self.assertIsNotNone(sr.add_request(self.room, {"id": "s9"}, "Ana")[1])  # 3 por cantor
        self.assertIsNone(sr.add_request(self.room, {"id": "s9"}, "Bia")[1])


if __name__ == "__main__":
    unittest.main()
