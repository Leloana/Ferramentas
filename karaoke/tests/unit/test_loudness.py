"""LUFS (BS.1770) e normalização do instrumental (utils/loudness.py)."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from utils import loudness, separation  # noqa: E402

FS = 48000


def _sine(amp=0.1, freq=1000.0, sec=10.0, fs=FS):
    t = np.arange(int(fs * sec)) / fs
    return amp * np.sin(2 * np.pi * freq * t)


class LoudnessTest(unittest.TestCase):
    def test_minus_20_dbfs_sine_measures_about_minus_23_lufs(self):
        # 1 kHz com pico −20 dBFS (RMS −23 dB): o K-weighting quase não mexe em 1 kHz
        self.assertAlmostEqual(loudness.integrated_loudness(_sine(), FS), -23.0, delta=1.0)
        self.assertAlmostEqual(loudness.integrated_loudness(_sine(fs=44100), 44100), -23.0, delta=1.0)
        # dois canais iguais somam energia: +3 LU
        stereo = np.stack([_sine(), _sine()])
        self.assertAlmostEqual(loudness.integrated_loudness(stereo, FS), -20.0, delta=1.0)

    def test_k_weighting_attenuates_low_frequencies(self):
        low = loudness.integrated_loudness(_sine(freq=20.0), FS)
        mid = loudness.integrated_loudness(_sine(freq=1000.0), FS)
        high = loudness.integrated_loudness(_sine(freq=8000.0), FS)
        self.assertLess(low, mid - 5)
        self.assertGreater(high, mid + 2)  # prateleira de +4 dB

    def test_silence_and_gating(self):
        self.assertEqual(loudness.integrated_loudness(np.zeros(FS * 2), FS), float("-inf"))
        # metade silêncio: o portão absoluto ignora o silêncio
        half = np.concatenate([_sine(sec=5), np.zeros(FS * 5)])
        self.assertAlmostEqual(loudness.integrated_loudness(half, FS),
                               loudness.integrated_loudness(_sine(sec=5), FS), delta=0.3)

    def test_gain_reaches_target(self):
        for signal in (_sine(), np.random.default_rng(0).normal(0, 0.3, (2, FS * 10)).clip(-1, 1)):
            out, info = loudness.normalize(signal, FS)
            self.assertAlmostEqual(loudness.integrated_loudness(out, FS), loudness.TARGET_LUFS, delta=0.5)
            self.assertAlmostEqual(info["gain_db"], loudness.TARGET_LUFS - info["lufs_before"], delta=0.01)

    def test_limiter_keeps_peaks_below_ceiling(self):
        rng = np.random.default_rng(1)
        quiet = rng.normal(0, 0.05, FS * 10)
        quiet[::FS // 2] = 0.95  # batidas isoladas perto de 0 dBFS
        out, info = loudness.normalize(quiet, FS)
        ceiling = 10 ** ((loudness.TRUE_PEAK_DB - loudness.PEAK_MARGIN_DB) / 20)
        self.assertLessEqual(np.abs(out).max(), ceiling + 1e-6)
        self.assertGreater(info["gain_db"], 5.0)
        self.assertAlmostEqual(loudness.integrated_loudness(out, FS), loudness.TARGET_LUFS, delta=0.5)

    def test_gain_is_capped_and_small_changes_skipped(self):
        _, info = loudness.normalize(_sine(amp=0.001), FS)
        self.assertEqual(info["gain_db"], loudness.MAX_GAIN_DB)
        target_amp = 0.1 * 10 ** (7.05 / 20)  # já em ~−16 LUFS
        signal = _sine(amp=target_amp)
        out, info = loudness.normalize(signal, FS)
        self.assertEqual(info["gain_db"], 0.0)
        np.testing.assert_allclose(out[0], signal, atol=1e-6)


class ExportBackingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="karaoke_loud_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _segment(self):
        from pydub import AudioSegment

        pcm = (np.stack([_sine(sec=3), _sine(sec=3)]).T.ravel() * 32767).astype("<i2")
        return AudioSegment(pcm.tobytes(), frame_rate=FS, sample_width=2, channels=2)

    def test_normalizes_and_records_meta(self):
        (self.tmp / "meta.json").write_text(json.dumps({"meta": {"title": "x"}}), encoding="utf-8")
        exported = []
        with patch("pydub.AudioSegment.export", lambda seg, dst, **kw: exported.append(seg)):
            info = separation.export_backing_mp3(self._segment(), self.tmp / "backing_track.mp3")
        self.assertAlmostEqual(info["gain_db"], 4.0, delta=0.5)  # estéreo: −20 LUFS
        meta = json.loads((self.tmp / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["loudness"], info)
        self.assertEqual(meta["meta"], {"title": "x"})
        raw = np.frombuffer(exported[0].raw_data, dtype="<i2") / 32768
        self.assertAlmostEqual(loudness.integrated_loudness(raw.reshape(-1, 2).T, FS), -16.0, delta=0.5)

    def test_failure_exports_original(self):
        exported = []
        with patch("pydub.AudioSegment.export", lambda seg, dst, **kw: exported.append(seg)), \
                patch.object(loudness, "normalize", side_effect=RuntimeError("boom")):
            seg = self._segment()
            info = separation.export_backing_mp3(seg, self.tmp / "backing_track.mp3")
        self.assertIsNone(info)
        self.assertIs(exported[0], seg)


if __name__ == "__main__":
    unittest.main()
