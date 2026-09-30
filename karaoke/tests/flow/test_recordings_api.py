"""API das gravações: versos da partida e gabarito anotado pelo cantor."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from fastapi.testclient import TestClient  # noqa: E402

SEGMENTS = [
    {"sing_start": 0.2, "sing_end": 0.6, "language": "pt", "lyrics": "Joga pedra na Geni",
     "lyrics_timed": [{"word": "Joga", "expected_start": 0.0, "expected_end": 0.2}]},
    {"sing_start": 0.7, "sing_end": 0.9, "language": "pt", "lyrics": "Maldita Geni",
     "lyrics_timed": [{"word": "Maldita", "expected_start": 0.0, "expected_end": 0.2}]},
]


class TestRecordingsApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from main import app
        cls.client = TestClient(app)

    def setUp(self):
        from mic_stream import MicTimeline
        from recorder import GameRecording

        self.tmp = Path(tempfile.mkdtemp(prefix="karaoke_rec_api_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        env = patch.dict("os.environ", {"KARAOKE_RECORD_DIR": str(self.tmp)})
        env.start()
        self.addCleanup(env.stop)

        timeline = MicTimeline()
        timeline.add(0, (np.full(16000, 0.1) * 32767).astype("<i2"), song_time=1.0, epoch=1)
        rec = GameRecording(self.tmp, "geni", "Geni e o Zepelim", SEGMENTS, "timing", {})
        rec.add_segment_result("Lelo", 0, (0.0, 0.6), 0.1, "Joga pedra na Geni", [], {"score": 95.0})
        self.rec_id = rec.save({"Lelo": timeline}, complete=True, whisper_model="x").name

    def test_get_lists_verses_with_score_and_what_was_heard(self):
        res = self.client.get(f"/api/recordings/{self.rec_id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["players"], ["Lelo"])
        self.assertEqual([v["n"] for v in data["verses"]], [1, 2])
        self.assertEqual(data["verses"][0]["players"]["Lelo"], {"score": 95.0, "heard": "Joga pedra na Geni"})
        self.assertEqual(data["verses"][1]["players"], {})  # verso sem nota (não chegou áudio)
        self.assertEqual(data["labels"], {})

    def test_post_saves_gabarito_next_to_the_recording(self):
        res = self.client.post(f"/api/recordings/{self.rec_id}/gabarito",
                               json={"player": "Lelo", "labels": {"1": "certo", "2": "cantarolei"}})
        self.assertEqual(res.status_code, 200)
        saved = json.loads((self.tmp / self.rec_id / "gabarito.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["labels"], {"Lelo": {"1": "certo", "2": "cantarolei"}})
        self.assertEqual(self.client.get(f"/api/recordings/{self.rec_id}").json()["labels"],
                         {"Lelo": {"1": "certo", "2": "cantarolei"}})

    def test_rejects_bad_input(self):
        url = f"/api/recordings/{self.rec_id}/gabarito"
        for body in ({"player": "Lelo", "labels": {"1": "talvez"}},
                     {"player": "Lelo", "labels": {"3": "certo"}},
                     {"player": "Outro", "labels": {"1": "certo"}}):
            with self.subTest(body=body):
                self.assertEqual(self.client.post(url, json=body).status_code, 400)
        self.assertFalse((self.tmp / self.rec_id / "gabarito.json").exists())

    def test_unknown_or_traversal_id_is_404(self):
        for rec_id in ("nao-existe", "..", "..%2F..%2Fserver"):
            with self.subTest(rec_id=rec_id):
                self.assertEqual(self.client.get(f"/api/recordings/{rec_id}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
