"""Tests for StatsSnapshotRepository.

Following TDD approach: these tests are written before implementation
to drive the design of the new repository.
"""
import pytest
from src.storage.stats_snapshot_repository import StatsSnapshotRepository


@pytest.fixture
def repo(db_conn):
    """Create a StatsSnapshotRepository instance for testing."""

    return StatsSnapshotRepository(db_conn)


class TestStatsSnapshotRepository:
    """Test StatsSnapshotRepository for stats_snapshots table operations."""

    def test_save_snapshot_creates_new_record(self, repo):
        """Test saving new snapshot creates a record."""
        rowid = repo.save_snapshot(
            deviationid="DEV-123",
            snapshot_date="2024-01-15",
            views=100,
            favourites=10,
            comments=5,
        )
        
        assert rowid > 0

    def test_save_snapshot_updates_existing_record(self, repo):
        """Test saving snapshot twice for same date updates the record."""
        # First save
        repo.save_snapshot(
            deviationid="DEV-123",
            snapshot_date="2024-01-15",
            views=100,
            favourites=10,
            comments=5,
        )
        
        # Second save with updated values (same date)
        repo.save_snapshot(
            deviationid="DEV-123",
            snapshot_date="2024-01-15",
            views=150,
            favourites=15,
            comments=8,
        )
        
        # Verify only one record exists with updated values
        snapshots = repo.get_snapshots_for_deviation("DEV-123")
        assert len(snapshots) == 1
        assert snapshots[0]["views"] == 150
        assert snapshots[0]["favourites"] == 15
        assert snapshots[0]["comments"] == 8

    def test_save_snapshot_allows_multiple_dates(self, repo):
        """Test saving snapshots for different dates creates multiple records."""
        repo.save_snapshot(
            deviationid="DEV-123",
            snapshot_date="2024-01-15",
            views=100,
            favourites=10,
            comments=5,
        )
        repo.save_snapshot(
            deviationid="DEV-123",
            snapshot_date="2024-01-16",
            views=120,
            favourites=12,
            comments=6,
        )
        
        snapshots = repo.get_snapshots_for_deviation("DEV-123")
        assert len(snapshots) == 2

    def test_get_snapshots_for_deviation_returns_empty_list(self, repo):
        """Test getting snapshots for non-existent deviation returns empty list."""
        snapshots = repo.get_snapshots_for_deviation("NONEXISTENT")
        assert snapshots == []

    def test_get_snapshots_for_deviation_orders_by_date_desc(self, repo):
        """Test that snapshots are returned in descending date order."""
        repo.save_snapshot(
            deviationid="DEV-123",
            snapshot_date="2024-01-15",
            views=100,
            favourites=10,
            comments=5,
        )
        repo.save_snapshot(
            deviationid="DEV-123",
            snapshot_date="2024-01-16",
            views=120,
            favourites=12,
            comments=6,
        )
        repo.save_snapshot(
            deviationid="DEV-123",
            snapshot_date="2024-01-14",
            views=90,
            favourites=9,
            comments=4,
        )
        
        snapshots = repo.get_snapshots_for_deviation("DEV-123")
        assert len(snapshots) == 3
        assert snapshots[0]["snapshot_date"] == "2024-01-16"  # Most recent first
        assert snapshots[1]["snapshot_date"] == "2024-01-15"
        assert snapshots[2]["snapshot_date"] == "2024-01-14"  # Oldest last

    def test_get_snapshots_for_deviation_respects_limit(self, repo):
        """Test that get_snapshots respects the limit parameter."""
        # Create 5 snapshots
        for i in range(5):
            repo.save_snapshot(
                deviationid="DEV-123",
                snapshot_date=f"2024-01-{15+i:02d}",
                views=100 + i * 10,
                favourites=10 + i,
                comments=5 + i,
            )
        
        # Request only 3
        snapshots = repo.get_snapshots_for_deviation("DEV-123", limit=3)
        assert len(snapshots) == 3
        # Should be the 3 most recent
        assert snapshots[0]["snapshot_date"] == "2024-01-19"
        assert snapshots[1]["snapshot_date"] == "2024-01-18"
        assert snapshots[2]["snapshot_date"] == "2024-01-17"

    def test_get_snapshots_for_deviation_returns_all_fields(self, repo):
        """Test that get_snapshots returns all fields correctly."""
        repo.save_snapshot(
            deviationid="DEV-123",
            snapshot_date="2024-01-15",
            views=100,
            favourites=10,
            comments=5,
        )
        
        snapshots = repo.get_snapshots_for_deviation("DEV-123")
        assert len(snapshots) == 1
        snapshot = snapshots[0]
        assert snapshot["deviationid"] == "DEV-123"
        assert snapshot["snapshot_date"] == "2024-01-15"
        assert snapshot["views"] == 100
        assert snapshot["favourites"] == 10
        assert snapshot["comments"] == 5
        assert "created_at" in snapshot
        assert "updated_at" in snapshot
