"""Tests for deviation comment services."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from src.service.comment_collector_service import CommentCollectorService
from src.service.comment_poster_service import CommentPosterService
from src.domain.models import DeviationCommentLogStatus


@patch("src.service.comment_collector_service.time.sleep", autospec=True)
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
        config=mock_config,
    )
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
        config=mock_config,
    )
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
        config=mock_config,
    )
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
