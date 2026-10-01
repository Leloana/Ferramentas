"""Versos gerados da transcrição do Whisper (server/utils/transcript_lines.py)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from utils.transcript_lines import MAX_LINE_SEC, MAX_LINE_WORDS, segments_to_lines  # noqa: E402


def _seg(start, words, step=0.3, gaps=None):
    """Trecho do Whisper com palavras a cada `step` s (gaps: {índice: pausa extra antes})."""
    out, t = [], start
    for i, w in enumerate(words):
        t += (gaps or {}).get(i, 0.0)
        out.append({"word": w, "start": round(t, 3), "end": round(t + step * 0.9, 3)})
        t += step
    return {"start": out[0]["start"], "end": out[-1]["end"], "text": " ".join(words), "words": out}


class TranscriptLinesTest(unittest.TestCase):
    def test_rap_without_pauses_becomes_singable_lines(self):
        # "Rap do Obito": um trecho de 52 s com 148 palavras virava um verso só
        rap = [_seg(33.0, [f"palavra{i}" for i in range(148)], step=0.35)]
        lines = segments_to_lines(rap)
        self.assertGreater(len(lines), 10)
        for ln in lines:
            self.assertLessEqual(len(ln["text"].split()), MAX_LINE_WORDS)
            self.assertLessEqual(ln["end"] - ln["start"], MAX_LINE_SEC + 0.5)
        self.assertEqual(sum(len(ln["text"].split()) for ln in lines), 148)  # nada se perde

    def test_neighbor_segments_without_pause_no_longer_glue_the_song(self):
        segs = [_seg(10.0 + 3.2 * k, ["Da", "morte", "eu", "voltei", "e", "desse", "mundo", "cansei"])
                for k in range(10)]
        lines = segments_to_lines(segs)
        self.assertEqual(len(lines), 10)

    def test_cuts_at_pause_and_punctuation(self):
        seg = _seg(0.0, ["A", "máscara", "esconde", "a", "revolta,", "de", "um", "ninja", "Obito", "o", "TRA",
                         "da", "morte", "eu", "voltei"], step=0.3, gaps={11: 0.8})
        texts = [ln["text"] for ln in segments_to_lines([seg])]
        self.assertEqual(texts[0], "A máscara esconde a revolta,")
        self.assertTrue(texts[1].endswith("TRA"))

    def test_short_fragments_are_still_joined(self):
        segs = [_seg(5.0, ["oh"]), _seg(5.5, ["yeah", "yeah"])]
        self.assertEqual([ln["text"] for ln in segments_to_lines(segs)], ["oh yeah yeah"])

    def test_normal_line_is_left_alone(self):
        seg = _seg(1.0, ["Joga", "pedra", "na", "Geni"])
        self.assertEqual(segments_to_lines([seg]), [{"start": seg["start"], "end": seg["end"], "text": "Joga pedra na Geni"}])


if __name__ == "__main__":
    unittest.main()
