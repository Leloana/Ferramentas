"""Capa do álbum: extração do id do YouTube e cache em disco (sem rede)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from utils import cover  # noqa: E402


class CoverTest(unittest.TestCase):
    def test_youtube_id_formats(self):
        self.assertEqual(cover.youtube_id("https://youtu.be/VKjEdYrx9P0?list=RDVKjEdYrx9P0"), "VKjEdYrx9P0")
        self.assertEqual(cover.youtube_id("https://www.youtube.com/watch?v=NUTGr5t3MoY&t=3"), "NUTGr5t3MoY")
        self.assertIsNone(cover.youtube_id(None))

    def test_existing_cover_is_reused_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            song = Path(tmp)
            (song / "cover.jpg").write_bytes(b"jpg")
            with patch.object(cover, "_get", side_effect=AssertionError("não deveria baixar")):
                self.assertEqual(cover.find_cover(song), song / "cover.jpg")

    def test_network_error_does_not_mark_as_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            song = Path(tmp)
            (song / "meta.json").write_text('{"meta": {"title": "X", "artist": "Y"}}', encoding="utf-8")
            with patch.object(cover, "_get", side_effect=OSError("offline")):
                self.assertIsNone(cover.find_cover(song))
            self.assertFalse((song / "cover.none").exists())


if __name__ == "__main__":
    unittest.main()
