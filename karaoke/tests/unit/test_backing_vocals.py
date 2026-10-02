"""Voz de apoio (entre parênteses na letra): aparece, mas fica fora da nota."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
from lyrics_text import backing_flags, has_lead_vocals, is_backing_only, lead_words, strip_backing  # noqa: E402
from segment_scoring import score_words, transcribe_kwargs  # noqa: E402
from ws.room import _verse_players, turn_owner  # noqa: E402


def _timed(text):
    return [{"word": w, "expected_start": i * 0.5, "expected_end": i * 0.5 + 0.4}
            for i, w in enumerate(text.split())]


def _heard(text):
    return [{"word": w, "start": i * 0.5, "end": i * 0.5 + 0.4, "probability": 0.9}
            for i, w in enumerate(text.split())]


class BackingTextTest(unittest.TestCase):
    def test_words_inside_parentheses_are_backing(self):
        self.assertEqual(backing_flags("E eu sei (eu sei) fui".split()),
                         [False, False, False, True, True, False])
        self.assertEqual(backing_flags(["(Monster)", "olha"]), [True, False])
        self.assertEqual(backing_flags(["（ねえ）", "君"]), [True, False])  # parêntese japonês

    def test_line_kinds(self):
        self.assertEqual(strip_backing("E quem vai entender? (E quem vai entender?)"), "E quem vai entender?")
        self.assertTrue(is_backing_only("(How should I feel?)"))
        self.assertFalse(is_backing_only("(Monster) olha o que eu me tornei"))
        self.assertFalse(is_backing_only(""))  # instrumental não é voz de apoio
        self.assertFalse(has_lead_vocals("(Monster)"))
        self.assertEqual([w["word"] for w in lead_words(_timed("Se quero (se quero)"))], ["Se", "quero"])


class BackingScoreTest(unittest.TestCase):
    SEG = {"lyrics": "E eu sei (eu sei) fui", "language": "pt", "lyrics_timed": _timed("E eu sei (eu sei) fui")}

    def test_singer_does_not_need_to_sing_the_backing(self):
        # o cantor canta só a parte dele: nota cheia, mesmo sem o "(eu sei)"
        heard = [{"word": "E", "start": 0.0, "end": 0.4, "probability": 0.9},
                 {"word": "eu", "start": 0.5, "end": 0.9, "probability": 0.9},
                 {"word": "sei", "start": 1.0, "end": 1.4, "probability": 0.9},
                 {"word": "fui", "start": 2.5, "end": 2.9, "probability": 0.9}]
        res = score_words(self.SEG, None, heard, "timing")
        self.assertEqual(res["total_expected"], 4)
        self.assertGreaterEqual(res["score"], 90)

    def test_whisper_hint_has_only_the_lead(self):
        kw = transcribe_kwargs(self.SEG)
        self.assertEqual(kw["initial_prompt"], "E eu sei fui")
        self.assertEqual(kw["expected_words"], ["E", "eu", "sei", "fui"])


class BackingVerseTest(unittest.TestCase):
    SEGS = [{"lyrics": "um"}, {"lyrics": "(Monster)"}, {"lyrics": "dois"}, {"lyrics": "(eu) tres"}]

    def test_backing_only_verse_is_nobodys_turn_and_not_scored(self):
        order = [["Ana"], ["Bia"]]
        owners = [turn_owner(self.SEGS, order, i) for i in range(len(self.SEGS))]
        self.assertEqual(owners, [["Ana"], None, ["Bia"], ["Ana"]])
        room = SimpleNamespace(active_players=["Ana", "Bia"], segments=self.SEGS, turn_order=None)
        self.assertEqual(_verse_players(room, 1), [])
        self.assertEqual(_verse_players(room, 3), ["Ana", "Bia"])


if __name__ == "__main__":
    unittest.main()
