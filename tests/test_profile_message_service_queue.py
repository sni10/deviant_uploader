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
        watcher_repo = MagicMock()
        logger = MagicMock()

        return ProfileMessageService(
            message_repo=message_repo,
            log_repo=log_repo,
            watcher_repo=watcher_repo,
            logger=logger,
        )

    def test_remove_selected_from_queue_removes_only_selected(self) -> None:
        """Remove selected should drop only items with selected=True."""
        service = self._create_service()
        service._watchers_queue = [
            {"username": "a", "userid": "1", "selected": True},
            {"username": "b", "userid": "2", "selected": False},
            {"username": "c", "userid": "3", "selected": True},
        ]

        result = service.remove_selected_from_queue()

        assert result["success"] is True
        assert result["removed_count"] == 2
        assert result["remaining_count"] == 1
        assert service.get_watchers_list() == [
            {"username": "b", "userid": "2", "selected": False}
        ]

    def test_remove_selected_from_queue_when_none_selected(self) -> None:
        """Remove selected should be a no-op when nothing is selected."""
        service = self._create_service()
        service._watchers_queue = [
            {"username": "a", "userid": "1", "selected": False},
            {"username": "b", "userid": "2", "selected": False},
        ]

        result = service.remove_selected_from_queue()

        assert result["success"] is True
        assert result["removed_count"] == 0
        assert result["remaining_count"] == 2
        assert [w["username"] for w in service.get_watchers_list()] == ["a", "b"]

    def test_add_selected_saved_to_queue_adds_skips_and_invalid(self) -> None:
        """Bulk add should add new watchers, skip duplicates, count invalid."""
        service = self._create_service()
        service._watchers_queue = [
            {"username": "exists", "userid": "1", "selected": False},
        ]

        result = service.add_selected_saved_to_queue(
            [
                {"username": "exists", "userid": "1"},
                {"username": "new", "userid": "2"},
                {"username": "new", "userid": "2"},
                {"username": "", "userid": "3"},
            ]
        )

        assert result["success"] is True
        assert result["added_count"] == 1
        assert result["skipped_count"] == 2
        assert result["invalid_count"] == 1

        queue = service.get_watchers_list()
        assert [w["username"] for w in queue] == ["exists", "new"]
        assert queue[1]["selected"] is True

    def test_add_selected_saved_to_queue_empty_is_noop(self) -> None:
        """Bulk add should return zeros for empty input."""
        service = self._create_service()

        result = service.add_selected_saved_to_queue([])

        assert result == {
            "success": True,
            "added_count": 0,
            "skipped_count": 0,
            "invalid_count": 0,
        }

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
    @patch("src.service.profile_message_service.requests.post")
    def test_worker_stops_when_queue_exhausted(
        self,
        post_mock: MagicMock,
        _sleep_mock: MagicMock,
        _uniform_mock: MagicMock,
    ) -> None:
        """Worker must stop on its own when no selected watchers remain."""
        service = self._create_service()

        # One selected watcher in queue
        service._watchers_queue = [{"username": "u", "userid": "1", "selected": True}]

        # Active message template
        message = MagicMock()
        message.is_active = True
        message.body = "Hello"
        service.message_repo.get_message_by_id.return_value = message

        # Successful HTTP response
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"commentid": "cid"}
        post_mock.return_value = resp

        result = service.start_worker(access_token="token", message_id=1)
        assert result["success"] is True

        assert service._worker_thread is not None
        service._worker_thread.join(timeout=1)
        assert service._worker_thread.is_alive() is False

        status = service.get_worker_status()
        assert status["running"] is False
        assert status["processed"] == 1
        assert status["queue_remaining"] == 0
