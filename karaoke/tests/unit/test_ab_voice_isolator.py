"""Partes sem GPU do tools/ab_voice_isolator.py: seleção, resumo, veredito e relatório."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import ab_voice_isolator as ab  # noqa: E402


def _song(root: Path, slug: str, score, vocal=True):
    d = root / slug
    d.mkdir()
    meta = {"meta": {"language": "pt"}, "lyrics": {"plain_lyrics": "la"}}
    if score is not None:
        meta["alignment_quality"] = {"score": score}
    (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    if vocal:
        (d / "vocal.mp3").write_bytes(b"")


class PickSongsTest(unittest.TestCase):
    def test_worst_best_and_requested_without_repeating(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            for slug, score in [("a", 30), ("b", 60), ("c", 90), ("d", 99)]:
                _song(root, slug, score)
            _song(root, "sem-nota", None)
            _song(root, "sem-voz", 10, vocal=False)
            self.assertEqual(ab.pick_songs(root, ["c"], worst=2, best=1), ["c", "a", "b", "d"])
            self.assertEqual(ab.pick_songs(root, [], worst=0, best=2), ["d", "c"])


class VerdictTest(unittest.TestCase):
    def _s(self, score, severe):
        return {"score": score, "severe": severe}

    def test_cases(self):
        self.assertEqual(ab.verdict(self._s(60, 3), self._s(70, 3)), "melhor")
        self.assertEqual(ab.verdict(self._s(60, 3), self._s(61, 1)), "melhor")
        self.assertEqual(ab.verdict(self._s(70, 1), self._s(60, 1)), "pior")
        self.assertEqual(ab.verdict(self._s(70, 1), self._s(70.5, 2)), "pior")
        self.assertEqual(ab.verdict(self._s(70, 1), self._s(71, 1)), "igual")
        # nota sobe mas versos graves também: inconclusivo
        self.assertEqual(ab.verdict(self._s(60, 1), self._s(70, 3)), "igual")


class ReportTest(unittest.TestCase):
    def test_summary_and_markdown(self):
        q = {"score": 80, "severe_lines": [2], "flags": ["x"],
             "lines": [{"flags": ["empilhadas"]}, {"flags": ["empilhadas", "grudadas"]}, {"flags": []}]}
        s = ab.summarize(q)
        self.assertEqual((s["score"], s["severe"], s["lines"]), (80, 1, 3))
        self.assertEqual(s["line_flags"], {"empilhadas": 2, "grudadas": 1})

        b = dict(s, score=90, severe=0, line_flags={"empilhadas": 1})
        results = [{"slug": "m", "A": s, "B": b, "delta": 10.0, "veredito": "melhor", "isolador_s": 4.2},
                   {"slug": "x", "erro": "sem letra ou sem vocal.mp3"}]
        md = ab.report_md(results, SimpleNamespace(isolador_cmd="voice-isolate {entrada} {saida}", estrutura=False))
        self.assertIn("| m | 80 | 90 | +10.0 | 1→0 | melhor | 4.2 s |", md)
        self.assertIn("erro: sem letra", md)
        self.assertIn("| empilhadas | 2 | 1 |", md)
        self.assertIn("melhor 1 · igual 0 · pior 0", md)


if __name__ == "__main__":
    unittest.main()
