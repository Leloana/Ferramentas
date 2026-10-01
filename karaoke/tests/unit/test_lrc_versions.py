"""Letra de outra versão do áudio: LRCLIB pela duração, encaixe global e estrutura.

Áudio sintético: tom onde há "voz", silêncio no resto. A transcrição é montada a
partir da letra com os tempos de cada versão, com os erros típicos do Whisper
em canto (palavra trocada, palavra curta casando com outra).
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from utils import lyrics_fetcher  # noqa: E402
from utils.lrc_fit import fit_lrc, remap_lrc  # noqa: E402
from utils.lrc_pro import parse_synced_lrc  # noqa: E402
from utils.lrc_structure import build_plan, plan_to_lrc  # noqa: E402
from utils.lrc_sync import sync_lrc, uncovered_voice  # noqa: E402

SR = 16000

LINES = [
    "hear the sound of the falling rain",
    "coming down like an armageddon flame",
    "the shame the ones who died without a name",
    "hear the dogs howling out of key",
    "to a hymn called faith and misery",
    "and bleed the company lost the war today",
    "i beg to dream and differ from the hollow lies",
    "this is the dawning of the rest of our lives",
    "hear the drum pounding out of time",
    "another protester has crossed the line",
    "to find the money on the other side",
    "can i get another amen",
]
CHORUS = [6, 7]          # linhas do refrão (índices)
LINE_SEC, GAP_SEC = 3.0, 1.0


def timeline(order, t0=4.0):
    """[(linha, início)] cantando as linhas na ordem dada."""
    out, t = [], t0
    for i in order:
        out.append((i, t))
        t += LINE_SEC + GAP_SEC
    return out


def audio_for(tl, tail=6.0):
    end = tl[-1][1] + LINE_SEC + tail
    audio = np.zeros(int(end * SR), dtype=np.float32)
    tone = 0.3 * np.sin(2 * np.pi * 220 * np.arange(int(LINE_SEC * SR)) / SR).astype(np.float32)
    for _, start in tl:
        lo = int(start * SR)
        audio[lo:lo + tone.size] = tone
    return audio


def words_for(tl, swaps=None):
    """Transcrição: cada palavra da linha espalhada pela linha. `swaps`: troca palavras."""
    swaps = swaps or {}
    out = []
    for line, start in tl:
        ws = LINES[line].split()
        step = LINE_SEC / len(ws)
        for k, w in enumerate(ws):
            out.append({"word": swaps.get(w, w), "start": start + k * step, "end": start + (k + 0.8) * step})
    return out


def lrc_for(tl):
    return "\n".join(f"[{int(t // 60):02d}:{t % 60:05.2f}]{LINES[i]}" for i, t in tl)


STUDIO = timeline(range(len(LINES)))


class TestPickVersion(unittest.TestCase):
    CANDS = [
        {"id": 1, "trackName": "Holiday", "artistName": "Green Day", "duration": 233.0,
         "plainLyrics": "a", "syncedLyrics": "[00:01.00]a"},
        {"id": 2, "trackName": "Holiday (Live)", "artistName": "Green Day", "duration": 301.0,
         "plainLyrics": "a", "syncedLyrics": "[00:01.00]a"},
        {"id": 3, "trackName": "Holiday", "artistName": "Madonna", "duration": 300.0,
         "plainLyrics": "b", "syncedLyrics": "[00:01.00]b"},
        {"id": 4, "trackName": "Holiday", "artistName": "Green Day", "duration": 299.0,
         "plainLyrics": "", "syncedLyrics": None, "instrumental": True},
    ]

    def test_closest_duration_of_the_same_song_wins(self):
        self.assertEqual(lyrics_fetcher.pick_lrclib_candidate(self.CANDS, "Green Day", "Holiday", 232.9)["id"], 1)
        # 300 s: a ao vivo, não a da Madonna nem a instrumental
        self.assertEqual(lyrics_fetcher.pick_lrclib_candidate(self.CANDS, "Green Day", "Holiday", 300.0)["id"], 2)

    def test_far_version_keeps_text_but_drops_the_sync(self):
        best = lyrics_fetcher.pick_lrclib_candidate(self.CANDS, "Green Day", "Holiday", 150.0)
        self.assertEqual(best["id"], 1)
        self.assertIsNone(best["syncedLyrics"])

    def test_fetch_with_duration_uses_search(self):
        with patch.object(lyrics_fetcher, "_get_json", return_value=self.CANDS) as get:
            res = lyrics_fetcher.fetch_lyrics("Green Day", "Holiday", duration=301.5)
        self.assertIn("/api/search", get.call_args[0][0])
        self.assertEqual(res["duration"], 301.0)
        self.assertEqual(res["syncedLyrics"], "[00:01.00]a")

    def test_get_fallback_drops_sync_of_another_version(self):
        single = {"plainLyrics": "a", "syncedLyrics": "[00:01.00]a", "duration": 233.0}
        with patch.object(lyrics_fetcher, "_get_json", side_effect=[[], single]):
            res = lyrics_fetcher.fetch_lyrics("Green Day", "Holiday", duration=400.0)
        self.assertEqual(res["plainLyrics"], "a")
        self.assertIsNone(res["syncedLyrics"])

    def test_without_duration_search_rescues_a_missed_exact_get(self):
        # "、" no título do YouTube × ", " no LRCLIB: o /api/get exato dá 404
        cands = [
            {"id": 7, "trackName": "青い, 濃い, 橙色の日", "artistName": "Mass Of The Fermenting Dregs",
             "duration": 282.0, "plainLyrics": "待ちぼうけさ", "syncedLyrics": None},
            {"id": 8, "trackName": "青い, 濃い, 橙色の日", "artistName": "MASS OF THE FERMENTING DREGS",
             "duration": 282.0, "plainLyrics": "待ちぼうけさ", "syncedLyrics": "[00:10.00]待ちぼうけさ"},
        ]
        with patch.object(lyrics_fetcher, "_get_json", side_effect=[Exception("HTTP Error 404"), cands]) as get:
            res = lyrics_fetcher.fetch_lyrics("MASS OF THE FERMENTING DREGS", "青い、濃い、橙色の日")
        self.assertIn("/api/search", get.call_args[0][0])
        self.assertEqual(res["syncedLyrics"], "[00:10.00]待ちぼうけさ")


class TestGlobalFit(unittest.TestCase):
    def test_longer_intro_and_slower_tempo_are_fitted(self):
        lrc = lrc_for(STUDIO)
        version = [(i, 1.04 * t + 7.0) for i, t in STUDIO]
        fitted, fit = fit_lrc(lrc, audio_for(version))
        self.assertTrue(fit.applied)
        self.assertAlmostEqual(fit.scale, 1.04, delta=0.006)
        self.assertAlmostEqual(fit.offset, 7.0, delta=0.3)
        starts = [ln["start"] for ln in parse_synced_lrc(fitted)]
        for got, (_, want) in zip(starts, version):
            self.assertAlmostEqual(got, want, delta=0.35)

    def test_same_version_is_left_alone(self):
        lrc = lrc_for(STUDIO)
        fitted, fit = fit_lrc(lrc, audio_for(STUDIO))
        self.assertFalse(fit.applied)
        self.assertEqual(fitted, lrc)

    def test_small_shift_below_the_gain_is_ignored(self):
        # 0,1 s de diferença melhora o F1 em ~0,03: abaixo do ganho mínimo, o LRC fica
        lrc = lrc_for(STUDIO)
        fitted, fit = fit_lrc(lrc, audio_for([(i, t + 0.1) for i, t in STUDIO]))
        self.assertFalse(fit.applied)
        self.assertEqual(fitted, lrc)

    def test_remap_clamps_stamps_pushed_below_zero_like_the_parser(self):
        self.assertEqual(remap_lrc("[offset:-1000]\n[00:00.20]x", lambda t: t + 2.0), "[00:02.00]x")

    def test_remap_folds_the_offset_tag(self):
        out = remap_lrc("[ti:x]\n[offset:+500]\n[00:01.00][00:02.00]a\n[00:03.00]", lambda t: t * 2)
        self.assertEqual(out, "[ti:x]\n[00:03.00][00:05.00]a\n[00:07.00]")


class TestStructure(unittest.TestCase):
    def plan(self, tl, swaps=None):
        audio = audio_for(tl)
        from utils.lrc_fit import HOP_SEC, vocal_activity

        return build_plan(LINES, words_for(tl, swaps), "en", len(audio) / SR, vocal_activity(audio), HOP_SEC)

    def test_extra_chorus_is_repeated(self):
        order = list(range(9)) + CHORUS + list(range(9, len(LINES)))
        plan = self.plan(timeline(order))
        self.assertEqual([a.line for a in plan.anchors], order)
        self.assertEqual(sorted(a.line for a in plan.anchors if a.kind == "repeat"), CHORUS)
        self.assertEqual(plan.dropped, [])

    def test_cut_verse_is_dropped(self):
        order = [i for i in range(len(LINES)) if i not in (3, 4, 5)]
        plan = self.plan(timeline(order))
        self.assertEqual([a.line for a in plan.anchors], order)
        self.assertEqual(plan.dropped, [3, 4, 5])

    def test_misheard_words_still_anchor_in_time(self):
        tl = timeline(range(len(LINES)))
        plan = self.plan(tl, {"dream": "trim", "differ": "devour", "hollow": "all"})
        got = {a.line: a.start for a in plan.anchors}
        for line, start in tl:
            self.assertAlmostEqual(got[line], start, delta=0.6)

    def test_short_words_alone_do_not_anchor_a_line(self):
        # "(three four)" sem voz própria não pode roubar "the ... our" do refrão
        lines = LINES + ["three four"]
        tl = timeline(range(len(LINES)))
        audio = audio_for(tl)
        from utils.lrc_fit import HOP_SEC, vocal_activity

        plan = build_plan(lines, words_for(tl), "en", len(audio) / SR, vocal_activity(audio), HOP_SEC)
        self.assertNotIn(len(LINES), [a.line for a in plan.anchors if a.kind == "match"])

    def test_count_in_before_an_extra_chorus_does_not_steal_it(self):
        # Holiday: "(Three, four)" vem logo antes do refrão a mais, e "four"~"our",
        # "three"~"the" casavam com as palavras do refrão extra
        count_in = len(LINES)
        lines = LINES + ["three four"]
        lyric_order = list(range(9)) + [count_in] + list(range(9, len(LINES)))
        sung = timeline(list(range(9)) + CHORUS + list(range(9, len(LINES))))
        audio = audio_for(sung)
        from utils.lrc_fit import HOP_SEC, vocal_activity

        plan = build_plan([lines[i] for i in lyric_order], words_for(sung), "en", len(audio) / SR,
                          vocal_activity(audio), HOP_SEC)
        matched = [lyric_order[a.line] for a in plan.anchors if a.kind == "match"]
        self.assertNotIn(count_in, matched)
        self.assertEqual(sorted(lyric_order[a.line] for a in plan.anchors if a.kind == "repeat"), CHORUS)

    def test_unanchored_line_lands_on_the_voice_not_on_the_pause(self):
        # linha 5 toda mal ouvida, depois de 12 s de instrumental: vai para onde há voz
        tl = timeline(range(5)) + [(i, t + 12.0) for i, t in timeline(range(5, len(LINES)), t0=24.0)]
        swaps = {w: "xq" for w in LINES[5].split()}
        plan = self.plan(tl, swaps)
        line5 = next(a for a in plan.anchors if a.line == 5)
        self.assertEqual(line5.kind, "interp")
        self.assertAlmostEqual(line5.start, dict(tl)[5], delta=0.5)

    def test_plan_lrc_has_one_line_per_anchor(self):
        order = list(range(9)) + CHORUS + list(range(9, len(LINES)))
        plan = self.plan(timeline(order))
        texts = [ln["text"] for ln in parse_synced_lrc(plan_to_lrc(plan, LINES))]
        self.assertEqual(texts, [LINES[i] for i in order])


class TestSync(unittest.TestCase):
    def test_same_structure_keeps_the_lrc(self):
        version = [(i, t + 5.0) for i, t in STUDIO]
        res = sync_lrc(lrc_for(STUDIO), None, audio_for(version), "en", words=words_for(version))
        self.assertEqual(res.method, "lrc+encaixe")
        starts = [ln["start"] for ln in parse_synced_lrc(res.lrc_text)]
        self.assertAlmostEqual(starts[0], version[0][1], delta=0.3)

    def test_other_structure_uses_the_plan(self):
        order = [i for i in range(len(LINES)) if i not in (3, 4, 5)]
        version = timeline(order)
        res = sync_lrc(lrc_for(STUDIO), None, audio_for(version), "en", words=words_for(version))
        self.assertEqual(res.method, "estrutura")
        texts = [ln["text"] for ln in parse_synced_lrc(res.lrc_text)]
        self.assertEqual(texts, [LINES[i] for i in order])
        self.assertIsNotNone(res.alternative)

    def test_plain_lyrics_alone_get_timed(self):
        res = sync_lrc(None, "\n".join(LINES), audio_for(STUDIO), "en", words=words_for(STUDIO))
        self.assertEqual(res.method, "estrutura")
        self.assertEqual(len(parse_synced_lrc(res.lrc_text)), len(LINES))

    def test_symbol_only_lines_do_not_count_against_the_plan(self):
        lines = []
        for line in LINES:
            lines += [line, "♪"]
        res = sync_lrc(None, "\n".join(lines), audio_for(STUDIO), "en", words=words_for(STUDIO))
        self.assertEqual(res.method, "estrutura")

    def test_no_transcription_means_only_the_fit(self):
        res = sync_lrc(lrc_for(STUDIO), None, audio_for(STUDIO), "en", transcribe=None)
        self.assertEqual(res.method, "lrc")
        self.assertIsNone(res.plan)

    def test_uncovered_voice(self):
        act = np.array([1, 1, 1, 1, 0, 0, 1, 1], dtype=bool)
        segs = [{"sing_start": 0.0, "sing_end": 0.2}]
        self.assertAlmostEqual(uncovered_voice(segs, act, 0.05), 2 / 6)


if __name__ == "__main__":
    unittest.main()
