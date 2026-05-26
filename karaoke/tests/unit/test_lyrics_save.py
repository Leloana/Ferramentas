# tests/unit/test_lyrics_save.py
"""Unit tests for lyrics saving logic and metadata generation."""

import unittest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path

# Add project root and server to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from routes.upload import _build_meta

class TestLyricsSave(unittest.TestCase):
    def test_build_meta_with_synced_lrc(self):
        # Case where synced_lrc is provided
        form = {
            "title": "Song Title",
            "artist": "Song Artist",
            "language": "en",
            "youtube_vocal_url": "url_v",
            "youtube_backing_url": "url_b",
            "plain_lyrics": "This is plain lyrics",
            "synced_lrc": "[00:10.00]Line 1",
            "vocal_file": None,
            "backing_file": None,
            "lrc_file": None,
            "lrc_text": None,
        }
        meta = _build_meta(form)
        self.assertTrue(meta["status"]["has_lrc_file"])
        self.assertEqual(meta["lyrics"]["plain_lyrics"], "This is plain lyrics")

    def test_build_meta_without_synced_lrc(self):
        # Case where synced_lrc is not provided and lrc files are empty
        form = {
            "title": "Song Title",
            "artist": "Song Artist",
            "language": "en",
            "youtube_vocal_url": "url_v",
            "youtube_backing_url": "url_b",
            "plain_lyrics": "This is plain lyrics",
            "synced_lrc": None,
            "vocal_file": None,
            "backing_file": None,
            "lrc_file": None,
            "lrc_text": None,
        }
        meta = _build_meta(form)
        self.assertFalse(meta["status"]["has_lrc_file"])
        self.assertEqual(meta["lyrics"]["plain_lyrics"], "This is plain lyrics")

    def test_build_meta_with_user_lrc_file(self):
        # Mocking UploadFile
        mock_lrc_file = MagicMock()
        mock_lrc_file.filename = "lyrics.lrc"

        form = {
            "title": "Song Title",
            "artist": "Song Artist",
            "language": "en",
            "youtube_vocal_url": "url_v",
            "youtube_backing_url": "url_b",
            "plain_lyrics": None,
            "synced_lrc": None,
            "vocal_file": None,
            "backing_file": None,
            "lrc_file": mock_lrc_file,
            "lrc_text": None,
        }
        meta = _build_meta(form)
        self.assertTrue(meta["status"]["has_lrc_file"])

if __name__ == "__main__":
    unittest.main()
