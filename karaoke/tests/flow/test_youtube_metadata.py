# tests/flow/test_youtube_metadata.py
"""Flow/Integration tests for YouTube metadata retrieval API."""

import unittest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root and server to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from fastapi.testclient import TestClient
from main import app

class TestYouTubeMetadataFlow(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    @patch("yt_dlp.YoutubeDL")
    def test_youtube_metadata_success(self, mock_ytdl):
        # Mock extract_info returned by YoutubeDL
        mock_instance = MagicMock()
        mock_instance.extract_info.return_value = {
            "title": "Rick and Renner - Escolta de Vagalumes (Official Music Video)"
        }
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        # Valid Request
        response = self.client.get("/api/youtube-metadata?url=https://youtube.com/watch?v=mockid")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify cleaning heuristics (removes Official Music Video, splits by hyphen)
        self.assertEqual(data["artist"], "Rick and Renner")
        self.assertEqual(data["title"], "Escolta de Vagalumes")

    def test_youtube_metadata_invalid_url(self):
        # Missing URL
        response = self.client.get("/api/youtube-metadata?url=")
        self.assertEqual(response.status_code, 400)

        # White space URL
        response = self.client.get("/api/youtube-metadata?url=%20")
        self.assertEqual(response.status_code, 400)

if __name__ == "__main__":
    unittest.main()
