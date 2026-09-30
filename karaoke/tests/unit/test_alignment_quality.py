"""Portão de qualidade do alinhamento (utils/alignment_quality.py)."""

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
from utils import alignment_quality as aq  # noqa: E402
from utils.segment_timing import finalize_segments  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "recorded_sessions"


def _fixture_segments():
    out = {}
    for path in sorted(FIXTURES.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "segments" in data:
            out[path.stem] = data["segments"]
    return out


def _seg(start, words, conf=None, end=None):
    """Verso com palavras (início, fim) relativas ao sing_start."""
    timed = []
    for i, (s, e) in enumerate(words):
        w = {"word": f"w{i}", "expected_start": s, "expected_end": e}
        if conf is not None:
            w["confidence"] = conf
        timed.append(w)
    last = max(e for _, e in words)
    return {"sing_start": start, "sing_end": end if end is not None else round(start + last + 0.05, 3),
            "lyrics": " ".join(w["word"] for w in timed), "lyrics_timed": timed}


def _good_song(conf=None):
    return [_seg(10.0 + 4 * i, [(0.1, 0.5), (0.6, 1.0), (1.1, 1.6), (1.7, 2.4)], conf) for i in range(10)]


class FixturesTest(unittest.TestCase):
    def test_fixtures_without_confidence(self):
        fixtures = _fixture_segments()
        self.assertEqual(len(fixtures), 3)
        for name, segs in fixtures.items():
            with self.subTest(song=name):
                q = aq.assess(segs)
                self.assertTrue(0 <= q["score"] <= 100)
                self.assertNotIn("median_confidence", q["metrics"])
                self.assertEqual(len(q["lines"]), sum(1 for s in segs if s["lyrics_timed"]))
                self.assertTrue(all(ln["confidence"] is None for ln in q["lines"]))
                # finalize_segments desfaz sobreposições: a nota só pode subir
                fixed = aq.assess(finalize_segments(copy.deepcopy(segs)))
                self.assertGreaterEqual(fixed["score"], q["score"])
                self.assertEqual(fixed["metrics"]["overlaps"], 0)

    def test_wolf_raw_needs_review(self):
        # Wolf antes do finalize: 42/59 versos sobrepostos e palavras empilhadas a 50 ms
        q = aq.assess(_fixture_segments()["a-wolf-at-the-door-radiohead"])
        self.assertLess(q["score"], aq.REVIEW_SCORE_MIN)
        self.assertTrue(any("sobrepostos" in f for f in q["flags"]))
        self.assertTrue(any("empilhadas" in f for f in q["flags"]))


class SyntheticTest(unittest.TestCase):
    def test_clean_alignment_scores_high(self):
        q = aq.assess(_good_song(conf=0.85), audio_duration=60.0)
        self.assertEqual(q["score"], 100.0)
        self.assertEqual(q["flags"], [])
        self.assertEqual(q["lines"][0], {"idx": 0, "confidence": 0.85, "flags": []})

    def test_low_confidence(self):
        q = aq.assess(_good_song(conf=0.1))
        self.assertLess(q["score"], aq.REVIEW_SCORE_MIN)
        self.assertTrue(q["flags"][0].startswith("confiança baixa"))
        self.assertIn("confiança baixa", q["lines"][3]["flags"])

    def test_stacked_short_and_long(self):
        stacked = [_seg(10.0, [(0.1, 0.12), (0.15, 0.17), (0.2, 0.22), (0.25, 0.27), (0.3, 5.0)])]
        q = aq.assess(stacked)
        self.assertEqual(q["metrics"]["stacked"], 5)
        self.assertEqual(q["metrics"]["short"], 4)
        self.assertEqual(q["lines"][0]["flags"], ["empilhadas", "palavras curtas"])
        long_verse = [_seg(10.0, [(0.1, 0.6), (6.0, 6.5), (13.0, 13.5)])]
        self.assertEqual(aq.assess(long_verse)["metrics"]["long_verses"], 1)
        self.assertLess(aq.assess(stacked)["score"], 70)

    def test_words_past_end_and_overlap(self):
        segs = _good_song()
        segs[2]["sing_end"] = segs[2]["sing_start"] + 1.0  # palavras depois do sing_end
        segs[5]["sing_end"] = segs[6]["sing_start"] + 0.5  # invade o próximo
        q = aq.assess(segs, audio_duration=40.0)  # última palavra do 8º verso e os dois últimos passam do áudio
        self.assertEqual(q["metrics"]["past_end"], 2 + 1 + 4 * 2)
        self.assertEqual(q["metrics"]["overlaps"], 2)
        self.assertIn("sobreposto", q["lines"][6]["flags"])
        self.assertIn("fora do verso", q["lines"][2]["flags"])

    def test_words_in_silence_of_vocal_stem(self):
        segs = _good_song()
        audio = np.zeros(60 * 16000, dtype=np.float32)
        rng = np.random.default_rng(0)
        # voz só nos 5 primeiros versos (10–30 s)
        audio[10 * 16000:30 * 16000] = rng.normal(0, 0.1, 20 * 16000)
        rms = aq.rms_frames(audio, 16000)
        q = aq.assess(segs, 60.0, rms)
        self.assertEqual(q["metrics"]["silence"], 20)
        self.assertIn("no silêncio", q["lines"][7]["flags"])
        self.assertNotIn("no silêncio", q["lines"][0]["flags"])
        self.assertLess(q["score"], aq.assess(segs, 60.0)["score"])

    def test_empty(self):
        self.assertEqual(aq.assess([])["score"], 0.0)
        self.assertEqual(aq.assess([{"sing_start": 0, "sing_end": 1, "lyrics": "", "lyrics_timed": []}])["score"], 0.0)


class RecordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="karaoke_aq_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_writes_meta_and_needs_review(self):
        (self.tmp / "meta.json").write_text(json.dumps({"meta": {"title": "x"}}), encoding="utf-8")
        aq.record_alignment_quality(self.tmp, _good_song(conf=0.9))
        meta = json.loads((self.tmp / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["meta"], {"title": "x"})
        self.assertEqual(meta["alignment_quality"]["score"], 100.0)
        self.assertFalse(meta["needs_review"])
        aq.record_alignment_quality(self.tmp, _good_song(conf=0.05))
        self.assertTrue(json.loads((self.tmp / "meta.json").read_text(encoding="utf-8"))["needs_review"])

    def test_never_raises(self):
        self.assertIsNone(aq.record_alignment_quality(self.tmp / "nao-existe"))
        # sem meta.json: avalia, mas não cria o arquivo
        self.assertIsNotNone(aq.record_alignment_quality(self.tmp, _good_song()))
        self.assertFalse((self.tmp / "meta.json").exists())


if __name__ == "__main__":
    unittest.main()
