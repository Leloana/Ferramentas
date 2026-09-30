import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
import pitch  # noqa: E402
from pitch import (PITCH_SR, extract_reference, hz_to_midi, load_or_build_reference,  # noqa: E402
                   verse_pitch_score, yin_f0)

SR = PITCH_SR
# melodia: (midi, duração s) — A3, C4, E4, D4, B3, G3 ...
MELODY = [(57, 0.4), (60, 0.3), (64, 0.5), (62, 0.3), (59, 0.4), (55, 0.3)] * 3


def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def tone(freq, dur, amp=0.3, harmonics=False):
    t = np.arange(int(dur * SR)) / SR
    y = np.sin(2 * np.pi * freq * t)
    if harmonics:
        y = y + 0.5 * np.sin(2 * np.pi * 2 * freq * t) + 0.25 * np.sin(2 * np.pi * 3 * freq * t)
        y /= 1.75
    return (amp * y).astype(np.float32)


def melody(shift=0.0, delay=0.0):
    parts = [np.zeros(int(delay * SR), np.float32)] if delay else []
    parts += [tone(midi_hz(m + shift), d) for m, d in MELODY]
    return np.concatenate(parts)


class YinTest(unittest.TestCase):
    def _median_f0(self, audio):
        f0, conf = yin_f0(audio)
        v = f0[f0 > 0]
        self.assertGreater(len(v), 0.8 * len(f0))
        return float(np.median(v))

    def test_clean_sine(self):
        self.assertAlmostEqual(self._median_f0(tone(220, 1.0)), 220.0, delta=1.0)

    def test_harmonics_and_noise(self):
        rng = np.random.default_rng(0)
        a = tone(220, 1.0, harmonics=True) + 0.02 * rng.standard_normal(SR).astype(np.float32)
        self.assertAlmostEqual(self._median_f0(a), 220.0, delta=1.0)

    def test_silence_and_empty(self):
        f0, conf = yin_f0(np.zeros(SR, np.float32))
        self.assertTrue((f0 == 0).all())
        f0, conf = yin_f0(np.zeros(0, np.float32))
        self.assertEqual(len(f0), 0)

    def test_hz_to_midi(self):
        m = hz_to_midi(np.array([440.0, 0.0, 220.0]))
        self.assertAlmostEqual(m[0], 69.0)
        self.assertTrue(np.isnan(m[1]))
        self.assertAlmostEqual(m[2], 57.0)

    def test_speed_4_minutes(self):
        rng = np.random.default_rng(1)
        n = 240 * SR
        a = (0.1 * rng.standard_normal(n)).astype(np.float32)
        a[: n // 2] += tone(220, 120)
        t0 = time.perf_counter()
        f0, _ = yin_f0(a)
        dt = time.perf_counter() - t0
        print(f"\nyin_f0 em 240 s de áudio: {dt:.2f} s")
        self.assertEqual(len(f0), 1 + n // 160)
        if dt > 15:
            self.skipTest(f"máquina lenta: {dt:.1f} s")


class VerseScoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.song = melody()
        cls.ref = extract_reference(cls.song)
        cls.start = 1.0
        cls.end = 5.0

    def window(self, audio):
        return audio[int(self.start * SR):int(self.end * SR)]

    def score(self, mic, **kw):
        return verse_pitch_score(mic, self.start, self.ref, **kw)

    def test_reference_json_friendly(self):
        self.assertEqual(self.ref["hop_sec"], 0.01)
        self.assertTrue(all(v is None or isinstance(v, float) for v in self.ref["midi"]))
        self.assertEqual(json.loads(json.dumps(self.ref)), self.ref)

    def test_same_melody(self):
        r = self.score(self.window(self.song))
        self.assertGreater(r["score"], 90)
        self.assertGreater(r["coverage"], 0.9)

    def test_octave_up(self):
        self.assertGreater(self.score(self.window(melody(shift=12)))["score"], 90)

    def test_three_semitones_off(self):
        # nota sustentada: com melodia, a folga de tempo acharia vizinhas a 3 semitons
        ref = extract_reference(tone(midi_hz(57), 4.0))
        r = verse_pitch_score(tone(midi_hz(60), 2.0), 1.0, ref)
        self.assertLess(r["score"], 30)

    def test_transpose(self):
        # música transposta +3: cantar 3 semitons acima da referência é o certo
        mic = self.window(melody(shift=3))
        self.assertGreater(self.score(mic, transpose_semitones=3)["score"], 90)

    def test_timing_slack(self):
        self.assertGreater(self.score(self.window(melody(delay=0.15)))["score"], 85)

    def test_silent_mic(self):
        self.assertIsNone(self.score(np.zeros(4 * SR, np.float32)))

    def test_robustness(self):
        self.assertIsNone(self.score(np.zeros(0, np.float32)))
        nan = self.window(self.song).copy()
        nan[::7] = np.nan
        self.assertIsNotNone(self.score(nan))
        # janela além do fim da referência
        self.assertIsNone(verse_pitch_score(self.window(self.song), 999.0, self.ref))
        self.assertIsNone(verse_pitch_score(self.window(self.song), 0.0, {"hop_sec": 0.01, "midi": []}))
        self.assertIsNone(verse_pitch_score(self.window(self.song), 0.0, None))


class LoadOrBuildTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.calls = 0

    def loader(self, path):
        self.calls += 1
        self.assertEqual(path.name, "vocal.mp3")
        return tone(220, 1.0)

    def test_no_vocal(self):
        self.assertIsNone(load_or_build_reference(self.dir, self.loader))
        self.assertEqual(self.calls, 0)

    def test_builds_writes_and_rereads(self):
        (self.dir / "vocal.mp3").write_bytes(b"fake")
        ref = load_or_build_reference(self.dir, self.loader)
        self.assertEqual(self.calls, 1)
        on_disk = json.loads((self.dir / "pitch.json").read_text())
        self.assertEqual(on_disk, ref)
        self.assertEqual([p.name for p in self.dir.iterdir() if p.suffix == ".tmp"], [])
        again = load_or_build_reference(self.dir, self.loader)
        self.assertEqual(self.calls, 1)
        self.assertEqual(again, ref)

    def test_loader_error_returns_none(self):
        (self.dir / "vocal.mp3").write_bytes(b"fake")

        def bad(_):
            raise RuntimeError("decode")
        with self.assertLogs(pitch.logger, "ERROR"):
            self.assertIsNone(load_or_build_reference(self.dir, bad))
        self.assertFalse((self.dir / "pitch.json").exists())


if __name__ == "__main__":
    unittest.main()
