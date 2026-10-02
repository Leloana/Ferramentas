# tests/unit/test_mic_stream.py
"""Linha do tempo do microfone: pacote, relógio da música, âncora e janelas."""

import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from mic_stream import (  # noqa: E402
    PACKET_HEADER,
    STREAM_SR,
    MicTimeline,
    SongClock,
    build_packet,
    parse_packet,
    FAST_VERSE_TAIL_SEC,
    is_fast_verse,
    segment_window,
)
from score_engine import calculate_score  # noqa: E402


class TestPacket(unittest.TestCase):
    def test_roundtrip(self):
        samples = np.linspace(-0.5, 0.5, 1600, dtype=np.float32)
        first_index, rate, pcm = parse_packet(build_packet(3200, samples))
        self.assertEqual((first_index, rate, len(pcm)), (3200, STREAM_SR, 1600))
        np.testing.assert_allclose(pcm / 32768.0, samples, atol=1e-4)

    def test_rejects_legacy_float32_and_truncated(self):
        self.assertIsNone(parse_packet(np.full(1000, 0.1, dtype=np.float32).tobytes()))
        self.assertIsNone(parse_packet(build_packet(0, np.zeros(10))[:PACKET_HEADER.size + 3]))

    def test_rejects_non_finite_or_negative_index(self):
        # NaN viraria âncora NaN e derrubaria o loop da TV no extract()
        for bad in (float("nan"), float("inf"), -1.0):
            self.assertIsNone(parse_packet(build_packet(bad, np.zeros(10))), bad)


class TestSongClock(unittest.TestCase):
    def test_extrapolates_between_updates(self):
        clock = SongClock()
        clock.update(10.0, now=100.0)
        self.assertAlmostEqual(clock.now(now=100.08), 10.08)
        # Sem notícia da TV, não extrapola além de 0,5 s.
        self.assertAlmostEqual(clock.now(now=105.0), 10.5)

    def test_seek_starts_new_epoch(self):
        clock = SongClock()
        clock.update(10.0, now=100.0)
        clock.update(10.1, now=100.1)
        epoch = clock.epoch
        clock.update(40.0, now=100.2)
        self.assertEqual(clock.epoch, epoch + 1)

    def test_network_jitter_is_not_seek(self):
        clock = SongClock()
        clock.update(10.0, now=100.0)
        epoch = clock.epoch
        # Rajada: 400 ms sem mensagem e depois três de uma vez.
        clock.update(10.1, now=100.4)
        clock.update(10.2, now=100.41)
        clock.update(10.3, now=100.42)
        self.assertEqual(clock.epoch, epoch)

    def test_pause_stalls_and_resume_starts_new_epoch(self):
        clock = SongClock()
        clock.update(10.0, now=100.0)
        epoch = clock.epoch
        for i in range(1, 5):  # TV pausada continua mandando o mesmo tempo a cada 100 ms
            clock.update(10.0, now=100.0 + i * 0.1)
        self.assertIsNone(clock.now(now=100.45))
        clock.update(10.1, now=101.0)
        self.assertEqual(clock.epoch, epoch + 2)
        self.assertIsNotNone(clock.now(now=101.0))


