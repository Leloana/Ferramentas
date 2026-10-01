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

    def test_line_with_nothing_heard_still_gets_times(self):
        # Whisper ouviu só lixo em katakana: antes os tempos voltavam None e o prepare_song quebrava
        timed = time_words_by_characters(LINE, "ja", _pieces(["コ", "シ", "カ"]))
        starts = [w["start"] for w in timed]
        self.assertTrue(all(s is not None for s in starts))
        self.assertEqual(starts, sorted(starts))
        self.assertLessEqual(timed[-1]["end"], 0.85)

    def test_song_list_brings_romaji_for_japanese_titles(self):
        from lyrics_text import to_romaji

        self.assertEqual(to_romaji("青い、濃い、橙色の日"), "aoi koi daidaiirono hi")
        self.assertEqual(to_romaji("Construção"), "Construção")

    def test_slug_of_a_japanese_title_is_romaji(self):
        from utils.text import slugify
        # antes: "-mass-of-the-fermenting-dregs" (o título sumia no ASCII)
        self.assertEqual(slugify("青い、濃い、橙色の日-MASS OF THE FERMENTING DREGS"),
                         "aoi-koi-daidaiirono-hi-mass-of-the-fermenting-dregs")
        self.assertEqual(slugify("Construção-Chico Buarque"), "construcao-chico-buarque")

    def test_queue_switches_to_japanese_when_lyrics_have_kana(self):
        self.assertEqual(infer_language("[00:01.10] 待ちぼうけさ\n[00:04.20] 追い掛けても", "en"), "ja")
        self.assertEqual(infer_language("Joga pedra na Geni", "pt"), "pt")
        self.assertEqual(infer_language("我爱你中国人民", "en"), "en")  # chinês não tem kana


class TestRomajiDisplay(unittest.TestCase):
    def test_romaji_follows_pronunciation(self):
        from lyrics_text import ja_romaji

        # partículas como se cantam: は→wa, へ→e, を→o; vogal longa preservada
        self.assertEqual([ja_romaji(w) for w in split_words("あの声はどこから来て", "ja")],
                         ["ano", "koewa", "dokokara", "kite"])
        self.assertEqual(ja_romaji("どこへ"), "dokoe")
        self.assertEqual(ja_romaji("日を"), "hio")
        self.assertEqual(ja_romaji("遠ざかって"), "toozakatte")

    def test_add_romaji_only_touches_japanese_segments(self):
        from lyrics_text import add_romaji

        ja = {"language": "ja", "lyrics": "青い、濃い、橙色の日",
              "lyrics_timed": [{"word": w} for w in split_words("青い、濃い、橙色の日", "ja")]}
        pt = {"language": "pt", "lyrics": "Joga pedra", "lyrics_timed": [{"word": "Joga"}, {"word": "pedra"}]}
        add_romaji([ja, pt])
        self.assertEqual(ja["lyrics_romaji"], "aoi koi daidaiirono hi")
        self.assertEqual([w["romaji"] for w in ja["lyrics_timed"]], ["aoi", "koi", "daidaiirono", "hi"])
        self.assertNotIn("lyrics_romaji", pt)
        self.assertNotIn("romaji", pt["lyrics_timed"][0])


class TestSongLoadAddsRomaji(unittest.TestCase):
    def test_song_manager_serves_romaji_for_japanese_songs_already_prepared(self):
        import json
        import shutil
        import tempfile

        from song_manager import SongManager

        tmp = Path(tempfile.mkdtemp(prefix="karaoke_ja_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "aoi").mkdir()
        segments = [{"language": "ja", "lyrics": "青い、濃い、橙色の日", "sing_start": 1.0, "sing_end": 3.0,
                     "lyrics_timed": [{"word": w, "expected_start": 0.1 * i, "expected_end": 0.1 * i + 0.1}
                                      for i, w in enumerate(split_words("青い、濃い、橙色の日", "ja"))]}]
        (tmp / "aoi" / "segments.json").write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")

        data = SongManager(tmp).get_song_data("aoi")
        self.assertEqual(data["segments"][0]["lyrics_romaji"], "aoi koi daidaiirono hi")
        # o arquivo no disco não muda: romaji é calculado ao carregar
        self.assertNotIn("lyrics_romaji", (tmp / "aoi" / "segments.json").read_text(encoding="utf-8"))


class TestRomajiLyrics(unittest.TestCase):
    """Letra colada só em romaji: fica como veio (sem inventar kana) e ainda pontua,
    porque o Whisper escreve em kana e a comparação é pela pronúncia."""

    LINE = "toozakatte iku hi mo mienai"
    SEGMENT = {
        "language": "ja", "lyrics": LINE,
        "lyrics_timed": [{"word": w, "expected_start": round(0.05 + i * 0.4, 2), "expected_end": round(0.35 + i * 0.4, 2)}
                         for i, w in enumerate(LINE.split())],
    }

    def test_romaji_line_is_split_on_spaces_and_gets_no_generated_script(self):
        from lyrics_text import add_romaji

        self.assertEqual(split_words(self.LINE, "ja"), self.LINE.split())
        self.assertEqual(join_words(self.LINE.split(), "ja"), self.LINE)
        seg = {**self.SEGMENT, "lyrics_timed": [dict(w) for w in self.SEGMENT["lyrics_timed"]]}
        add_romaji([seg])
        self.assertNotIn("lyrics_romaji", seg)
        self.assertNotIn("romaji", seg["lyrics_timed"][0])

    def test_typed_romaji_matches_the_sung_pronunciation(self):
        self.assertEqual(ja_reading("koe wa"), ja_reading("声は"))  # partícula は = "wa"
        self.assertEqual(ja_reading("toozakatte"), ja_reading("遠ざかって"))
        self.assertEqual(ja_reading("tōzakatte"), "tozakatte")  # mácron normalizado

    def test_sung_right_scores_high_and_wrong_lyrics_low(self):
        heard = _pieces(["遠", "ざ", "かって", "いく", "日", "も", "見", "えない"])
        self.assertGreaterEqual(score_words(self.SEGMENT, None, heard, "timing")["score"], 90.0)
        other = _pieces(["あの", "声", "は", "どこ", "から", "来", "て"])
        self.assertLess(score_words(self.SEGMENT, None, other, "timing")["score"], 20.0)

    def test_song_prep_times_romaji_words_in_order(self):
        heard = _pieces(["遠", "ざ", "かって", "いく", "日", "も", "見", "えない"])
        timed = time_words_by_characters(self.LINE, "ja", heard)
        self.assertEqual([w["word"] for w in timed], self.LINE.split())
        starts = [w["start"] for w in timed]
        self.assertEqual(starts, sorted(starts))
        self.assertTrue(all(w["end"] >= w["start"] for w in timed))

    def test_mixed_line_keeps_spaces_around_latin_words(self):
        words = split_words("Oh baby 愛してる、ずっと", "ja")
        self.assertEqual(words[:2], ["Oh", "baby"])
        self.assertEqual(join_words(words, "ja"), "Oh baby 愛してる、ずっと")


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
