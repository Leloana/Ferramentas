"""Alinhamento por janela de linha do lrc_pro, com um alinhador falso (sem o modelo MMS_FA)."""

import sys
import unittest
from collections import namedtuple
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from utils import lrc_pro  # noqa: E402
from utils.alignment_quality import assess  # noqa: E402

Span = namedtuple("Span", "start end score")

# "Música" de 60 s: três linhas, pausa instrumental longa entre a 2ª e a 3ª.
TRUE_TIMES = {
    "hello": (10.2, 10.6), "world": (10.7, 11.3),
    "this": (13.1, 13.4), "is": (13.5, 13.7), "the": (13.8, 14.0), "place": (14.1, 14.9),
    "goodbye": (45.3, 46.0), "now": (46.2, 46.8),
}
PLAIN = "Hello world\nThis is the place\nGoodbye now"
LRC = "[ti:x]\n[00:10.00]Hello world\n[00:13.00]This is the place\n[00:15.50]\n[00:45.00]Goodbye now"


class FakeAligner:
    """Devolve os tempos "verdadeiros" das palavras que estão dentro da janela."""

    def __init__(self, fail_on=(), max_window=lrc_pro.MAX_WINDOW_SEC):
        self.calls = []
        self.fail_on = set(fail_on)
        self.max_window = max_window

    def __call__(self, t0, t1, words):
        self.calls.append((t0, t1, list(words)))
        if t1 - t0 > self.max_window + 1e-6:
            raise MemoryError("janela grande demais")
        if self.fail_on & set(words):
            raise RuntimeError("CTC: frames insuficientes")
        out = []
        for w in words:
            s, e = TRUE_TIMES[w]
            out.append((s, e, 0.9) if t0 <= s and e <= t1 else None)
        return out


class ParseLrcTest(unittest.TestCase):
    def test_lines_and_end_marks(self):
        lines = lrc_pro.parse_synced_lrc(LRC + "\n[offset:+500]")
        self.assertEqual([ln["text"] for ln in lines], ["Hello world", "This is the place", "Goodbye now"])
        self.assertEqual([ln["start"] for ln in lines], [10.5, 13.5, 45.5])
        self.assertEqual(lines[1]["end"], 16.0)
        self.assertIsNone(lines[0]["end"])

    def test_multi_stamp(self):
        lines = lrc_pro.parse_synced_lrc("[00:05.00][00:30.00]refrão\n[00:10.00]verso")
        self.assertEqual([(ln["start"], ln["text"]) for ln in lines], [(5.0, "refrão"), (10.0, "verso"), (30.0, "refrão")])

    def test_lrc_text_used_when_line_counts_differ(self):
        lines, starts, _ = lrc_pro.lines_for_alignment("Hello world This is the place\nGoodbye now", LRC, "en")
        self.assertEqual(len(lines), 3)
        self.assertEqual(starts, [10.0, 13.0, 45.0])
        lines, starts, _ = lrc_pro.lines_for_alignment(PLAIN, None, "en")
        self.assertIsNone(starts)


class WindowTest(unittest.TestCase):
    def test_window_bounds(self):
        starts = [10.0, 13.0, 45.0]
        self.assertEqual(lrc_pro.line_window(0, starts, 60.0), (9.0, 13.5))
        # marca de fim no LRC encurta; pausa longa sem marca fica em no máximo 30 s
        self.assertEqual(lrc_pro.line_window(1, starts, 60.0, [None, 15.5, None]), (12.0, 16.0))
        t0, t1 = lrc_pro.line_window(1, starts, 60.0)
        self.assertEqual((t0, t1), (12.0, 42.0))
        # a linha anterior terminou depois do início − 1 s: a janela começa ali
        self.assertEqual(lrc_pro.line_window(1, starts, 60.0, floor=12.6)[0], 12.6)
        self.assertEqual(lrc_pro.line_window(1, starts, 60.0, floor=20.0)[0], 13.0)
        self.assertEqual(lrc_pro.line_window(2, starts, 60.0), (44.0, 60.0))


