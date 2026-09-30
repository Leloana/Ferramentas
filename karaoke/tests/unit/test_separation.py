import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from utils import separation  # noqa: E402


class _Proc:
    def __init__(self, code, stderr=""):
        self.returncode = code
        self.stderr = stderr


class SeparationTest(unittest.TestCase):
    def test_command_uses_server_python_and_model(self):
        cmd = separation.demucs_command(Path("/x/original.mp3"), Path("/x/out"), "cuda", model="htdemucs_ft")
        self.assertEqual(cmd[:3], [sys.executable, "-m", "demucs.separate"])
        self.assertIn("htdemucs_ft", cmd)
        self.assertEqual(cmd[cmd.index("--two-stems") + 1], "vocals")

    def test_gpu_failure_retries_on_cpu_and_reports_stderr(self):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd[cmd.index("-d") + 1])
            return _Proc(1, "Traceback\nRuntimeError: CUDA out of memory")

        with patch.object(separation, "_best_device", return_value="cuda"), \
                patch.object(separation.subprocess, "run", side_effect=fake_run):
            with self.assertRaises(RuntimeError) as ctx:
                separation.separate_stems(Path("/x/original.mp3"), Path("/x/out"))
        self.assertEqual(calls, ["cuda", "cpu"])
        self.assertIn("CUDA out of memory", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
