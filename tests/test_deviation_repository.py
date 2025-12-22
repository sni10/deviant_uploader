"""Tests for DeviationRepository (PostgreSQL-only)."""

from __future__ import annotations

from datetime import datetime

from src.domain.models import Deviation, UploadStatus
from src.storage.deviation_repository import DeviationRepository


class TestDeviationRepository:
    """Test DeviationRepository upsert behavior."""

    def test_save_deviation_upserts_by_filename_and_preserves_created_at(self, db_conn):
        """Saving the same filename twice should update fields without UniqueViolation."""

        repo = DeviationRepository(db_conn)

        d1 = Deviation(
            filename="same.png",
            title="first",
            file_path="C:/tmp/first.png",
            status=UploadStatus.DRAFT,
            created_at=datetime(2020, 1, 1, 0, 0, 0),
        )
        id1 = repo.save_deviation(d1)

        d2 = Deviation(
            filename="same.png",
            title="second",
            file_path="C:/tmp/second.png",
            status=UploadStatus.PUBLISHED,
            created_at=datetime(2025, 1, 1, 0, 0, 0),
        )
        id2 = repo.save_deviation(d2)

        assert id2 == id1

        stored = repo.get_deviation_by_filename("same.png")
        assert stored is not None
        assert stored.deviation_id == id1
        assert stored.title == "second"
        assert stored.file_path == "C:/tmp/second.png"
        assert stored.status == UploadStatus.PUBLISHED

        # created_at comes from the first insert; on conflict we don't overwrite it.
        assert stored.created_at == datetime(2020, 1, 1, 0, 0, 0)
