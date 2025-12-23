"""Tests for ProfileMessageService queue utilities."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

from src.service.profile_message_service import ProfileMessageService


class TestProfileMessageServiceQueue:
    """Test in-memory watchers queue operations."""

    def _create_service(self) -> ProfileMessageService:
        message_repo = MagicMock()
        log_repo = MagicMock()
        log_repo.get_stats.return_value = {"sent": 0, "failed": 0}
        queue_repo = MagicMock()
        watcher_repo = MagicMock()
        logger = MagicMock()

        return ProfileMessageService(
            message_repo=message_repo,
            log_repo=log_repo,
            queue_repo=queue_repo,
            watcher_repo=watcher_repo,
            logger=logger,
        )


    def test_get_worker_status_running_true_when_thread_alive(self) -> None:
        """Status.running must reflect a living thread even if internal flag is stale."""
        service = self._create_service()

        stop_event = threading.Event()
        started = threading.Event()

        def worker() -> None:
            started.set()
            stop_event.wait(timeout=1)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        assert started.wait(timeout=0.2) is True

        service._worker_thread = t
        service._worker_running = False  # simulate stale flag

        status = service.get_worker_status()
        assert status["running"] is True

        stop_event.set()
        t.join(timeout=1)

    def test_stop_worker_can_stop_when_thread_alive_but_flag_false(self) -> None:
        """stop_worker must be able to stop a live thread even if flag says stopped."""
        service = self._create_service()
        service._stop_flag.clear()

        def worker() -> None:
            while not service._stop_flag.is_set():
                time.sleep(0.01)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        service._worker_thread = t
        service._worker_running = False  # simulate stale flag

        result = service.stop_worker()
        assert result["success"] is True

        t.join(timeout=1)
        assert t.is_alive() is False

    @patch("src.service.profile_message_service.random.uniform", return_value=0)
    @patch("src.service.profile_message_service.time.sleep", return_value=None)
    def test_worker_stops_when_queue_exhausted(
        self,
        _sleep_mock: MagicMock,
        _uniform_mock: MagicMock,
    ) -> None:
        """Worker must stop on its own when no pending entries remain in DB queue."""
        # Create mock http_client
        http_client = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"commentid": "cid"}
        http_client.post.return_value = resp

        # Create service with mock http_client
        message_repo = MagicMock()
        log_repo = MagicMock()
        log_repo.get_stats.return_value = {"sent": 0, "failed": 0}
        queue_repo = MagicMock()
        watcher_repo = MagicMock()
        logger = MagicMock()

        service = ProfileMessageService(
            message_repo=message_repo,
            log_repo=log_repo,
            queue_repo=queue_repo,
            watcher_repo=watcher_repo,
            logger=logger,
            http_client=http_client,
        )

        # Mock queue_repo to return one entry, then empty
        queue_entry = MagicMock()
        queue_entry.recipient_username = "u"
        queue_entry.recipient_userid = "1"
        queue_entry.queue_id = 123
        queue_repo.get_pending.side_effect = [[queue_entry], []]
        # Return 1 initially (for start_worker check), then 0 (for status check)
        queue_repo.get_queue_count.side_effect = [1, 0]

        # Active message templates
        message = MagicMock()
        message.message_id = 1
        message.is_active = True
        message.body = "Hello"
        service.message_repo.get_active_messages.return_value = [message]

        result = service.start_worker(access_token="token")
        assert result["success"] is True

        assert service._worker_thread is not None
        service._worker_thread.join(timeout=1)
        assert service._worker_thread.is_alive() is False

        status = service.get_worker_status()
        assert status["running"] is False
        assert status["processed"] == 1
        assert status["queue_remaining"] == 0