class TestMicTimeline(unittest.TestCase):
    def test_anchor_filters_network_jitter(self):
        """A âncora converge para o pacote de menor atraso, não para a média."""
        true_anchor = 10.0
        delays = [0.25, 0.08, 0.30, 0.02, 0.15, 0.12]
        signal = np.sin(np.arange(1600 * len(delays)) * 0.01) * 0.5
        timeline = MicTimeline()
        for k, delay in enumerate(delays):
            chunk = (signal[k * 1600:(k + 1) * 1600] * 32767).astype(np.int16)
            arrival = true_anchor + (k + 1) * 1600 / STREAM_SR + delay
            timeline.add(k * 1600, chunk, arrival, epoch=1)
        self.assertAlmostEqual(timeline.anchors[1], true_anchor + min(delays), places=6)

        audio, covered = timeline.extract(10.5, 10.6)
        self.assertTrue(covered.all())
        shift = int(round(min(delays) * STREAM_SR))
        start = int(0.5 * STREAM_SR) - shift
        np.testing.assert_allclose(audio, signal[start:start + len(audio)], atol=1e-3)

    def test_counter_stall_starts_new_anchor(self):
        """Tela do iPhone bloqueou 2 s: o contador parou, a música não."""
        timeline = MicTimeline()
        for k in range(3):  # [10.0, 10.3) com atraso de rede de 20 ms
            timeline.add(k * 1600, np.full(1600, 1000, dtype=np.int16), 10.0 + (k + 1) * 0.1 + 0.02, epoch=1)
        # Volta com o contador em 4800, mas a música já está em 12.3 s.
        timeline.add(4800, np.full(1600, -1000, dtype=np.int16), 12.4 + 0.02, epoch=1)
        audio, covered = timeline.extract(12.32, 12.42)
        self.assertTrue(covered.all())
        np.testing.assert_allclose(audio, -1000 / 32768.0)
        # E não foi parar logo depois do trecho antigo, onde a âncora velha o poria.
        _, covered_old = timeline.extract(10.32, 10.42)
        self.assertFalse(covered_old.any())

    def test_counter_restart_from_zero_starts_new_anchor(self):
        """AudioContext recriado: o índice volta a 0 no meio da música."""
        timeline = MicTimeline()
        timeline.add(0, np.full(1600, 1000, dtype=np.int16), song_time=5.1, epoch=1)
        timeline.add(0, np.full(1600, -1000, dtype=np.int16), song_time=20.1, epoch=1)
        audio, covered = timeline.extract(20.0, 20.1)
        self.assertTrue(covered.all())
        np.testing.assert_allclose(audio, -1000 / 32768.0)

    def test_network_jitter_keeps_single_anchor(self):
        timeline = MicTimeline()
        for k, delay in enumerate([0.02, 0.35, 0.10, 0.45, 0.03]):
            timeline.add(k * 1600, np.ones(1600, dtype=np.int16), 10.0 + (k + 1) * 0.1 + delay, epoch=1)
        self.assertEqual(len(timeline.anchors), 1)

    def test_in_flight_packet_after_stop_uses_current_anchor(self):
        clock = SongClock()
        clock.update(10.0, now=100.0)
        timeline = MicTimeline()
        timeline.add(0, np.full(1600, 1000, dtype=np.int16), clock.now(now=100.0), clock.epoch)
        for i in range(1, 4):  # música parada: o currentTime da TV não anda mais
            clock.update(10.0, now=100.0 + i * 0.1)
        self.assertIsNone(clock.now(now=100.35))
        self.assertTrue(clock.just_stopped(now=100.35))
        self.assertFalse(clock.just_stopped(now=101.0))
        timeline.add_in_flight(1600, np.full(1600, -1000, dtype=np.int16))
        audio, covered = timeline.extract(10.0, 10.1)
        self.assertTrue(covered.all())
        np.testing.assert_allclose(audio, -1000 / 32768.0)

    def test_lateness_follows_slow_network_and_decays(self):
        timeline = MicTimeline()
        delays = [0.05, 0.9, 0.06] + [0.05] * 60
        seen = []
        for k, delay in enumerate(delays):
            timeline.add(k * 1600, np.ones(1600, dtype=np.int16), 10.0 + (k + 1) * 0.1 + delay, epoch=1)
            seen.append(timeline.lateness)
        # A rajada de 0,9 s não virou âncora própria: foi medida como atraso.
        self.assertEqual(len(set(timeline.anchors.values())), 1)
        self.assertAlmostEqual(max(seen), 0.85, places=6)
        self.assertLess(seen[-1], 0.3)

    def test_room_grace_has_floor_and_ceiling(self):
        from types import SimpleNamespace
        from ws.room import _late_packet_grace

        def grace(*lateness):
            room = SimpleNamespace(mic_timelines={i: SimpleNamespace(lateness=v) for i, v in enumerate(lateness)})
            return _late_packet_grace(room)

        self.assertEqual(grace(), 0.6)
        self.assertEqual(grace(0.05), 0.6)
        self.assertAlmostEqual(grace(0.05, 0.8), 0.9)
        self.assertEqual(grace(5.0), 2.0)

    def test_stop_freezes_clock_and_accepts_in_flight(self):
        clock = SongClock()
        clock.update(10.0, now=100.0)
        clock.stop()
        self.assertIsNone(clock.now(now=100.2))
        self.assertTrue(clock.just_stopped(now=105.0))

    def test_gaps_are_silence_and_not_covered(self):
        timeline = MicTimeline()
        timeline.add(0, np.full(1600, 1000, dtype=np.int16), song_time=5.1, epoch=1)
        audio, covered = timeline.extract(4.5, 5.5)
        self.assertEqual(int(covered.sum()), 1600)
        self.assertEqual(float(np.abs(audio[~covered]).max()), 0.0)

    def test_newer_epoch_overwrites_same_instant(self):
        timeline = MicTimeline()
        timeline.add(0, np.full(1600, 1000, dtype=np.int16), song_time=5.1, epoch=1)
        # Seek para trás e cantou de novo o mesmo trecho (outro índice, outra época).
        timeline.add(48000, np.full(1600, -2000, dtype=np.int16), song_time=5.1, epoch=2)
        audio, covered = timeline.extract(5.0, 5.1)
        self.assertTrue(covered.all())
        np.testing.assert_allclose(audio, -2000 / 32768.0)

    def test_prune_and_drop(self):
        timeline = MicTimeline()
        for k in range(5):  # 5 pacotes de 100 ms cobrindo [10.0, 10.5)
            timeline.add(k * 1600, np.ones(1600, dtype=np.int16), song_time=10.0 + (k + 1) * 0.1, epoch=1)
        timeline.prune_before(10.25)
        self.assertEqual(len(timeline.chunks), 3)
        timeline.drop_from(10.35)
        self.assertEqual(len(timeline.chunks), 2)


