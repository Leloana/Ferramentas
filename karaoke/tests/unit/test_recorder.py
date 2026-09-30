"""Gravação da partida e repetição offline (tools/replay_recording.py)."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "server"))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from mic_stream import STREAM_SR, MicTimeline  # noqa: E402
from recorder import (  # noqa: E402
    SESSION_FILE,
    GameRecording,
    covered_intervals,
    covered_mask,
    read_wav,
    recording_base_dir,
)

SEGMENTS = [
    {"sing_start": 1.0, "sing_end": 3.0, "language": "en", "lyrics": "hello world",
     "lyrics_timed": [{"word": "hello", "expected_start": 0.2, "expected_end": 0.8},
                      {"word": "world", "expected_start": 1.0, "expected_end": 1.8}]},
    {"sing_start": 4.0, "sing_end": 6.0, "language": "en", "lyrics": "oh oh",
     "lyrics_timed": [{"word": "oh", "expected_start": 0.0, "expected_end": 0.5},
                      {"word": "oh", "expected_start": 0.6, "expected_end": 1.0}]},
]
WINDOWS = {"pre_sing_sec": 1.5, "post_sing_sec": 0.5}


def _timeline_with_voice() -> MicTimeline:
    """Celular mandando 100 ms por pacote de 0 a 6 s; âncora exata em 0."""
    timeline = MicTimeline()
    chunk = 1600
    rng = np.random.default_rng(0)
    for i in range(60):
        samples = (rng.uniform(-0.2, 0.2, chunk) * 32768).astype("<i2")
        timeline.add(i * chunk, samples, song_time=(i + 1) * chunk / STREAM_SR, epoch=1)
    return timeline


class TestRecordingDir(unittest.TestCase):
    def test_on_by_default_and_can_be_disabled(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(recording_base_dir(), PROJECT_ROOT / "recordings")
        with patch.dict("os.environ", {"KARAOKE_RECORD": "0"}, clear=True):
            self.assertIsNone(recording_base_dir())
        with patch.dict("os.environ", {"KARAOKE_RECORD_DIR": "x/y"}, clear=True):
            self.assertEqual(recording_base_dir(), Path("x/y"))


class TestCoverage(unittest.TestCase):
    def test_intervals_roundtrip(self):
        mask = np.zeros(48000, dtype=bool)
        mask[1600:8000] = True
        mask[16000:16001] = True
        intervals = covered_intervals(mask)
        self.assertEqual(len(intervals), 2)
        self.assertEqual(intervals[0], [0.1, 0.5])
        np.testing.assert_array_equal(covered_mask(intervals, len(mask)), mask)


class TestSaveAndReplay(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="karaoke_rec_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _record(self) -> Path:
        rec = GameRecording(self.tmp, "song-x", "Song X", SEGMENTS, "timing", WINDOWS)
        rec.add_segment_result("Lelo", 0, (0.0, 3.5), 0.11, "hello world", [], {"score": 90.0})
        return rec.save({"Lelo": _timeline_with_voice()}, complete=True, whisper_model="tiny")

    def test_save_writes_audio_in_song_time(self):
        session_dir = self._record()
        session = json.loads((session_dir / SESSION_FILE).read_text(encoding="utf-8"))
        self.assertEqual(session["players"]["Lelo"]["covered"], [[0.0, 6.0]])
        self.assertEqual(session["results"][0]["score"], 90.0)
        wav = read_wav(session_dir / "Lelo.wav")
        self.assertEqual(len(wav), 6 * STREAM_SR)
        # Mesmas amostras que a linha do tempo devolve ao servidor.
        live, _ = _timeline_with_voice().extract(0.0, 6.0)
        np.testing.assert_array_equal(wav, live)

    def test_nothing_saved_without_audio(self):
        rec = GameRecording(self.tmp, "song-x", "Song X", SEGMENTS, "timing", WINDOWS)
        self.assertIsNone(rec.save({}, complete=True, whisper_model=None))
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_replay_scores_like_the_server(self):
        import replay_recording
        import segment_scoring
        from mic_stream import segment_window

        session_dir = self._record()
        session = json.loads((session_dir / SESSION_FILE).read_text(encoding="utf-8"))
        wav = read_wav(session_dir / "Lelo.wav")
        covered = covered_mask(session["players"]["Lelo"]["covered"], len(wav))

        # Whisper responde em tempo relativo ao início da janela [0, 3.5).
        whisper_words = [{"word": "hello", "start": 1.2, "end": 1.7, "probability": 0.9},
                         {"word": "world", "start": 2.0, "end": 2.7, "probability": 0.9}]
        stt = MagicMock()
        stt.transcribe.return_value = ("hello world", whisper_words)

        replayed = replay_recording.replay_player(session, wav, covered, stt, "timing", 1.5, 0.5)

        # Verso 1 pelo Whisper, com o mesmo deslocamento de janela do servidor.
        t0, t1 = segment_window(SEGMENTS, 0, 1.5, 0.5)
        live_audio, _ = _timeline_with_voice().extract(t0, t1)
        np.testing.assert_array_equal(stt.transcribe.call_args.args[0], live_audio)
        expected = segment_scoring.score_words(
            SEGMENTS[0], None, segment_scoring.shift_words(whisper_words, t0 - 1.0), "timing")
        self.assertEqual(replayed[0]["score"], expected["score"])
        self.assertEqual(replayed[0]["score"], 100.0)
        # Verso 2 é vocalize: nota por energia, sem Whisper.
        self.assertEqual(stt.transcribe.call_count, 1)
        self.assertEqual(replayed[1]["score"], 100.0)


class TestGabarito(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="karaoke_gab_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_labels_saved_by_the_game_over_screen_feed_the_replay(self):
        import replay_recording
        from recorder import save_labels

        save_labels(self.tmp, "Lelo", {"1": "certo", "3": "cantarolei", "2": "errado"})
        save_labels(self.tmp, "Ana", {"1": "errado"})
        self.assertEqual(replay_recording.load_gabarito(self.tmp, "Lelo"), {0: 100.0, 1: 0.0, 2: 0.0})
        self.assertEqual(replay_recording.load_gabarito(self.tmp, "Ana"), {0: 0.0})
        self.assertEqual(replay_recording.load_gabarito(self.tmp, "Ninguém"), {})

    def test_invalid_label_is_rejected(self):
        from recorder import save_labels

        with self.assertRaises(ValueError):
            save_labels(self.tmp, "Lelo", {"1": "mais ou menos"})


class TestRoomSavesPartialGame(unittest.TestCase):
    def test_reset_saves_unfinished_game(self):
        from rooms import KaraokeRoom

        tmp = Path(tempfile.mkdtemp(prefix="karaoke_rec_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        room = KaraokeRoom("song-x")
        room.recording = GameRecording(tmp, "song-x", "Song X", SEGMENTS, "timing", WINDOWS)
        room.mic_timelines["Lelo"] = _timeline_with_voice()

        room.reset_audio()

        self.assertIsNone(room.recording)
        self.assertEqual(room.mic_timelines, {})
        (session_dir,) = list(tmp.iterdir())
        session = json.loads((session_dir / SESSION_FILE).read_text(encoding="utf-8"))
        self.assertFalse(session["complete"])


if __name__ == "__main__":
    unittest.main()
