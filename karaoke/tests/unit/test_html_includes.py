"""Montagem do index.html a partir dos parciais (server/utils/html_includes.py)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from utils.html_includes import IncludeError, render_includes, render_page  # noqa: E402

CLIENT_DIR = Path(__file__).resolve().parents[2] / "client"


class HtmlIncludesTest(unittest.TestCase):
    def test_real_index_has_no_pending_includes(self):
        html = render_page(CLIENT_DIR)
        self.assertNotIn("<!-- @include", html)
        self.assertIn('id="app"', html)

    def test_nested_includes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "partials").mkdir()
            (root / "partials" / "a.html").write_text("A<!-- @include partials/b.html -->", encoding="utf-8")
            (root / "partials" / "b.html").write_text("B", encoding="utf-8")
            self.assertEqual(render_includes("<!-- @include partials/a.html -->", root), "AB")

    def test_rejects_paths_outside_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(IncludeError):
                render_includes("<!-- @include ../etc/passwd -->", Path(tmp))

    def test_include_cycle_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "loop.html").write_text("<!-- @include loop.html -->", encoding="utf-8")
            with self.assertRaises(IncludeError):
                render_includes("<!-- @include loop.html -->", root)


if __name__ == "__main__":
    unittest.main()
