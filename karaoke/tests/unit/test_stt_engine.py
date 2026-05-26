# tests/unit/test_stt_engine.py
"""Unit tests for stt_engine.py focusing on confidence threshold calculation."""

import unittest
import sys
from pathlib import Path

# Add project root and server to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from stt_engine import _get_word_threshold

class TestSttEngine(unittest.TestCase):

    def test_get_word_threshold(self):
        # Adaptive thresholds depending on no_speech_prob:
        # no_speech_prob > 0.60 -> 0.50
        self.assertEqual(_get_word_threshold(0.70), 0.50)
        # no_speech_prob > 0.40 -> 0.30
        self.assertEqual(_get_word_threshold(0.50), 0.30)
        # no_speech_prob > 0.25 -> 0.18
        self.assertEqual(_get_word_threshold(0.30), 0.18)
        # no_speech_prob > 0.15 -> 0.18
        self.assertEqual(_get_word_threshold(0.20), 0.18)
        # clean audio (no_speech_prob <= 0.15) -> 0.08
        self.assertEqual(_get_word_threshold(0.10), 0.08)

if __name__ == "__main__":
    unittest.main()
