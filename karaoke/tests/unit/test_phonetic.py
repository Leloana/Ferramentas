"""Nota pela pronúncia: o Whisper escreve parecido com o que foi cantado.

Casos das partidas de 2026-10-01 (raps e My Iron Lung): "belly shot" × "Belisha",
"praquefazer" × "pra que fazer". E as armadilhas achadas ao medir: emenda que
ganharia palavra de graça ("felizes" × "E felizes") e o Metaphone sem vogais
("Crackers magazine" soava como "Smacks you in").
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from phonetic import phonetic_key  # noqa: E402
from score_engine import calculate_score  # noqa: E402


def _score(lyrics: str, heard: str, language: str, starts=None) -> float:
    expected = [{"word": w, "expected_start": i * 0.5, "expected_end": i * 0.5 + 0.4}
                for i, w in enumerate(lyrics.split())]
    starts = starts or [i * 0.5 for i in range(len(heard.split()))]
    words = [{"word": w, "start": t, "end": t + 0.4, "probability": 0.9}
             for w, t in zip(heard.split(), starts)]
    return calculate_score(expected, words, language=language)["score"]


class PhoneticKeyTest(unittest.TestCase):
    def test_portuguese_sounds(self):
        same = [("chuva", "xuva"), ("gente", "genti"), ("caça", "cassa"), ("filho", "filio"),
                ("carro", "caro"), ("quero", "kero"), ("hoje", "oje")]
        for a, b in same:
            with self.subTest(a=a, b=b):
                self.assertEqual(phonetic_key(a, "pt"), phonetic_key(b, "pt"))
        # "ss" é s, um s sozinho entre vogais é z
        self.assertNotEqual(phonetic_key("assassino", "pt"), phonetic_key("asasino", "pt"))

    def test_english_uses_metaphone(self):
        self.assertEqual(phonetic_key("steel", "en"), phonetic_key("still", "en"))


class PhoneticScoreTest(unittest.TestCase):
    def test_words_the_whisper_wrote_by_ear_now_count(self):
        self.assertEqual(_score("My Belisha beacon", "My belly shot beacon", "en"), 100.0)
        self.assertEqual(_score("Steel toe caps", "still toe caps", "en"), 100.0)
        self.assertEqual(_score("pra que fazer isso", "praquefazer isso", "pt", starts=[0.0, 1.5]), 100.0)
        self.assertEqual(_score("olha a chuva caindo", "olha a xuva caindo", "pt"), 100.0)

    def test_a_split_does_not_win_a_word_for_free(self):
        self.assertEqual(_score("E felizes a saltitar", "felizes a saltitar", "pt"), 75.0)
        self.assertLess(_score("a mim mesmo", "mim mesmo", "pt"), 70.0)

    def test_other_words_still_score_zero(self):
        self.assertEqual(_score("Smacks you in the head", "Crackers magazine", "en"), 0.0)
        self.assertEqual(_score("Mas que belo assassino", "na na na na", "pt"), 0.0)


if __name__ == "__main__":
    unittest.main()
