import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
from ws.room import _all_audio_arrived  # noqa: E402


class _Timeline:
    def __init__(self, end):
        self._end = end

    def end_time(self):
        return self._end


class AllAudioArrivedTest(unittest.TestCase):
    def test_waits_for_the_slowest_phone(self):
        room = SimpleNamespace(active_players=["Ana", "Bia"],
                               mic_timelines={"Ana": _Timeline(12.0), "Bia": _Timeline(9.5)})
        self.assertFalse(_all_audio_arrived(room, 10.0))
        room.mic_timelines["Bia"] = _Timeline(10.2)
        self.assertTrue(_all_audio_arrived(room, 10.0))

    def test_phone_without_audio_keeps_the_grace(self):
        room = SimpleNamespace(active_players=["Ana", "Bia"], mic_timelines={"Ana": _Timeline(12.0)})
        self.assertFalse(_all_audio_arrived(room, 10.0))


if __name__ == "__main__":
    unittest.main()
