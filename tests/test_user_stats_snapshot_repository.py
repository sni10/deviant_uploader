"""Tests for UserStatsSnapshotRepository.

Following TDD approach: these tests are written before implementation
to drive the design of the new repository.
"""
import pytest
from src.storage.user_stats_snapshot_repository import UserStatsSnapshotRepository


@pytest.fixture
def repo(db_conn):
    """Create a UserStatsSnapshotRepository instance for testing."""

    return UserStatsSnapshotRepository(db_conn)


class TestUserStatsSnapshotRepository:
    """Test UserStatsSnapshotRepository for user_stats_snapshots table operations."""

    def test_save_user_stats_snapshot_creates_new_record(self, repo):
        """Test saving new user stats snapshot creates a record."""
        rowid = repo.save_user_stats_snapshot(
            user_id=1,
            username="testuser",
            snapshot_date="2024-01-15",
            watchers=100,
            friends=50,
        )
        
        assert rowid > 0

    def test_save_user_stats_snapshot_updates_existing_record(self, repo):
        """Test saving snapshot twice for same date updates the record."""
        # First save
        repo.save_user_stats_snapshot(
            user_id=1,
            username="testuser",
            snapshot_date="2024-01-15",
            watchers=100,
            friends=50,
        )
        
        # Second save with updated values (same date)
        repo.save_user_stats_snapshot(
            user_id=1,
            username="testuser",
            snapshot_date="2024-01-15",
            watchers=120,
            friends=55,
        )
        
        # Verify only one record exists with updated values
        history = repo.get_user_stats_history("testuser", limit=10)
        assert len(history) == 1
        assert history[0]["watchers"] == 120
        assert history[0]["friends"] == 55

    def test_save_user_stats_snapshot_allows_multiple_dates(self, repo):
        """Test saving snapshots for different dates creates multiple records."""
        repo.save_user_stats_snapshot(
            user_id=1,
            username="testuser",
            snapshot_date="2024-01-15",
            watchers=100,
            friends=50,
        )
        repo.save_user_stats_snapshot(
            user_id=1,
            username="testuser",
            snapshot_date="2024-01-16",
            watchers=105,
            friends=51,
        )
        
        history = repo.get_user_stats_history("testuser", limit=10)
        assert len(history) == 2

    def test_save_user_stats_snapshot_accepts_none_user_id(self, repo):
        """Test saving snapshot with None user_id (user not in DB yet)."""
        rowid = repo.save_user_stats_snapshot(
            user_id=None,
            username="newuser",
            snapshot_date="2024-01-15",
            watchers=10,
            friends=5,
        )
        
        assert rowid > 0

    def test_get_latest_user_stats_snapshot_returns_none_when_not_found(self, repo):
        """Test getting latest snapshot for non-existent user returns None."""
        snapshot = repo.get_latest_user_stats_snapshot("nonexistent")
        assert snapshot is None

    def test_get_latest_user_stats_snapshot_returns_most_recent(self, repo):
        """Test that get_latest returns the most recent snapshot."""
        repo.save_user_stats_snapshot(
            user_id=1,
            username="testuser",
            snapshot_date="2024-01-14",
            watchers=100,
            friends=50,
        )
        repo.save_user_stats_snapshot(
            user_id=1,
            username="testuser",
            snapshot_date="2024-01-15",
            watchers=105,
            friends=51,
        )
        repo.save_user_stats_snapshot(
            user_id=1,
            username="testuser",
            snapshot_date="2024-01-13",
            watchers=95,
            friends=49,
        )
        
        snapshot = repo.get_latest_user_stats_snapshot("testuser")
        assert snapshot is not None
        assert snapshot["snapshot_date"] == "2024-01-15"
        assert snapshot["watchers"] == 105

    def test_get_latest_user_stats_snapshot_calculates_diff(self, repo):
        """Test that get_latest calculates watchers_diff from yesterday."""
        # Yesterday
        repo.save_user_stats_snapshot(
            user_id=1,
            username="testuser",
            snapshot_date="2024-01-14",
            watchers=100,
            friends=50,
        )
        # Today
        repo.save_user_stats_snapshot(
            user_id=1,
            username="testuser",
            snapshot_date="2024-01-15",
            watchers=105,
            friends=51,
        )
        
        snapshot = repo.get_latest_user_stats_snapshot("testuser")
        assert snapshot is not None
        assert snapshot["watchers"] == 105
        assert snapshot["watchers_diff"] == 5  # 105 - 100

    def test_get_latest_user_stats_snapshot_handles_no_yesterday(self, repo):
        """Test that watchers_diff is 0 when there's no yesterday data."""
        repo.save_user_stats_snapshot(
            user_id=1,
            username="testuser",
            snapshot_date="2024-01-15",
            watchers=105,
            friends=51,
        )
        
        snapshot = repo.get_latest_user_stats_snapshot("testuser")
        assert snapshot is not None
        assert snapshot["watchers"] == 105
        assert snapshot["watchers_diff"] == 105  # No yesterday, so diff from 0

    def test_get_user_stats_history_returns_empty_list(self, repo):
        """Test getting history for non-existent user returns empty list."""
        history = repo.get_user_stats_history("nonexistent", limit=10)
        assert history == []

    def test_get_user_stats_history_orders_by_date_desc(self, repo):
        """Test that history is returned in descending date order."""
        repo.save_user_stats_snapshot(
            user_id=1,
            username="testuser",
            snapshot_date="2024-01-15",
            watchers=105,
            friends=51,
        )
        repo.save_user_stats_snapshot(
            user_id=1,
            username="testuser",
            snapshot_date="2024-01-16",
            watchers=110,
            friends=52,
        )
        repo.save_user_stats_snapshot(
            user_id=1,
            username="testuser",
            snapshot_date="2024-01-14",
            watchers=100,
            friends=50,
        )
        
        history = repo.get_user_stats_history("testuser", limit=10)
        assert len(history) == 3
        assert history[0]["snapshot_date"] == "2024-01-16"  # Most recent first
        assert history[1]["snapshot_date"] == "2024-01-15"
        assert history[2]["snapshot_date"] == "2024-01-14"  # Oldest last

    def test_get_user_stats_history_respects_limit(self, repo):
        """Test that get_user_stats_history respects the limit parameter."""
        # Create 5 snapshots
        for i in range(5):
            repo.save_user_stats_snapshot(
                user_id=1,
                username="testuser",
                snapshot_date=f"2024-01-{15+i:02d}",
                watchers=100 + i * 5,
                friends=50 + i,
            )
        
        # Request only 3
        history = repo.get_user_stats_history("testuser", limit=3)
        assert len(history) == 3
        # Should be the 3 most recent
        assert history[0]["snapshot_date"] == "2024-01-19"
        assert history[1]["snapshot_date"] == "2024-01-18"
        assert history[2]["snapshot_date"] == "2024-01-17"
