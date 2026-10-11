"""Álbum da música (agrupamento da lista): escolha entre resultados do iTunes, sem rede."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from utils import album  # noqa: E402


def r(track, collection, year, artist="The Strokes", number=1, count=11, collection_artist=""):
    return {"artistName": artist, "trackName": track, "collectionName": collection,
            "releaseDate": f"{year}-01-01T08:00:00Z", "trackNumber": number, "trackCount": count,
            "collectionArtistName": collection_artist}


class PickAlbumTest(unittest.TestCase):
    def test_original_album_beats_singles_live_and_lullabies(self):
        found = album.pick_album("The Strokes", "Last Nite", [
            r("Last Nite (Rough Trade Version - The Modern Age B-Side)", "The Singles, Vol. 1", 2023, count=2),
            r("Last Nite", "The Singles, Vol. 1", 2001, count=2),
            r("Last Nite", "Is This It", 2001, number=7),
            r("Last Nite", "Lullaby Versions of The Strokes", 2016, artist="Twinkle Twinkle Little Rock Star"),
            r("Last Nite (Live)", "Live at Somewhere", 2005),
        ])
        self.assertEqual(found, {"name": "Is This It", "year": 2001, "track": 7, "kind": "album", "source": "itunes"})

    def test_deluxe_edition_is_the_same_album(self):
        found = album.pick_album("Linkin Park", "In the End", [
            r("In the End", "Hybrid Theory (Deluxe Edition)", 2000, artist="LINKIN PARK", number=8, count=16),
            r("In the End", "Hybrid Theory", 2000, artist="LINKIN PARK", number=8, count=12),
        ])
        self.assertEqual((found["name"], found["track"]), ("Hybrid Theory", 8))

    def test_earliest_album_beats_later_compilation(self):
        found = album.pick_album("Chico Buarque", "Meu Caro Amigo", [
            r("Meu Caro Amigo", "O Sambista", 2000, artist="Chico Buarque", number=7, count=14),
            r("Meu Caro Amigo", "Meus Caros Amigos", 1976, artist="Chico Buarque", number=10, count=10),
        ])
        self.assertEqual((found["name"], found["year"]), ("Meus Caros Amigos", 1976))

    def test_only_singles_and_nothing(self):
        single = album.pick_album("Mhrap", "Tipo Madara", [
            r("Tipo Madara", "Tipo Madara - Single", 2021, artist="Mhrap", count=1)])
        self.assertEqual(single["kind"], "single")
        self.assertIsNone(single["name"])
        self.assertEqual(album.pick_album("X", "Y", [])["kind"], "unknown")

    def test_studio_album_beats_older_ep_and_compilation(self):
        found = album.pick_album("Radiohead", "You", [
            r("You (Drill Version)", "Drill EP", 1992, artist="Radiohead", count=4),
            r("You", "Drill EP", 1992, artist="Radiohead", count=4),
            r("You", "Pablo Honey", 1993, artist="Radiohead", count=12),
        ])
        self.assertEqual(found["name"], "Pablo Honey")
        found = album.pick_album("Chico Buarque", "Vai Passar", [
            r("Vai Passar", "Maxximum - Chico Buarque", 1987, artist="Chico Buarque", count=20),
            r("Vai Passar", "Chico Buarque", 1984, artist="Chico Buarque", count=10),
        ])
        self.assertEqual(found["name"], "Chico Buarque")  # disco homônimo não é coletânea

    def test_apostrophes_and_remaster_tags(self):
        found = album.pick_album("Oasis", "Don’t Look Back In Anger", [
            r("Don't Look Back in Anger (Remastered)", "(What's The Story) Morning Glory? [Deluxe Remastered Edition]",
              1995, artist="Oasis", number=4, count=12)])
        self.assertEqual(found["name"], "(What's The Story) Morning Glory?")
        found = album.pick_album("Weezer", "Undone (The Sweater Song) (2024 Remaster)", [
            r("Undone - The Sweater Song", "Weezer", 1994, artist="Weezer", number=5, count=10)])
        self.assertEqual((found["name"], found["track"]), ("Weezer", 5))  # "-" × "(...)"

    def test_ep_name(self):
        self.assertEqual(album.clean_album_name("The Modern Age - EP"), "The Modern Age (EP)")
        self.assertEqual(album.clean_album_name("AM (Live EP Bonus Edition)"), "AM")


class FillAlbumTest(unittest.TestCase):
    def test_keeps_hand_edited_album_and_saves_new_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            song = Path(tmp)
            meta = {"meta": {"title": "Reptilia", "artist": "The Strokes"}}
            (song / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
            found = {"name": "Room On Fire", "year": 2003, "track": 2, "kind": "album", "source": "itunes"}
            with patch.object(album, "lookup_album", return_value=found) as lookup:
                self.assertEqual(album.fill_album(song), found)
                self.assertEqual(album.fill_album(song), found)  # já tem: não busca de novo
            self.assertEqual(lookup.call_count, 1)
            saved = json.loads((song / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["album"]["name"], "Room On Fire")
            self.assertEqual(saved["meta"]["title"], "Reptilia")

    def test_network_down_leaves_meta_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            song = Path(tmp)
            (song / "meta.json").write_text(json.dumps({"meta": {"title": "a", "artist": "b"}}), encoding="utf-8")
            with patch.object(album, "lookup_album", return_value=None):
                self.assertIsNone(album.fill_album(song))
            self.assertNotIn("album", json.loads((song / "meta.json").read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
