"""Tests for ProfileMessageService retry logic."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

from src.service.profile_message_service import ProfileMessageService


class TestProfileMessageServiceRetry:
    """Test retry logic for temporary errors."""

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

    def test_should_retry_returns_true_when_under_max(self) -> None:
        """_should_retry should return True when retry_count < MAX_RETRIES."""
        service = self._create_service()
        
        watcher = {"username": "user", "userid": "1", "retry_count": 0}
        assert service._should_retry(watcher) is True
        
        watcher = {"username": "user", "userid": "1", "retry_count": 2}
        assert service._should_retry(watcher) is True

    def test_should_retry_returns_false_when_at_max(self) -> None:
        """_should_retry should return False when retry_count >= MAX_RETRIES."""
        service = self._create_service()
        
        watcher = {"username": "user", "userid": "1", "retry_count": 3}
        assert service._should_retry(watcher) is False
        
        watcher = {"username": "user", "userid": "1", "retry_count": 5}
        assert service._should_retry(watcher) is False

    def test_calculate_backoff_delay_exponential(self) -> None:
        """_calculate_backoff_delay should return exponential backoff."""
        service = self._create_service()
        
        # BASE_RETRY_DELAY = 5
        assert service._calculate_backoff_delay(0) == 5   # 5 * 2^0 = 5
        assert service._calculate_backoff_delay(1) == 10  # 5 * 2^1 = 10
        assert service._calculate_backoff_delay(2) == 20  # 5 * 2^2 = 20
        assert service._calculate_backoff_delay(3) == 40  # 5 * 2^3 = 40

    def test_calculate_backoff_delay_capped_at_60(self) -> None:
        """_calculate_backoff_delay should cap delay at 60 seconds."""
        service = self._create_service()
        
        assert service._calculate_backoff_delay(4) == 60  # 5 * 2^4 = 80, capped at 60
        assert service._calculate_backoff_delay(10) == 60

    @patch("src.service.profile_message_service.time.sleep", return_value=None)
    @patch("src.service.profile_message_service.requests.post")
    def test_worker_retries_400_error(
        self,
        post_mock: MagicMock,
        _sleep_mock: MagicMock,
    ) -> None:
        """Worker should retry 400 errors with exponential backoff."""
        service = self._create_service()
        service._watchers_queue = [{"username": "u", "userid": "1", "selected": True, "retry_count": 0}]

        # Active message template
        message = MagicMock()
        message.message_id = 1
        message.body = "Hello"
        service.message_repo.get_active_messages.return_value = [message]

        # First call: 400 error
        resp_400 = MagicMock()
        resp_400.status_code = 400
        resp_400.text = "Bad Request"
        resp_400.headers = {}

        # Second call: success
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {"commentid": "cid"}

        post_mock.side_effect = [resp_400, resp_200]

        result = service.start_worker(access_token="token")
        assert result["success"] is True

        assert service._worker_thread is not None
        service._worker_thread.join(timeout=2)

        # Should have made 2 POST calls (1 fail + 1 retry success)
        assert post_mock.call_count == 2

        # Should have logged 1 success
        assert service.log_repo.add_log.call_count == 1
        assert service.log_repo.add_log.call_args[1]["status"].value == "sent"

    @patch("src.service.profile_message_service.time.sleep", return_value=None)
    @patch("src.service.profile_message_service.requests.post")
    def test_worker_retries_503_with_retry_after(
        self,
        post_mock: MagicMock,
        sleep_mock: MagicMock,
    ) -> None:
        """Worker should respect Retry-After header for 503 errors."""
        service = self._create_service()
        service._watchers_queue = [{"username": "u", "userid": "1", "selected": True, "retry_count": 0}]

        # Active message template
        message = MagicMock()
        message.message_id = 1
        message.body = "Hello"
        service.message_repo.get_active_messages.return_value = [message]

        # First call: 503 with Retry-After
        resp_503 = MagicMock()
        resp_503.status_code = 503
        resp_503.text = "Service Unavailable"
        resp_503.headers = {"Retry-After": "15"}

        # Second call: success
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {"commentid": "cid"}

        post_mock.side_effect = [resp_503, resp_200]

        result = service.start_worker(access_token="token")
        assert result["success"] is True

        assert service._worker_thread is not None
        service._worker_thread.join(timeout=2)

        # Should have made 2 POST calls
        assert post_mock.call_count == 2

        # Should have slept for 15 seconds (from Retry-After)
        sleep_calls = [call[0][0] for call in sleep_mock.call_args_list]
        assert 15 in sleep_calls

    @patch("src.service.profile_message_service.time.sleep", return_value=None)
    @patch("src.service.profile_message_service.requests.post")
    def test_worker_fails_after_max_retries_400(
        self,
        post_mock: MagicMock,
        _sleep_mock: MagicMock,
    ) -> None:
        """Worker should fail after MAX_RETRIES for 400 errors."""
        service = self._create_service()
        service._watchers_queue = [{"username": "u", "userid": "1", "selected": True, "retry_count": 0}]

        # Active message template
        message = MagicMock()
        message.message_id = 1
        message.body = "Hello"
        service.message_repo.get_active_messages.return_value = [message]

        # All calls return 400
        resp_400 = MagicMock()
        resp_400.status_code = 400
        resp_400.text = "Bad Request"
        resp_400.headers = {}
        post_mock.return_value = resp_400

        result = service.start_worker(access_token="token")
        assert result["success"] is True

        assert service._worker_thread is not None
        service._worker_thread.join(timeout=2)

        # Should have made MAX_RETRIES + 1 = 4 POST calls (1 initial + 3 retries)
        assert post_mock.call_count == 4

        # Should have logged 1 failure with "max retries exceeded"
        assert service.log_repo.add_log.call_count == 1
        assert service.log_repo.add_log.call_args[1]["status"].value == "failed"
        assert "max retries exceeded" in service.log_repo.add_log.call_args[1]["error_message"]

    @patch("src.service.profile_message_service.time.sleep", return_value=None)
    @patch("src.service.profile_message_service.requests.post")
    def test_worker_retries_network_error(
        self,
        post_mock: MagicMock,
        _sleep_mock: MagicMock,
    ) -> None:
        """Worker should retry network errors with exponential backoff."""
        service = self._create_service()
        service._watchers_queue = [{"username": "u", "userid": "1", "selected": True, "retry_count": 0}]

        # Active message template
        message = MagicMock()
        message.message_id = 1
        message.body = "Hello"
        service.message_repo.get_active_messages.return_value = [message]

        # First call: network error
        import requests
        post_mock.side_effect = [
            requests.ConnectionError("Connection failed"),
            MagicMock(status_code=200, json=lambda: {"commentid": "cid"}),
        ]

        result = service.start_worker(access_token="token")
        assert result["success"] is True

        assert service._worker_thread is not None
        service._worker_thread.join(timeout=2)

        # Should have made 2 POST calls (1 fail + 1 retry success)
        assert post_mock.call_count == 2

        # Should have logged 1 success
        assert service.log_repo.add_log.call_count == 1
        assert service.log_repo.add_log.call_args[1]["status"].value == "sent"

    @patch("src.service.profile_message_service.time.sleep", return_value=None)
    @patch("src.service.profile_message_service.requests.post")
    def test_worker_does_not_retry_500_error(
        self,
        post_mock: MagicMock,
        _sleep_mock: MagicMock,
    ) -> None:
        """Worker should NOT retry 500 errors (final fail)."""
        service = self._create_service()
        service._watchers_queue = [{"username": "u", "userid": "1", "selected": True, "retry_count": 0}]

        # Active message template
        message = MagicMock()
        message.message_id = 1
        message.body = "Hello"
        service.message_repo.get_active_messages.return_value = [message]

        # 500 error
        resp_500 = MagicMock()
        resp_500.status_code = 500
        resp_500.text = "Internal Server Error"
        resp_500.headers = {}
        post_mock.return_value = resp_500

        result = service.start_worker(access_token="token")
        assert result["success"] is True

        assert service._worker_thread is not None
        service._worker_thread.join(timeout=2)

        # Should have made only 1 POST call (no retry)
        assert post_mock.call_count == 1

        # Should have logged 1 failure WITHOUT "max retries exceeded"
        assert service.log_repo.add_log.call_count == 1
        assert service.log_repo.add_log.call_args[1]["status"].value == "failed"
        assert "max retries exceeded" not in service.log_repo.add_log.call_args[1]["error_message"]
