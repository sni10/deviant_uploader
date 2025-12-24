"""Tests for StatsService worker integration."""

from __future__ import annotations

from logging import Logger
from unittest.mock import MagicMock

from src.service.base_worker_service import BaseWorkerService
from src.service.stats_service import StatsService


def _create_service(*, gallery_repo=MagicMock()) -> StatsService:
    """Create StatsService with mocked repositories."""
    deviation_stats_repo = MagicMock()
    stats_snapshot_repo = MagicMock()
    user_stats_snapshot_repo = MagicMock()
    deviation_metadata_repo = MagicMock()
    deviation_repo = MagicMock()
    logger = MagicMock(spec=Logger)

    return StatsService(
        deviation_stats_repository=deviation_stats_repo,
        stats_snapshot_repository=stats_snapshot_repo,
        user_stats_snapshot_repository=user_stats_snapshot_repo,
        deviation_metadata_repository=deviation_metadata_repo,
        deviation_repository=deviation_repo,
        logger=logger,
        gallery_repository=gallery_repo,
    )


def test_stats_service_inherits_base_worker_service() -> None:
    """Ensure StatsService uses BaseWorkerService."""
    assert issubclass(StatsService, BaseWorkerService)


def test_stats_service_get_worker_status_includes_standard_fields() -> None:
    """Return standard worker fields plus gallery-specific stats."""
    service = _create_service()
    status = service.get_worker_status()

    for key in (
        "running",
        "processed",
        "errors",
        "last_error",
        "consecutive_failures",
        "processed_galleries",
        "processed_deviations",
        "current_gallery",
    ):
        assert key in status

    assert status["processed_galleries"] == 0
    assert status["processed_deviations"] == 0
    assert status["current_gallery"] is None


def test_stats_service_start_worker_requires_gallery_repo() -> None:
    """Reject worker start without a gallery repository."""
    service = _create_service(gallery_repo=None)

    result = service.start_worker("token")

    assert result["success"] is False
    assert "Gallery repository" in result["message"]
