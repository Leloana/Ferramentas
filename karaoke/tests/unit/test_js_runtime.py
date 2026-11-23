"""utils.youtube.js_runtime_path: acha o Deno do venv antes do PATH (yt-dlp precisa dele)."""
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from utils import youtube  # noqa: E402


class JsRuntimeTest(unittest.TestCase):
    def test_venv_scripts_first_then_path_then_none(self):
        with tempfile.TemporaryDirectory() as t:
            exe = "deno" + (".exe" if os.name == "nt" else "")
            deno = Path(t) / exe
            with patch("sysconfig.get_path", return_value=t), \
                 patch("sysconfig.get_config_var", return_value=".exe" if os.name == "nt" else ""), \
                 patch("shutil.which", return_value="/usr/bin/deno"):
                self.assertEqual(youtube.js_runtime_path(), "/usr/bin/deno")
                deno.write_bytes(b"")
                deno.chmod(deno.stat().st_mode | stat.S_IXUSR)
                self.assertEqual(youtube.js_runtime_path(), str(deno))
            with patch("sysconfig.get_path", return_value=str(Path(t) / "nada")), \
                 patch("shutil.which", return_value=None):
                self.assertIsNone(youtube.js_runtime_path())


if __name__ == "__main__":
    unittest.main()
