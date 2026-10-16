"""Salas pelo nome e qual conexão de tela vale (rooms.py)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from rooms import KaraokeRoom, RoomManager, display_conflict, room_key, room_name  # noqa: E402


class RoomNameTest(unittest.TestCase):
    def test_same_room_ignoring_case_and_spaces(self):
        self.assertEqual(room_key("  Casa  do Lelo "), room_key("casa do lelo"))
        self.assertEqual(room_name("  Casa  do Lelo "), "Casa do Lelo")
        self.assertEqual(len(room_name("x" * 60)), 24)


class DisplayConflictTest(unittest.TestCase):
    def setUp(self):
        self.room = KaraokeRoom("")
        self.room.display = object()
        self.room.display_device = "tv-1"
        self.room.display_seq = 200

    def test_older_socket_of_same_screen_is_stale(self):
        self.assertEqual(display_conflict(self.room, "tv-1", 100), "stale")
        self.assertIsNone(display_conflict(self.room, "tv-1", 300))

    def test_other_device_is_taken(self):
        self.assertEqual(display_conflict(self.room, "cel-9", 999), "taken")

    def test_no_screen_or_old_client_without_id_takes_over(self):
        self.assertIsNone(display_conflict(self.room, "", 0))
        self.room.display = None
        self.assertIsNone(display_conflict(self.room, "cel-9", 1))
        self.room.display = object()
        self.room.display_device = ""
        self.assertIsNone(display_conflict(self.room, "cel-9", 1))


class OpenRoomsTest(unittest.TestCase):
    def test_only_rooms_with_a_screen_by_typed_name(self):
        mgr = RoomManager()
        mgr.get_or_create_room("casa do lelo", "", [], "Casa do Lelo").display = object()
        mgr.get_or_create_room("1234", "", [], "1234")
        self.assertEqual([r["id"] for r in mgr.open_rooms()], ["Casa do Lelo"])


if __name__ == "__main__":
    unittest.main()
