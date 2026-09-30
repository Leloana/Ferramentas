import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
from utils.lrc_realign import realign_segments  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "recorded_sessions" / "ze-assassino-compulsivo-o-terno.json"


class RealignKeepsAbsoluteTimesTest(unittest.TestCase):
    """expected_* é relativo ao verso: o realinhamento tratava como absoluto e
    todos os versos saíam começando em ~0 s (o "refazer com alinhamento")."""

    def test_verse_starts_survive_realign(self):
        segments = json.loads(FIXTURE.read_text(encoding="utf-8"))["segments"]
        plain = "\n".join(seg["lyrics"] for seg in segments)
        out, lrc = realign_segments(segments, plain)

        self.assertEqual(len(out), len(segments))
        for before, after in zip(segments, out):
            self.assertAlmostEqual(after["sing_start"], before["sing_start"] + before["lyrics_timed"][0]["expected_start"], delta=0.5)
            # palavras continuam relativas ao verso, começando perto de 0
            self.assertLess(after["lyrics_timed"][0]["expected_start"], 0.5)
            self.assertGreaterEqual(after["lyrics_timed"][0]["expected_start"], 0.0)
        self.assertIn("[00:23", lrc)


if __name__ == "__main__":
    unittest.main()
