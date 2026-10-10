"""Download do YouTube (server/utils/youtube.py): tenta de novo quando o YouTube recusa."""
import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from utils import youtube  # noqa: E402


class TestDownloadRetry(unittest.TestCase):
    def _run(self, outcomes):
        """`outcomes`: por tentativa, True grava o mp3, False levanta erro."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        target = Path(tmp.name) / "original.mp3"
        calls = []

        def download(urls):
            ok = outcomes[len(calls)]
            calls.append(urls)
            if not ok:
                raise RuntimeError("HTTP Error 403: Forbidden")
            target.write_bytes(b"x" * 5000)

        ydl = MagicMock()
        ydl.download.side_effect = download
        with patch("yt_dlp.YoutubeDL") as cls, patch.object(youtube, "DOWNLOAD_RETRY_DELAY_SEC", 0):
            cls.return_value.__enter__.return_value = ydl
            ok = asyncio.run(youtube.download_youtube_audio("https://youtu.be/x", target))
        return ok, len(calls)

    def test_a_refused_request_is_tried_again(self):
        self.assertEqual(self._run([False, True]), (True, 2))

    def test_gives_up_after_the_last_attempt(self):
        self.assertEqual(self._run([False] * youtube.DOWNLOAD_ATTEMPTS), (False, youtube.DOWNLOAD_ATTEMPTS))

    def test_first_success_does_not_download_again(self):
        self.assertEqual(self._run([True]), (True, 1))


if __name__ == "__main__":
    unittest.main()
