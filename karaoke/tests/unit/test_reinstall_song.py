# tests/unit/test_reinstall_song.py
import unittest
from unittest.mock import MagicMock, patch, mock_open
import sys
import json
from pathlib import Path

# Add project root and server to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from tools.reinstall_song import reinstall_song

class TestReinstallSong(unittest.IsolatedAsyncioTestCase):
    @patch("tools.reinstall_song.Path")
    @patch("tools.reinstall_song.open", new_callable=mock_open)
    @patch("utils.lyrics_fetcher.fetch_lyrics")
    @patch("tools.reinstall_song.download_youtube_audio")
    @patch("tools.reinstall_song.AudioSegment")
    @patch("tools.reinstall_song.prepare_song")
    async def test_reinstall_fetches_api_lyrics_and_saves_synced(
        self, mock_prepare, mock_audioseg, mock_download, mock_fetch, mock_open_file, mock_path
    ):
        # Setup mocks
        mock_path_inst = MagicMock()
        mock_path.return_value = mock_path_inst
        
        # meta.json exists
        mock_meta_file = MagicMock()
        mock_meta_file.exists.return_value = True
        mock_path_inst.__truediv__.return_value = mock_meta_file
        
        # Mock file contents for meta.json
        meta_data = {
            "meta": {
                "title": "Imagine",
                "artist": "John Lennon",
                "language": "en",
                "slug": "imagine-john-lennon"
            },
            "audio": {
                "youtube_vocal_url": "vocal_url",
                "youtube_backing_url": ""
            },
            "lyrics": {
                "plain_lyrics": ""
            }
        }
        
        # When reading meta.json
        mock_open_file.return_value.read.return_value = json.dumps(meta_data)
        
        # Mock lyrics fetcher
        mock_fetch.return_value = {
            "plainLyrics": "Imagine all the people",
            "syncedLyrics": "[00:10.00] Imagine all the people",
            "source": "lrclib"
        }
        
        # Mock download success
        mock_download.return_value = True
        
        # Call reinstall_song
        # Note: reinstall_song is async, so we must run it
        import asyncio
        success = await reinstall_song(
            song_dir_path="/mock/song/dir",
            clean_existing=False,
            align_lyrics=False
        )
        
        self.assertTrue(success)
        
        # Verify fetch_lyrics was called with right args
        mock_fetch.assert_called_once_with("John Lennon", "Imagine")

if __name__ == "__main__":
    unittest.main()
