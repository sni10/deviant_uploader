"""Tests for domain models."""
import pytest
from datetime import datetime
from src.domain.models import User, Gallery, Deviation, UploadStatus


class TestUploadStatus:
    """Test UploadStatus enum."""
    
    def test_enum_values(self):
        """Test that all expected enum values exist."""
        assert UploadStatus.NEW.value == "new"
        assert UploadStatus.UPLOADING.value == "uploading"
        assert UploadStatus.DONE.value == "done"
        assert UploadStatus.FAILED.value == "failed"
    
    def test_enum_comparison(self):
        """Test enum comparison."""
        status = UploadStatus.NEW
        assert status == UploadStatus.NEW
        assert status != UploadStatus.DONE


class TestUser:
    """Test User model."""
    
    def test_user_creation_minimal(self):
        """Test creating a user with minimal required fields."""
        user = User(
            userid="test-uuid-123",
            username="testuser",
            usericon="https://example.com/avatar.png",
            type="regular"
        )
        
        assert user.userid == "test-uuid-123"
        assert user.username == "testuser"
        assert user.usericon == "https://example.com/avatar.png"
        assert user.type == "regular"
        assert user.user_db_id is None
        assert isinstance(user.created_at, datetime)
    
    def test_user_creation_with_profile(self):
        """Test creating a user with extended profile information."""
        user = User(
            userid="test-uuid-123",
            username="testuser",
            usericon="https://example.com/avatar.png",
            type="premium",
            real_name="Test Artist",
            country="USA",
            artist_level="Professional",
            artist_specialty="Digital Art",
            user_deviations=150
        )
        
        assert user.real_name == "Test Artist"
        assert user.country == "USA"
        assert user.artist_level == "Professional"
        assert user.artist_specialty == "Digital Art"
        assert user.user_deviations == 150


class TestGallery:
    """Test Gallery model."""
    
    def test_gallery_creation_minimal(self):
        """Test creating a gallery with minimal required fields."""
        gallery = Gallery(
            folderid="gallery-uuid-456",
            name="Featured"
        )
        
        assert gallery.folderid == "gallery-uuid-456"
        assert gallery.name == "Featured"
        assert gallery.parent is None
        assert gallery.size is None
        assert gallery.gallery_db_id is None
        assert isinstance(gallery.created_at, datetime)
    
    def test_gallery_creation_with_parent(self):
        """Test creating a gallery with parent folder."""
        gallery = Gallery(
            folderid="gallery-uuid-456",
            name="Subfolder",
            parent="parent-gallery-uuid-123",
            size=10
        )
        
        assert gallery.parent == "parent-gallery-uuid-123"
        assert gallery.size == 10


class TestDeviation:
    """Test Deviation model."""
    
    def test_deviation_creation_minimal(self):
        """Test creating a deviation with minimal required fields."""
        deviation = Deviation(
            filename="artwork.png",
            title="My Artwork"
        )
        
        assert deviation.filename == "artwork.png"
        assert deviation.title == "My Artwork"
        assert deviation.is_mature is False
        assert deviation.feature is True
        assert deviation.allow_comments is True
        assert deviation.status == UploadStatus.NEW
        assert deviation.tags == []
        assert deviation.mature_classification == []
        assert isinstance(deviation.created_at, datetime)
        assert deviation.published_time is None
    
    def test_deviation_creation_with_tags(self):
        """Test creating a deviation with tags."""
        deviation = Deviation(
            filename="artwork.png",
            title="My Artwork",
            tags=["digital", "art", "fantasy"]
        )
        
        assert len(deviation.tags) == 3
        assert "digital" in deviation.tags
        assert "art" in deviation.tags
        assert "fantasy" in deviation.tags
    
    def test_deviation_mature_content(self):
        """Test deviation with mature content settings."""
        deviation = Deviation(
            filename="artwork.png",
            title="Mature Artwork",
            is_mature=True,
            mature_level="strict",
            mature_classification=["nudity", "gore"]
        )
        
        assert deviation.is_mature is True
        assert deviation.mature_level == "strict"
        assert len(deviation.mature_classification) == 2
        assert "nudity" in deviation.mature_classification
        assert "gore" in deviation.mature_classification
    
    def test_deviation_ai_generated(self):
        """Test deviation with AI-generated flags."""
        deviation = Deviation(
            filename="ai_artwork.png",
            title="AI Generated Art",
            is_ai_generated=True,
            noai=True
        )
        
        assert deviation.is_ai_generated is True
        assert deviation.noai is True
    
    def test_deviation_with_stash_fields(self):
        """Test deviation with stash submit fields."""
        deviation = Deviation(
            filename="artwork.png",
            title="My Artwork",
            artist_comments="This is my latest work",
            original_url="https://example.com/original",
            stack="My Stack",
            itemid=123456789
        )
        
        assert deviation.artist_comments == "This is my latest work"
        assert deviation.original_url == "https://example.com/original"
        assert deviation.stack == "My Stack"
        assert deviation.itemid == 123456789
    
    def test_deviation_status_workflow(self):
        """Test deviation status transitions."""
        deviation = Deviation(
            filename="artwork.png",
            title="My Artwork"
        )
        
        # Initial status
        assert deviation.status == UploadStatus.NEW
        
        # Change to uploading
        deviation.status = UploadStatus.UPLOADING
        assert deviation.status == UploadStatus.UPLOADING
        
        # Change to done
        deviation.status = UploadStatus.DONE
        assert deviation.status == UploadStatus.DONE
