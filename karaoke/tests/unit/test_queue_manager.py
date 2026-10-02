# tests/unit/test_queue_manager.py
"""Unit tests for the SongQueueManager class."""

import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

# Add project root and server to sys.path
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from queue_manager import SongQueueManager, QueueStatus, QueueItem

class TestSongQueueManager(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.songs_dir = Path(tmp.name)  # a fila agora é gravada na pasta das músicas
        self.manager = SongQueueManager(self.songs_dir)

    def test_queue_item_init_and_to_dict(self):
        item = QueueItem(
            id="test-id",
            slug="test-slug",
            title="Test Title",
            artist="Test Artist",
            language="pt",
            youtube_url="https://youtube.com/watch?v=123",
            plain_lyrics="line 1\nline 2",
            synced_lrc="[00:10.00] line 1\n[00:12.00] line 2",
            align_lyrics=True,
            added_by="user1"
        )
        self.assertEqual(item.align_lyrics, True)
        d = item.to_dict()
        self.assertEqual(d["align_lyrics"], True)
        self.assertEqual(d["has_lrc"], True)
        self.assertEqual(d["has_plain_lyrics"], False)

        item2 = QueueItem(
            id="test-id2",
            slug="test-slug2",
            title="Test Title 2",
            artist="Test Artist 2",
            language="en",
            youtube_url="url2",
            plain_lyrics="line 1\nline 2",
            synced_lrc=None,
            align_lyrics=False
        )
        d2 = item2.to_dict()
        self.assertEqual(d2["has_lrc"], False)
        self.assertEqual(d2["has_plain_lyrics"], True)


    @patch("asyncio.create_task")
    async def test_enqueue(self, mock_create_task):
        mock_create_task.return_value = MagicMock()
        item = await self.manager.enqueue(
            title="Title",
            artist="Artist",
            language="en",
            youtube_url="https://youtube.com/watch?v=abc",
            plain_lyrics="lyrics",
            added_by="me",
            align_lyrics=True
        )
        self.assertEqual(len(self.manager.queue), 1)
        self.assertEqual(self.manager.queue[0].title, "Title")
        self.assertEqual(self.manager.queue[0].align_lyrics, True)
        self.assertEqual(self.manager.queue[0].added_by, "me")
        mock_create_task.assert_called_once()

    def test_remove_item(self):
        item = QueueItem(
            id="item1",
            slug="slug",
            title="Title",
            artist="Artist",
            language="en",
            youtube_url="url",
            align_lyrics=False
        )
        mock_task = MagicMock()
        mock_task.done.return_value = False
        item._task = mock_task
        
        self.manager.queue.append(item)
        
        removed = self.manager.remove_item("item1")
        self.assertTrue(removed)
        self.assertEqual(len(self.manager.queue), 0)
        mock_task.cancel.assert_called_once()

    async def test_delayed_remove(self):
        item = QueueItem(
            id="item1",
            slug="slug",
            title="Title",
            artist="Artist",
            language="en",
            youtube_url="url",
            align_lyrics=False
        )
        self.manager.queue.append(item)
        
        # Call delayed remove with 0 delay to test execution
        await self.manager._delayed_remove("item1", delay=0.01)
        self.assertEqual(len(self.manager.queue), 0)

    @patch("asyncio.create_task")
    async def test_try_process_pending_gpu_busy(self, mock_create_task):
        self.manager.notify_game_started()  # Set gpu_game_active = True
        
        item = QueueItem(
            id="item1",
            slug="slug",
            title="Title",
            artist="Artist",
            language="en",
            youtube_url="url",
            align_lyrics=False,
            status=QueueStatus.AWAITING_ALIGNMENT
        )
        self.manager.queue.append(item)
        
        await self.manager._try_process_pending()
        mock_create_task.assert_not_called()

    @patch("asyncio.create_task")
    async def test_try_process_pending_already_running_phase2(self, mock_create_task):
        item1 = QueueItem(
            id="item1",
            slug="slug1",
            title="Title1",
            artist="Artist1",
            language="en",
            youtube_url="url1",
            align_lyrics=False,
            status=QueueStatus.ALIGNING
        )
        item2 = QueueItem(
            id="item2",
            slug="slug2",
            title="Title2",
            artist="Artist2",
            language="en",
            youtube_url="url2",
            align_lyrics=False,
            status=QueueStatus.AWAITING_ALIGNMENT
        )
        self.manager.queue.extend([item1, item2])
        
        await self.manager._try_process_pending()
        mock_create_task.assert_not_called()

    @patch("asyncio.create_task")
    async def test_try_process_pending_starts_new_phase2(self, mock_create_task):
        item = QueueItem(
            id="item1",
            slug="slug1",
            title="Title1",
            artist="Artist1",
            language="en",
            youtube_url="url1",
            align_lyrics=False,
            status=QueueStatus.AWAITING_ALIGNMENT
        )
        self.manager.queue.append(item)
        
        await self.manager._try_process_pending()
        mock_create_task.assert_called_once()

class TestQueueOnDisk(unittest.IsolatedAsyncioTestCase):
    """A Tipo Madara ficou "pendente" sem segments: o servidor reiniciou com ela na fila,
    que só existia na memória."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.songs_dir = Path(tmp.name)
        self.saved = self.songs_dir / ".queue.json"

    @patch("asyncio.create_task")
    async def test_queue_survives_a_restart(self, mock_create_task):
        mock_create_task.return_value = MagicMock()
        first = SongQueueManager(self.songs_dir)
        item = await first.enqueue(title="Tipo Madara", artist="MHRAP", language="pt",
                                   youtube_url="https://youtu.be/x", synced_lrc="[00:01.00] a",
                                   align_lyrics=True, added_by="Lelo")
        item.status = QueueStatus.SEPARATING  # caiu no meio da fase 1

        mock_create_task.reset_mock()
        with patch.dict(os.environ, {"KARAOKE_QUEUE_RESUME": "1"}):
            second = SongQueueManager(self.songs_dir)
            self.assertEqual(second.resume_saved(), 1)
        back = second.queue[0]
        self.assertEqual((back.id, back.slug, back.title, back.synced_lrc, back.align_lyrics, back.added_by),
                         (item.id, item.slug, "Tipo Madara", "[00:01.00] a", True, "Lelo"))
        self.assertEqual(back.status, QueueStatus.QUEUED)
        mock_create_task.assert_called_once()  # a fase 1 recomeça (e pula o que já baixou)

    @patch("asyncio.create_task")
    async def test_done_removed_and_failed_items_do_not_come_back(self, mock_create_task):
        mock_create_task.return_value = MagicMock()
        manager = SongQueueManager(self.songs_dir)
        a = await manager.enqueue(title="A", artist="X", language="pt", youtube_url="u1")
        b = await manager.enqueue(title="B", artist="X", language="pt", youtube_url="u2")
        self.assertEqual([d["id"] for d in json.loads(self.saved.read_text(encoding="utf-8"))], [a.id, b.id])
        a.status = QueueStatus.READY
        b.status = QueueStatus.ERROR
        manager._save()
        self.assertFalse(self.saved.exists())
        c = await manager.enqueue(title="C", artist="X", language="pt", youtube_url="u3")
        manager.remove_item(c.id)
        self.assertFalse(self.saved.exists())

    @patch("asyncio.create_task")
    async def test_reinstall_cleans_only_once(self, mock_create_task):
        mock_create_task.return_value = MagicMock()
        manager = SongQueueManager(self.songs_dir)
        item = await manager.enqueue(title="A", artist="X", language="pt", youtube_url="u", clean_existing=True)
        self.assertTrue(json.loads(self.saved.read_text(encoding="utf-8"))[0]["clean_existing"])
        item.clean_existing = False  # o que a fase 1 faz depois de limpar a pasta
        manager._save()
        self.assertFalse(json.loads(self.saved.read_text(encoding="utf-8"))[0]["clean_existing"])

    def test_resume_is_off_in_tests_and_tolerates_a_broken_file(self):
        self.saved.write_text("[{", encoding="utf-8")
        manager = SongQueueManager(self.songs_dir)
        self.assertEqual(manager.resume_saved(), 0)  # conftest: KARAOKE_QUEUE_RESUME=0
        with patch.dict(os.environ, {"KARAOKE_QUEUE_RESUME": "1"}):
            self.assertEqual(manager.resume_saved(), 0)
        self.assertEqual(manager.queue, [])


if __name__ == "__main__":
    unittest.main()
