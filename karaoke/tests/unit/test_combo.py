import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
from combo import combo_runs  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from ws.room import _combo_for  # noqa: E402


class ComboRunsTest(unittest.TestCase):
    def test_counts_good_verses_in_a_row(self):
        self.assertEqual(combo_runs({0: 90, 1: 85, 2: 99}), (3, 3))

    def test_a_weak_verse_breaks_it_but_keeps_the_best(self):
        self.assertEqual(combo_runs({0: 90, 1: 92, 2: 84.9, 3: 88}), (1, 2))

    def test_verse_order_not_arrival_order(self):
        # o Whisper devolveu o verso 2 antes do 1
        self.assertEqual(combo_runs({0: 90, 2: 95, 1: 40}), (1, 1))

    def test_verse_still_in_whisper_breaks_the_run(self):
        # vocalize do verso 2 (sem Whisper) chegou antes do verso 1
        self.assertEqual(combo_runs({0: 90, 2: 95}, verses={0, 1, 2}), (1, 1))
        self.assertEqual(combo_runs({0: 90, 1: 88, 2: 95}, verses={0, 1, 2}), (3, 3))

    def test_verse_without_audio_breaks_the_run(self):
        # verso 1 fechado sem áudio deste celular: nunca terá nota
        self.assertEqual(combo_runs({0: 90, 2: 95, 3: 99}, verses={0, 1, 2, 3}), (2, 2))

    def test_closed_verses_after_the_last_score_do_not_count_yet(self):
        # verso 3 fechado e ainda no Whisper: a sequência até o 2 continua
        self.assertEqual(combo_runs({0: 90, 1: 92, 2: 95}, verses={0, 1, 2, 3}), (3, 3))

    def test_turns_only_count_own_verses(self):
        # revezando, o cantor tem só os versos 0, 2 e 4
        self.assertEqual(combo_runs({0: 90, 2: 91, 4: 99}), (3, 3))

    def test_empty(self):
        self.assertEqual(combo_runs({}), (0, 0))



class ComboForTest(unittest.TestCase):
    def _room(self, scores, closed, turn_order=None, players=("Ana", "Bia")):
        segs = [{"lyrics": "a"}] * 6
        return SimpleNamespace(active_players=list(players), segments=segs, turn_order=turn_order,
                               transcribed_segments=set(closed), player_segment_scores=scores)

    def test_verse_still_in_whisper_breaks_the_run(self):
        room = self._room({"Ana": {0: 90, 2: 95}}, closed={0, 1, 2})
        self.assertEqual(_combo_for(room, "Ana"), (1, 1))

    def test_turns_skip_the_other_singers_verses(self):
        # revezando, Ana canta 0, 2 e 4: o verso 1 (de Bia) não quebra o combo dela
        room = self._room({"Ana": {0: 90, 2: 95, 4: 99}, "Bia": {1: 20}}, closed={0, 1, 2, 3, 4},
                          turn_order=[["Ana"], ["Bia"]])
        self.assertEqual(_combo_for(room, "Ana"), (3, 3))
        self.assertEqual(_combo_for(room, "Bia"), (0, 0))

    def test_solo_without_lineup(self):
        room = self._room({"Solo": {0: 90, 1: 91}}, closed={0, 1}, players=())
        self.assertEqual(_combo_for(room, "Solo"), (2, 2))

    def test_singer_without_scores(self):
        self.assertEqual(_combo_for(self._room({}, closed={0}), "Ana"), (0, 0))

if __name__ == "__main__":
    unittest.main()
