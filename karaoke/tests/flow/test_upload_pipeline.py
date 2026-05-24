# tests/flow/test_upload_pipeline.py
"""Flow/Integration tests for song upload and reinstall HTTP APIs."""

import unittest
import sys
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Add project root and server to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from fastapi.testclient import TestClient

class TestUploadPipelineFlow(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Create a temporary directory for songs
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="karaoke_test_upload_"))
        
        # Patch SONGS_DIR before importing app
        cls.patcher_dir = patch("state.SONGS_DIR", cls.temp_dir)
        cls.patcher_dir.start()
        
        cls.patcher_upload_dir = patch("routes.upload.SONGS_DIR", cls.temp_dir)
        cls.patcher_upload_dir.start()
        
        cls.patcher_songs_dir = patch("routes.songs.SONGS_DIR", cls.temp_dir)
        cls.patcher_songs_dir.start()

        from main import app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.patcher_dir.stop()
        cls.patcher_upload_dir.stop()
        cls.patcher_songs_dir.stop()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    @patch("routes.upload.run_reinstall_song")
    def test_upload_song_success(self, mock_run_reinstall):
        mock_run_reinstall.return_value = True

        # Mock files
        vocal_data = b"vocal pcm data"
        backing_data = b"backing pcm data"
        lrc_data = b"[00:01.00]Hello world\n"

        # Create temporary files to upload
        files = {
            "vocal_file": ("vocal.mp3", vocal_data, "audio/mpeg"),
            "backing_file": ("backing.mp3", backing_data, "audio/mpeg"),
            "lrc_file": ("lyrics.lrc", lrc_data, "text/plain")
        }

        # Form fields
        data = {
            "title": "Upload Test Song",
            "artist": "Test Artist",
            "language": "en",
            "align_lyrics": "false"
        }

        # Make sure target dir does not exist
        song_slug = "upload-test-song-test-artist"
        song_dir = self.temp_dir / song_slug
        if song_dir.exists():
            shutil.rmtree(song_dir)

        # Trigger upload
        response = self.client.post("/api/upload-song", data=data, files=files)
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertTrue(res_data["success"])
        self.assertEqual(res_data["lyrics_status"], "draft")
        self.assertEqual(res_data["slug"], song_slug)

        # Verify files were saved correctly on disk
        self.assertTrue(song_dir.exists())
        self.assertTrue((song_dir / "meta.json").exists())
        self.assertTrue((song_dir / "vocal.mp3").exists())
        self.assertTrue((song_dir / "backing_track.mp3").exists())
        self.assertTrue((song_dir / "lyrics.lrc").exists())

        # Verify meta.json layout is correct
        with open(song_dir / "meta.json", "r", encoding="utf-8") as f:
            meta = json.load(f)
            self.assertEqual(meta["meta"]["title"], "Upload Test Song")
            self.assertEqual(meta["meta"]["artist"], "Test Artist")
            self.assertTrue(meta["status"]["has_vocal_file"])
            self.assertTrue(meta["status"]["has_backing_file"])
            self.assertTrue(meta["status"]["has_lrc_file"])

    @patch("tools.reinstall_song.reinstall_song")
    def test_reinstall_song_success(self, mock_reinstall):
        mock_reinstall.return_value = True

        # Precreate target song directory
        song_slug = "reinstall-song-slug"
        song_dir = self.temp_dir / song_slug
        song_dir.mkdir(parents=True, exist_ok=True)
        with open(song_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump({"meta": {"title": "Reinstall Test", "slug": song_slug}}, f)

        # Trigger reinstall API
        response = self.client.post(f"/api/reinstall-song/{song_slug}?align_lyrics=true")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        mock_reinstall.assert_called_once_with(str(song_dir), align_lyrics=True)

    def test_reinstall_song_not_found(self):
        response = self.client.post("/api/reinstall-song/non-existent-song")
        self.assertEqual(response.status_code, 404)

if __name__ == "__main__":
    unittest.main()
