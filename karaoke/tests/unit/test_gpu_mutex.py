import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from queue_manager import SongQueueManager  # noqa: E402


class GpuMutexTest(unittest.TestCase):
    def test_alignment_busy_while_job_runs(self):
        qm = SongQueueManager(Path(tempfile.mkdtemp()))

        async def scenario():
            self.assertIsNone(qm.alignment_busy())
            async with qm.gpu_job("Geni - Chico"):
                self.assertEqual(qm.alignment_busy(), "Geni - Chico")
                self.assertTrue(qm.whisper_lock.locked())
            self.assertIsNone(qm.alignment_busy())
            self.assertFalse(qm.whisper_lock.locked())

        asyncio.run(scenario())

    def test_job_is_released_on_error(self):
        qm = SongQueueManager(Path(tempfile.mkdtemp()))

        async def scenario():
            with self.assertRaises(RuntimeError):
                async with qm.gpu_job("x"):
                    raise RuntimeError("falhou")
            self.assertIsNone(qm.alignment_busy())

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
