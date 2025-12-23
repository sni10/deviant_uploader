"""Tests for DeviantArtHttpClient expired token detection and cleanup."""

from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from src.service.http_client import DeviantArtHttpClient


class TestExpiredTokenDetection:
    """Test expired token detection and automatic cleanup."""

    def test_is_expired_token_response_detects_expired_token(self) -> None:
        """_is_expired_token_response should detect expired token error."""
        response = Mock()
        response.status_code = 401
        response.json.return_value = {
            "error": "invalid_token",
            "error_description": "Expired oAuth2 user token. The client should request a new one with an access code or a refresh token.",
            "status": "error",
        }

        result = DeviantArtHttpClient._is_expired_token_response(response)

        assert result is True

    def test_is_expired_token_response_case_insensitive(self) -> None:
        """_is_expired_token_response should be case-insensitive."""
        response = Mock()
        response.status_code = 401
        response.json.return_value = {
            "error": "invalid_token",
            "error_description": "EXPIRED OAUTH2 USER TOKEN. Please re-authenticate.",
            "status": "error",
        }

        result = DeviantArtHttpClient._is_expired_token_response(response)

        assert result is True

    def test_is_expired_token_response_ignores_other_401_errors(self) -> None:
        """_is_expired_token_response should ignore other 401 errors."""
        response = Mock()
        response.status_code = 401
        response.json.return_value = {
            "error": "unauthorized",
            "error_description": "Invalid credentials",
            "status": "error",
        }

        result = DeviantArtHttpClient._is_expired_token_response(response)

        assert result is False

    def test_is_expired_token_response_ignores_non_401_status(self) -> None:
        """_is_expired_token_response should ignore non-401 status codes."""
        response = Mock()
        response.status_code = 400
        response.json.return_value = {
            "error": "invalid_token",
            "error_description": "Expired oAuth2 user token",
            "status": "error",
        }

        result = DeviantArtHttpClient._is_expired_token_response(response)

        assert result is False

    def test_is_expired_token_response_handles_invalid_json(self) -> None:
        """_is_expired_token_response should handle invalid JSON gracefully."""
        response = Mock()
        response.status_code = 401
        response.json.side_effect = ValueError("Invalid JSON")

        result = DeviantArtHttpClient._is_expired_token_response(response)

        assert result is False

    @patch("src.service.http_client.requests.request")
    def test_expired_token_triggers_deletion_on_error(
        self, mock_request: MagicMock
    ) -> None:
        """HTTP client should delete token when expired token is detected."""
        logger = MagicMock()
        token_repo = MagicMock()

        # Mock response with expired token error
        response = Mock()
        response.status_code = 401
        response.text = '{"error":"invalid_token","error_description":"Expired oAuth2 user token"}'
        response.json.return_value = {
            "error": "invalid_token",
            "error_description": "Expired oAuth2 user token. The client should request a new one.",
            "status": "error",
        }
        response.raise_for_status.side_effect = requests.HTTPError(
            "401 Client Error", response=response
        )
        mock_request.return_value = response

        client = DeviantArtHttpClient(
            logger=logger, enable_retry=True, token_repo=token_repo
        )

        # Should raise HTTPError after deleting token
        with pytest.raises(requests.HTTPError):
            client.get("https://api.example.com/test")

        # Verify token was deleted
        token_repo.delete_token.assert_called_once()

        # Verify CRITICAL log was written
        assert any(
            "EXPIRED TOKEN DETECTED" in str(call)
            for call in logger.critical.call_args_list
        )

    @patch("src.service.http_client.requests.request")
    def test_expired_token_logs_critical_without_token_repo(
        self, mock_request: MagicMock
    ) -> None:
        """HTTP client should log CRITICAL even without token_repo."""
        logger = MagicMock()

        # Mock response with expired token error
        response = Mock()
        response.status_code = 401
        response.text = '{"error":"invalid_token","error_description":"Expired oAuth2 user token"}'
        response.json.return_value = {
            "error": "invalid_token",
            "error_description": "Expired oAuth2 user token. The client should request a new one.",
            "status": "error",
        }
        response.raise_for_status.side_effect = requests.HTTPError(
            "401 Client Error", response=response
        )
        mock_request.return_value = response

        client = DeviantArtHttpClient(
            logger=logger, enable_retry=True, token_repo=None
        )

        # Should raise HTTPError
        with pytest.raises(requests.HTTPError):
            client.get("https://api.example.com/test")

        # Verify CRITICAL log was written even without token_repo
        assert any(
            "EXPIRED TOKEN DETECTED" in str(call)
            for call in logger.critical.call_args_list
        )

    @patch("src.service.http_client.requests.request")
    def test_expired_token_handles_deletion_error_gracefully(
        self, mock_request: MagicMock
    ) -> None:
        """HTTP client should handle token deletion errors gracefully."""
        logger = MagicMock()
        token_repo = MagicMock()
        token_repo.delete_token.side_effect = Exception("Database error")

        # Mock response with expired token error
        response = Mock()
        response.status_code = 401
        response.text = '{"error":"invalid_token","error_description":"Expired oAuth2 user token"}'
        response.json.return_value = {
            "error": "invalid_token",
            "error_description": "Expired oAuth2 user token. The client should request a new one.",
            "status": "error",
        }
        response.raise_for_status.side_effect = requests.HTTPError(
            "401 Client Error", response=response
        )
        mock_request.return_value = response

        client = DeviantArtHttpClient(
            logger=logger, enable_retry=True, token_repo=token_repo
        )

        # Should still raise HTTPError even if deletion fails
        with pytest.raises(requests.HTTPError):
            client.get("https://api.example.com/test")

        # Verify deletion was attempted
        token_repo.delete_token.assert_called_once()

        # Verify error was logged
        assert any(
            "Failed to delete expired token" in str(call)
            for call in logger.error.call_args_list
        )

    @patch("src.service.http_client.requests.request")
    def test_expired_token_detection_in_http_error_path(
        self, mock_request: MagicMock
    ) -> None:
        """Expired token should be detected in HTTPError exception path."""
        logger = MagicMock()
        token_repo = MagicMock()

        # Mock response with expired token error that raises immediately
        response = Mock()
        response.status_code = 401
        response.text = '{"error":"invalid_token","error_description":"Expired oAuth2 user token"}'
        response.json.return_value = {
            "error": "invalid_token",
            "error_description": "Expired oAuth2 user token. The client should request a new one.",
            "status": "error",
        }

        # Simulate HTTPError being raised
        http_error = requests.HTTPError("401 Client Error", response=response)
        mock_request.side_effect = http_error

        client = DeviantArtHttpClient(
            logger=logger, enable_retry=True, token_repo=token_repo
        )

        # Should raise HTTPError after deleting token
        with pytest.raises(requests.HTTPError):
            client.get("https://api.example.com/test")

        # Verify token was deleted
        token_repo.delete_token.assert_called_once()

        # Verify CRITICAL log was written
        assert any(
            "EXPIRED TOKEN DETECTED" in str(call)
            for call in logger.critical.call_args_list
        )
