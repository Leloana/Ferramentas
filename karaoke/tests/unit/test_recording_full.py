"""Gravação completa (formato 3): contexto, eventos, aparelhos, rede, ruído, versões."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tests" / "unit"))
from mic_stream import STREAM_SR  # noqa: E402
from recorder import SESSION_FILE, FORMAT_VERSION, GameRecording, noise_floor  # noqa: E402
from test_recorder import SEGMENTS, WINDOWS, _timeline_with_voice  # noqa: E402


class FullRecordingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.song = self.tmp / "song-x"
        self.song.mkdir()
        (self.song / "meta.json").write_text('{"meta": {"title": "X"}, "needs_review": false}', encoding="utf-8")
        (self.song / "pitch.json").write_text('{"hop_sec": 0.01, "midi": [null, 60.0]}', encoding="utf-8")
        (self.song / ".lyrics_edited").write_text("", encoding="utf-8")

    def test_session_has_everything(self):
        rec = GameRecording(self.tmp / "rec", "song-x", "Song X", SEGMENTS, "timing", WINDOWS, song_dir=self.song)
        rec.set_config({"game_mode": "1v1", "transpose": 2.0, "speed": 1.0, "guide_volume": 0.2, "unused": None})
        rec.add_event("play", 0.0)
        rec.add_event("seek", 12.5, value=10.0)
        rec.set_device("Ana", {"user_agent": "Android", "track": {"sampleRate": 48000}})
        rec.add_segment_result("Ana", 0, (0.0, 3.5), 0.05, "hello world", [], {"score": 90.0},
                               pitch=72.0, whisper_raw=[{"prompted": True, "segments": []}],
                               timing={"lock_wait_s": 0.0, "whisper_s": 0.4, "since_dispatch_s": 0.5})
        saved = rec.save({"Ana": _timeline_with_voice()}, complete=True, whisper_model="x",
                         final={"player_scores": {"Ana": 90.0}})
        session = json.loads((saved / SESSION_FILE).read_text(encoding="utf-8"))

        self.assertEqual(session["format"], FORMAT_VERSION)
        self.assertEqual(session["config"]["transpose"], 2.0)
        self.assertNotIn("unused", session["config"])
        self.assertEqual([e["kind"] for e in session["events"]], ["play", "seek"])
        self.assertEqual(session["events"][1]["value"], 10.0)
        self.assertEqual(session["devices"]["Ana"]["track"]["sampleRate"], 48000)
        res = session["results"][0]
        self.assertEqual(res["pitch"], 72.0)
        self.assertEqual(res["timing"]["whisper_s"], 0.4)
        self.assertTrue(res["whisper_raw"][0]["prompted"])
        net = session["players"]["Ana"]["network"]
        self.assertEqual(net["packets"], 60)
        self.assertIn("late_p90", net)
        self.assertIn("commit", session["versions"])
        self.assertIn("TIMING_TOLERANT_SEC", session["versions"]["constants"]["score_engine"])
        self.assertEqual(session["final"]["player_scores"], {"Ana": 90.0})
        for name in ("song_meta.json", "song_pitch.json", "song_lyrics_edited"):
            self.assertTrue((saved / name).exists(), name)

    def test_noise_floor_ignores_verses(self):
        n = 8 * STREAM_SR
        audio = np.full(n, 0.001, dtype=np.float32)
        audio[int(0 * STREAM_SR):int(3.5 * STREAM_SR)] = 0.3  # voz no verso 1 (janela com pré/pós)
        covered = np.ones(n, dtype=bool)
        nf = noise_floor(audio, covered, SEGMENTS, WINDOWS)
        self.assertIsNotNone(nf)
        self.assertLess(nf["rms_median"], 0.01)  # só pausas contam


if __name__ == "__main__":
    unittest.main()
