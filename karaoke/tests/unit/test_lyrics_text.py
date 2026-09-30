"""Letras por idioma: japonês (sem espaço entre palavras) no preparo e no score."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from lyrics_text import (  # noqa: E402
    infer_language,
    ja_reading,
    join_words,
    regroup_timed_words,
    split_words,
    time_words_by_characters,
)
from segment_scoring import score_words  # noqa: E402

# 青い、濃い、橙色の日 — MASS OF THE FERMENTING DREGS (música de teste do japonês)
LINE = "遠ざかっていく日も見えない"


def _pieces(chunks, step=0.3):
    """Como o Whisper devolve japonês: pedaços de 1–3 caracteres com tempo."""
    return [{"word": c, "start": round(i * step, 3), "end": round(i * step + 0.25, 3), "probability": 0.9}
            for i, c in enumerate(chunks)]


class TestJapaneseWords(unittest.TestCase):
    def test_line_splits_into_bunsetsu(self):
        self.assertEqual(split_words(LINE, "ja"), ["遠ざかって", "いく日も", "見えない"])
        self.assertEqual(split_words("青い、濃い、橙色の日", "ja"), ["青い、", "濃い、", "橙色の", "日"])

    def test_other_languages_keep_splitting_on_spaces(self):
        self.assertEqual(split_words("Joga pedra na Geni", "pt"), ["Joga", "pedra", "na", "Geni"])
        self.assertEqual(join_words(["Joga", "pedra"], "pt"), "Joga pedra")
        self.assertEqual(join_words(["青い、", "濃い、"], "ja"), "青い、濃い、")

    def test_reading_is_the_same_in_kanji_or_kana(self):
        self.assertEqual(ja_reading("遠ざかって"), ja_reading("とおざかって"))
        self.assertEqual(ja_reading("日"), ja_reading("ひ"))
        self.assertRegex(ja_reading("橙色の"), r"^[a-z]+$")  # MMS_FA só aceita a–z

    def test_whisper_pieces_regroup_into_lyric_units_with_times(self):
        words = regroup_timed_words(_pieces(["遠", "ざ", "かって", "いく", "日", "も", "見", "えない"]), "ja")
        self.assertEqual([w["word"] for w in words], ["遠ざかって", "いく日も", "見えない"])
        self.assertEqual((words[1]["start"], words[1]["end"]), (0.9, 1.75))
        # Fora do japonês, nada muda.
        latin = _pieces(["joga", "pedra"])
        self.assertIs(regroup_timed_words(latin, "pt"), latin)

    def test_times_by_characters_survive_kana_written_as_kanji(self):
        timed = time_words_by_characters(LINE, "ja", _pieces(["とお", "ざかって", "いくひも", "見えない"]))
        self.assertEqual([w["word"] for w in timed], ["遠ざかって", "いく日も", "見えない"])
        starts = [w["start"] for w in timed]
        self.assertEqual(starts, sorted(starts))
        self.assertTrue(all(s is not None for s in starts))

    def test_queue_switches_to_japanese_when_lyrics_have_kana(self):
        self.assertEqual(infer_language("[00:01.10] 待ちぼうけさ\n[00:04.20] 追い掛けても", "en"), "ja")
        self.assertEqual(infer_language("Joga pedra na Geni", "pt"), "pt")
        self.assertEqual(infer_language("我爱你中国人民", "en"), "en")  # chinês não tem kana


class TestJapaneseScoring(unittest.TestCase):
    SEGMENT = {
        "language": "ja", "lyrics": LINE,
        "lyrics_timed": [
            {"word": "遠ざかって", "expected_start": 0.05, "expected_end": 0.8},
            {"word": "いく日も", "expected_start": 0.9, "expected_end": 1.7},
            {"word": "見えない", "expected_start": 1.8, "expected_end": 2.4},
        ],
    }

    def test_sung_right_scores_full_when_whisper_writes_like_the_lyrics(self):
        # Com a linha como dica, o Whisper devolve a mesma escrita da letra.
        kanji = _pieces(["遠", "ざ", "かって", "いく", "日", "も", "見", "えない"])
        self.assertEqual(score_words(self.SEGMENT, None, kanji, "timing")["score"], 100.0)

    def test_sung_right_written_all_in_kana_still_scores_high(self):
        # Limite conhecido: em kana o MeCab divide diferente (いく / ひも) e lê o 日 da
        # letra pelo contexto (いく日も → ikukamo); a comparação pela leitura segura quase tudo.
        kana = _pieces(["とお", "ざか", "って", "いく", "ひ", "も", "みえ", "ない"])
        self.assertGreaterEqual(score_words(self.SEGMENT, None, kana, "timing")["score"], 90.0)

    def test_other_lyrics_score_low(self):
        other = _pieces(["あの", "声", "は", "どこ", "から", "来", "て"])
        self.assertLess(score_words(self.SEGMENT, None, other, "timing")["score"], 20.0)


class TestMmsNormalization(unittest.TestCase):
    def test_japanese_lyrics_become_romaji_units_for_mms(self):
        from utils.lrc_pro import parse_and_normalize_lyrics

        lines, flat = parse_and_normalize_lyrics(f"{LINE}\n青い、濃い、橙色の日", "ja")
        self.assertEqual([w["raw"] for w in lines[0]], ["遠ざかって", "いく日も", "見えない"])
        self.assertTrue(all(n.isascii() and n.isalpha() for n in flat))
        self.assertEqual(len(flat), 7)


if __name__ == "__main__":
    unittest.main()
