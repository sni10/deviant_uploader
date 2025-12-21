"""Tests for FeedDeviationRepository (PostgreSQL-only)."""

from __future__ import annotations
from src.storage.feed_deviation_repository import FeedDeviationRepository
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
