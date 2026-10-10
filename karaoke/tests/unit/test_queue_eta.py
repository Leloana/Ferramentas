"""Tempo estimado da fila (server/queue_eta.py) e o eta_sec dos itens."""
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "server"))

import queue_eta  # noqa: E402
from queue_manager import QueueItem, QueueStatus, SongQueueManager  # noqa: E402


class TestQueueEta(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = patch.object(queue_eta, "STATS_FILE", Path(tmp.name) / "queue_stats.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _item(self, **kw):
        base = dict(id="x", slug="s", title="t", artist="a", language="ja", youtube_url="u", audio_sec=180.0)
        base.update(kw)
        return QueueItem(**base)

    def test_estimate_scales_with_the_audio(self):
        self.assertEqual(queue_eta.estimate("download", 999), queue_eta.DEFAULTS["download"])
        self.assertAlmostEqual(queue_eta.estimate("separate_roformer", 120), 2 * queue_eta.DEFAULTS["separate_roformer"])
        # sem a duração: supõe DEFAULT_AUDIO_SEC
        self.assertAlmostEqual(queue_eta.estimate("align_fast", None),
                               queue_eta.DEFAULTS["align_fast"] * queue_eta.DEFAULT_AUDIO_SEC / 60)

    def test_record_moves_the_average_toward_the_measure(self):
        old = queue_eta.DEFAULTS["separate_demucs"]
        queue_eta.record("separate_demucs", 60.0, 120.0)  # 30 s por minuto
        new = queue_eta.estimate("separate_demucs", 60)
        self.assertGreater(new, old)
        self.assertLess(new, 30.0)
        queue_eta.record("align_pro", 50.0, None)  # sem duração não dá taxa: ignora
        self.assertEqual(queue_eta.estimate("align_pro", 60), queue_eta.DEFAULTS["align_pro"])

    def test_eta_counts_the_stages_still_ahead(self):
        queued = self._item(status=QueueStatus.QUEUED, separator="roformer").eta_sec()
        waiting = self._item(status=QueueStatus.AWAITING_ALIGNMENT, separator="roformer").eta_sec()
        self.assertGreater(queued, waiting)
        self.assertEqual(waiting, round(queue_eta.estimate("align_fast", 180)))
        pro = self._item(status=QueueStatus.AWAITING_ALIGNMENT, align_lyrics=True).eta_sec()
        self.assertGreater(pro, waiting)
        self.assertIsNone(self._item(status=QueueStatus.READY).eta_sec())
        self.assertIn("eta_sec", self._item().to_dict())

    def test_running_stage_counts_down_but_never_hits_zero(self):
        item = self._item(status=QueueStatus.ALIGNING, stage_started=time.monotonic() - 10_000)
        self.assertGreaterEqual(item.eta_sec(), 5)

    def test_pipeline_overlaps_separation_with_the_previous_alignment(self):
        song = [("download", 10.0), ("separate_demucs", 20.0), ("align_fast", 30.0)]
        finish = queue_eta.pipeline_finish([song, song, song], download_slots=2)
        # 1ª: 10+20+30. A 2ª separa enquanto a 1ª gera a letra e espera a letra dela.
        self.assertEqual(finish, [60.0, 90.0, 120.0])
        # bem menos que a soma de tudo (3 × 60)
        self.assertLess(finish[-1], 3 * 60)

    def test_pipeline_downloads_only_a_few_at_a_time(self):
        song = [("download", 100.0), ("separate_demucs", 1.0), ("align_fast", 1.0)]
        finish = queue_eta.pipeline_finish([song] * 4, download_slots=2)
        self.assertEqual(finish[0], 102.0)
        self.assertGreaterEqual(finish[2], 200.0)  # 3ª espera um download terminar

    def test_manager_eta_counts_the_songs_ahead(self):
        manager = SongQueueManager(Path(tempfile.mkdtemp()))
        for i in range(3):
            manager.queue.append(self._item(id=f"i{i}", separator="demucs"))
        etas = manager.etas()
        self.assertLess(etas["i0"], etas["i1"])
        self.assertLess(etas["i1"], etas["i2"])
        self.assertEqual(manager.get_queue_status()[2]["eta_sec"], etas["i2"])

    def test_only_the_item_holding_the_separation_counts_down(self):
        manager = SongQueueManager(Path(tempfile.mkdtemp()))
        long_ago = time.monotonic() - 10_000
        for i in range(3):
            manager.queue.append(self._item(id=f"s{i}", status=QueueStatus.SEPARATING,
                                            separator="demucs", stage_started=long_ago))
        manager.queue[1]._separating = True  # a 2ª ganhou o lock primeiro
        _, jobs = manager._pending_jobs()
        full = queue_eta.estimate("separate_demucs", 180)
        self.assertLess(jobs[1][0][1], full)       # a que está separando: quase lá
        self.assertEqual(jobs[0][0][1], full)      # as outras só esperam o lock
        self.assertEqual(jobs[2][0][1], full)

    def test_separation_time_counts_from_the_lock_not_the_wait(self):
        """Antes o cronômetro começava ao entrar em SEPARATING: a espera pelas outras
        separações entrava na média (90 s/min medidos contra ~20 s/min reais)."""
        import asyncio
        from utils import separation

        manager = SongQueueManager(Path(tempfile.mkdtemp()))
        item = self._item(status=QueueStatus.SEPARATING, stage_started=time.monotonic() - 500)
        manager.queue.append(item)
        seen = {}

        def fake_separate(audio, out, heavy_ok=True, cancel=None, on_start=None):
            seen["before"] = item._separating
            on_start()
            seen["during"] = item._separating
            seen["elapsed"] = time.monotonic() - item.stage_started
            raise separation.SeparationCancelled()

        with patch.object(separation, "separate_stems", fake_separate):
            with self.assertRaises(separation.SeparationCancelled):
                asyncio.run(manager._run_demucs(item, Path(tempfile.mkdtemp()), Path("x.mp3")))
        self.assertEqual((seen["before"], seen["during"]), (False, True))
        self.assertLess(seen["elapsed"], 5)          # não os 500 s de espera
        self.assertFalse(item._separating)
        self.assertEqual(manager._separations_started, 1)

    def test_estimate_batch_adds_the_current_queue(self):
        manager = SongQueueManager(Path(tempfile.mkdtemp()))
        with patch.object(SongQueueManager, "_separator_now", return_value="demucs"):
            alone = manager.estimate_batch([200.0, 200.0, None])
            self.assertEqual(alone["total_sec"], alone["own_sec"])
            self.assertEqual(alone["queued"], 0)
            manager.queue.append(self._item(id="busy", separator="demucs"))
            busy = manager.estimate_batch([200.0, 200.0, None])
        self.assertGreater(busy["total_sec"], alone["total_sec"])
        self.assertEqual(busy["own_sec"], alone["own_sec"])
        self.assertEqual(busy["queued"], 1)
        self.assertEqual(manager.estimate_batch([])["own_sec"], 0)


if __name__ == "__main__":
    unittest.main()
