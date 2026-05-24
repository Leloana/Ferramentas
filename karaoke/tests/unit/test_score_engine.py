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