class TestSegmentWindow(unittest.TestCase):
    SEGMENTS = [
        {"sing_start": 1.0, "sing_end": 5.0},
        {"sing_start": 5.2, "sing_end": 9.0},   # verso colado no anterior
        {"sing_start": 15.0, "sing_end": 20.0},  # depois de uma pausa longa
    ]

    def test_windows_are_disjoint_and_ordered(self):
        windows = [segment_window(self.SEGMENTS, i, 1.5, 0.5) for i in range(3)]
        self.assertEqual(windows[0], (0.0, 5.2))
        self.assertEqual(windows[1], (5.2, 9.5))
        self.assertEqual(windows[2], (13.5, 20.5))
        for (_, end), (start, _) in zip(windows, windows[1:]):
            self.assertLessEqual(end, start)

    def test_fast_verse_gets_a_tail_over_the_next_one(self):
        # rap: quem canta vem atrás da letra; o fim do verso emendado caía na janela seguinte
        def verse(start, end, text):
            words = text.split()
            step = (end - start) / len(words)
            return {"sing_start": start, "sing_end": end, "lyrics": text,
                    "lyrics_timed": [{"word": w, "expected_start": i * step} for i, w in enumerate(words)]}

        rap = [verse(10.0, 11.5, "Maldição do ódio que gera chacina"),          # 28 letras / 1,5 s
               verse(11.5, 13.0, "Já sente o genjutsu olhando a retina")]
        self.assertTrue(is_fast_verse(rap[0]))
        (_, end0), (start1, _) = segment_window(rap, 0, 1.5, 0.5), segment_window(rap, 1, 1.5, 0.5)
        self.assertAlmostEqual(end0, 11.5 + FAST_VERSE_TAIL_SEC)
        self.assertEqual(start1, 11.5)  # o próximo continua começando onde começa

        slow = [verse(10.0, 14.0, "This is the place"), verse(14.0, 18.0, "Where we used to go")]
        self.assertFalse(is_fast_verse(slow[0]))
        self.assertEqual(segment_window(slow, 0, 1.5, 0.5), (8.5, 14.0))
        # voz de apoio não conta como palavra cantada
        self.assertFalse(is_fast_verse(verse(10.0, 11.0, "(Monster monster monster)")))


class TestTimingReference(unittest.TestCase):
    def test_perfect_singing_scores_100_after_window_shift(self):
        """Regressão do teto de 85: o tempo do Whisper conta do início da janela, não do verso."""
        from segment_scoring import shift_words as _shift_words

        expected = [{"word": w, "expected_start": t} for w, t in
                    [("eu", 0.05), ("vou", 0.6), ("cantar", 1.2), ("agora", 2.0)]]
        segments = [{"sing_start": 10.0, "sing_end": 14.0}, {"sing_start": 20.0, "sing_end": 23.0}]
        t0, _ = segment_window(segments, 1, 1.5, 0.5)
        offset = t0 - segments[1]["sing_start"]
        # Canto perfeito: cada palavra no tempo esperado, medido pelo Whisper a partir de t0.
        whisper_words = [{"word": e["word"], "start": e["expected_start"] - offset,
                          "end": e["expected_start"] - offset + 0.3} for e in expected]

        unshifted = calculate_score(expected, whisper_words, language="pt")["score"]
        shifted = calculate_score(expected, _shift_words(whisper_words, offset), language="pt")["score"]
        self.assertEqual(unshifted, 85.0)
        self.assertEqual(shifted, 100.0)


if __name__ == "__main__":
    unittest.main()
