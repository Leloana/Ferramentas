import json
import sys
import tempfile
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
                patch.object(separation, "SEPARATOR", "demucs"), \
                patch.object(separation.subprocess, "run", side_effect=fake_run):
            with self.assertRaises(RuntimeError) as ctx:
                separation.separate_stems(Path("/x/original.mp3"), Path("/x/out"))
        self.assertEqual(calls, ["cuda", "cpu"])
        self.assertIn("CUDA out of memory", str(ctx.exception))

    def test_auto_picks_roformer_only_when_installed(self):
        with patch.object(separation, "SEPARATOR", "auto"), \
                patch.object(separation, "_best_device", return_value="cuda"):
            with patch.object(separation, "roformer_available", return_value=True):
                self.assertEqual(separation.separator_backend(), "roformer")
            with patch.object(separation, "roformer_available", return_value=False):
                self.assertEqual(separation.separator_backend(), "demucs")
        with patch.object(separation, "SEPARATOR", "demucs"), \
                patch.object(separation, "roformer_available", return_value=True):
            self.assertEqual(separation.separator_backend(), "demucs")

    def test_auto_without_gpu_stays_on_demucs(self):
        with patch.object(separation, "SEPARATOR", "auto"), \
                patch.object(separation, "_best_device", return_value="cpu"), \
                patch.object(separation, "roformer_available", return_value=True):
            self.assertEqual(separation.separator_backend(), "demucs")

    def test_roformer_command_names_both_stems(self):
        cmd = separation.roformer_command(Path("/x/original.mp3"), Path("/x/out"), model="m.ckpt")
        self.assertEqual(cmd[0], sys.executable)
        self.assertEqual(cmd[cmd.index("-m") + 1], "m.ckpt")
        names = json.loads(cmd[cmd.index("--custom_output_names") + 1])
        self.assertEqual(names, {"Vocals": "vocals", "Instrumental": "no_vocals"})

    def test_roformer_failure_falls_back_to_demucs(self):
        seen = []

        def fake_run(cmd, env=None, **kw):
            if "demucs.separate" in cmd:
                seen.append(("demucs", cmd[cmd.index("-d") + 1]))
                out = Path(cmd[cmd.index("-o") + 1]) / separation.DEMUCS_MODEL / "original"
                out.mkdir(parents=True, exist_ok=True)
                (out / "vocals.wav").write_bytes(b"v")
                (out / "no_vocals.wav").write_bytes(b"i")
                return _Proc(0)
            # GPU e depois CPU (sem GPU visível) para o RoFormer
            seen.append(("roformer", "cpu" if env and env.get("CUDA_VISIBLE_DEVICES") == "" else "cuda"))
            return _Proc(1, "RuntimeError: CUDA out of memory")

        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(separation, "_best_device", return_value="cuda"), \
                patch.object(separation, "SEPARATOR", "roformer"), \
                patch.object(separation.subprocess, "run", side_effect=fake_run):
            vocals, no_vocals = separation.separate_stems(Path(tmp) / "original.mp3", Path(tmp) / "out")
            self.assertTrue(vocals.exists() and no_vocals.exists())
        # com GPU, o RoFormer não tenta a CPU: vai direto ao Demucs
        self.assertEqual(seen, [("roformer", "cuda"), ("demucs", "cuda")])

    def _demucs_only_run(self, seen):
        def fake_run(cmd, env=None, **kw):
            seen.append("demucs" if "demucs.separate" in cmd else "roformer")
            if "demucs.separate" in cmd:
                out = Path(cmd[cmd.index("-o") + 1]) / separation.DEMUCS_MODEL / "original"
                out.mkdir(parents=True, exist_ok=True)
                (out / "vocals.wav").write_bytes(b"v")
                (out / "no_vocals.wav").write_bytes(b"i")
            return _Proc(0)
        return fake_run

    def test_game_in_progress_uses_demucs(self):
        seen = []
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(separation, "_best_device", return_value="cuda"), \
                patch.object(separation, "SEPARATOR", "roformer"), \
                patch.object(separation.subprocess, "run", side_effect=self._demucs_only_run(seen)):
            separation.separate_stems(Path(tmp) / "original.mp3", Path(tmp) / "out", heavy_ok=lambda: False)
        self.assertEqual(seen, ["demucs"])

    def test_hung_separation_times_out_and_falls_back(self):
        seen = []
        demucs = self._demucs_only_run(seen)

        def fake_run(cmd, env=None, timeout=None, **kw):
            self.assertIsNotNone(timeout)
            if "demucs.separate" not in cmd:
                seen.append("roformer")
                raise separation.subprocess.TimeoutExpired(cmd, timeout)
            return demucs(cmd, env)

        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(separation, "_best_device", return_value="cuda"), \
                patch.object(separation, "SEPARATOR", "roformer"), \
                patch.object(separation.subprocess, "run", side_effect=fake_run):
            separation.separate_stems(Path(tmp) / "original.mp3", Path(tmp) / "out")
        self.assertEqual(seen, ["roformer", "demucs"])


    def test_cancel_kills_the_running_separator(self):
        # processo de verdade que demoraria 30 s: o cancelamento tem que matá-lo logo
        import threading
        import time

        cancel = threading.Event()
        slow = [sys.executable, "-c", "import time; time.sleep(30)"]
        threading.Timer(0.3, cancel.set).start()
        started = time.monotonic()
        with patch.object(separation, "_best_device", return_value="cuda"), \
                patch.object(separation, "SEPARATOR", "demucs"), \
                patch.object(separation, "demucs_command", return_value=slow):
            with self.assertRaises(separation.SeparationCancelled):
                separation.separate_stems(Path("/x/original.mp3"), Path("/x/out"), cancel=cancel)
        self.assertLess(time.monotonic() - started, 5)
        self.assertFalse(separation._SEPARATION_LOCK.locked())  # a próxima música não fica esperando

    def test_cancel_while_waiting_for_another_separation(self):
        import threading

        cancel = threading.Event()
        cancel.set()
        separation._SEPARATION_LOCK.acquire()
        try:
            with self.assertRaises(separation.SeparationCancelled):
                separation.separate_stems(Path("/x/original.mp3"), Path("/x/out"), cancel=cancel)
        finally:
            separation._SEPARATION_LOCK.release()


if __name__ == "__main__":
    unittest.main()
