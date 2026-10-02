"""prepare_song: a marca vazia do LRC (fim do verso) corta o áudio do verso."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "server"), str(ROOT / "tools")]
import prepare_song  # noqa: E402


class _DeafEngine:
    """Whisper que não ouve nada e anota quanto áudio recebeu por verso."""

    def __init__(self):
        self.seconds = []

    def transcribe(self, audio, **kwargs):
        self.seconds.append(len(audio) / prepare_song.WHISPER_SR)
        return "", []


class PrepareSongCutTest(unittest.TestCase):
    def test_solo_after_the_end_mark_is_left_out(self):
        # My Iron Lung: "My Belisha beacon" acaba em 3:25,85 e o próximo verso só
        # vem em 3:42; antes o recorte ia até 3:42 e as palavras se espalhavam pelo solo
        lrc = "[00:10.00]My Belisha beacon\n[00:14.50]\n[00:30.00]And if you're frightened\n"
        engine = _DeafEngine()
        with tempfile.TemporaryDirectory() as tmp:
            song = Path(tmp)
            (song / "vocal.mp3").write_bytes(b"")
            (song / "lyrics.lrc").write_text(lrc, encoding="utf-8")
            with patch.object(prepare_song, "load_audio_full",
                              return_value=np.zeros(40 * prepare_song.WHISPER_SR, dtype=np.float32)), \
                    patch.object(prepare_song, "get_stt_engine", return_value=engine), \
                    patch.object(prepare_song, "record_alignment_quality"):
                prepare_song.prepare_song(str(song), "en")
            segs = json.loads((song / "segments.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(engine.seconds[0], 4.5, places=2)
        first = segs[0]
        self.assertLessEqual(first["sing_end"], 14.5 + 1e-6)
        self.assertLess(first["lyrics_timed"][-1]["expected_start"], 4.5)


if __name__ == "__main__":
    unittest.main()
