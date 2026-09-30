"""As duas passadas do Whisper (com e sem a letra como dica) chegam ao gravador,
e a repontuação das partidas gravadas aplica o mesmo portão do ao vivo."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "server"))
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "unit"))

from recorder import SESSION_FILE, GameRecording  # noqa: E402
from stt_engine import STTEngine, pick_transcription  # noqa: E402
from test_recorded_sessions import FIXTURES, rescore_session, result_words  # noqa: E402

AUDIO = np.full(16000, 0.1, dtype=np.float32)


def _segment(words):
    ws = [SimpleNamespace(word=f" {w}", start=i * 0.4, end=i * 0.4 + 0.3, probability=p)
          for i, (w, p) in enumerate(words)]
    return SimpleNamespace(text=" ".join(w for w, _ in words), no_speech_prob=0.1, words=ws)


class _FakeWhisper:
    def __init__(self, prompted, unprompted):
        self.prompted, self.unprompted = prompted, unprompted

    def transcribe(self, audio, initial_prompt=None, **kwargs):
        return iter([_segment(self.prompted if initial_prompt else self.unprompted)]), None


def _engine(prompted, unprompted):
    engine = STTEngine.__new__(STTEngine)  # sem carregar o modelo
    engine.model = _FakeWhisper(prompted, unprompted)
    return engine


class TestTranscribeDetails(unittest.TestCase):
    def test_distrusted_prompt_exposes_both_runs(self):
        details = {}
        text, words = _engine([("Maldita", 0.175), ("Geni", 0.002)], [("Não", 0.9), ("não", 0.88)]).transcribe(
            AUDIO, language="pt", initial_prompt="Maldita Geni", expected_words=["Maldita", "Geni"], details=details)
        self.assertEqual(details["used"], "unprompted")
        self.assertEqual([w["word"] for w in details["prompted_words"]], ["Maldita", "Geni"])
        self.assertEqual([w["word"] for w in details["unprompted_words"]], ["Não", "não"])
        self.assertEqual(words, details["unprompted_words"])
        self.assertEqual(text, "Não não")

    def test_trusted_prompt_skips_second_run(self):
        details = {}
        text, words = _engine([("Um", 0.95), ("dia", 0.97)], [("x", 0.9)]).transcribe(
            AUDIO, language="pt", initial_prompt="Um dia", expected_words=["Um", "dia"], details=details)
        self.assertEqual(details["used"], "prompted")
        self.assertIsNone(details["unprompted_words"])
        self.assertEqual(words, details["prompted_words"])
        self.assertEqual(text, "Um dia")

    def test_without_prompt_and_silence(self):
        details = {}
        _engine([], [("oi", 0.9)]).transcribe(AUDIO, language="pt", details=details)
        self.assertEqual((details["used"], details["prompted_words"]), ("unprompted", None))
        details = {}
        self.assertEqual(_engine([], []).transcribe(np.zeros(16000, np.float32), language="pt",
                                                    initial_prompt="oi", details=details), ("", []))
        self.assertIsNone(details["used"])

    def test_return_signature_unchanged_without_details(self):
        out = _engine([("oi", 0.9)], []).transcribe(AUDIO, language="pt", initial_prompt="oi")
        self.assertEqual(len(out), 2)

    def test_pick_transcription(self):
        good, bad, alt = [{"probability": 0.9}], [{"probability": 0.05}], [{"probability": 0.7}]
        self.assertEqual(pick_transcription(good, alt), (good, "prompted"))
        self.assertEqual(pick_transcription(bad, alt), (alt, "unprompted"))
        self.assertEqual(pick_transcription(bad, None), (bad, "prompted"))  # sem 2ª passada
        self.assertEqual(pick_transcription(None, alt), (alt, "unprompted"))
        self.assertEqual(pick_transcription(None, None), ([], None))


SEG = {"sing_start": 1.0, "sing_end": 3.0, "language": "pt", "lyrics": "Maldita Geni",
       "lyrics_timed": [{"word": "Maldita", "expected_start": 0.1, "expected_end": 0.6},
                        {"word": "Geni", "expected_start": 0.7, "expected_end": 1.2}]}
PROMPTED = [{"word": "Maldita", "start": 0.1, "end": 0.6, "probability": 0.1},
            {"word": "Geni", "start": 0.7, "end": 1.2, "probability": 0.05}]
UNPROMPTED = [{"word": "não", "start": 0.1, "end": 0.4, "probability": 0.9},
              {"word": "não", "start": 0.5, "end": 0.8, "probability": 0.9}]


class TestRecordedBothRuns(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="karaoke_runs_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_recorder_stores_both_runs(self):
        from test_recorder import _timeline_with_voice

        rec = GameRecording(self.tmp, "s", "S", [SEG], "timing", {})
        rec.add_segment_result("Lelo", 0, (0.0, 3.5), 0.1, "não não", UNPROMPTED, {"score": 0.0},
                               prompted_words=PROMPTED, unprompted_words=UNPROMPTED, used="unprompted")
        rec.add_segment_result("Ana", 0, (0.0, 3.5), 0.0, "", [], {"score": 0.0})  # sem Whisper
        session_dir = rec.save({"Lelo": _timeline_with_voice()}, complete=True, whisper_model="tiny")
        results = json.loads((session_dir / SESSION_FILE).read_text(encoding="utf-8"))["results"]
        lelo = next(r for r in results if r["player"] == "Lelo")
        self.assertEqual((lelo["used"], lelo["prompted_words"], lelo["unprompted_words"]),
                         ("unprompted", PROMPTED, UNPROMPTED))
        ana = next(r for r in results if r["player"] == "Ana")
        self.assertNotIn("used", ana)

    def test_rescore_applies_live_gate(self):
        base = {"segment": 0, "live_score": 100.0, "words": PROMPTED}
        old = {"segments": [SEG], "scoring_mode": "timing", "results": [base]}
        new = {**old, "results": [{**base, "prompted_words": PROMPTED, "unprompted_words": UNPROMPTED,
                                   "used": "unprompted"}]}
        self.assertEqual(result_words(old["results"][0]), PROMPTED)  # fixture antiga: como antes
        self.assertEqual(result_words(new["results"][0]), UNPROMPTED)  # dica sem confiança
        self.assertGreater(rescore_session(old)[0][1], 80.0)
        self.assertLess(rescore_session(new)[0][1], 20.0)

    def test_rescore_prompted_when_no_second_run(self):
        good = [{**w, "probability": 0.9} for w in PROMPTED]
        data = {"segments": [SEG], "scoring_mode": "timing",
                "results": [{"segment": 0, "words": good, "prompted_words": good,
                             "unprompted_words": None, "used": "prompted"}]}
        self.assertGreater(rescore_session(data)[0][1], 80.0)

    def test_old_fixtures_still_load(self):
        for path in FIXTURES.glob("*.json"):
            if path.name == "wrong_lyrics_pairs.json":
                continue
            scores, n = rescore_session(json.loads(path.read_text(encoding="utf-8")))
            self.assertTrue(scores and n)


if __name__ == "__main__":
    unittest.main()
