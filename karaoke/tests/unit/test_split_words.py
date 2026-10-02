"""Palavra partida entre linhas da letra ("My un-" / "cle Bill"): vira uma linha só."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from utils import lyrics_fetcher as lf  # noqa: E402
from utils.text import join_split_words, normalize_lyrics_text  # noqa: E402


class SplitWordsTest(unittest.TestCase):
    def test_plain_lyrics_join_the_split_word(self):
        text = "The headshrinkers\nThey want everything\nMy un-\ncle Bill\nMy Belisha beacon"
        self.assertEqual(normalize_lyrics_text(text).splitlines(),
                         ["The headshrinkers", "They want everything", "My uncle Bill", "My Belisha beacon"])

    def test_lrc_keeps_the_time_of_the_first_line(self):
        lrc = "[01:02.10] They want everything\n[01:04.50] My un-\n[01:05.90] cle Bill\n[01:07.00] My Belisha beacon"
        self.assertEqual(join_split_words(lrc).splitlines(),
                         ["[01:02.10] They want everything", "[01:04.50] My uncle Bill", "[01:07.00] My Belisha beacon"])

    def test_dash_capital_and_end_mark_are_not_joined(self):
        cases = [
            "Vai -\nfica aqui",               # travessão solto, não é palavra partida
            "Toilet-\nTrained and dumb",      # a seguinte começa com maiúscula: outro verso
            "[00:10.00] My un-\n[00:12.00]",  # marca vazia de fim do verso do LRC
            "2-\nfoi",                         # número, não sílaba
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(join_split_words(text), text)

    def test_fetched_lyrics_come_joined(self):
        out = lf._normalized({"plainLyrics": "My un-\r\ncle Bill", "syncedLyrics": "[00:01.00] My un-\n[00:02.00] cle Bill"})
        self.assertEqual(out["plainLyrics"], "My uncle Bill")
        self.assertEqual(out["syncedLyrics"], "[00:01.00] My uncle Bill")

    def test_idempotent(self):
        text = "My un-\ncle Bill"
        self.assertEqual(normalize_lyrics_text(normalize_lyrics_text(text)), "My uncle Bill")


if __name__ == "__main__":
    unittest.main()
