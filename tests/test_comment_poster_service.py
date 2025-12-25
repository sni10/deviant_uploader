"""Tests for CommentPosterService behavior."""

from __future__ import annotations

from logging import Logger
from unittest.mock import MagicMock, patch

from src.service.base_worker_service import BaseWorkerService
from src.service.comment_poster_service import CommentPosterService


def _create_service() -> CommentPosterService:
    """Create CommentPosterService with mocked repositories."""
    message_repo = MagicMock()
    queue_repo = MagicMock()
    log_repo = MagicMock()
    logger = MagicMock(spec=Logger)

    return CommentPosterService(
        message_repo=message_repo,
        queue_repo=queue_repo,
        log_repo=log_repo,
        logger=logger,
    )


def test_comment_poster_start_worker_passes_auth_service() -> None:
    """Pass auth_service to base start_worker without error."""
    service = _create_service()
    auth_service = MagicMock()

    with patch.object(
        BaseWorkerService,
        "start_worker",
        autospec=True,
        return_value={"success": True, "message": "Worker started"},
    ) as start_worker:
        result = service.start_worker(
            "token",
            auth_service=auth_service,
        )

    start_worker.assert_called_once_with(
        service,
        "token",
        None,
        auth_service=auth_service,
    )
    assert result["success"] is True
