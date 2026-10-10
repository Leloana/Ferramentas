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


class TestYouTubePlaylistFlow(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_playlist_url_detection(self):
        from utils.youtube import is_playlist_url

        self.assertTrue(is_playlist_url("https://www.youtube.com/playlist?list=PLabc-123"))
        self.assertTrue(is_playlist_url("https://music.youtube.com/playlist?list=OLAK5uy_x"))
        self.assertTrue(is_playlist_url("https://www.youtube.com/watch?v=abcdefghijk&list=RDabc"))
        self.assertFalse(is_playlist_url("https://www.youtube.com/watch?v=abcdefghijk"))
        self.assertFalse(is_playlist_url("oasis wonderwall"))

    def test_rejects_a_link_that_is_not_a_playlist(self):
        response = self.client.get("/api/youtube-playlist?url=https://youtube.com/watch?v=abcdefghijk")
        self.assertEqual(response.status_code, 400)

    @patch("yt_dlp.YoutubeDL")
    def test_lists_the_songs_and_marks_known_ones(self, mock_ytdl):
        import tempfile, json as _json
        from routes import upload as upload_route
        from utils import youtube as yt

        mock_instance = MagicMock()
        mock_instance.extract_info.return_value = {
            "title": "Minha playlist",
            "entries": [
                {"id": "aaaaaaaaaaa", "title": "Oasis - Wonderwall (Official Video)", "channel": "Oasis", "duration": 258},
                {"id": "bbbbbbbbbbb", "title": "Too Close", "channel": "Sir Chloe - Topic", "duration": 200},
                {"id": "ccccccccccc", "title": "[Private video]"},
                {"id": "aaaaaaaaaaa", "title": "Oasis - Wonderwall (Official Video)"},  # repetida
                {"id": "ddddddddddd", "title": "Weezer - Undone", "duration": 300},
            ],
        }
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        with tempfile.TemporaryDirectory() as tmp:
            songs = Path(tmp)
            done = songs / "wonderwall-oasis"
            done.mkdir()
            (done / "segments.json").write_text("[]", encoding="utf-8")
            (done / "meta.json").write_text(_json.dumps(
                {"audio": {"youtube_vocal_url": "https://www.youtube.com/watch?v=aaaaaaaaaaa"}}), encoding="utf-8")
            queued = MagicMock(youtube_url="https://www.youtube.com/watch?v=ddddddddddd")
            with patch.object(upload_route, "SONGS_DIR", songs),                     patch.object(upload_route.queue_manager, "queue", [queued]):
                response = self.client.get("/api/youtube-playlist?url=https://www.youtube.com/playlist?list=PLx")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Minha playlist")
        self.assertFalse(data["truncated"])
        by_id = {r["id"]: r for r in data["results"]}
        self.assertEqual(list(by_id), ["aaaaaaaaaaa", "bbbbbbbbbbb", "ddddddddddd"])
        self.assertEqual(by_id["aaaaaaaaaaa"]["status"], "library")
        self.assertEqual(by_id["ddddddddddd"]["status"], "queue")
        self.assertEqual(by_id["bbbbbbbbbbb"]["status"], "new")
        self.assertEqual(by_id["bbbbbbbbbbb"]["artist_guess"], "Sir Chloe")
        self.assertEqual(by_id["aaaaaaaaaaa"]["title_guess"], "Wonderwall")
        # pede um a mais que o limite para saber se cortou
        opts = mock_ytdl.call_args[0][0]
        self.assertEqual(opts["playlistend"], yt.PLAYLIST_LIMIT + 1)

    def test_estimate_endpoint(self):
        response = self.client.post("/api/queue/estimate", json={"durations": [240, None, 180]})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(data["total_sec"], 0)
        self.assertGreaterEqual(data["total_sec"], data["own_sec"])


if __name__ == "__main__":
    unittest.main()
