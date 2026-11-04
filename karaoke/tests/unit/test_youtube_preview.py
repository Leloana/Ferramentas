"""Prévia da busca do YouTube (server/utils/youtube.py + GET /api/youtube-preview)."""
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

VIDEO = "abcDEF12345"


class TestFetchPreview(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        for name, value in (("PREVIEW_DIR", self.dir), ("PREVIEW_RETRY_DELAY_SEC", 0)):
            p = patch.object(youtube, name, value)
            p.start()
            self.addCleanup(p.stop)

    def _run(self, outcomes, video=VIDEO):
        """`outcomes`: por tentativa, True grava o m4a, False levanta erro."""
        calls = []

        def download(urls):
            ok = outcomes[len(calls)]
            calls.append(urls)
            if not ok:
                (self.dir / f"{video}.m4a.part").write_bytes(b"x" * 5000)
                raise RuntimeError("HTTP Error 403: Forbidden")
            (self.dir / f"{video}.m4a").write_bytes(b"x" * 5000)

        ydl = MagicMock()
        ydl.download.side_effect = download
        with patch("yt_dlp.YoutubeDL") as cls:
            cls.return_value.__enter__.return_value = ydl
            path = asyncio.run(youtube.fetch_youtube_preview(video))
        return path, len(calls)

    def test_downloads_the_audio(self):
        path, calls = self._run([True])
        self.assertEqual((path.name, calls), (f"{VIDEO}.m4a", 1))

    def test_second_request_uses_the_cache(self):
        self._run([True])
        path, calls = self._run([])
        self.assertEqual((path.name, calls), (f"{VIDEO}.m4a", 0))

    def test_half_download_is_not_served(self):
        self.assertEqual(self._run([False] * youtube.PREVIEW_ATTEMPTS), (None, youtube.PREVIEW_ATTEMPTS))

    def test_a_refused_request_is_tried_again(self):
        path, calls = self._run([False, True])
        self.assertEqual((path.name, calls), (f"{VIDEO}.m4a", 2))

    def test_old_previews_are_pruned(self):
        with patch.object(youtube, "PREVIEW_KEEP", 2):
            for i in range(4):
                self._run([True], video=f"video{i:06d}")
        self.assertEqual(len(list(self.dir.iterdir())), 2)

    def test_video_id_validation(self):
        self.assertTrue(youtube.is_video_id(VIDEO))
        for bad in ("", "short", "../../etc/pa", "abcDEF12345x", "abc DEF1234"):
            self.assertFalse(youtube.is_video_id(bad), bad)


class TestPreviewRoute(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routes import upload

        app = FastAPI()
        app.include_router(upload.router)
        self.client = TestClient(app)
        self.upload = upload

    def test_invalid_id_is_refused_without_downloading(self):
        with patch.object(self.upload, "fetch_youtube_preview") as fetch:
            resp = self.client.get("/api/youtube-preview/..%2F..%2Fsecret")
        self.assertIn(resp.status_code, (400, 404))
        fetch.assert_not_called()

    def test_serves_audio_with_range(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        audio = Path(tmp.name) / f"{VIDEO}.m4a"
        audio.write_bytes(bytes(range(256)) * 20)

        async def fake(video_id):
            return audio

        with patch.object(self.upload, "fetch_youtube_preview", fake):
            resp = self.client.get(f"/api/youtube-preview/{VIDEO}", headers={"Range": "bytes=0-99"})
        self.assertEqual(resp.status_code, 206)
        self.assertEqual(resp.headers["content-type"], "audio/mp4")
        self.assertEqual(len(resp.content), 100)

    def test_failed_download_is_502(self):
        async def fake(video_id):
            return None

        with patch.object(self.upload, "fetch_youtube_preview", fake):
            resp = self.client.get(f"/api/youtube-preview/{VIDEO}")
        self.assertEqual(resp.status_code, 502)


if __name__ == "__main__":
    unittest.main()
