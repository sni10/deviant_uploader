"""Tests for FeedDeviationRepository.

These tests cover both execution paths:
- SQLAlchemy Core executed via SQLAlchemy Session (preferred)
- SQLAlchemy Core compiled to SQL string executed via sqlite3 adapter
"""

from __future__ import annotations

import os
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.storage.adapters import SQLiteAdapter
from src.storage.adapters.sqlalchemy_adapter import SQLAlchemyConnection
from src.storage.feed_deviation_repository import FeedDeviationRepository
from src.storage.feed_tables import metadata as feed_metadata


class TestFeedDeviationRepository:
    """Test FeedDeviationRepository behavior."""

    def test_get_stats_sqlalchemy_session(self):
        """Return correct stats when executed via SQLAlchemy Session."""
        engine = create_engine("sqlite:///:memory:")
        feed_metadata.create_all(engine)

        SessionFactory = sessionmaker(bind=engine)
        session = SessionFactory()
        try:
            conn = SQLAlchemyConnection(session)
            repo = FeedDeviationRepository(conn)

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
        finally:
            session.close()

    def test_get_stats_sqlite_adapter_cursor(self):
        """Return correct stats when executed via sqlite3 adapter cursor."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            adapter = SQLiteAdapter(db_path)
            adapter.initialize()

            conn = adapter.get_connection()
            try:
                repo = FeedDeviationRepository(conn)

                repo.add_deviation("dev-1", ts=100)
                repo.add_deviation("dev-2", ts=200)
                repo.mark_faved("dev-2")

                stats = repo.get_stats()

                assert stats["pending"] == 1
                assert stats["faved"] == 1
                assert stats["failed"] == 0
                assert stats["total"] == 2
            finally:
                conn.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
