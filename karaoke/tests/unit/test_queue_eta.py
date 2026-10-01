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
from queue_manager import QueueItem, QueueStatus  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
