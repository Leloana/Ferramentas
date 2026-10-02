# tests/unit/test_stt_engine.py
"""Unit tests for stt_engine.py focusing on confidence threshold calculation."""

import unittest
import sys
from pathlib import Path

# Add project root and server to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from stt_engine import _get_word_threshold

class TestSttEngine(unittest.TestCase):

    def test_get_word_threshold(self):
        # Adaptive thresholds depending on no_speech_prob:
        # no_speech_prob > 0.60 -> 0.50
        self.assertEqual(_get_word_threshold(0.70), 0.50)
        # no_speech_prob > 0.40 -> 0.30
        self.assertEqual(_get_word_threshold(0.50), 0.30)
        # no_speech_prob > 0.25 -> 0.18
        self.assertEqual(_get_word_threshold(0.30), 0.18)
        # no_speech_prob > 0.15 -> 0.18
        self.assertEqual(_get_word_threshold(0.20), 0.18)
        # clean audio (no_speech_prob <= 0.15) -> 0.08
        self.assertEqual(_get_word_threshold(0.10), 0.08)

def _fake_segment(words):
    from types import SimpleNamespace
    ws = [SimpleNamespace(word=f" {w}", start=i * 0.4, end=i * 0.4 + 0.3, probability=p) for i, (w, p) in enumerate(words)]
    return SimpleNamespace(text=" ".join(w for w, _ in words), no_speech_prob=0.1, words=ws)


class _FakeWhisper:
    """Com a letra como dica "ouve" a letra; sem dica, ouve o que foi cantado."""

    def __init__(self, prompted, unprompted):
        self.prompted, self.unprompted, self.calls = prompted, unprompted, []

    def transcribe(self, audio, initial_prompt=None, **kwargs):
        self.calls.append(initial_prompt)
        return iter([_fake_segment(self.prompted if initial_prompt else self.unprompted)]), None


class TestPromptHallucination(unittest.TestCase):
    """Sessão de 2026-09-29: cantarolando "não não não" num verso de "Maldita Geni", o Whisper
    devolveu a letra da dica (confiança média 0,09) e o verso tirou 100."""

    def _engine(self, fake):
        from stt_engine import STTEngine
        engine = STTEngine.__new__(STTEngine)  # sem carregar o modelo de verdade
        engine.model = fake
        return engine

    def test_low_confidence_prompted_lyrics_are_rechecked_without_prompt(self):
        import numpy as np
        fake = _FakeWhisper(prompted=[("Maldita", 0.175), ("Geni", 0.002)],
                            unprompted=[("Não", 0.9), ("não", 0.88), ("não", 0.87)])
        text, words = self._engine(fake).transcribe(
            np.full(16000, 0.1, dtype=np.float32), language="pt",
            initial_prompt="Maldita Geni", expected_words=["Maldita", "Geni"])
        self.assertEqual(fake.calls, ["Maldita Geni", None])
        self.assertEqual([w["word"] for w in words], ["Não", "não", "não"])

    def test_confident_prompted_transcription_is_kept(self):
        import numpy as np
        fake = _FakeWhisper(prompted=[("Um", 0.95), ("dia", 0.97), ("surgiu", 0.9)],
                            unprompted=[("Um", 0.95), ("dia", 0.97), ("surge", 0.9)])
        _, words = self._engine(fake).transcribe(
            np.full(16000, 0.1, dtype=np.float32), language="pt",
            initial_prompt="Um dia surgiu", expected_words=["Um", "dia", "surgiu"])
        self.assertEqual(fake.calls, ["Um dia surgiu"])
        self.assertEqual([w["word"] for w in words], ["Um", "dia", "surgiu"])


class TestPhantomPhrases(unittest.TestCase):
    """Trecho sem voz em música japonesa (aoi-koi, 2026-10-01): o Whisper inventou
    "ご視聴ありがとうございました" ("obrigado por assistir") e o verso pontuou lixo."""

    def _run(self, heard):
        import numpy as np
        from stt_engine import STTEngine
        engine = STTEngine.__new__(STTEngine)
        engine.model = _FakeWhisper(prompted=heard, unprompted=heard)
        return engine.transcribe(np.full(16000, 0.1, dtype=np.float32), language="ja")

    def test_known_phantom_phrases_are_dropped(self):
        for phrase in ("ご視聴ありがとうございました", "ご清聴ありがとうございました",
                       "チャンネル登録よろしくお願いします", "goshichoo arigatoo gozaimashita",
                       "Obrigado por assistir", "Inscreva-se no canal"):
            with self.subTest(phrase=phrase):
                _, words = self._run([(phrase, 0.9)])
                self.assertEqual(words, [])

    def test_real_lyrics_with_arigatou_are_kept(self):
        _, words = self._run([("ありがとう", 0.9), ("さよなら", 0.9)])
        self.assertEqual([w["word"] for w in words], ["ありがとう", "さよなら"])


class TestCudaFallback(unittest.TestCase):
    def test_cublas_error_reloads_on_cpu_and_retries(self):
        import numpy as np
        from stt_engine import STTEngine

        class Broken:
            def transcribe(self, *a, **k):
                raise RuntimeError("cublas64_12.dll not found")

        cpu = _FakeWhisper(prompted=[("oi", 0.9)], unprompted=[("oi", 0.9)])
        engine = STTEngine.__new__(STTEngine)
        engine.model = Broken()
        engine.compute_override = "int8_float16"

        def fake_load(device):
            self.assertEqual(device, "cpu")
            engine.model = cpu
        engine._load = fake_load

        _, words = engine.transcribe(np.full(16000, 0.1, dtype=np.float32), language="pt",
                                     initial_prompt="oi", expected_words=["oi"])
        self.assertEqual([w["word"] for w in words], ["oi"])
        self.assertIsNone(engine.compute_override)


if __name__ == "__main__":
    unittest.main()
