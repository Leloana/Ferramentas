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
            (song / "cover.options.json").write_text("[]", encoding="utf-8")
            with patch.object(cover, "_get", side_effect=AssertionError("não deveria baixar")):
                self.assertEqual(cover.find_cover(song), song / "cover.jpg")

    def test_legacy_cover_is_picked_again_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            song = Path(tmp)
            (song / "cover.jpg").write_bytes(b"old")
            best = [{"url": "https://x/best.jpg", "thumb": "t", "source": "Deezer", "album": "A", "score": 0.9}]
            with patch.object(cover, "collect_candidates", return_value=(best, False)), \
                    patch.object(cover, "_get", return_value=b"n" * 1000):
                cover.find_cover(song)
            self.assertEqual((song / "cover.jpg").read_bytes(), b"n" * 1000)
            with patch.object(cover, "_get", side_effect=AssertionError("só uma vez")):
                cover.find_cover(song)

    def test_network_error_does_not_mark_as_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            song = Path(tmp)
            (song / "meta.json").write_text('{"meta": {"title": "X", "artist": "Y"}}', encoding="utf-8")
            with patch.object(cover, "_get", side_effect=OSError("offline")):
                self.assertIsNone(cover.find_cover(song))
            self.assertFalse((song / "cover.none").exists())

    def test_tribute_album_loses_to_the_original(self):
        original = cover.score_candidate("Radiohead", "A Wolf at the Door", "Radiohead", "A Wolf At the Door", "Hail to the Thief")
        tribute = cover.score_candidate("Radiohead", "A Wolf at the Door", "Various Artists", "A Wolf at the Door", "Our Tribute to Radiohead")
        karaoke = cover.score_candidate("Radiohead", "A Wolf at the Door", "Radiohead", "A Wolf at the Door (Karaoke)", "Karaoke Hits")
        self.assertGreater(original, tribute)
        self.assertGreater(original, karaoke)

    def test_best_candidate_is_used_and_only_listed_urls_can_be_chosen(self):
        with tempfile.TemporaryDirectory() as tmp:
            song = Path(tmp)
            (song / "meta.json").write_text('{"meta": {"title": "Geni", "artist": "Chico"}}', encoding="utf-8")
            fake = [
                {"url": "https://x/tribute.jpg", "thumb": "t", "source": "iTunes", "album": "Tributo", "score": 0.4},
                {"url": "https://x/best.jpg", "thumb": "t", "source": "Deezer", "album": "Original", "score": 0.95},
            ]
            got = []
            with patch.object(cover, "collect_candidates", return_value=(sorted(fake, key=lambda c: -c["score"]), False)), \
                    patch.object(cover, "_get", side_effect=lambda url: got.append(url) or b"x" * 1000):
                self.assertEqual(cover.find_cover(song), song / "cover.jpg")
                self.assertEqual(got, ["https://x/best.jpg"])
                self.assertFalse(cover.choose_cover(song, "https://evil/other.jpg"))
                self.assertTrue(cover.choose_cover(song, "https://x/tribute.jpg"))
                self.assertEqual(cover.cover_options(song)["current"], "https://x/tribute.jpg")


if __name__ == "__main__":
    unittest.main()
