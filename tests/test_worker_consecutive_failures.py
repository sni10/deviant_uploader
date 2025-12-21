"""Tests for worker consecutive failures logic."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import requests

from src.domain.models import ProfileMessage
from src.service.profile_message_service import ProfileMessageService
from src.service.mass_fave_service import MassFaveService


class TestProfileMessageServiceConsecutiveFailures:
    """Test consecutive failures logic in ProfileMessageService."""

    def _create_service(self) -> ProfileMessageService:
        """Create ProfileMessageService with mocked dependencies."""
        message_repo = MagicMock()
        log_repo = MagicMock()
        log_repo.get_stats.return_value = {"sent": 0, "failed": 0}
        watcher_repo = MagicMock()
        logger = MagicMock()

        # Mock http_client
        http_client = MagicMock()

        return ProfileMessageService(
            message_repo=message_repo,
            log_repo=log_repo,
            watcher_repo=watcher_repo,
            logger=logger,
            http_client=http_client,
        )

    @patch("src.service.profile_message_service.time.sleep", return_value=None)
    @patch("src.service.profile_message_service.random.uniform", return_value=0)
    def test_worker_stops_after_max_consecutive_failures(
        self, _uniform_mock: MagicMock, _sleep_mock: MagicMock
    ) -> None:
        """Worker should stop after MAX_CONSECUTIVE_FAILURES consecutive errors."""
        service = self._create_service()

        # Setup: 6 watchers in queue
        service._watchers_queue = [
            {"username": f"user{i}", "userid": f"{i}", "selected": True}
            for i in range(6)
        ]

        # Mock active message
        message = MagicMock()
        message.message_id = 1
        message.body = "Hello"
        service.message_repo.get_active_messages.return_value = [message]

        # Mock http_client to always fail
        service.http_client.post.side_effect = requests.RequestException("Rate limited")

        # Start worker
        result = service.start_worker(access_token="token")
        assert result["success"] is True

        # Wait for worker to stop (should stop after 5 failures)
        assert service._worker_thread is not None
        service._worker_thread.join(timeout=5)

        # Verify worker stopped
        status = service.get_worker_status()
        assert status["running"] is False
        assert status["errors"] == 5
        assert status["consecutive_failures"] == 5
        assert status["processed"] == 0

        # Verify only 5 watchers were processed (not all 6)
        assert len(service._watchers_queue) == 1  # 1 watcher left

    @patch("src.service.profile_message_service.time.sleep", return_value=None)
    @patch("src.service.profile_message_service.random.uniform", return_value=0)
    def test_consecutive_failures_resets_on_success(
        self, _uniform_mock: MagicMock, _sleep_mock: MagicMock
    ) -> None:
        """consecutive_failures should reset to 0 after successful send."""
        service = self._create_service()

        # Setup: 10 watchers in queue
        service._watchers_queue = [
            {"username": f"user{i}", "userid": f"{i}", "selected": True}
            for i in range(10)
        ]

        # Mock active message
        message = MagicMock()
        message.message_id = 1
        message.body = "Hello"
        service.message_repo.get_active_messages.return_value = [message]

        # Mock http_client: fail 3 times, then succeed, then fail 3 more times
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 4:
                # 4th call succeeds
                resp = MagicMock()
                resp.json.return_value = {"commentid": "cid"}
                return resp
            else:
                # All other calls fail
                raise requests.RequestException("Rate limited")

        service.http_client.post.side_effect = side_effect

        # Start worker
        result = service.start_worker(access_token="token")
        assert result["success"] is True

        # Wait for worker to process
        assert service._worker_thread is not None
        service._worker_thread.join(timeout=10)

        # Verify: 3 failures, 1 success, 5 more failures = worker should stop after 5 more
        status = service.get_worker_status()
        assert status["running"] is False
        assert status["processed"] == 1  # 1 success
        assert status["errors"] == 8  # 3 + 5 failures
        assert status["consecutive_failures"] == 5  # Reset after success, then 5 more

    @patch("src.service.profile_message_service.time.sleep", return_value=None)
    @patch("src.service.profile_message_service.random.uniform", return_value=0)
    def test_consecutive_failures_in_status(
        self, _uniform_mock: MagicMock, _sleep_mock: MagicMock
    ) -> None:
        """get_worker_status should include consecutive_failures field."""
        service = self._create_service()

        # Initial status
        status = service.get_worker_status()
        assert "consecutive_failures" in status
        assert status["consecutive_failures"] == 0

        # After starting worker
        service._watchers_queue = [
            {"username": "user1", "userid": "1", "selected": True}
        ]
        message = MagicMock()
        message.message_id = 1
        message.body = "Hello"
        service.message_repo.get_active_messages.return_value = [message]
        service.http_client.post.side_effect = requests.RequestException("Error")

        service.start_worker(access_token="token")
        assert service._worker_thread is not None
        service._worker_thread.join(timeout=2)

        status = service.get_worker_status()
        assert "consecutive_failures" in status
        assert status["consecutive_failures"] == 1


class TestMassFaveServiceConsecutiveFailures:
    """Test consecutive failures logic in MassFaveService."""

    def _create_service(self) -> MassFaveService:
        """Create MassFaveService with mocked dependencies."""
        repo = MagicMock()
        repo.get_stats.return_value = {"pending": 0, "faved": 0, "failed": 0}
        logger = MagicMock()
        http_client = MagicMock()

        return MassFaveService(
            feed_deviation_repo=repo,
            logger=logger,
            http_client=http_client,
        )

    @patch("src.service.mass_fave_service.time.sleep", return_value=None)
    @patch("src.service.mass_fave_service.random.uniform", return_value=0)
    def test_worker_stops_after_max_consecutive_failures(
        self, _uniform_mock: MagicMock, _sleep_mock: MagicMock
    ) -> None:
        """Worker should stop after MAX_CONSECUTIVE_FAILURES consecutive errors."""
        service = self._create_service()

        # Mock repo to return deviations
        call_count = 0

        def get_one_pending():
            nonlocal call_count
            call_count += 1
            if call_count <= 6:
                return {"deviationid": f"dev{call_count}"}
            return None

        service.repo.get_one_pending.side_effect = get_one_pending

        # Mock http_client to always fail
        service.http_client.post.side_effect = requests.RequestException("Rate limited")

        # Start worker
        result = service.start_worker(access_token="token")
        assert result["success"] is True

        # Wait for worker to stop
        assert service._worker_thread is not None
        service._worker_thread.join(timeout=5)

        # Verify worker stopped after 5 failures
        status = service.get_worker_status()
        assert status["running"] is False
        assert status["errors"] == 5
        assert status["consecutive_failures"] == 5
        assert status["processed"] == 0

    @patch("src.service.mass_fave_service.time.sleep", return_value=None)
    @patch("src.service.mass_fave_service.random.uniform", return_value=0)
    def test_consecutive_failures_resets_on_success(
        self, _uniform_mock: MagicMock, _sleep_mock: MagicMock
    ) -> None:
        """consecutive_failures should reset to 0 after successful fave."""
        service = self._create_service()

        # Mock repo to return deviations
        call_count = 0

        def get_one_pending():
            nonlocal call_count
            call_count += 1
            if call_count <= 10:
                return {"deviationid": f"dev{call_count}"}
            return None

        service.repo.get_one_pending.side_effect = get_one_pending

        # Mock http_client: fail 3 times, succeed once, fail 3 more times
        post_call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal post_call_count
            post_call_count += 1
            if post_call_count == 4:
                # 4th call succeeds
                resp = MagicMock()
                resp.json.return_value = {"success": True}
                return resp
            else:
                raise requests.RequestException("Rate limited")

        service.http_client.post.side_effect = side_effect

        # Start worker
        result = service.start_worker(access_token="token")
        assert result["success"] is True

        # Wait for worker
        assert service._worker_thread is not None
        service._worker_thread.join(timeout=10)

        # Verify: 3 failures, 1 success, 5 more failures = worker should stop after 5 more
        status = service.get_worker_status()
        assert status["running"] is False
        assert status["processed"] == 1
        assert status["errors"] == 8  # 3 + 5 failures
        assert status["consecutive_failures"] == 5  # Reset after success, then 5 more

    @patch("src.service.mass_fave_service.time.sleep", return_value=None)
    @patch("src.service.mass_fave_service.random.uniform", return_value=0)
    def test_consecutive_failures_in_status(
        self, _uniform_mock: MagicMock, _sleep_mock: MagicMock
    ) -> None:
        """get_worker_status should include consecutive_failures field."""
        service = self._create_service()

        # Initial status
        status = service.get_worker_status()
        assert "consecutive_failures" in status
        assert status["consecutive_failures"] == 0

        # After starting worker with failure
        service.repo.get_one_pending.return_value = {"deviationid": "dev1"}
        service.http_client.post.side_effect = requests.RequestException("Error")

        service.start_worker(access_token="token")
        assert service._worker_thread is not None
        service._worker_thread.join(timeout=2)

        status = service.get_worker_status()
        assert "consecutive_failures" in status
        assert status["consecutive_failures"] >= 1
