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

    @patch("routes.lyrics.run_prepare_song")
    @patch("routes.lyrics.lrc_from_plain")
    def test_save_lyrics_rebuilds_the_lrc_when_the_lyrics_changed(self, mock_from_plain, mock_prepare):
        # letra nova colada na aba "Letra", LRC antigo intocado: o LRC é refeito pelo áudio
        mock_from_plain.return_value = "[00:02.00]Letra certa\n[00:05.00]Segunda linha"
        meta = {"meta": {"title": "Mock Song", "artist": "Artist", "language": "en", "slug": self.song_slug},
                "lyrics": {"plain_lyrics": "Letra certa\nSegunda linha"}}
        old_lrc = "[00:01.00]Letra errada\n[00:03.00]Outra"
        resp = self.client.post("/api/save-lyrics", data={
            "slug": self.song_slug, "language": "en", "lyrics_lrc": old_lrc, "meta_json": json.dumps(meta)})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(mock_from_plain.call_args[0][1], "Letra certa\nSegunda linha")
        self.assertIn("Letra certa", (self.song_dir / "lyrics.lrc").read_text(encoding="utf-8"))
        self.assertIn("Letra certa", resp.json()["lyrics"])
        mock_prepare.assert_called_once()

        # LRC mexido à mão: vale o LRC, mesmo com a letra diferente
        mock_from_plain.reset_mock()
        resp = self.client.post("/api/save-lyrics", data={
            "slug": self.song_slug, "language": "en", "lyrics_lrc": "[00:01.00]Letra certa\n[00:04.00]Linha nova",
            "meta_json": json.dumps(meta), "lrc_edited": "true"})
        self.assertEqual(resp.status_code, 200)
        mock_from_plain.assert_not_called()
        self.assertIn("Linha nova", (self.song_dir / "lyrics.lrc").read_text(encoding="utf-8"))

        # não deu para encaixar: avisa em vez de gerar com a letra velha
        mock_from_plain.return_value = None
        resp = self.client.post("/api/save-lyrics", data={
            "slug": self.song_slug, "language": "en", "lyrics_lrc": old_lrc, "meta_json": json.dumps(meta)})
        self.assertEqual(resp.status_code, 422)

    def test_plain_differs_from_lrc_ignores_repeats_and_punctuation(self):
        from utils.lyrics_resync import plain_differs_from_lrc
        lrc = "[00:01.00]Enquanto eu viver\n[00:02.00]Enquanto eu viver\n[00:03.00]Eu sou (eu sou)\n[00:04.00]"
        self.assertFalse(plain_differs_from_lrc(lrc, "[Refrão]\nEnquanto eu viver,\n\nEu sou (eu sou)"))
        self.assertTrue(plain_differs_from_lrc(lrc, "Enquanto eu viver\nEu sou (eu sou)\nGaara do deserto"))
        self.assertFalse(plain_differs_from_lrc(lrc, ""))  # sem letra: nada a refazer

    def test_song_routes_reject_path_traversal(self):
        # slug vindo do cliente não pode sair de songs/ (delete, save-meta, get-lyrics)
        outside = self.temp_dir.parent / "fora-de-songs"
        outside.mkdir(exist_ok=True)
        (outside / "meta.json").write_text("{}", encoding="utf-8")
        try:
            self.assertEqual(self.client.delete("/api/delete-song/%2E%2E").status_code, 404)
            resp = self.client.post("/api/save-meta", data={
                "slug": "../fora-de-songs",
                "meta_json": json.dumps({"meta": {"title": "x", "artist": "y"}}),
            })
            self.assertEqual(resp.status_code, 404)
            self.assertEqual(self.client.get("/api/get-lyrics", params={"slug": "../fora-de-songs"}).status_code, 404)
            self.assertTrue(self.temp_dir.exists())
            self.assertTrue((outside / "meta.json").exists())
        finally:
            import shutil
            shutil.rmtree(outside, ignore_errors=True)

    def test_status_panel(self):
        data = self.client.get("/api/status").json()
        self.assertIn("gpu", data)
        self.assertIn("free_gb", data["disk"])
        self.assertIsInstance(data["rooms"], list)
        self.assertIn("total", data["queue"])

    def test_players_api(self):
        self.assertEqual(self.client.get("/api/players").status_code, 200)
        self.assertEqual(self.client.get("/api/players/ninguem").status_code, 404)

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
        self.assertIsNone(response.json()["public_url"])

    def test_get_ip_reports_tunnel_url(self):
        with patch.dict("os.environ", {"KARAOKE_PUBLIC_URL": "https://karaoke.myall.net.br"}):
            response = self.client.get("/api/get-ip")
        self.assertEqual(response.json()["public_url"], "https://karaoke.myall.net.br")

    def test_static_assets_are_served_and_revalidated(self):
        for path in ("/styles/tokens.css", "/assets/art/logo-mark.svg", "/js/main.js", "/js/worklets/audio-processor.js?v=km01"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertEqual(response.headers["cache-control"], "no-cache", path)

    def test_index_is_assembled_from_partials(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("<!-- @include", response.text)
        for element_id in ('id="selection-area"', 'id="game-area"', 'id="lobby-seats"', 'id="add-song-modal"'):
            self.assertIn(element_id, response.text)


if __name__ == "__main__":
    unittest.main()
