"""Tests for BaseWorkerService class."""
import pytest
from unittest.mock import Mock, patch
from logging import Logger
import requests

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

    def test_is_expired_token_error_detects_invalid_token(self):
        """Test that expired token error is correctly detected."""
        logger = Mock(spec=Logger)
        service = ConcreteWorkerService(logger=logger)

        # Create mock HTTP error with expired token response
        response = Mock()
        response.status_code = 401
        response.json.return_value = {
            "error": "invalid_token",
            "error_description": "Expired oAuth2 user token",
        }

        error = requests.HTTPError()
        error.response = response

        assert service._is_expired_token_error(error) is True

    def test_is_expired_token_error_detects_expired_in_description(self):
        """Test that expired token is detected from error description."""
        logger = Mock(spec=Logger)
        service = ConcreteWorkerService(logger=logger)

        response = Mock()
        response.status_code = 401
        response.json.return_value = {
            "error": "token_error",
            "error_description": "Token has expired",
        }

        error = requests.HTTPError()
        error.response = response

        assert service._is_expired_token_error(error) is True

    def test_is_expired_token_error_ignores_other_401_errors(self):
        """Test that other 401 errors are not detected as expired token."""
        logger = Mock(spec=Logger)
        service = ConcreteWorkerService(logger=logger)

        response = Mock()
        response.status_code = 401
        response.json.return_value = {
            "error": "unauthorized",
            "error_description": "Access denied",
        }

        error = requests.HTTPError()
        error.response = response

        assert service._is_expired_token_error(error) is False

    def test_is_expired_token_error_ignores_non_401_status(self):
        """Test that non-401 errors are not detected as expired token."""
        logger = Mock(spec=Logger)
        service = ConcreteWorkerService(logger=logger)

        response = Mock()
        response.status_code = 403
        response.json.return_value = {
            "error": "invalid_token",
            "error_description": "Expired oAuth2 user token",
        }

        error = requests.HTTPError()
        error.response = response

        assert service._is_expired_token_error(error) is False

    def test_is_expired_token_error_handles_no_response(self):
        """Test that error without response is not detected as expired token."""
        logger = Mock(spec=Logger)
        service = ConcreteWorkerService(logger=logger)

        error = requests.HTTPError()
        error.response = None

        assert service._is_expired_token_error(error) is False

    def test_refresh_access_token_success(self):
        """Test successful token refresh."""
        logger = Mock(spec=Logger)
        service = ConcreteWorkerService(logger=logger)

        # Mock auth service
        mock_auth_service = Mock()
        mock_auth_service.ensure_authenticated.return_value = True
        mock_auth_service.get_valid_token.return_value = "new_token_123"

        service._auth_service = mock_auth_service

        # Refresh token
        new_token = service._refresh_access_token()

        assert new_token == "new_token_123"
        mock_auth_service.ensure_authenticated.assert_called_once()
        mock_auth_service.get_valid_token.assert_called_once()
        logger.info.assert_any_call("Attempting to refresh expired OAuth token...")
        logger.info.assert_any_call("Successfully refreshed OAuth token")

    def test_refresh_access_token_authentication_fails(self):
        """Test token refresh when authentication fails."""
        logger = Mock(spec=Logger)
        service = ConcreteWorkerService(logger=logger)

        # Mock auth service with authentication failure
        mock_auth_service = Mock()
        mock_auth_service.ensure_authenticated.return_value = False

        service._auth_service = mock_auth_service

        # Refresh token
        new_token = service._refresh_access_token()

        assert new_token is None
        logger.error.assert_called_once_with("Token refresh failed: authentication failed")

    def test_refresh_access_token_get_valid_token_fails(self):
        """Test token refresh when get_valid_token returns None."""
        logger = Mock(spec=Logger)
        service = ConcreteWorkerService(logger=logger)

        # Mock auth service with valid authentication but no token
        mock_auth_service = Mock()
        mock_auth_service.ensure_authenticated.return_value = True
        mock_auth_service.get_valid_token.return_value = None

        service._auth_service = mock_auth_service

        # Refresh token
        new_token = service._refresh_access_token()

        assert new_token is None
        logger.error.assert_called_once_with(
            "Token refresh failed: could not get valid token"
        )

    def test_refresh_access_token_no_auth_service(self):
        """Test token refresh when auth_service not provided."""
        logger = Mock(spec=Logger)
        service = ConcreteWorkerService(logger=logger)

        # No auth service set
        service._auth_service = None

        # Refresh token
        new_token = service._refresh_access_token()

        assert new_token is None
        logger.error.assert_called_once_with(
            "Cannot refresh token: auth_service not provided to start_worker()"
        )

    def test_refresh_access_token_exception_handling(self):
        """Test token refresh exception handling."""
        logger = Mock(spec=Logger)
        service = ConcreteWorkerService(logger=logger)

        # Mock auth service that raises exception
        mock_auth_service = Mock()
        mock_auth_service.ensure_authenticated.side_effect = Exception("Network error")

        service._auth_service = mock_auth_service

        # Refresh token
        new_token = service._refresh_access_token()

        assert new_token is None
        logger.error.assert_called()
        args = logger.error.call_args[0]
        assert "Token refresh failed with exception" in args[0]

    def test_start_worker_stores_auth_service(self):
        """Test that start_worker stores auth_service for token refresh."""
        logger = Mock(spec=Logger)
        service = ConcreteWorkerService(logger=logger)

        # Mock auth service
        mock_auth_service = Mock()

        # Mock _validate_worker_start to succeed
        with patch.object(service, "_validate_worker_start", return_value={"valid": True}):
            # Mock _worker_loop to avoid thread issues
            with patch.object(service, "_worker_loop"):
                # Call start_worker with auth_service
                result = service.start_worker("test_token", auth_service=mock_auth_service)

        # Verify auth_service was stored
        assert service._auth_service is mock_auth_service
        assert result["success"] is True
