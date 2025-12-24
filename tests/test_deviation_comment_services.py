"""Tests for deviation comment services."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from src.service.comment_collector_service import CommentCollectorService
from src.service.comment_poster_service import CommentPosterService
from src.domain.models import DeviationCommentLogStatus


@patch("src.service.api_pagination_helper.time.sleep", autospec=True)
def test_comment_collector_collects_and_sets_offset(sleep_mock: MagicMock) -> None:
    """Collector should paginate, set offset, and respect recommended delay."""
    queue_repo = MagicMock()
    log_repo = MagicMock()
    state_repo = MagicMock()
    logger = MagicMock()
    http_client = MagicMock()

    state_repo.get_state.return_value = "0"
    log_repo.get_commented_deviationids.return_value = {"skip1"}
    http_client.get_recommended_delay.return_value = 7

    resp1 = MagicMock()
    resp1.json.return_value = {
        "results": [
            {"deviationid": "skip1", "published_time": 100},
            {"deviationid": "keep1", "published_time": 101},
        ],
        "has_more": True,
        "next_offset": 50,
    }
    resp2 = MagicMock()
    resp2.json.return_value = {"results": [], "has_more": False, "next_offset": None}
    http_client.get.side_effect = [resp1, resp2]

    service = CommentCollectorService(
        queue_repo=queue_repo,
        log_repo=log_repo,
        state_repo=state_repo,
        logger=logger,
        http_client=http_client,
    )

    result = service.collect_from_watch_feed(access_token="token", max_pages=2)

    assert result["pages"] == 2
    assert result["deviations_added"] == 1
    queue_repo.add_deviation.assert_called_once()
    state_repo.set_state.assert_called_once_with("comment_watch_offset", "50")
    http_client.get_recommended_delay.assert_called_once_with()
    sleep_mock.assert_called_once_with(7)


def test_comment_poster_worker_success_logs_and_marks() -> None:
    """Worker should mark queue item commented and log success."""
    message_repo = MagicMock()
    queue_repo = MagicMock()
    log_repo = MagicMock()
    logger = MagicMock()
    http_client = MagicMock()

    # Mock config to avoid environment variable requirements
    mock_config = MagicMock()
    mock_config.broadcast_min_delay_seconds = 60
    mock_config.broadcast_max_delay_seconds = 180

    template = MagicMock()
    template.message_id = 1
    template.body = "Hello"
    template.is_active = True
    message_repo.get_active_messages.return_value = [template]

    queue_repo.get_one_pending.return_value = {
        "deviationid": "dev1",
        "deviation_url": "https://www.deviantart.com/view/1",
        "author_username": "author",
        "attempts": 0,
    }
    http_client.post.return_value = MagicMock(
        json=MagicMock(return_value={"commentid": "cid"})
    )
    http_client.get_recommended_delay.return_value = 0

    service = CommentPosterService(
        message_repo=message_repo,
        queue_repo=queue_repo,
        log_repo=log_repo,
        logger=logger,
        http_client=http_client,
    )
    service._config = mock_config
    # First call (broadcast_delay): return False to continue
    # Second call (after success): return True to stop
    service._stop_flag.wait = MagicMock(side_effect=[False, True])

    service._worker_loop(access_token="token", template_id=None)

    queue_repo.mark_commented.assert_called_once_with("dev1")
    assert log_repo.add_log.call_args.kwargs["status"] == DeviationCommentLogStatus.SENT


def test_comment_poster_non_retryable_http_error_marks_failed() -> None:
    """HTTP 400 should be treated as non-retryable and mark failed."""
    message_repo = MagicMock()
    queue_repo = MagicMock()
    log_repo = MagicMock()
    logger = MagicMock()
    http_client = MagicMock()

    # Mock config to avoid environment variable requirements
    mock_config = MagicMock()
    mock_config.broadcast_min_delay_seconds = 60
    mock_config.broadcast_max_delay_seconds = 180

    template = MagicMock()
    template.message_id = 1
    template.body = "Hello"
    template.is_active = True
    message_repo.get_active_messages.return_value = [template]

    queue_repo.get_one_pending.return_value = {
        "deviationid": "dev1",
        "deviation_url": None,
        "author_username": "author",
        "attempts": 0,
    }

    response = MagicMock()
    response.status_code = 400
    response.json.return_value = {"error": "invalid_request"}
    http_client.post.side_effect = requests.HTTPError("400", response=response)
    http_client.get_recommended_delay.return_value = 0

    service = CommentPosterService(
        message_repo=message_repo,
        queue_repo=queue_repo,
        log_repo=log_repo,
        logger=logger,
        http_client=http_client,
    )
    service._config = mock_config
    # First call (broadcast_delay): return False to continue
    # Second call (after failure): return True to stop
    service._stop_flag.wait = MagicMock(side_effect=[False, True])

    service._worker_loop(access_token="token", template_id=None)

    queue_repo.mark_failed.assert_called_once()
    assert log_repo.add_log.call_args.kwargs["status"] == DeviationCommentLogStatus.FAILED


def test_fave_deviation_success() -> None:
    """_fave_deviation should return True on successful fave."""
    message_repo = MagicMock()
    queue_repo = MagicMock()
    log_repo = MagicMock()
    logger = MagicMock()
    http_client = MagicMock()

    # Mock successful POST response
    http_client.post.return_value = MagicMock()

    service = CommentPosterService(
        message_repo=message_repo,
        queue_repo=queue_repo,
        log_repo=log_repo,
        logger=logger,
        http_client=http_client,
    )

    result = service._fave_deviation(
        access_token="test_token",
        deviationid="dev123",
    )

    assert result is True
    http_client.post.assert_called_once_with(
        service.FAVE_URL,
        data={"deviationid": "dev123", "access_token": "test_token"},
        timeout=30,
    )
    logger.info.assert_called_once()


def test_fave_deviation_failure_does_not_raise() -> None:
    """_fave_deviation should return False and log warning on error, not raise."""
    message_repo = MagicMock()
    queue_repo = MagicMock()
    log_repo = MagicMock()
    logger = MagicMock()
    http_client = MagicMock()

    # Mock HTTP error
    response = MagicMock()
    response.status_code = 400
    http_client.post.side_effect = requests.HTTPError("400", response=response)

    service = CommentPosterService(
        message_repo=message_repo,
        queue_repo=queue_repo,
        log_repo=log_repo,
        logger=logger,
        http_client=http_client,
    )

    # Should not raise exception
    result = service._fave_deviation(
        access_token="test_token",
        deviationid="dev123",
    )

    assert result is False
    logger.warning.assert_called_once()
    # Verify warning message contains deviation ID and error
    warning_call = logger.warning.call_args
    assert "dev123" in str(warning_call)


def test_fave_deviation_generic_exception_does_not_raise() -> None:
    """_fave_deviation should handle any exception gracefully."""
    message_repo = MagicMock()
    queue_repo = MagicMock()
    log_repo = MagicMock()
    logger = MagicMock()
    http_client = MagicMock()

    # Mock generic exception
    http_client.post.side_effect = Exception("Network timeout")

    service = CommentPosterService(
        message_repo=message_repo,
        queue_repo=queue_repo,
        log_repo=log_repo,
        logger=logger,
        http_client=http_client,
    )

    # Should not raise exception
    result = service._fave_deviation(
        access_token="test_token",
        deviationid="dev456",
    )

    assert result is False
    logger.warning.assert_called_once()


def test_worker_calls_fave_after_successful_comment() -> None:
    """Worker should call _fave_deviation after successful comment."""
    message_repo = MagicMock()
    queue_repo = MagicMock()
    log_repo = MagicMock()
    logger = MagicMock()
    http_client = MagicMock()

    # Mock config
    mock_config = MagicMock()
    mock_config.broadcast_min_delay_seconds = 60
    mock_config.broadcast_max_delay_seconds = 180

    template = MagicMock()
    template.message_id = 1
    template.body = "Hello"
    template.is_active = True
    message_repo.get_active_messages.return_value = [template]

    queue_repo.get_one_pending.return_value = {
        "deviationid": "dev1",
        "deviation_url": "https://www.deviantart.com/view/1",
        "author_username": "author",
        "attempts": 0,
    }
    http_client.post.return_value = MagicMock(
        json=MagicMock(return_value={"commentid": "cid"})
    )
    http_client.get_recommended_delay.return_value = 0

    service = CommentPosterService(
        message_repo=message_repo,
        queue_repo=queue_repo,
        log_repo=log_repo,
        logger=logger,
        http_client=http_client,
    )
    service._config = mock_config
    service._stop_flag.wait = MagicMock(side_effect=[False, True])

    service._worker_loop(access_token="token", template_id=None)

    # Verify http_client.post was called twice: once for comment, once for fave
    assert http_client.post.call_count == 2
    
    # First call: comment
    first_call = http_client.post.call_args_list[0]
    assert "comments/post" in first_call[0][0]
    
    # Second call: fave
    second_call = http_client.post.call_args_list[1]
    assert second_call[0][0] == service.FAVE_URL
    assert second_call[1]["data"]["deviationid"] == "dev1"
    assert second_call[1]["data"]["access_token"] == "token"


def test_comment_poster_http_500_removes_from_queue_and_logs_deleted() -> None:
    """HTTP 500 should remove item from queue and log as DELETED."""
    message_repo = MagicMock()
    queue_repo = MagicMock()
    log_repo = MagicMock()
    logger = MagicMock()
    http_client = MagicMock()

    # Mock config
    mock_config = MagicMock()
    mock_config.broadcast_min_delay_seconds = 60
    mock_config.broadcast_max_delay_seconds = 180

    template = MagicMock()
    template.message_id = 1
    template.body = "Hello"
    template.is_active = True
    message_repo.get_active_messages.return_value = [template]

    queue_item = {
        "deviationid": "dev1",
        "deviation_url": "https://www.deviantart.com/view/1",
        "author_username": "author",
        "attempts": 0,
    }
    queue_repo.get_one_pending.return_value = queue_item

    # Mock HTTP 500 error
    response = MagicMock()
    response.status_code = 500
    response.json.return_value = {
        "error": "server_error",
        "error_description": "Internal Server Error.",
        "error_code": 500,
        "status": "error",
    }
    http_error = requests.HTTPError("500 Server Error", response=response)
    http_client.post.side_effect = http_error
    http_client.get_recommended_delay.return_value = 0

    service = CommentPosterService(
        message_repo=message_repo,
        queue_repo=queue_repo,
        log_repo=log_repo,
        logger=logger,
        http_client=http_client,
    )
    # First call (broadcast_delay): return False to continue
    # Second call (after handling deleted): return True to stop
    service._stop_flag.wait = MagicMock(side_effect=[False, True])

    service._worker_loop(access_token="token", template_id=None)

    # Verify item was removed from queue
    queue_repo.remove_by_ids.assert_called_once_with(["dev1"])

    # Verify log was created with DELETED status
    assert log_repo.add_log.call_count == 1
    log_call = log_repo.add_log.call_args
    assert log_call.kwargs["status"] == DeviationCommentLogStatus.DELETED
    assert log_call.kwargs["deviationid"] == "dev1"
    assert "HTTP 500" in log_call.kwargs["error_message"]
    assert "server_error" in log_call.kwargs["error_message"]

    # Verify queue was NOT marked as failed (since it was removed)
    queue_repo.mark_failed.assert_not_called()

    # Verify worker logged warning about deleted deviation
    logger.warning.assert_called_once()
    warning_call = logger.warning.call_args
    assert "deleted" in str(warning_call).lower()
    assert "dev1" in str(warning_call)


def test_check_deviation_exists_returns_true_for_http_200() -> None:
    """_check_deviation_exists should return True when deviation exists (HTTP 200)."""
    message_repo = MagicMock()
    queue_repo = MagicMock()
    log_repo = MagicMock()
    logger = MagicMock()
    http_client = MagicMock()

    # Mock successful GET request (HTTP 200)
    http_client.get.return_value = MagicMock()

    service = CommentPosterService(
        message_repo=message_repo,
        queue_repo=queue_repo,
        log_repo=log_repo,
        logger=logger,
        http_client=http_client,
    )

    result = service._check_deviation_exists("token", "dev123")

    assert result is True
    http_client.get.assert_called_once()
    logger.debug.assert_called_once()


def test_check_deviation_exists_returns_false_for_http_404() -> None:
    """_check_deviation_exists should return False when deviation is deleted (HTTP 404)."""
    message_repo = MagicMock()
    queue_repo = MagicMock()
    log_repo = MagicMock()
    logger = MagicMock()
    http_client = MagicMock()

    # Mock HTTP 404 error
    response = MagicMock()
    response.status_code = 404
    http_error = requests.HTTPError("404 Not Found", response=response)
    http_client.get.side_effect = http_error

    service = CommentPosterService(
        message_repo=message_repo,
        queue_repo=queue_repo,
        log_repo=log_repo,
        logger=logger,
        http_client=http_client,
    )

    result = service._check_deviation_exists("token", "dev123")

    assert result is False
    logger.debug.assert_called_once()


def test_check_deviation_exists_returns_false_for_http_500() -> None:
    """_check_deviation_exists should return False when deviation is deleted (HTTP 500)."""
    message_repo = MagicMock()
    queue_repo = MagicMock()
    log_repo = MagicMock()
    logger = MagicMock()
    http_client = MagicMock()

    # Mock HTTP 500 error
    response = MagicMock()
    response.status_code = 500
    http_error = requests.HTTPError("500 Server Error", response=response)
    http_client.get.side_effect = http_error

    service = CommentPosterService(
        message_repo=message_repo,
        queue_repo=queue_repo,
        log_repo=log_repo,
        logger=logger,
        http_client=http_client,
    )

    result = service._check_deviation_exists("token", "dev123")

    assert result is False
    logger.debug.assert_called_once()


def test_check_deviation_exists_returns_true_for_other_errors() -> None:
    """_check_deviation_exists should return True for temporary errors (network, timeout)."""
    message_repo = MagicMock()
    queue_repo = MagicMock()
    log_repo = MagicMock()
    logger = MagicMock()
    http_client = MagicMock()

    # Mock network error
    http_client.get.side_effect = Exception("Network timeout")

    service = CommentPosterService(
        message_repo=message_repo,
        queue_repo=queue_repo,
        log_repo=log_repo,
        logger=logger,
        http_client=http_client,
    )

    result = service._check_deviation_exists("token", "dev123")

    assert result is True
    logger.warning.assert_called_once()


def test_worker_skips_deleted_deviation_without_broadcast_delay() -> None:
    """Worker should skip deleted deviations immediately without waiting for broadcast_delay."""
    message_repo = MagicMock()
    queue_repo = MagicMock()
    log_repo = MagicMock()
    logger = MagicMock()
    http_client = MagicMock()

    # Mock config
    mock_config = MagicMock()
    mock_config.broadcast_min_delay_seconds = 120
    mock_config.broadcast_max_delay_seconds = 240

    template = MagicMock()
    template.message_id = 1
    template.body = "Hello"
    template.is_active = True
    message_repo.get_active_messages.return_value = [template]

    queue_item = {
        "deviationid": "dev1",
        "deviation_url": "https://www.deviantart.com/view/1",
        "author_username": "author",
        "attempts": 0,
    }
    # First call returns queue_item, subsequent calls return None
    # Need multiple None because loop continues after handling deleted deviation
    queue_repo.get_one_pending.side_effect = [queue_item, None, None, None]

    # Mock _check_deviation_exists to return False (deviation deleted)
    response = MagicMock()
    response.status_code = 404
    http_error = requests.HTTPError("404 Not Found", response=response)
    http_client.get.side_effect = http_error
    http_client.get_recommended_delay.return_value = 0

    service = CommentPosterService(
        message_repo=message_repo,
        queue_repo=queue_repo,
        log_repo=log_repo,
        logger=logger,
        http_client=http_client,
    )
    # Mock _stop_flag.wait: return False first time (continue loop), True second time (stop loop)
    service._stop_flag.wait = MagicMock(side_effect=[False, True])

    service._worker_loop(access_token="token", template_id=None)

    # Verify deviation was removed from queue
    queue_repo.remove_by_ids.assert_called_once_with(["dev1"])

    # Verify log was created with DELETED status
    assert log_repo.add_log.call_count == 1
    log_call = log_repo.add_log.call_args
    assert log_call.kwargs["status"] == DeviationCommentLogStatus.DELETED

    # Verify http_client.post was NEVER called (no comment attempt)
    # This proves that worker skipped deleted deviation without trying to comment
    http_client.post.assert_not_called()
    
    # Verify http_client.get was called (deviation existence check)
    http_client.get.assert_called_once()
