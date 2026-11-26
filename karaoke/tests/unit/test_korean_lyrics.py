"""K-pop: hangul misturado com inglês (romanização, idioma por verso, nota)."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from lyrics_text import (  # noqa: E402
    add_romaji, assign_line_languages, infer_language, ko_romaja, line_language, to_romaji, whisper_language,
)
from score_engine import clean_text  # noqa: E402
from utils.lrc_pro import parse_and_normalize_lyrics  # noqa: E402


class KoreanLyricsTest(unittest.TestCase):
    def test_hangul_switches_language_to_korean(self):
        self.assertEqual(infer_language("I was a ghost\n어두워진 압길속에", "en"), "ko")
        self.assertEqual(infer_language("I was a ghost", "en"), "en")

    def test_romanization_follows_pronunciation(self):
        self.assertEqual(ko_romaja("끝없이"), "kkeuteopsi")
        self.assertEqual(ko_romaja("paid,끝없이 on stage"), "paid,kkeuteopsi on stage")
        self.assertEqual(to_romaji("영원히"), "yeongwonhi")

    def test_line_language_hangul_korean_rest_english(self):
        segs = [{"lyrics": "I was a ghost", "language": "ko"},
                {"lyrics": "어두워진 압길속에", "language": "en"}]
        assign_line_languages(segs, "ko")
        self.assertEqual([s["language"] for s in segs], ["en", "ko"])

    def test_song_without_hangul_untouched(self):
        segs = [{"lyrics": "Olá", "language": "pt"}]
        assign_line_languages(segs, "pt")
        self.assertEqual(segs[0]["language"], "pt")

    def test_romaji_fields_for_screen(self):
        segs = [{"lyrics": "끝없이 on stage", "language": "ko",
                 "lyrics_timed": [{"word": "끝없이"}, {"word": "on"}, {"word": "stage"}]}]
        add_romaji(segs)
        self.assertEqual(segs[0]["lyrics_romaji"], "kkeuteopsi on stage")
        self.assertEqual(segs[0]["lyrics_timed"][0]["romaji"], "kkeuteopsi")

    def test_score_and_alignment_compare_in_latin(self):
        self.assertEqual(clean_text("끝없이", "ko"), "kkeuteopsi")
        self.assertEqual(clean_text("Stage!", "ko"), "stage")
        lines, flat = parse_and_normalize_lyrics("밝게 빛나는 우린", "ko")
        self.assertEqual(flat, ["bakge", "bitnaneun", "urin"])

    def test_whole_song_whisper_language(self):
        mostly_english = "I was a ghost\n어두워진 압길속에\nGiven the throne\nHow to believe"
        self.assertEqual(whisper_language("ko", mostly_english), "en")
        self.assertEqual(whisper_language("ko", "영원히 깨질\n밝게 빛나는\nGolden"), "ko")
        self.assertEqual(whisper_language("pt", "Olá"), "pt")
        self.assertEqual(line_language("끝없이 on stage", "ko"), "ko")
        self.assertEqual(line_language("on stage", "ko"), "en")


if __name__ == "__main__":
    unittest.main()
