"""Tests for DeviationStatsRepository.

Following TDD approach: these tests are written before implementation
to drive the design of the new repository.
"""
import sqlite3
import pytest
from src.storage.deviation_stats_repository import DeviationStatsRepository
from src.storage.database import DATABASE_SCHEMA


@pytest.fixture
def connection():
    """Create an isolated in-memory SQLite connection for testing."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(DATABASE_SCHEMA)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def repo(connection):
    """Create a DeviationStatsRepository instance for testing."""
    return DeviationStatsRepository(connection)


class TestDeviationStatsRepository:
    """Test DeviationStatsRepository for deviation_stats table operations."""

    def test_save_deviation_stats_creates_new_record(self, repo):
        """Test saving new deviation stats creates a record."""
        rowid = repo.save_deviation_stats(
            deviationid="DEV-123",
            title="Test Artwork",
            views=100,
            favourites=10,
            comments=5,
            thumb_url="https://example.com/thumb.jpg",
            gallery_folderid="GAL-456",
            is_mature=False,
            url="https://deviantart.com/art/123",
        )
        
        assert rowid > 0

    def test_save_deviation_stats_updates_existing_record(self, repo):
        """Test saving stats twice updates the existing record."""
        # First save
        repo.save_deviation_stats(
            deviationid="DEV-123",
            title="Test Artwork",
            views=100,
            favourites=10,
            comments=5,
        )
        
        # Second save with updated values
        repo.save_deviation_stats(
            deviationid="DEV-123",
            title="Updated Artwork",
            views=150,
            favourites=15,
            comments=8,
        )
        
        # Verify only one record exists with updated values
        stats = repo.get_deviation_stats("DEV-123")
        assert stats is not None
        assert stats["title"] == "Updated Artwork"
        assert stats["views"] == 150
        assert stats["favourites"] == 15
        assert stats["comments"] == 8

    def test_get_deviation_stats_returns_none_when_not_found(self, repo):
        """Test getting stats for non-existent deviation returns None."""
        stats = repo.get_deviation_stats("NONEXISTENT")
        assert stats is None

    def test_get_deviation_stats_returns_complete_record(self, repo):
        """Test getting stats returns all fields correctly."""
        repo.save_deviation_stats(
            deviationid="DEV-123",
            title="Test Artwork",
            views=100,
            favourites=10,
            comments=5,
            thumb_url="https://example.com/thumb.jpg",
            gallery_folderid="GAL-456",
            is_mature=True,
            url="https://deviantart.com/art/123",
        )
        
        stats = repo.get_deviation_stats("DEV-123")
        assert stats is not None
        assert stats["deviationid"] == "DEV-123"
        assert stats["title"] == "Test Artwork"
        assert stats["views"] == 100
        assert stats["favourites"] == 10
        assert stats["comments"] == 5
        assert stats["thumb_url"] == "https://example.com/thumb.jpg"
        assert stats["gallery_folderid"] == "GAL-456"
        assert stats["is_mature"] == 1  # SQLite stores as int
        assert stats["url"] == "https://deviantart.com/art/123"

    def test_get_all_deviation_stats_returns_all_records(self, repo):
        """Test getting all stats returns multiple records."""
        repo.save_deviation_stats(
            deviationid="DEV-1",
            title="Artwork 1",
            views=100,
            favourites=10,
            comments=5,
        )
        repo.save_deviation_stats(
            deviationid="DEV-2",
            title="Artwork 2",
            views=200,
            favourites=20,
            comments=10,
        )
        
        all_stats = repo.get_all_deviation_stats()
        assert len(all_stats) == 2
        assert all_stats[0]["deviationid"] in ("DEV-1", "DEV-2")
        assert all_stats[1]["deviationid"] in ("DEV-1", "DEV-2")

    def test_get_all_deviation_stats_orders_by_views_desc(self, repo):
        """Test that get_all returns records ordered by views descending."""
        repo.save_deviation_stats(
            deviationid="DEV-1",
            title="Low views",
            views=50,
            favourites=5,
            comments=2,
        )
        repo.save_deviation_stats(
            deviationid="DEV-2",
            title="High views",
            views=500,
            favourites=50,
            comments=20,
        )
        
        all_stats = repo.get_all_deviation_stats()
        assert all_stats[0]["deviationid"] == "DEV-2"  # Higher views first
        assert all_stats[1]["deviationid"] == "DEV-1"
