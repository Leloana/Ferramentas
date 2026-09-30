import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tests" / "unit"))
from calibration import label_mae, rescore_session  # noqa: E402
from recorder import GameRecording, save_labels  # noqa: E402
from test_recorder import SEGMENTS, WINDOWS, _timeline_with_voice  # noqa: E402


class ExportRecordingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        rec = GameRecording(self.tmp / "rec", "song-x", "Song X", SEGMENTS, "timing", WINDOWS)
        sung = [{"word": "hello", "start": 0.2, "end": 0.7, "probability": 0.9},
                {"word": "world", "start": 1.0, "end": 1.7, "probability": 0.9}]
        rec.add_segment_result("Ana", 0, (0.0, 3.5), 0.05, "hello world", sung, {"score": 100.0},
                               prompted_words=sung, unprompted_words=None, used="prompted")
        rec.add_segment_result("Ana", 1, (3.5, 6.5), 0.05, "", [], {"score": 0.0})
        self.session = rec.save({"Ana": _timeline_with_voice()}, complete=True, whisper_model="x")
        save_labels(self.session, "Ana", {"1": "certo", "2": "cantarolei"})

    def run_tool(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "tools" / "export_recordings.py"), *args],
                              capture_output=True, text=True, cwd=ROOT)

    def test_exports_labeled_player_with_baseline(self):
        out = self.tmp / "fixtures"
        proc = self.run_tool(str(self.tmp / "rec"), "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        files = list(out.glob("*.json"))
        self.assertEqual(len(files), 1)
        data = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(data["labels"], {"1": "certo", "2": "cantarolei"})
        self.assertEqual(data["baseline"]["labeled_verses"], 2)
        self.assertIn("prompted_words", data["results"][0])
        # o mesmo cálculo do teste de regressão bate com a linha de base gravada
        scores, _ = rescore_session(data)
        self.assertEqual(label_mae(scores, data["labels"])[0], data["baseline"]["mae"])

    def test_zip_backup_includes_audio(self):
        dest = self.tmp / "backup.zip"
        proc = self.run_tool(str(self.tmp / "rec"), "--zip", str(dest))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        names = zipfile.ZipFile(dest).namelist()
        self.assertTrue(any(n.endswith(".wav") for n in names))
        self.assertTrue(any(n.endswith("session.json") for n in names))


if __name__ == "__main__":
    unittest.main()
