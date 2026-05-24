# tests/unit/test_lrc_alignment.py
"""Unit tests for lyric alignment utilities (lrc_align.py and lrc_pro.py)."""

import unittest
import sys
from pathlib import Path

# Add project root and server to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from utils.lrc_align import align_plain_lyrics
from utils.lrc_pro import parse_and_normalize_lyrics

# Mock whisper segment representation
class MockWhisperWord:
    def __init__(self, word, start, end):
        self.word = word
        self.start = start
        self.end = end

class MockWhisperSegment:
    def __init__(self, text, words):
        self.text = text
        self.words = words

class TestLrcAlignment(unittest.TestCase):

    def test_align_plain_lyrics_happy_path(self):
        plain_lyrics = "Hello world\nThis is a test"
        
        # Mock Whisper word output
        whisper_segments = [
            MockWhisperSegment("Hello world", [
                MockWhisperWord("Hello", 1.0, 1.5),
                MockWhisperWord("world", 1.6, 2.0)
            ]),
            MockWhisperSegment("This is a test", [
                MockWhisperWord("This", 3.0, 3.4),
                MockWhisperWord("is", 3.5, 3.7),
                MockWhisperWord("a", 3.8, 3.9),
                MockWhisperWord("test", 4.0, 4.5)
            ])
        ]
        
        lrc_text, fallback_used = align_plain_lyrics(
            plain_lyrics,
            whisper_segments,
            title="Test Song",
            artist="Tester",
            total_vocal_duration_sec=10.0
        )
        
        self.assertFalse(fallback_used)
        self.assertIn("[ti:Test Song]", lrc_text)
        self.assertIn("[ar:Tester]", lrc_text)
        self.assertIn("[00:01.00]Hello world", lrc_text)
        self.assertIn("[00:03.00]This is a test", lrc_text)

    def test_align_plain_lyrics_fallback_linear(self):
        plain_lyrics = "Hello world\nThis is a test"
        # Empty whisper segment output should trigger linear fallback
        whisper_segments = []
        
        lrc_text, fallback_used = align_plain_lyrics(
            plain_lyrics,
            whisper_segments,
            title="Test Song",
            artist="Tester",
            total_vocal_duration_sec=10.0
        )
        
        # When no whisper words exist, it uses the linear interval fallback (4 seconds by default)
        self.assertIn("[00:00.00]Hello world", lrc_text)
        self.assertIn("[00:04.00]This is a test", lrc_text)

    def test_lrc_pro_parse_and_normalize_lyrics(self):
        plain_lyrics = "[ti:Test Metadata Tag]\n[offset:500]\nOlá! Como vai você, bem-te-vi?"
        
        lines, flat_normalized_words = parse_and_normalize_lyrics(plain_lyrics)
        
        # Should skip header tags
        self.assertEqual(len(lines), 1)
        self.assertEqual(len(lines[0]), 5) # Olá!, Como, vai, você,, bem-te-vi?
        
        # Check raw words
        self.assertEqual(lines[0][0]["raw"], "Olá!")
        self.assertEqual(lines[0][4]["raw"], "bem-te-vi?")
        
        # Check normalized words for MMS_FA
        self.assertEqual(lines[0][0]["norm"], "ola")
        self.assertEqual(lines[0][4]["norm"], "bemtevi") # Removes hyphen and special chars
        
        # Check flat normalized words
        self.assertIn("ola", flat_normalized_words)
        self.assertIn("como", flat_normalized_words)
        self.assertIn("vai", flat_normalized_words)
        self.assertIn("voce", flat_normalized_words)
        self.assertIn("bemtevi", flat_normalized_words)

if __name__ == "__main__":
    unittest.main()
