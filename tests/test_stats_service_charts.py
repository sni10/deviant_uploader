"""Regression tests for StatsService chart queries on PostgreSQL.

These tests ensure that chart queries:
- do not use SQLite-specific `?` placeholders
- pass parameters to SQLAlchemy as dicts (not lists/tuples)
- use PostgreSQL-compatible date filtering
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from src.service.stats_service import StatsService
from src.storage.deviation_metadata_repository import DeviationMetadataRepository
from src.storage.deviation_repository import DeviationRepository
from src.storage.deviation_stats_repository import DeviationStatsRepository
from src.storage.stats_snapshot_repository import StatsSnapshotRepository
from src.storage.user_stats_snapshot_repository import UserStatsSnapshotRepository


def _make_service(db_conn) -> StatsService:
    logger = logging.getLogger("test")
    return StatsService(
        deviation_stats_repository=DeviationStatsRepository(db_conn),
        stats_snapshot_repository=StatsSnapshotRepository(db_conn),
        user_stats_snapshot_repository=UserStatsSnapshotRepository(db_conn),
        deviation_metadata_repository=DeviationMetadataRepository(db_conn),
        deviation_repository=DeviationRepository(db_conn),
        logger=logger,
    )


def test_get_aggregated_stats_no_filter(db_conn):
    service = _make_service(db_conn)
    snapshots = StatsSnapshotRepository(db_conn)

    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    snapshots.save_snapshot("dev-a", today, views=10, favourites=2, comments=1)
    snapshots.save_snapshot("dev-b", today, views=5, favourites=1, comments=0)
    snapshots.save_snapshot("dev-a", yesterday, views=7, favourites=0, comments=2)

    data = service.get_aggregated_stats(period_days=7, deviation_ids=None)

    assert data["labels"] == [yesterday, today]
    assert data["datasets"]["views"] == [7, 15]
    assert data["datasets"]["favourites"] == [0, 3]
    assert data["datasets"]["comments"] == [2, 1]


def test_get_aggregated_stats_with_deviation_filter(db_conn):
    service = _make_service(db_conn)
    snapshots = StatsSnapshotRepository(db_conn)

    today = date.today().isoformat()
    snapshots.save_snapshot("dev-a", today, views=10, favourites=2, comments=1)
    snapshots.save_snapshot("dev-b", today, views=5, favourites=1, comments=0)

    data = service.get_aggregated_stats(period_days=7, deviation_ids=["dev-b"])
    assert data["labels"] == [today]
    assert data["datasets"]["views"] == [5]
    assert data["datasets"]["favourites"] == [1]
    assert data["datasets"]["comments"] == [0]


def test_get_user_watchers_history(db_conn):
    service = _make_service(db_conn)
    repo = UserStatsSnapshotRepository(db_conn)

    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    repo.save_user_stats_snapshot(
        user_id=None,
        username="aiviso",
        snapshot_date=yesterday,
        watchers=100,
        friends=10,
    )
    repo.save_user_stats_snapshot(
        user_id=None,
        username="aiviso",
        snapshot_date=today,
        watchers=105,
        friends=10,
    )

    data = service.get_user_watchers_history("aiviso", period_days=7)
    assert data["labels"] == [yesterday, today]
    assert data["datasets"]["watchers"] == [100, 105]
    assert data["datasets"]["friends"] == [10, 10]
