"""Tests for critical error detection in worker services."""
import json
from unittest.mock import Mock, patch, MagicMock
import pytest
import requests

from src.service.comment_poster_service import CommentPosterService
from src.service.profile_message_service import ProfileMessageService


@pytest.fixture(autouse=True)
def mock_config():
    """Mock get_config() to avoid requiring environment variables in tests."""
    mock_cfg = Mock()
    with patch("src.service.base_service.get_config", return_value=mock_cfg):
        yield mock_cfg


class TestCommentPosterCriticalErrors:
    """Test critical error detection in CommentPosterService."""

    def test_is_critical_error_spam_detection(self):
        """Test that spam errors are detected as critical."""
        service = CommentPosterService(
            queue_repo=Mock(),
            log_repo=Mock(),
            message_repo=Mock(),
            http_client=Mock(),
            logger=Mock(),
        )

        # Create mock HTTP error with spam message
        response = Mock()
        response.json.return_value = {
            "error": "invalid_request",
            "error_description": "Couldn't post the comment, since the system thinks it's spam.",
            "error_code": 400,
            "status": "error"
        }
        response.status_code = 400

        error = requests.HTTPError()
        error.response = response

        assert service._is_critical_error(error) is True

    def test_is_critical_error_banned_account(self):
        """Test that banned account errors are detected as critical."""
        service = CommentPosterService(
            queue_repo=Mock(),
            log_repo=Mock(),
            message_repo=Mock(),
            http_client=Mock(),
            logger=Mock(),
        )

        response = Mock()
        response.json.return_value = {
            "error": "access_denied",
            "error_description": "Your account has been banned.",
            "error_code": 403
        }
        response.status_code = 403

        error = requests.HTTPError()
        error.response = response

        assert service._is_critical_error(error) is True

    def test_is_critical_error_suspended_account(self):
        """Test that suspended account errors are detected as critical."""
        service = CommentPosterService(
            queue_repo=Mock(),
            log_repo=Mock(),
            message_repo=Mock(),
            http_client=Mock(),
            logger=Mock(),
        )

        response = Mock()
        response.json.return_value = {
            "error": "access_denied",
            "error_description": "Account suspended due to policy violation.",
            "error_code": 403
        }
        response.status_code = 403

        error = requests.HTTPError()
        error.response = response

        assert service._is_critical_error(error) is True

    def test_is_critical_error_abuse_detection(self):
        """Test that abuse/violation errors are detected as critical."""
        service = CommentPosterService(
            queue_repo=Mock(),
            log_repo=Mock(),
            message_repo=Mock(),
            http_client=Mock(),
            logger=Mock(),
        )

        response = Mock()
        response.json.return_value = {
            "error": "rate_limit_exceeded",
            "error_description": "Rate limit abuse detected.",
            "error_code": 429
        }
        response.status_code = 429

        error = requests.HTTPError()
        error.response = response

        assert service._is_critical_error(error) is True

    def test_is_critical_error_normal_error(self):
        """Test that normal errors are not detected as critical."""
        service = CommentPosterService(
            queue_repo=Mock(),
            log_repo=Mock(),
            message_repo=Mock(),
            http_client=Mock(),
            logger=Mock(),
        )

        response = Mock()
        response.json.return_value = {
            "error": "not_found",
            "error_description": "Deviation not found.",
            "error_code": 404
        }
        response.status_code = 404

        error = requests.HTTPError()
        error.response = response

        assert service._is_critical_error(error) is False

    def test_is_critical_error_no_response(self):
        """Test that errors without response are not critical."""
        service = CommentPosterService(
            queue_repo=Mock(),
            log_repo=Mock(),
            message_repo=Mock(),
            http_client=Mock(),
            logger=Mock(),
        )

        error = requests.HTTPError()
        error.response = None

        assert service._is_critical_error(error) is False

    def test_is_critical_error_invalid_json(self):
        """Test that errors with invalid JSON are not critical."""
        service = CommentPosterService(
            queue_repo=Mock(),
            log_repo=Mock(),
            message_repo=Mock(),
            http_client=Mock(),
            logger=Mock(),
        )

        response = Mock()
        response.json.side_effect = ValueError("Invalid JSON")
        response.status_code = 500

        error = requests.HTTPError()
        error.response = response

        assert service._is_critical_error(error) is False


class TestProfileMessageCriticalErrors:
    """Test critical error detection in ProfileMessageService."""

    def test_is_critical_error_spam_detection(self):
        """Test that spam errors are detected as critical."""
        service = ProfileMessageService(
            message_repo=Mock(),
            log_repo=Mock(),
            queue_repo=Mock(),
            watcher_repo=Mock(),
            http_client=Mock(),
            logger=Mock(),
        )

        # Create mock HTTP error with spam message
        response = Mock()
        response.json.return_value = {
            "error": "invalid_request",
            "error_description": "Couldn't post the comment, since the system thinks it's spam.",
            "error_code": 400,
            "status": "error"
        }
        response.status_code = 400

        error = requests.HTTPError()
        error.response = response

        assert service._is_critical_error(error) is True

    def test_is_critical_error_normal_error(self):
        """Test that normal errors are not detected as critical."""
        service = ProfileMessageService(
            message_repo=Mock(),
            log_repo=Mock(),
            queue_repo=Mock(),
            watcher_repo=Mock(),
            http_client=Mock(),
            logger=Mock(),
        )

        response = Mock()
        response.json.return_value = {
            "error": "not_found",
            "error_description": "User not found.",
            "error_code": 404
        }
        response.status_code = 404

        error = requests.HTTPError()
        error.response = response

        assert service._is_critical_error(error) is False

    def test_format_http_error_with_details(self):
        """Test HTTP error formatting with full details."""
        service = ProfileMessageService(
            message_repo=Mock(),
            log_repo=Mock(),
            queue_repo=Mock(),
            watcher_repo=Mock(),
            http_client=Mock(),
            logger=Mock(),
        )

        response = Mock()
        response.json.return_value = {
            "error": "invalid_request",
            "error_description": "Spam detected",
            "error_code": 400
        }
        response.status_code = 400

        error = requests.HTTPError()
        error.response = response

        formatted = service._format_http_error(error)
        assert "HTTP 400" in formatted
        assert "invalid_request" in formatted
        assert "code=400" in formatted
        assert "Spam detected" in formatted

    def test_format_http_error_no_response(self):
        """Test HTTP error formatting without response."""
        service = ProfileMessageService(
            message_repo=Mock(),
            log_repo=Mock(),
            queue_repo=Mock(),
            watcher_repo=Mock(),
            http_client=Mock(),
            logger=Mock(),
        )

        error = requests.HTTPError("Connection failed")
        error.response = None

        formatted = service._format_http_error(error)
        assert "Connection failed" in formatted
