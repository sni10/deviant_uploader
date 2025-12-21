"""Tests for DeviationMetadataRepository.

Following TDD approach: these tests are written before implementation
to drive the design of the new repository.
"""
import pytest

from src.storage.deviation_metadata_repository import DeviationMetadataRepository


@pytest.fixture
def repo(db_conn):
    """Create a DeviationMetadataRepository instance for testing."""

    return DeviationMetadataRepository(db_conn)


class TestDeviationMetadataRepository:
    """Test DeviationMetadataRepository for deviation_metadata table operations."""

    def test_save_metadata_creates_new_record(self, repo):
        """Test saving new metadata creates a record."""
        rowid = repo.save_metadata(
            deviationid="DEV-123",
            title="Test Artwork",
            description="A test description",
            license="cc-by",
            allows_comments=True,
            tags=["digital", "art"],
            is_favourited=False,
            is_watching=False,
            is_mature=False,
            mature_level=None,
            mature_classification=[],
            printid=None,
            author={"username": "testuser"},
            creation_time="2024-01-15T10:00:00Z",
            category="digital/paintings",
            file_size="2.5 MB",
            resolution="1920x1080",
            submitted_with={"app": "browser"},
            stats_json={"views": 100},
            camera=None,
            collections=[],
            galleries=[],
            can_post_comment=True,
            stats_views_today=10,
            stats_downloads_today=2,
            stats_downloads=50,
            stats_views=100,
            stats_favourites=15,
            stats_comments=5,
        )
        
        assert rowid > 0

    def test_save_metadata_updates_existing_record(self, repo):
        """Test saving metadata twice updates the existing record."""
        # First save
        repo.save_metadata(
            deviationid="DEV-123",
            title="Original Title",
            description="Original description",
            license="cc-by",
            allows_comments=True,
            tags=["test"],
            is_favourited=False,
            is_watching=False,
            is_mature=False,
            mature_level=None,
            mature_classification=[],
            printid=None,
            author=None,
            creation_time=None,
            category=None,
            file_size=None,
            resolution=None,
            submitted_with=None,
            stats_json=None,
            camera=None,
            collections=[],
            galleries=[],
            can_post_comment=True,
            stats_views_today=10,
            stats_downloads_today=2,
            stats_downloads=50,
            stats_views=100,
            stats_favourites=15,
            stats_comments=5,
        )
        
        # Second save with updated values
        repo.save_metadata(
            deviationid="DEV-123",
            title="Updated Title",
            description="Updated description",
            license="cc-by-nc",
            allows_comments=False,
            tags=["updated", "test"],
            is_favourited=True,
            is_watching=True,
            is_mature=True,
            mature_level="moderate",
            mature_classification=["nudity"],
            printid="PRINT-456",
            author={"username": "updateduser"},
            creation_time="2024-01-16T12:00:00Z",
            category="photography",
            file_size="3.0 MB",
            resolution="2048x1536",
            submitted_with={"app": "mobile"},
            stats_json={"views": 200},
            camera={"model": "Canon EOS"},
            collections=["col1"],
            galleries=["gal1"],
            can_post_comment=False,
            stats_views_today=20,
            stats_downloads_today=5,
            stats_downloads=100,
            stats_views=200,
            stats_favourites=30,
            stats_comments=10,
        )
        
        # Verify only one record exists with updated values
        metadata = repo.get_metadata("DEV-123")
        assert metadata is not None
        assert metadata["title"] == "Updated Title"
        assert metadata["description"] == "Updated description"
        assert metadata["tags"] == ["updated", "test"]
        assert metadata["is_favourited"] == 1
        assert metadata["stats_views"] == 200

    def test_get_metadata_returns_none_when_not_found(self, repo):
        """Test getting metadata for non-existent deviation returns None."""
        metadata = repo.get_metadata("NONEXISTENT")
        assert metadata is None

    def test_get_metadata_returns_complete_record(self, repo):
        """Test getting metadata returns all fields correctly."""
        repo.save_metadata(
            deviationid="DEV-123",
            title="Test Artwork",
            description="A test description",
            license="cc-by",
            allows_comments=True,
            tags=["digital", "art", "fantasy"],
            is_favourited=True,
            is_watching=False,
            is_mature=True,
            mature_level="strict",
            mature_classification=["nudity", "violence"],
            printid="PRINT-789",
            author={"username": "testuser", "userid": "USER-123"},
            creation_time="2024-01-15T10:00:00Z",
            category="digital/paintings",
            file_size="2.5 MB",
            resolution="1920x1080",
            submitted_with={"app": "browser", "version": "1.0"},
            stats_json={"views": 100, "downloads": 50},
            camera={"model": "Canon EOS", "lens": "50mm"},
            collections=["col1", "col2"],
            galleries=["gal1"],
            can_post_comment=True,
            stats_views_today=10,
            stats_downloads_today=2,
            stats_downloads=50,
            stats_views=100,
            stats_favourites=15,
            stats_comments=5,
        )
        
        metadata = repo.get_metadata("DEV-123")
        assert metadata is not None
        assert metadata["deviationid"] == "DEV-123"
        assert metadata["title"] == "Test Artwork"
        assert metadata["description"] == "A test description"
        assert metadata["license"] == "cc-by"
        assert metadata["allows_comments"] == 1
        assert metadata["tags"] == ["digital", "art", "fantasy"]
        assert metadata["is_favourited"] == 1
        assert metadata["is_watching"] == 0
        assert metadata["is_mature"] == 1
        assert metadata["mature_level"] == "strict"
        assert metadata["mature_classification"] == ["nudity", "violence"]
        assert metadata["printid"] == "PRINT-789"
        assert metadata["author"]["username"] == "testuser"
        assert metadata["creation_time"] == "2024-01-15T10:00:00Z"
        assert metadata["category"] == "digital/paintings"
        assert metadata["file_size"] == "2.5 MB"
        assert metadata["resolution"] == "1920x1080"
        assert metadata["submitted_with"]["app"] == "browser"
        assert metadata["stats_json"]["views"] == 100
        assert metadata["camera"]["model"] == "Canon EOS"
        assert metadata["collections"] == ["col1", "col2"]
        assert metadata["galleries"] == ["gal1"]
        assert metadata["can_post_comment"] == 1
        assert metadata["stats_views_today"] == 10
        assert metadata["stats_downloads_today"] == 2
        assert metadata["stats_downloads"] == 50
        assert metadata["stats_views"] == 100
        assert metadata["stats_favourites"] == 15
        assert metadata["stats_comments"] == 5

    def test_save_metadata_handles_none_values(self, repo):
        """Test saving metadata with None values for optional fields."""
        rowid = repo.save_metadata(
            deviationid="DEV-123",
            title="Minimal Artwork",
            description=None,
            license=None,
            allows_comments=None,
            tags=[],
            is_favourited=None,
            is_watching=None,
            is_mature=None,
            mature_level=None,
            mature_classification=[],
            printid=None,
            author=None,
            creation_time=None,
            category=None,
            file_size=None,
            resolution=None,
            submitted_with=None,
            stats_json=None,
            camera=None,
            collections=[],
            galleries=[],
            can_post_comment=None,
            stats_views_today=None,
            stats_downloads_today=None,
            stats_downloads=None,
            stats_views=None,
            stats_favourites=None,
            stats_comments=None,
        )
        
        assert rowid > 0
        metadata = repo.get_metadata("DEV-123")
        assert metadata is not None
        assert metadata["title"] == "Minimal Artwork"
        assert metadata["description"] is None
        assert metadata["tags"] == []
