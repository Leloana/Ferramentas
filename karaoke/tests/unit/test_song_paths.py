import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from utils.song_paths import safe_song_dir  # noqa: E402


class SafeSongDirTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_accepts_plain_slug(self):
        self.assertEqual(safe_song_dir(self.root, "evidencias-chitaozinho"),
                         (self.root / "evidencias-chitaozinho").resolve())

    def test_rejects_traversal(self):
        for bad in ["..", ".", "", "../x", "a/b", "a\\b", "../../etc", "x\x00"]:
            self.assertIsNone(safe_song_dir(self.root, bad), bad)


if __name__ == "__main__":
    unittest.main()