class AlignLinesTest(unittest.TestCase):
    def _lines(self):
        lines, starts, ends = lrc_pro.lines_for_alignment(PLAIN, LRC, "en")
        return lines, starts, ends

    def test_each_line_aligned_in_its_window_with_confidence(self):
        lines, starts, ends = self._lines()
        fake = FakeAligner()
        modes = lrc_pro.align_lines(lines, 60.0, fake, starts, ends)
        self.assertEqual(modes, ["window"] * 3)
        self.assertEqual([c[2] for c in fake.calls], [["hello", "world"], ["this", "is", "the", "place"], ["goodbye", "now"]])
        self.assertTrue(all(t1 - t0 <= lrc_pro.MAX_WINDOW_SEC for t0, t1, _ in fake.calls))
        self.assertEqual((lines[2][0]["start"], lines[2][0]["confidence"]), (45.3, 0.9))

        segs = lrc_pro.build_segments(lines, modes, 60.0, "en")
        self.assertEqual([s["align"] for s in segs], ["window"] * 3)
        self.assertEqual(segs[1]["confidence"], 0.9)
        self.assertEqual(segs[1]["lyrics_timed"][0]["confidence"], 0.9)
        self.assertAlmostEqual(segs[2]["sing_start"] + segs[2]["lyrics_timed"][0]["expected_start"], 45.3, places=2)
        q = assess(segs, 60.0)
        self.assertGreaterEqual(q["score"], 90.0)

    def test_failed_line_falls_back_inside_window_not_over_the_gap(self):
        lines, starts, _ = lrc_pro.lines_for_alignment(PLAIN, LRC, "en")
        modes = lrc_pro.align_lines(lines, 60.0, FakeAligner(fail_on={"place"}), starts, None)
        self.assertEqual(modes, ["window", "fallback", "window"])
        line = lines[1]
        self.assertGreaterEqual(line[0]["start"], 13.0)
        # ~0,3 s por sílaba: não se espalha pelos 30 s de instrumental até a linha seguinte
        self.assertLess(line[-1]["end"], 16.0)
        self.assertEqual({w["confidence"] for w in line}, {0.0})
        starts_ = [w["start"] for w in line]
        self.assertEqual(starts_, sorted(starts_))

        segs = lrc_pro.build_segments(lines, modes, 60.0, "en")
        q = assess(segs, 60.0)
        self.assertIn("sem alinhamento", q["lines"][1]["flags"])
        self.assertIn("confiança baixa", q["lines"][1]["flags"])
        self.assertLess(q["score"], assess(lrc_pro.build_segments(*self._aligned(), 60.0, "en"), 60.0)["score"])

    def _aligned(self):
        lines, starts, ends = self._lines()
        return lines, lrc_pro.align_lines(lines, 60.0, FakeAligner(), starts, ends)

    def test_words_without_tokens_are_interpolated(self):
        lines, starts, ends = lrc_pro.lines_for_alignment("Hello 20 world\nThis is the place\nGoodbye now", LRC, "en")
        modes = lrc_pro.align_lines(lines, 60.0, FakeAligner(), starts, ends)
        self.assertEqual(modes[0], "window")
        num = lines[0][1]
        self.assertEqual(num["norm"], "")
        self.assertIsNone(num["confidence"])
        self.assertTrue(lines[0][0]["start"] <= num["start"] <= lines[0][2]["start"])

    def test_global_path_without_lrc(self):
        lines, _ = lrc_pro.parse_and_normalize_lyrics(PLAIN, "en")
        fake = FakeAligner(max_window=60.0)
        modes = lrc_pro.align_lines(lines, 25.0, fake, None)
        self.assertEqual(modes, ["global"] * 3)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0][:2], (0.0, 25.0))

    def test_end_to_end_with_injected_aligner(self):
        audio = np.zeros(60 * lrc_pro.SAMPLE_RATE, dtype=np.float32)
        with patch("utils.audio.load_audio_full", return_value=audio):
            segs, lrc = lrc_pro.align_lyrics_forced("vocal.mp3", PLAIN, "en", synced_lrc=LRC, align_fn=FakeAligner())
        self.assertEqual(len(segs), 3)
        self.assertIn("Goodbye now", lrc)
        for seg in segs:
            starts = [w["expected_start"] for w in seg["lyrics_timed"]]
            self.assertEqual(starts, sorted(set(starts)))  # estritamente crescente
        for a, b in zip(segs, segs[1:]):
            self.assertLessEqual(a["sing_end"], b["sing_start"])

    def test_out_of_sync_lrc_falls_back_to_whole_song(self):
        # LRC de outra versão (tudo 5 s depois): nenhuma janela acha as palavras
        shifted = "[00:15.00]Hello world\n[00:18.00]This is the place\n[00:50.00]Goodbye now"
        audio = np.zeros(60 * lrc_pro.SAMPLE_RATE, dtype=np.float32)
        fake = FakeAligner(max_window=60.0)
        with patch("utils.audio.load_audio_full", return_value=audio):
            segs, _ = lrc_pro.align_lyrics_forced("vocal.mp3", PLAIN, "en", synced_lrc=shifted, align_fn=fake)
        self.assertEqual(fake.calls[-1][:2], (0.0, 60.0))
        self.assertEqual([s["align"] for s in segs], ["global"] * 3)
        self.assertAlmostEqual(segs[0]["sing_start"] + segs[0]["lyrics_timed"][0]["expected_start"], 10.2, places=2)


