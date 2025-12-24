"""Tests for BaseWorkerService class."""
import pytest
from unittest.mock import Mock, patch
from logging import Logger

from src.service.base_worker_service import BaseWorkerService
from src.service.http_client import DeviantArtHttpClient


class ConcreteWorkerService(BaseWorkerService):
    """Concrete implementation of BaseWorkerService for testing."""

    def _validate_worker_start(self):
        """Minimal validation for testing."""
        return {"valid": True}

    def _worker_loop(self, *args, **kwargs):
        """Minimal worker loop for testing."""
        pass


class TestBaseWorkerService:
    """Test BaseWorkerService initialization and inheritance."""

    def test_initialization_inherits_from_base_service(self):
        """Test that BaseWorkerService inherits BaseService functionality."""
        logger = Mock(spec=Logger)
        token_repo = Mock()

        with patch(
            "src.service.base_service.DeviantArtHttpClient"
        ) as mock_http_client_class:
            mock_http_client = Mock(spec=DeviantArtHttpClient)
            mock_http_client_class.return_value = mock_http_client

            service = ConcreteWorkerService(
                logger=logger, token_repo=token_repo
            )

            # Verify BaseService initialization
            assert service.logger is logger
            assert service._token_repo is token_repo
            assert service.http_client is mock_http_client

    def test_initialization_creates_worker_infrastructure(self):
        """Test that worker-specific infrastructure is initialized."""
        logger = Mock(spec=Logger)

        service = ConcreteWorkerService(logger=logger)

        # Verify worker infrastructure
        assert service._worker_thread is None
        assert service._stop_flag is not None
        assert service._worker_running is False
        assert service._stats_lock is not None
        assert service._worker_stats == {
            "processed": 0,
            "errors": 0,
            "last_error": None,
            "consecutive_failures": 0,
        }

    def test_config_property_accessible(self):
        """Test that config property from BaseService is accessible."""
        logger = Mock(spec=Logger)

        with patch("src.service.base_service.get_config") as mock_get_config:
            mock_config = Mock()
            mock_get_config.return_value = mock_config

            service = ConcreteWorkerService(logger=logger)

            # Config should be accessible via inherited property
            config = service.config
            assert config is mock_config
            mock_get_config.assert_called_once()

    def test_is_worker_alive_returns_false_initially(self):
        """Test that _is_worker_alive returns False before worker starts."""
        logger = Mock(spec=Logger)
        service = ConcreteWorkerService(logger=logger)

        assert service._is_worker_alive() is False

    def test_interruptible_sleep_returns_false_without_stop(self):
        """Test that _interruptible_sleep returns False when not stopped."""
        logger = Mock(spec=Logger)
        service = ConcreteWorkerService(logger=logger)

        # Sleep for very short time
        result = service._interruptible_sleep(0.001)

        # Should return False (not interrupted)
        assert result is False

    def test_interruptible_sleep_returns_true_with_stop(self):
        """Test that _interruptible_sleep returns True when stop flag set."""
        logger = Mock(spec=Logger)
        service = ConcreteWorkerService(logger=logger)

        # Set stop flag
        service._stop_flag.set()

        # Sleep should be interrupted immediately
        result = service._interruptible_sleep(10.0)

        # Should return True (interrupted)
        assert result is True

    def test_get_worker_status_returns_default_stats(self):
        """Test that get_worker_status returns standardized status."""
        logger = Mock(spec=Logger)
        service = ConcreteWorkerService(logger=logger)

        status = service.get_worker_status()

        # Verify standard status fields
        assert status["running"] is False
        assert status["processed"] == 0
        assert status["errors"] == 0
        assert status["last_error"] is None
        assert status["consecutive_failures"] == 0

    def test_get_worker_status_syncs_running_flag(self):
        """Test that get_worker_status syncs _worker_running with thread."""
        logger = Mock(spec=Logger)
        service = ConcreteWorkerService(logger=logger)

        # Manually set running flag to True (simulating stale state)
        service._worker_running = True

        # get_worker_status should sync it back to False
        status = service.get_worker_status()

        assert status["running"] is False
        assert service._worker_running is False

    def test_get_worker_status_with_stats(self):
        """Test that get_worker_status returns updated stats."""
        logger = Mock(spec=Logger)
        service = ConcreteWorkerService(logger=logger)

        # Update stats
        with service._stats_lock:
            service._worker_stats["processed"] = 42
            service._worker_stats["errors"] = 3
            service._worker_stats["last_error"] = "Test error"
            service._worker_stats["consecutive_failures"] = 2

        status = service.get_worker_status()

        # Verify updated stats
        assert status["processed"] == 42
        assert status["errors"] == 3
        assert status["last_error"] == "Test error"
        assert status["consecutive_failures"] == 2

    def test_get_broadcast_delay_uses_config_defaults(self):
        """Test that _get_broadcast_delay uses config values by default."""
        logger = Mock(spec=Logger)

        with patch("src.service.base_service.get_config") as mock_get_config:
            mock_config = Mock()
            mock_config.broadcast_min_delay_seconds = 10
            mock_config.broadcast_max_delay_seconds = 20
            mock_get_config.return_value = mock_config

            service = ConcreteWorkerService(logger=logger)

            # Generate delay multiple times to verify range
            for _ in range(10):
                delay = service._get_broadcast_delay()
                assert 10 <= delay <= 20

    def test_get_broadcast_delay_accepts_custom_values(self):
        """Test that _get_broadcast_delay accepts custom min/max values."""
        logger = Mock(spec=Logger)
        service = ConcreteWorkerService(logger=logger)

        # Generate delay with custom values
        for _ in range(10):
            delay = service._get_broadcast_delay(min_delay=5, max_delay=8)
            assert 5 <= delay <= 8

    def test_get_broadcast_delay_logs_values(self):
        """Test that _get_broadcast_delay logs the generated delay."""
        logger = Mock(spec=Logger)

        with patch("src.service.base_service.get_config") as mock_get_config:
            mock_config = Mock()
            mock_config.broadcast_min_delay_seconds = 10
            mock_config.broadcast_max_delay_seconds = 10
            mock_get_config.return_value = mock_config

            service = ConcreteWorkerService(logger=logger)

            delay = service._get_broadcast_delay()

            # Verify logging was called with correct format and args
            logger.debug.assert_called_once()
            call_args = logger.debug.call_args[0]
            assert "Generated broadcast delay:" in call_args[0]
            assert call_args[1] == 10  # delay value
            assert call_args[2] == 10  # min_val
            assert call_args[3] == 10  # max_val
