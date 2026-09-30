"""Testes das telas no navegador (Playwright) sobre o preview (tools/preview_front.py).

Sobe o preview numa porta livre e percorre os fluxos principais em tela de
PC, celular (390 px) e TV (?tv=1). Sem Playwright instalado, os testes são
pulados:

    pip install playwright && python -m playwright install chromium
    python -m pytest tests/ui
"""
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "server"))

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

PHONE = {"width": 390, "height": 780}
DESKTOP = {"width": 1400, "height": 860}


@unittest.skipUnless(sync_playwright, "Playwright não instalado")
class ScreensTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import preview_front

        preview_front.seed_sample_players()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), preview_front.Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()

    def open(self, path="/", viewport=DESKTOP):
        page = self.browser.new_page(viewport=viewport)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(self.base + path)
        page.wait_for_selector("#app")
        page.wait_for_timeout(400)
        self.addCleanup(page.close)
        return page, errors

    def no_horizontal_scroll(self, page):
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        self.assertLessEqual(overflow, 1, "rolagem horizontal na tela")

    def open_first_song(self, page):
        page.locator(".artist-group__header").first.click()
        page.locator(".song-card").first.click()
        page.wait_for_function("document.getElementById('app').dataset.state === 'waiting'")

    # --- fluxos ---

    def test_song_list_lobby_and_back(self):
        page, errors = self.open()
        # só "Músicas" e "Adicionar" (as abas do celular-microfone ficam ocultas)
        self.assertEqual(page.locator(".tab-btn:visible").count(), 2)
        self.open_first_song(page)
        self.assertTrue(page.locator("#lobby-seats .seat").count() >= 1)
        page.locator("#btn-back").click()
        page.wait_for_function("document.getElementById('app').dataset.state === 'idle'")
        self.assertEqual(errors, [])

    def test_add_song_steps_back_before_closing(self):
        page, errors = self.open()
        page.locator("#tab-btn-queue").click()
        page.locator("#btn-open-add-song").click()
        page.fill("#youtube-search-input", "https://www.youtube.com/watch?v=abc123")
        page.locator("#btn-youtube-search").click()
        page.wait_for_function("document.querySelector('[data-step]').getAttribute('data-step') === '2'")
        page.keyboard.press("Escape")
        page.wait_for_function("document.querySelector('[data-step]').getAttribute('data-step') === '1'")
        self.assertTrue(page.locator("#add-song-modal[data-open]").count() == 1)
        page.keyboard.press("Escape")
        page.wait_for_function("!document.getElementById('add-song-modal').hasAttribute('data-open')")
        page.wait_for_timeout(300)
        self.assertTrue(page.url.startswith(self.base))  # "voltar" não saiu do app
        self.assertEqual(errors, [])

    def test_players_ranking_and_profile(self):
        page, errors = self.open()
        page.locator("#btn-open-players").click()
        page.wait_for_selector(".player-row")
        self.assertGreaterEqual(page.locator(".player-row").count(), 2)
        page.locator(".player-row").first.click()
        page.wait_for_selector(".profile-stats")
        page.locator("#btn-players-back").click()
        page.wait_for_selector(".player-row")
        self.assertEqual(errors, [])

    def test_status_panel(self):
        page, errors = self.open()
        page.locator(".header-status").click()
        page.wait_for_selector(".status-block")
        self.assertIn("Sala 1234", page.locator("#status-view").inner_text())
        self.assertEqual(errors, [])

    def test_game_over_escapes_names_and_share_card_fits(self):
        page, errors = self.open()
        page.evaluate("""async () => {
            window.__xss = 0;
            const gv = await import('/js/game-view.js');
            gv.handleServerMessage({type: 'game_over', total_score: 80,
                player_scores: {'<img src=x onerror="window.__xss=1">': 80, 'Ana': 70},
                player_stats: {'Ana': {good: 3, ok: 1, poor: 1}}, song_id: 'x', records: {}, leaderboard: []});
        }""")
        page.wait_for_timeout(300)
        self.assertEqual(page.evaluate("window.__xss"), 0)
        page.locator("#btn-share-card").click()
        box = page.locator(".share-card").bounding_box()
        self.assertLessEqual(box["y"] + box["height"], DESKTOP["height"] + 1)
        page.mouse.click(5, 5)
        self.assertEqual(page.locator("#share-card-overlay").count(), 0)
        self.assertEqual(errors, [])

    def test_phone_layouts_have_no_horizontal_scroll(self):
        page, errors = self.open(viewport=PHONE)
        self.no_horizontal_scroll(page)
        self.open_first_song(page)
        self.no_horizontal_scroll(page)
        # no celular a seta de voltar fica na barra do app
        self.assertTrue(page.locator("#btn-header-back").is_visible())
        self.assertEqual(errors, [])

    def test_mic_role_tabs_and_states(self):
        page, errors = self.open("/?role=mic&room=1234", viewport=PHONE)
        for state in ("registering", "waiting", "singing"):
            page.evaluate(f"document.getElementById('app').setAttribute('data-state', '{state}')")
            self.no_horizontal_scroll(page)
        page.locator(".mic-tabbar [data-tab='queue']").click()
        self.assertTrue(page.locator("#mic-queue-panel").is_visible())
        page.locator(".mic-tabbar [data-tab='profile']").click()
        self.assertTrue(page.locator("#mic-profile-panel").is_visible())
        self.assertFalse(page.locator(".mic-body").is_visible())
        # sem WebSocket no preview: só erros de página contam
        self.assertEqual(errors, [])

    def test_tv_remote_moves_focus(self):
        page, errors = self.open("/?tv=1")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowDown")
        focused = page.evaluate("document.activeElement && document.activeElement.tagName")
        self.assertIn(focused, ("BUTTON", "INPUT", "DIV", "A"))
        self.assertNotEqual(page.evaluate("document.activeElement === document.body"), True)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