class SpansTest(unittest.TestCase):
    def test_confidence_is_frame_weighted_mean(self):
        spans = [[Span(10, 12, 0.9), Span(12, 20, 0.5)], [], [Span(30, 31, -0.1053)]]
        out = lrc_pro.spans_to_words(spans, 5.0, 0.02)
        self.assertAlmostEqual(out[0][0], 5.2)
        self.assertAlmostEqual(out[0][1], 5.4)
        self.assertAlmostEqual(out[0][2], (0.9 * 2 + 0.5 * 8) / 10)
        self.assertIsNone(out[1])
        self.assertAlmostEqual(out[2][2], 0.9, places=3)  # log-probabilidade convertida


class RealAlignerPlumbingTest(unittest.TestCase):
    """mms_align_fn com o tokenizer/aligner reais do torchaudio e um modelo falso (sem pesos)."""

    def test_windows_map_back_to_song_time(self):
        try:
            import torch
            import torchaudio
        except ImportError:
            self.skipTest("sem torch/torchaudio")
        bundle = torchaudio.pipelines.MMS_FA
        n_labels = len(bundle.get_dict())

        class FakeModel(torch.nn.Module):
            def forward(self, wav):
                frames = wav.shape[-1] // 320  # 20 ms por quadro, como o wav2vec2
                torch.manual_seed(0)
                return torch.log_softmax(torch.randn(1, frames, n_labels), dim=-1), None

        audio = np.zeros(20 * lrc_pro.SAMPLE_RATE, dtype=np.float32)
        with patch.object(type(bundle), "get_model", lambda self, *a, **k: FakeModel()):
            align, release = lrc_pro.mms_align_fn(audio, "cpu")
            out = align(5.0, 8.0, ["hello", "world"])
            release()
        self.assertEqual(len(out), 2)
        (s0, e0, c0), (s1, e1, c1) = out
        self.assertTrue(5.0 <= s0 < e0 <= s1 < e1 <= 8.0 + 1e-6)
        self.assertTrue(0.0 < c0 <= 1.0 and 0.0 < c1 <= 1.0)


if __name__ == "__main__":
    unittest.main()
