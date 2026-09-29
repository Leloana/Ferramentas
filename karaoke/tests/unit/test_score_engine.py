# tests/unit/test_score_engine.py
"""Unit tests for score_engine.py covering text normalization, fuzzy scoring, leakage forgiveness, and sandwich recovery."""

import unittest
import sys
from pathlib import Path

# Add project root and server to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from score_engine import clean_text, calculate_score, filter_vocal_fragments, merge_vocal_fragments

class TestScoreEngine(unittest.TestCase):

    def test_clean_text_normalizes_correctly(self):
        # English cases
        self.assertEqual(clean_text("there's", "en"), "there")
        self.assertEqual(clean_text("i'm", "en"), "i")
        self.assertEqual(clean_text("too", "en"), "to")
        
        # Portuguese cases
        self.assertEqual(clean_text("há", "pt"), "ah")
        self.assertEqual(clean_text("é", "pt"), "eh")
        self.assertEqual(clean_text("mas", "pt"), "mais")
        
        # E a palavra normalizada deve substituir hífens por espaços
        self.assertEqual(clean_text("bem-te-vi", "pt"), "bem te vi")
        self.assertEqual(clean_text("Olá, mundo!", "pt"), "olá mundo")

    def test_calculate_score_happy_path(self):
        expected = [
            {"word": "hello", "expected_start": 1.0, "expected_end": 1.5},
            {"word": "world", "expected_start": 2.0, "expected_end": 2.5}
        ]
        transcribed = [
            {"word": "hello", "start": 1.0, "end": 1.5},
            {"word": "world", "start": 2.0, "end": 2.5}
        ]
        res = calculate_score(expected, transcribed, language="en")
        self.assertEqual(res["score"], 100.0)
        self.assertEqual(res["matched_words"], 2)

    def test_calculate_score_fuzzy_match(self):
        expected = [{"word": "running", "expected_start": 1.0, "expected_end": 1.5}]
        # "runing" is highly similar to "running"
        transcribed = [{"word": "runing", "start": 1.0, "end": 1.5}]
        res = calculate_score(expected, transcribed, language="en")
        self.assertGreaterEqual(res["score"], 80.0)

    def test_calculate_score_timing_penalty(self):
        expected = [{"word": "hello", "expected_start": 1.0, "expected_end": 1.5}]
        # Transcription is 2 seconds late -> TIMING_PENALTY_MID applies (0.85)
        transcribed = [{"word": "hello", "start": 3.1, "end": 3.6}]
        res1 = calculate_score(expected, transcribed, language="en")
        
        # Transcription is 4 seconds late -> TIMING_PENALTY_FAR applies (0.65)
        transcribed_far = [{"word": "hello", "start": 5.0, "end": 5.5}]
        res2 = calculate_score(expected, transcribed_far, language="en")
        
        self.assertEqual(res1["score"], 85.0)
        self.assertEqual(res2["score"], 65.0)

    def test_leakage_forgiveness(self):
        prev_expected = ["far", "away"]
        expected = [{"word": "hello", "expected_start": 1.0, "expected_end": 1.5}]
        # The user sang "far away hello", where "far away" is leakage from previous verse
        transcribed = [
            {"word": "far", "start": 0.2, "end": 0.5},
            {"word": "away", "start": 0.5, "end": 0.8},
            {"word": "hello", "start": 1.0, "end": 1.5}
        ]
        res = calculate_score(expected, transcribed, prev_expected_words=prev_expected, language="en")
        # Leakage should be pardoned and score should be 100% for "hello"
        self.assertEqual(res["score"], 100.0)

    @staticmethod
    def _timed(words, step=0.4):
        return [{"word": w, "expected_start": i * step, "expected_end": i * step + 0.3} for i, w in enumerate(words)]

    @staticmethod
    def _sung(words, step=0.4):
        return [{"word": w, "start": i * step, "end": i * step + 0.3} for i, w in enumerate(words)]

    def test_verse_repeating_the_end_of_the_previous_is_not_leakage(self):
        """Casos reais das gravações de 2026-09-29: verso que repete o fim (ou o começo)
        do anterior foi cantado certo e o "perdão de vazamento" apagava as palavras."""
        cases = [
            # (verso anterior, verso atual, idioma) — A Wolf at the Door / Zé Assassino / Geni
            ("Help me, call the doctor, put me inside", "Put me inside", "en"),
            ("De mãos dadas a cantar, mataram o doutor", "Mataram o doutor", "pt"),
            ("Take it with the love its given", "Take it with a pinch of salt", "en"),
            ("Ela é feita pra apanhar", "Ela é boa de cuspir", "pt"),
            ("Get up get the gunge", "Get the eggs", "en"),
        ]
        for prev, current, lang in cases:
            with self.subTest(current=current):
                words = current.replace(",", "").split()
                res = calculate_score(self._timed(words), self._sung(words),
                                      prev_expected_words=prev.split(), language=lang)
                self.assertEqual(res["score"], 100.0)

    def test_short_vowel_words_in_the_lyrics_are_not_merged_away(self):
        """"é", "eu", "a", "I" cantados no meio do verso são palavras, não "aaa" esticado."""
        cases = [
            ("Ela é boa de cuspir", "pt"),
            ("Quando eu quero você", "pt"),
            ("Vai a cidade e o bispo", "pt"),
            ("Now I promise to be good", "en"),
        ]
        for current, lang in cases:
            with self.subTest(current=current):
                words = current.split()
                res = calculate_score(self._timed(words), self._sung(words), language=lang)
                self.assertEqual(res["score"], 100.0)

    def test_vowel_fragment_not_in_lyrics_still_merges(self):
        """"ooh" / "a" esticados que não estão na letra continuam colados à palavra anterior."""
        expected = self._timed(["love", "me"])
        sung = [{"word": "love", "start": 0.0, "end": 0.3}, {"word": "ah", "start": 0.3, "end": 0.6},
                {"word": "me", "start": 0.4, "end": 0.7}]
        self.assertEqual(calculate_score(expected, sung, language="en")["score"], 100.0)

    def test_rushing_the_whole_line_is_still_penalized(self):
        """Ler a linha inteira correndo (3 s de letra em 0,8 s) continua perdendo pontos."""
        words = ["one", "two", "three", "four", "five", "six", "seven"]
        expected = self._timed(words, step=0.5)          # vão esperado: 3,0 s
        rushed = self._sung(words, step=0.8 / 6)          # vão cantado: 0,8 s
        res = calculate_score(expected, rushed, language="en")
        self.assertLess(res["tempo_factor"], 0.85)
        self.assertLess(res["score"], 75.0)

    def test_natural_timing_noise_is_not_penalized(self):
        """Verso certo com o vão esticado (mediana 1,33x nas gravações de 2026-09-29) ou
        levemente comprimido dentro da imprecisão do Whisper não perde andamento."""
        words = ["tanto", "horror", "e", "muita", "iniquidade"]
        expected = self._timed(words, step=0.3)          # vão esperado: 1,2 s
        for sung_step in (0.3 * 1.33, 0.3 * 1.9, 0.3 * 0.55):   # 1,6 s · 2,3 s · 0,66 s
            with self.subTest(sung_span=round(sung_step * 4, 2)):
                res = calculate_score(expected, self._sung(words, step=sung_step), language="pt")
                self.assertEqual(res["tempo_factor"], 1.0)

    def test_real_leakage_is_still_forgiven(self):
        """Geni 72: o fim do verso anterior vazou antes de "Bendita Geni"."""
        prev = "Você dá pra qualquer um".split()
        expected = self._timed(["Bendita", "Geni"], step=0.8)
        sung = [{"word": w, "start": -1.2 + i * 0.3, "end": -1.0 + i * 0.3}
                for i, w in enumerate(["Dá", "pra", "qualquer", "um"])]
        sung += [{"word": "Bendita", "start": 0.0, "end": 0.5}, {"word": "Geni", "start": 0.8, "end": 1.2}]
        res = calculate_score(expected, sung, prev_expected_words=prev, language="pt")
        self.assertEqual(res["score"], 100.0)

    def test_sandwich_recovery(self):
        expected = [
            {"word": "one", "expected_start": 1.0, "expected_end": 1.3},
            {"word": "two", "expected_start": 1.5, "expected_end": 1.8},
            {"word": "three", "expected_start": 2.0, "expected_end": 2.3}
        ]
        # "two" is missing in transcription
        transcribed = [
            {"word": "one", "start": 1.0, "end": 1.3},
            {"word": "three", "start": 2.0, "end": 2.3}
        ]
        res = calculate_score(expected, transcribed, language="en")
        # Sandwich recovery rescues "two" since it's surrounded by correct words
        self.assertGreater(res["score"], 80.0)

    def test_vocal_fragments(self):
        words = [
            {"word": "hello", "start": 1.0, "end": 1.5},
            {"word": "ah", "start": 1.6, "end": 2.0}
        ]
        filtered = filter_vocal_fragments(words)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["word"], "hello")

        merged = merge_vocal_fragments(words)
        self.assertEqual(len(merged), 1)
        # End time of hello should be extended to end time of "ah" (2.0)
        self.assertEqual(merged[0]["end"], 2.0)

if __name__ == "__main__":
    unittest.main()
