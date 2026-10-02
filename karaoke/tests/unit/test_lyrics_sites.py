"""Letra de sites quando o LRCLIB não tem (letras.com.br, Genius): leitura da página e ordem."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from utils import lyrics_fetcher as lf  # noqa: E402

GENIUS_PAGE = """<html><body><div class="header">1 Contributor</div>
<div data-lyrics-container="true" class="Lyrics__Container">
  <div data-exclude-from-selection="true">Rap do Obito Lyrics<span>[Letra]</span></div>
  [Refrão]<br>Da morte eu voltei<br/>E desse mundo cansei<br><a href="/x"><span>A máscara esconde</span></a> a revolta de um ninja
</div>
<div class="ad">compre já</div>
<div data-lyrics-container="true">Obito<br>Obito Uchiha</div>
</body></html>"""

LETRAS_BR_PAGE = """<html><print-component :lyrics="`Player tauz
Como eu era tolo uma criança inocente
Acreditava que podia ter um mundo diferente`"></print-component></html>"""


class LyricsSitesTest(unittest.TestCase):
    def test_genius_page_keeps_only_the_lyrics(self):
        text = lf.clean_web_lyrics(lf.genius_lyrics_from_html(GENIUS_PAGE))
        self.assertEqual(text.splitlines(), [
            "Da morte eu voltei", "E desse mundo cansei", "A máscara esconde a revolta de um ninja",
            "", "Obito", "Obito Uchiha"])  # bloco novo = estrofe nova

    def test_letras_br_reads_the_print_component_and_tries_the_title_without_parens(self):
        seen = []

        def fake_page(url):
            seen.append(url)
            return LETRAS_BR_PAGE if url.endswith("/player-tauz/rap-do-obito") else None

        with patch.object(lf, "_get_page", side_effect=fake_page):
            res = lf.fetch_lyrics_letras_br("Player Tauz", "Rap do Obito (Naruto)")
        self.assertEqual(seen[-1], "https://www.letras.com.br/player-tauz/rap-do-obito")
        self.assertTrue(res["plainLyrics"].startswith("Player tauz\nComo eu era tolo"))
        self.assertIsNone(res["syncedLyrics"])

    def test_sites_come_after_lrclib_in_order_and_genius_needs_the_token(self):
        calls = []
        with patch.object(lf, "search_lyrics_lrclib", return_value=None), \
                patch.object(lf, "fetch_lyrics_lrclib", return_value=None), \
                patch.object(lf, "fetch_lyrics_ovh", side_effect=lambda a, t: calls.append("ovh")), \
                patch.object(lf, "fetch_lyrics_letras_br", side_effect=lambda a, t: calls.append("letras")), \
                patch.dict(lf.os.environ, {"KARAOKE_GENIUS_TOKEN": ""}):
            self.assertIsNone(lf.fetch_lyrics("X", "Y"))
        self.assertEqual(calls, ["ovh", "letras"])  # Genius sem token nem tenta a rede

    def test_title_variants(self):
        self.assertEqual(lf.title_variants("Rap do Obito (Naruto)"), ["Rap do Obito (Naruto)", "Rap do Obito"])
        self.assertEqual(lf.title_variants("Creep"), ["Creep"])


if __name__ == "__main__":
    unittest.main()
