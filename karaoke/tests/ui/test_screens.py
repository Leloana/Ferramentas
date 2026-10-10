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

    def test_add_playlist_pick_edit_and_estimate(self):
        import preview_front
        from unittest.mock import patch

        fake = {"title": "Rock 90", "truncated": False, "results": [
            {"id": f"v{i}", "url": f"https://www.youtube.com/watch?v=v{i}", "title": f"Banda {i} - Som {i}",
             "channel": "Canal", "duration": 240, "thumbnail": "", "artist_guess": f"Banda {i}",
             "title_guess": f"Som {i}", "status": "library" if i == 2 else "new"} for i in range(1, 5)]}
        for path, viewport in (("/", PHONE), ("/", DESKTOP)):  # na TV a aba Adicionar fica oculta
            with patch.object(preview_front, "youtube_playlist", lambda url: fake):
                page, errors = self.open(path, viewport)
                page.locator("#tab-btn-queue").click()
                page.locator("#btn-open-add-song").click()
                page.fill("#youtube-search-input", "https://www.youtube.com/playlist?list=PLabc")
                page.locator("#btn-youtube-search").click()
                page.wait_for_function("document.querySelector('[data-step]').getAttribute('data-step') === 'playlist'")
                self.assertEqual(page.locator(".playlist-item").count(), 4)
                # a já baixada vem desmarcada
                self.assertEqual(page.locator(".playlist-item__check:checked").count(), 3)
                self.assertEqual(page.text_content("#btn-submit-song").strip(), "Adicionar 3 à fila")
                page.wait_for_function("document.getElementById('playlist-summary').textContent.indexOf('prontas em') >= 0")
                page.locator(".playlist-item__check").first.uncheck()
                self.assertEqual(page.text_content("#btn-submit-song").strip(), "Adicionar 2 à fila")
                page.wait_for_function("document.getElementById('playlist-summary').textContent.indexOf('2 de 4') === 0")
                # sem artista da maioria, "Artista" troca o de todas as marcadas
                page.locator("#btn-playlist-artist").click()
                page.wait_for_function("document.querySelector('[data-step]').getAttribute('data-step') === 'playlist-artist'")
                page.fill("#playlist-artist-input", "Banda Única")
                page.keyboard.press("Enter")
                page.wait_for_function("document.querySelector('[data-step]').getAttribute('data-step') === 'playlist'")
                artists = page.eval_on_selector_all(".playlist-item__fields .input:nth-child(2)", "els => els.map(e => e.value)")
                self.assertEqual(artists, ["Banda 1", "Banda 2", "Banda Única", "Banda Única"])  # 1ª e 2ª desmarcadas
                page.locator("#btn-playlist-toggle-all").click()
                self.assertEqual(page.locator(".playlist-item__check:checked").count(), 4)
                page.locator(".playlist-item__title-input").nth(1).fill("")
                page.locator("#btn-submit-song").click()  # título vazio: não envia
                self.assertEqual(page.locator("#add-song-form[data-step='playlist']").count(), 1)
                self.no_horizontal_scroll(page)
                page.keyboard.press("Escape")
                page.wait_for_function("document.querySelector('[data-step]').getAttribute('data-step') === '1'")
                self.assertEqual(page.locator(".playlist-item").count(), 0)
                self.assertEqual(errors, [])

    def test_album_asks_the_artist_once_for_all_songs(self):
        import preview_front
        from unittest.mock import patch

        songs = ["Arabella", "R U Mine?", "Fireside", "Mad Sounds", "Feat"]
        fake = {"title": "AM", "truncated": False, "results": [
            {"id": f"a{i}", "url": f"https://www.youtube.com/watch?v=a{i}", "title": t, "channel": "Official Arctic Monkeys",
             "duration": 200, "thumbnail": "", "title_guess": t, "status": "new",
             "artist_guess": "Convidado" if t == "Feat" else "Official Arctic Monkeys"} for i, t in enumerate(songs)]}
        step = "document.querySelector('[data-step]').getAttribute('data-step') === '%s'"
        with patch.object(preview_front, "youtube_playlist", lambda url: fake):
            page, errors = self.open("/", PHONE)
            page.locator("#tab-btn-queue").click()
            page.locator("#btn-open-add-song").click()
            page.fill("#youtube-search-input", "https://www.youtube.com/playlist?list=OLAK5uy")
            page.locator("#btn-youtube-search").click()
            page.wait_for_function(step % "playlist-artist")
            self.assertEqual(page.input_value("#playlist-artist-input"), "Official Arctic Monkeys")
            self.assertEqual(page.text_content("#btn-submit-song").strip(), "Confirmar")
            page.fill("#playlist-artist-input", "")
            page.locator("#btn-submit-song").click()  # vazio: fica na tela
            page.wait_for_function(step % "playlist-artist")
            page.fill("#playlist-artist-input", "Arctic Monkeys")
            page.keyboard.press("Enter")
            page.wait_for_function(step % "playlist")
            artists = page.eval_on_selector_all(".playlist-item__fields .input:nth-child(2)", "els => els.map(e => e.value)")
            # a do convidado não muda
            self.assertEqual(artists, ["Arctic Monkeys"] * 4 + ["Convidado"])
            self.assertEqual(page.text_content("#btn-submit-song").strip(), "Adicionar 5 à fila")
            # "Artista" reabre a tela; Voltar volta para a lista, não para a busca
            page.locator("#btn-playlist-artist").click()
            page.wait_for_function(step % "playlist-artist")
            self.assertEqual(page.input_value("#playlist-artist-input"), "Arctic Monkeys")
            page.keyboard.press("Escape")
            page.wait_for_function(step % "playlist")
            self.assertEqual(page.text_content("#btn-submit-song").strip(), "Adicionar 5 à fila")
            self.no_horizontal_scroll(page)
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
            const gv = await import('/js/game/server-messages.js');
            gv.handleServerMessage({type: 'game_over', total_score: 80,
                player_scores: {'<img src=x onerror="window.__xss=1">': 80, 'Ana': 70},
                player_stats: {'Ana': {good: 3, ok: 1, poor: 1}}, song_id: 'x', records: {}, leaderboard: []});
        }""")
        page.wait_for_timeout(300)
        self.assertEqual(page.evaluate("window.__xss"), 0)
        # o cartão é o próprio placar: sem botão "Cartão", com os quadradinhos sem texto
        self.assertEqual(page.locator("#btn-share-card").count(), 0)
        # um cartão por cantor, da maior nota para a menor; uma fileira só de estilos
        self.assertEqual(page.locator("#game-over-share .share-card").count(), 2)
        self.assertIn("Ana", page.locator("#game-over-share .share-card").nth(1).inner_text())
        for i in range(2):
            box = page.locator("#game-over-share .share-card").nth(i).bounding_box()
            self.assertLessEqual(box["y"] + box["height"], DESKTOP["height"] + 1)
        # ouvir a apresentação só no celular de cada um
        self.assertEqual(page.locator("#game-over-modal .btn-replay").count(), 0)
        self.assertEqual(page.locator("#game-over-share .card-swatch").count(), 9)
        self.assertEqual(page.locator("#game-over-share .card-swatches").inner_text().strip(), "")
        self.assertEqual(errors, [])

    def test_every_card_style_fits_on_phone_and_tv(self):
        """Os nove estilos no fim de jogo, solo e com 4 cantores (um cartão cada): nada sai do cartão nem da tela."""
        stats = {"good": 41, "ok": 12, "poor": 13, "verses": [95] * 41 + [78] * 12 + [40] * 13}
        solo = {"type": "game_over", "total_score": 88.4, "song_id": "x", "player_scores": {"Marcelo Ferreira": 88.4},
                "player_stats": {"Marcelo Ferreira": stats}, "player_pitch": {"Marcelo Ferreira": 72},
                "records": {"Marcelo Ferreira": {"is_record": True, "times_sung": 3}}, "leaderboard": []}
        duo = dict(solo, player_scores={"Lelo": 88, "Ana": 74, "Marcelo": 61, "Bia": 50},
                   player_stats={n: stats for n in ("Lelo", "Ana", "Marcelo", "Bia")})
        for path, viewport in (("/", PHONE), ("/?tv=1", {"width": 1920, "height": 1080})):
            page, errors = self.open(path, viewport)
            for msg in (solo, duo):
                out = page.evaluate("""async (msg) => {
                    document.getElementById('current-song-title').textContent = 'Agora o meu coração é um lixeiro azul';
                    document.getElementById('current-song-artist').textContent = 'Cidade Dormitório';
                    (await import('/js/game/server-messages.js')).handleServerMessage(msg);
                    const res = [];
                    for (const sw of document.querySelectorAll('#game-over-share .card-swatch')) {
                        sw.click();
                        const cards = Array.from(document.querySelectorAll('#game-over-share .share-card'));
                        let cut = [];
                        let bottom = 0;
                        let right = 0;
                        cards.forEach((card) => {
                            const box = card.getBoundingClientRect();
                            cut = cut.concat(Array.from(card.querySelectorAll('*')).filter((n) => {
                                const r = n.getBoundingClientRect();
                                return r.height && (r.bottom > box.bottom + 1 || r.right > box.right + 1);
                            }).map((n) => n.className));
                            bottom = Math.max(bottom, box.bottom);
                            right = Math.max(right, box.right);
                        });
                        const styles = cards.map((c) => c.dataset.style);
                        const swatches = document.querySelector('#game-over-share .card-swatches').getBoundingClientRect();
                        res.push({ style: styles[0], same: styles.every((x) => x === styles[0]), count: cards.length,
                                   picked: sw.getAttribute('aria-checked'), cut, bottom, right,
                                   swatchRight: swatches.right });
                    }
                    return res;
                }""", msg)
                self.assertEqual([o["style"] for o in out], ["caderno", "neon", "vidro", "ingresso", "cupom",
                                                             "vinil", "poster", "mosaico", "letreiro"])
                for o in out:
                    with self.subTest(path=path, style=o["style"], cantores=len(msg["player_scores"])):
                        self.assertEqual(o["count"], len(msg["player_scores"]))
                        self.assertTrue(o["same"])  # trocar o estilo troca o de todos
                        self.assertLessEqual(o["swatchRight"], viewport["width"] + 1)
                        self.assertEqual(o["picked"], "true")
                        self.assertEqual(o["cut"], [])
                        if viewport is not PHONE or o["count"] == 1:
                            # no celular vários cartões ficam em coluna e o quadro rola
                            self.assertLessEqual(o["bottom"], viewport["height"] + 1)
                        self.assertLessEqual(o["right"], viewport["width"] + 1)
            # a escolha fica guardada: o próximo fim de jogo já abre no último estilo
            self.assertEqual(page.evaluate("localStorage.getItem('karaoke_card_style')"), "letreiro")
            self.assertEqual(errors, [])
            page.close()

    # Tela de cantar: cabe na janela sem rolar. Sempre: a nota de quem canta, a letra
    # legível e a próxima linha inteira no palco; nada cobre letra, título, tempo ou Pausar.
    FIT_MEASURE = r"""async ({n, teams, text}) => {
  const { state } = await import('/js/core/state.js');
  const hud = await import('/js/game/hud.js');
  const app = document.getElementById('app');
  app.setAttribute('data-state', 'singing');
  if (n > 1) {
    const names = ['Lelo', 'Aninha', 'Bia', 'Duda', 'Edu', 'Fê', 'Gabi', 'Hugo'];
    let groups;
    if (teams) groups = [0, 1].map((t) => ({ team: 'AB'[t], mics: names.slice(t * 2, t * 2 + 2) }));
    else groups = names.slice(0, n).map((m, i) => ({ team: 'ABCD'[i], mics: [m] }));
    const mics = [].concat(...groups.map((g) => g.mics));
    hud.setPlayersLayout({ mics, mode: teams ? 'teams' : '1v1', groups });
  }
  state.isSingingActive = true;
  document.querySelector('.prev-line').textContent = 'Verso anterior que já passou';
  document.querySelector('.curr-line').textContent = text;
  document.querySelector('.next-line').textContent = 'Mando notícias nessa fita, se eu não lhe faço uma visita';
  window.dispatchEvent(new Event('resize'));
  await new Promise((r) => setTimeout(r, 700));
  const R = (el) => { if (!el) return null; const x = el.getBoundingClientRect(); return { l: x.left, t: x.top, r: x.right, b: x.bottom, w: x.width, h: x.height }; };
  const vis = (el) => el && getComputedStyle(el).display !== 'none' && el.getBoundingClientRect().height > 0;
  const W = innerWidth, H = innerHeight;
  const inView = (x) => x && x.t >= -1 && x.l >= -1 && x.b <= H + 1 && x.r <= W + 1;
  const inside = (x, s) => x && s && x.t >= s.t - 1 && x.b <= s.b + 1;
  const overlap = (a, b) => a && b && a.l < b.r - 1 && a.r > b.l + 1 && a.t < b.b - 1 && a.b > b.t + 1;
  const stage = R(document.querySelector('.carousel-container'));
  const curr = R(document.querySelector('.curr-line'));
  const next = R(document.querySelector('.next-line'));
  const problems = [];
  const scroll = Math.max(document.documentElement.scrollHeight, document.body.scrollHeight) - H;
  if (scroll > 1) problems.push(`rola ${Math.round(scroll)}px`);
  const hscroll = document.documentElement.scrollWidth - W;
  if (hscroll > 1) problems.push(`rola de lado ${Math.round(hscroll)}px`);
  if (!inView(stage)) problems.push('palco fora da tela');
  if (!inside(curr, stage)) problems.push('verso atual cortado');
  if (!inside(next, stage)) problems.push('próximo cortado');
  if (!vis(document.querySelector('.next-line')) || !next || next.h < 10) problems.push('sem próximo');
  const scores = n > 1
    ? Array.from(document.querySelectorAll('.mp-score-bar[data-active="true"]')).map((b) => [b.id, R(b), vis(b)])
    : [['solo', R(document.getElementById('score-percentage-text')), vis(document.getElementById('score-percentage-text'))]];
  scores.forEach(([id, r, v]) => {
    if (!v) problems.push(`${id} escondido`);
    else if (!inView(r)) problems.push(`${id} fora da tela`);
    else if (overlap(r, stage)) problems.push(`${id} cobre a letra`);
  });
  const others = [['título', document.querySelector('.game-header')], ['tempo', document.querySelector('.song-progress-container')],
                  ['pausar', document.getElementById('btn-pause-play')]].filter(([, el]) => vis(el)).map(([k, el]) => [k, R(el)]);
  scores.forEach(([id, r, v]) => { if (v) others.forEach(([k, o]) => { if (overlap(r, o)) problems.push(`${id} cobre ${k}`); }); });
  const pause = document.getElementById('btn-pause-play');
  if (!vis(pause) || !inView(R(pause))) problems.push('sem pausar');
  const fs = parseFloat(getComputedStyle(document.querySelector('.curr-line')).fontSize);
  const nfs = parseFloat(getComputedStyle(document.querySelector('.next-line')).fontSize);
  if (fs < 22) problems.push(`letra pequena ${fs}px`);
  if (nfs < 16) problems.push(`próximo pequeno ${nfs}px`);
  return { problems, stage: stage && [Math.round(stage.t), Math.round(stage.b)], fs, nfs };
}"""

    def test_singing_screen_fits(self):
        screens = [("/", 1366, 768), ("/", 1280, 600), ("/?tv=1", 1920, 1080), ("/?tv=1", 960, 540)]
        cases = [(1, False), (2, False), (2, True), (4, False)]
        texts = ["Agora o meu coração é um lixeiro azul que ninguém quer esvaziar",
                 "Meu caro amigo, me perdoe, por favor, se eu não lhe faço uma visita, "
                 "mas como agora apareceu um portador, mando notícias nessa fita"]
        for path, w, h in screens:
            for n, teams in cases:
                for text in texts:
                    page, errors = self.open(path, {"width": w, "height": h})
                    out = page.evaluate(self.FIT_MEASURE, {"n": n, "teams": teams, "text": text})
                    with self.subTest(tela=f"{path} {w}x{h}", cantores=n, duplas=teams, verso=len(text)):
                        self.assertEqual(out["problems"], [])
                        self.assertEqual(errors, [])
                    page.close()

    def test_phone_ignores_the_other_singers_verse(self):
        """Revezar versos: o servidor só manda a nota de quem cantou; o celular de quem
        não cantava mostrava essa nota ("falha 0%") como se fosse a dele."""
        page, errors = self.open("/?role=mic&room=1234", viewport=PHONE)
        out = page.evaluate("""async () => {
            const { state } = await import('/js/core/state.js');
            state.isActiveInGame = true;
            state.mobileNickname = 'Aninha';
            const { handleMicMessage } = await import('/js/mobile/mic-messages.js');
            const last = () => document.getElementById('mobile-score-last').textContent;
            handleMicMessage({type: 'segment_result', score: 90, total_score: 90,
                player_scores: {Aninha: {score: 90, total_score: 90}}});
            const mine = last();
            handleMicMessage({type: 'segment_result', score: 0, total_score: 45,
                player_scores: {Lelo: {score: 0, total_score: 45}}});
            return [mine, last(), document.getElementById('mobile-score-total').textContent];
        }""")
        self.assertIn("90%", out[0])
        self.assertEqual(out[1], out[0])   # o verso do Lelo não muda a nota da Aninha
        self.assertEqual(out[2], "90%")
        self.assertEqual(errors, [])

    def test_two_players_bars_on_the_sides_without_settings(self):
        for n, sides in ((2, ["mp-score-bar-p3", "mp-score-bar-p4"]),
                         (4, ["mp-score-bar-p1", "mp-score-bar-p2", "mp-score-bar-p3", "mp-score-bar-p4"])):
            page, errors = self.open("/", {"width": 1366, "height": 768})
            out = page.evaluate("""async (n) => {
                const hud = await import('/js/game/hud.js');
                document.getElementById('app').setAttribute('data-state', 'singing');
                const names = ['Lelo', 'Aninha', 'Bia', 'Duda'].slice(0, n);
                hud.setPlayersLayout({mics: names, mode: '1v1',
                    groups: names.map((m, i) => ({team: 'ABCD'[i], mics: [m]}))});
                return {
                    bars: Array.from(document.querySelectorAll('.mp-score-bar[data-active="true"]')).map((b) => b.id),
                    first: document.querySelector('#mp-score-bar-' + (n === 2 ? 'p3' : 'p1') + ' .mp-player-name').textContent,
                    settings: getComputedStyle(document.getElementById('sync-controls')).display,
                };
            }""", n)
            self.assertEqual(out["bars"], sides)
            self.assertEqual(out["first"], "Lelo")
            self.assertEqual(out["settings"], "none")  # com vários cantores os ajustes saem
            self.assertEqual(errors, [])
            page.close()

    def test_phone_final_screen_is_the_singers_card(self):
        page, errors = self.open("/?role=mic&room=1234", viewport=PHONE)
        page.evaluate("""async () => {
            const { state } = await import('/js/core/state.js');
            state.isActiveInGame = true;
            state.mobileNickname = 'Ana';
            document.getElementById('app').setAttribute('data-state', 'singing');  // o celular termina cantando
            document.getElementById('mobile-active-mic-container').setAttribute('data-mic-active', 'true');
            (await import('/js/mobile/mic-final.js')).showMicGameOver({song_id: 'x', song_title: '505 - Arctic Monkeys',
                total_score: 80, player_scores: {Ana: 81.5, Lelo: 70},
                player_stats: {Ana: {good: 5, ok: 1, poor: 1, verses: [90, 90, 90, 90, 90, 75, 40]}}, recording_id: 'r1'});
        }""")
        page.wait_for_timeout(300)
        self.assertEqual(page.locator(".mic-final__share .share-card").count(), 1)
        self.assertEqual(page.locator(".mic-final__share .card-swatch").count(), 9)
        self.assertEqual(page.locator(".mic-final .btn-replay").count(), 2)  # anotar e ouvir
        page.locator(".mic-final__share .card-swatch[data-style='ingresso']").click()
        self.assertEqual(page.locator(".sc-ticket__barcode span").count(), 7)
        self.no_horizontal_scroll(page)
        self.assertEqual(errors, [])

    def _sing_long_verse(self, page):
        """Palco com um verso de rap de 148 palavras (letra gerada sem LRC)."""
        self.open_first_song(page)
        page.evaluate("""async () => {
            document.getElementById('app').setAttribute('data-state', 'singing');
            const { state } = await import('/js/core/state.js');
            const { renderLyrics } = await import('/js/game/lyrics-carousel.js');
            const words = Array.from({length: 148}, (_, i) => ({word: 'palavra' + i, expected_start: i * 0.35, expected_end: i * 0.35 + 0.3}));
            state.isFirstSegment = true;
            state.syncMode = 'word';
            renderLyrics({id: 2, sing_start: 0, sing_end: 52, language: 'pt', lyrics: words.map(w => w.word).join(' '),
                lyrics_timed: words, prev_lyrics: 'Da morte eu voltei', next_lyrics: 'Lágrimas, lua, se encheram de sangue',
                upcoming_lyrics: 'Obito'});
        }""")
        page.wait_for_timeout(200)

    def test_long_verse_shrinks_and_scrolls_inside_the_stage(self):
        for path in ("/", "/?tv=1"):
            with self.subTest(path=path):
                page, errors = self.open(path)
                self._sing_long_verse(page)
                curr = page.locator("#line-curr")
                self.assertIn("is-scroll", curr.get_attribute("class"))
                box = page.locator(".carousel-container").bounding_box()
                line = curr.bounding_box()
                self.assertLessEqual(line["height"], box["height"])  # cabe no palco, não estoura
                # a palavra cantada lá no fim do verso aparece: a janela rolou até ela
                page.evaluate("""async () => {
                    const { followWord } = await import('/js/game/long-verse.js');
                    const el = document.getElementById('word-140');
                    followWord(el.parentElement, el);
                }""")
                page.wait_for_timeout(600)
                word = page.locator("#word-140").bounding_box()
                self.assertGreaterEqual(word["y"], line["y"] - 1)
                self.assertLessEqual(word["y"] + word["height"], line["y"] + line["height"] + 1)
                self.assertEqual(errors, [])
                page.close()

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

    def test_night_queue_bar_opens_the_request_in_the_lobby(self):
        page, errors = self.open()
        page.evaluate("""async () => {
            const rq = await import('/js/lobby/requests.js');
            const songs = await fetch('/api/songs').then(r => r.json());
            const song = songs.find(s => s.is_ready);
            rq.onRequestsUpdate([{id: 'r1', song_id: song.id, title: song.title, artist: song.artist, singer: 'Ana'}]);
        }""")
        self.assertTrue(page.locator("#requests-bar").is_visible())
        page.locator(".request-chip__open").first.click()
        page.wait_for_function("document.getElementById('app').dataset.state === 'waiting'")
        self.assertEqual(errors, [])

    def test_song_cards_have_preview_and_lobby_has_cover_picker(self):
        page, errors = self.open()
        page.locator(".artist-group__header").first.click()
        self.assertTrue(page.locator(".song-card .song-card__preview-btn").first.is_visible())
        page.locator(".song-card").first.click()
        page.wait_for_function("document.getElementById('app').dataset.state === 'waiting'")
        self.assertTrue(page.locator("#btn-change-cover").is_visible())
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
