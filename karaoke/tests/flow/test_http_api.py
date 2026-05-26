# tests/flow/test_http_api.py
"""Flow/Integration tests for Karaoke HTTP APIs using FastAPI TestClient and a temporary songs directory."""

import unittest
import sys
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock

# Add project root and server to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from fastapi.testclient import TestClient

class TestHttpApiFlow(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Create a temporary directory for songs
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="karaoke_test_songs_"))
        
        # Populate temp directory with a mock song
        cls.song_slug = "mock-song-artist"
        cls.song_dir = cls.temp_dir / cls.song_slug
        cls.song_dir.mkdir(parents=True, exist_ok=True)
        
        cls.meta_data = {
            "meta": {
                "title": "Mock Song",
                "artist": "Artist",
                "language": "en",
                "slug": cls.song_slug
            },
            "audio": {
                "youtube_vocal_url": "https://youtube.com/vocal",
                "youtube_backing_url": "https://youtube.com/backing"
            },
            "lyrics": {
                "plain_lyrics": "Hello world\nThis is a mock song"
            },
            "status": {
                "has_vocal_file": True,
                "has_backing_file": True,
                "has_lrc_file": True
            }
        }
        with open(cls.song_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(cls.meta_data, f, indent=4)
            
        with open(cls.song_dir / "lyrics.lrc", "w", encoding="utf-8") as f:
            f.write("[ti:Mock Song]\n[ar:Artist]\n[00:01.00]Hello world\n[00:03.00]This is a mock song\n")
            
        with open(cls.song_dir / "lyrics.txt", "w", encoding="utf-8") as f:
            f.write("Hello world\nThis is a mock song\n")
            
        with open(cls.song_dir / "segments.json", "w", encoding="utf-8") as f:
            json.dump([], f)
            
        with open(cls.song_dir / "backing_track.mp3", "w", encoding="utf-8") as f:
            f.write("mock audio")
            
        # Patch SONGS_DIR and song_manager in state module before importing app
        cls.patcher_dir = patch("state.SONGS_DIR", cls.temp_dir)
        cls.patcher_dir.start()
        
        from song_manager import SongManager
        cls.mock_song_manager = SongManager(cls.temp_dir)
        cls.patcher_mgr = patch("state.song_manager", cls.mock_song_manager)
        cls.patcher_mgr.start()
        
        # Also patch routes modules that import state.SONGS_DIR or state.song_manager
        cls.patcher_routes_songs = patch("routes.songs.song_manager", cls.mock_song_manager)
        cls.patcher_routes_songs.start()
        cls.patcher_routes_songs_dir = patch("routes.songs.SONGS_DIR", cls.temp_dir)
        cls.patcher_routes_songs_dir.start()
        
        cls.patcher_routes_lyrics_dir = patch("routes.lyrics.SONGS_DIR", cls.temp_dir)
        cls.patcher_routes_lyrics_dir.start()

        # Import FastAPI app
        from main import app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        # Stop all patches
        cls.patcher_dir.stop()
        cls.patcher_mgr.stop()
        cls.patcher_routes_songs.stop()
        cls.patcher_routes_songs_dir.stop()
        cls.patcher_routes_lyrics_dir.stop()
        
        # Remove temporary directory
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_list_songs(self):
        response = self.client.get("/api/songs")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertTrue(len(data) >= 1)
        self.assertEqual(data[0]["id"], self.song_slug)
        self.assertEqual(data[0]["title"], "Mock Song")
        self.assertEqual(data[0]["artist"], "Artist")

    def test_get_song(self):
        # Valid song ID
        response = self.client.get(f"/api/songs/{self.song_slug}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], self.song_slug)
        self.assertEqual(data["title"], "Mock Song")
        self.assertEqual(data["artist"], "Artist")
        self.assertIsInstance(data["segments"], list)

        # Invalid song ID
        response_invalid = self.client.get("/api/songs/non-existent-song")
        self.assertEqual(response_invalid.status_code, 404)

    def test_get_audio(self):
        # Valid song ID
        response = self.client.get(f"/songs/{self.song_slug}/audio")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"mock audio")

        # Invalid song ID
        response_invalid = self.client.get("/songs/non-existent-song/audio")
        self.assertEqual(response_invalid.status_code, 404)

    def test_get_lyrics(self):
        response = self.client.get(f"/api/get-lyrics?slug={self.song_slug}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("[00:01.00]Hello world", data["lyrics"])
        self.assertIn("meta", json.loads(data["meta_json"]))

    @patch("routes.lyrics.run_prepare_song")
    def test_save_lyrics(self, mock_run_prepare):
        # Mock run_prepare_song to do nothing
        mock_run_prepare.return_value = None
        
        updated_lrc = "[ti:Mock Song]\n[ar:Artist]\n[00:01.00]Hello brand new world\n[00:03.00]This is a mock song\n"
        updated_meta = {
            "meta": {
                "title": "Mock Song",
                "artist": "Artist",
                "language": "en",
                "slug": self.song_slug
            },
            "lyrics": {
                "plain_lyrics": "Hello brand new world\nThis is a mock song"
            }
        }
        
        response = self.client.post("/api/save-lyrics", data={
            "slug": self.song_slug,
            "language": "en",
            "lyrics_lrc": updated_lrc,
            "meta_json": json.dumps(updated_meta)
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        
        # Verify it was updated on disk
        with open(self.song_dir / "lyrics.lrc", "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Hello brand new world", content)

    def test_delete_song(self):
        # Create a temp song specifically for deleting
        del_song_slug = "delete-me-artist"
        del_song_dir = self.temp_dir / del_song_slug
        del_song_dir.mkdir(parents=True, exist_ok=True)
        with open(del_song_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump({}, f)
            
        # Delete it via API
        response = self.client.delete(f"/api/delete-song/{del_song_slug}")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        
        # Check that folder is gone
        self.assertFalse(del_song_dir.exists())

    def test_get_ip(self):
        response = self.client.get("/api/get-ip")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ip", response.json())

if __name__ == "__main__":
    unittest.main()
