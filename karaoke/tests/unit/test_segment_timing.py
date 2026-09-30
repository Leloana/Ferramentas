import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
from utils.segment_timing import finalize_segments, match_words_in_order  # noqa: E402


def _w(word, start, end):
    return {"word": word, "start": start, "end": end}


class MatchWordsInOrderTest(unittest.TestCase):
    def test_missing_whisper_words_are_interpolated_not_stacked(self):
        # Whisper perdeu "them" e "again": antes as palavras da letra grudavam
        official = "see them again if I squeal".split()
        whisper = [_w("see", 0.0, 0.3), _w("if", 1.2, 1.4), _w("I", 1.4, 1.6), _w("squeal", 1.6, 2.2)]
        out = match_words_in_order(official, whisper)
        starts = [w["start"] for w in out]
        self.assertEqual([w["word"] for w in out], official)
        self.assertEqual(starts, sorted(starts))
        self.assertAlmostEqual(out[0]["start"], 0.0)
        self.assertAlmostEqual(out[3]["start"], 1.2)
        # "them"/"again" ficam entre "see" e "if", com espaço entre elas
        self.assertGreater(out[1]["start"], 0.2)
        self.assertLess(out[2]["start"], 1.2)
        self.assertGreater(out[2]["start"] - out[1]["start"], 0.1)

    def test_extra_whisper_words_do_not_shift_matches(self):
        official = ["Joga", "pedra", "na", "Geni"]
        whisper = [_w("ah", 0.0, 0.2), _w("joga", 0.5, 0.8), _w("pedra", 0.8, 1.1),
                   _w("na", 1.1, 1.2), _w("geni", 1.2, 1.8), _w("ê", 2.0, 2.2)]
        out = match_words_in_order(official, whisper)
        self.assertEqual([w["start"] for w in out], [0.5, 0.8, 1.1, 1.2])

    def test_accents_and_case_still_match(self):
        out = match_words_in_order(["Não", "é"], [_w("nao", 1.0, 1.3), _w("e", 1.3, 1.5)])
        self.assertEqual([w["start"] for w in out], [1.0, 1.3])


class FinalizeSegmentsTest(unittest.TestCase):
    def _seg(self, start, end, words):
        return {"sing_start": start, "sing_end": end, "pause_start": end, "pause_end": end + 0.1,
                "lyrics_timed": [{"word": "w", "expected_start": a, "expected_end": b} for a, b in words]}

    def test_verse_does_not_overlap_next(self):
        segs = [self._seg(10.0, 14.4, [(0.1, 1.0), (1.0, 3.9)]), self._seg(14.0, 17.0, [(0.1, 1.0)])]
        finalize_segments(segs)
        self.assertLessEqual(segs[0]["sing_end"], segs[1]["sing_start"])
        self.assertLessEqual(segs[0]["pause_end"], segs[1]["sing_start"])

    def test_last_word_fits_inside_verse(self):
        segs = [self._seg(10.0, 12.0, [(0.1, 1.0), (1.0, 2.6)]), self._seg(20.0, 22.0, [(0.1, 1.0)])]
        finalize_segments(segs)
        self.assertGreaterEqual(segs[0]["sing_end"], 10.0 + 2.6)
        for seg in segs:
            for w in seg["lyrics_timed"]:
                self.assertLessEqual(seg["sing_start"] + w["expected_end"], seg["sing_end"] + 1e-6)


class ParseLrcTest(unittest.TestCase):
    def test_multiple_timestamps_and_pause_marks(self):
        from tools.prepare_song import parse_lrc

        with tempfile.NamedTemporaryFile("w", suffix=".lrc", delete=False, encoding="utf-8") as f:
            f.write("[ar:x]\n[00:10.00]verso um\n[00:14.00]\n[00:20.00][01:05.50]refrão\n[00:25.00]verso dois\n")
        lines, offset = parse_lrc(f.name)
        self.assertEqual([(ln["start"], ln["text"]) for ln in lines],
                         [(10.0, "verso um"), (20.0, "refrão"), (25.0, "verso dois"), (65.5, "refrão")])
        self.assertEqual(lines[0]["end"], 14.0)
        self.assertEqual(offset, 0.0)


if __name__ == "__main__":
    unittest.main()
