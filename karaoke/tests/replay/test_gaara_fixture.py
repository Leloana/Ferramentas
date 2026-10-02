"""Partida de verdade para depurar a nota em outro PC: Rap do Gaara cantado pelo Lelo.

A pasta `tests/fixtures/replay/rap-do-gaara-lelo/` é uma gravação completa (a voz do
celular em WAV 16 kHz, o session.json com o que o Whisper ouviu verso a verso, a letra
e o gabarito anotado pelo cantor: 53 versos "certo", 13 "errado"). Detalhes no README.

- Sempre: repontua as palavras gravadas com o score atual (sem GPU, ~1 s).
- Com KARAOKE_REPLAY=1: roda o Whisper de novo no WAV, como no jogo (~1 min na GPU,
  bem mais na CPU) — mede janela, VAD, dica e nota juntos.

Referência (2026-10-02, commit 702ed83, large-v3-turbo na RTX 4070):
repontuar 87,7 / erro 12,3 · replay com Whisper 88,4 / erro 11,5.
"""
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "server"), str(ROOT / "tools")]

FIXTURE = ROOT / "tests" / "fixtures" / "replay" / "rap-do-gaara-lelo"
PLAYER = "Lelo"
MAX_MAE = 15.0        # erro médio contra o gabarito (referência ~12)
MIN_FINAL = 80.0      # nota final (referência ~88)


def _load(name):
    return json.loads((FIXTURE / name).read_text(encoding="utf-8"))


class GaaraFixtureTest(unittest.TestCase):
    def test_fixture_has_everything_to_debug(self):
        for name in ("Lelo.wav", "session.json", "gabarito.json", "song_lyrics.lrc", "song_meta.json"):
            self.assertTrue((FIXTURE / name).exists(), name)
        session, gab = _load("session.json"), _load("gabarito.json")
        self.assertEqual(len(session["segments"]), 66)
        self.assertEqual(len(gab["labels"][PLAYER]), 66)
        self.assertIn(PLAYER, session["players"])

    def test_rescoring_the_recorded_words_matches_the_labels(self):
        from calibration import label_mae, rescore_session

        scores, n = rescore_session(_load("session.json"))
        mae, count = label_mae(scores, _load("gabarito.json")["labels"][PLAYER])
        final = sum(scores.values()) / n
        print(f"\n[gaara] repontuar: nota {final:.1f} · erro vs gabarito {mae} ({count} versos)")
        self.assertLessEqual(mae, MAX_MAE)
        self.assertGreaterEqual(final, MIN_FINAL)


@unittest.skipUnless(os.environ.get("KARAOKE_REPLAY") == "1",
                     "replay com Whisper: rode com KARAOKE_REPLAY=1 (precisa do faster-whisper)")
class GaaraWhisperReplayTest(unittest.TestCase):
    def test_whisper_replay_matches_the_labels(self):
        import utils.cuda_bootstrap  # noqa: F401  (DLLs do CUDA antes do Whisper)
        import torch  # noqa: F401  (cuDNN do torch antes do ctranslate2)
        import replay_recording as rr
        from stt_engine import STTEngine

        session = _load("session.json")
        info = session["players"][PLAYER]
        audio = rr.read_wav(FIXTURE / info["audio"])
        covered = rr.covered_mask(info["covered"], len(audio), session["sample_rate"])
        windows = session.get("windows", {})
        replayed = rr.replay_player(session, audio, covered, STTEngine(), session["scoring_mode"],
                                    windows.get("pre_sing_sec", 1.5), windows.get("post_sing_sec", 0.5))
        gab = rr.load_gabarito(FIXTURE, PLAYER)
        errs = [abs(replayed.get(i, {"score": 0.0})["score"] - exp) for i, exp in gab.items()]
        mae = sum(errs) / len(errs)
        final = sum(r["score"] for r in replayed.values()) / len(session["segments"])
        print(f"\n[gaara] replay Whisper: nota {final:.1f} · erro vs gabarito {mae:.1f} ({len(errs)} versos)")
        self.assertLessEqual(mae, MAX_MAE + 1.0)  # o Whisper varia ±1 entre rodadas
        self.assertGreaterEqual(final, MIN_FINAL)


if __name__ == "__main__":
    unittest.main()
