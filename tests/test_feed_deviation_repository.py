"""Tests for FeedDeviationRepository (PostgreSQL-only)."""

from __future__ import annotations

from sqlalchemy import select

from src.storage.feed_deviation_repository import FeedDeviationRepository
from src.storage.feed_tables import feed_deviations


class TestFeedDeviationRepository:
    """Test FeedDeviationRepository behavior."""

    def test_get_stats(self, db_conn):
        """Return correct stats when executed via SQLAlchemy/PostgreSQL."""

        repo = FeedDeviationRepository(db_conn)

        repo.add_deviation("dev-1", ts=100)
        repo.add_deviation("dev-2", ts=200)
        repo.add_deviation("dev-3", ts=300)
        repo.mark_faved("dev-2")
        repo.mark_failed("dev-3", error="boom")

        stats = repo.get_stats()

        assert stats == {
            "pending": 1,
            "faved": 1,
            "failed": 1,
            "total": 3,
        }

    def test_set_state_upsert(self, db_conn):
        """Set state should overwrite existing key without errors."""

        repo = FeedDeviationRepository(db_conn)

        repo.set_state("feed_offset", "1")
        repo.set_state("feed_offset", "2")

        assert repo.get_state("feed_offset") == "2"

    def test_add_deviation_updates_ts_by_max_and_preserves_status(self, db_conn):
        """Repeated add_deviation keeps ts=max(existing, incoming) and doesn't reset status."""

        repo = FeedDeviationRepository(db_conn)

        repo.add_deviation("dev-1", ts=100)
        repo.mark_faved("dev-1")

        # Should not reduce ts
        repo.add_deviation("dev-1", ts=50)

        # Should increase ts
        repo.add_deviation("dev-1", ts=200)

        row = repo._execute_core(
            select(
                feed_deviations.c.deviationid,
                feed_deviations.c.ts,
                feed_deviations.c.status,
            ).where(feed_deviations.c.deviationid == "dev-1")
        ).fetchone()

        assert row[0] == "dev-1"
        assert row[1] == 200
        assert row[2] == "faved"
