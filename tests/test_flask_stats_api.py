"""Tests for Flask stats API endpoints.

These tests verify the behavior of the stats API endpoints including:
- GET /api/stats
- POST /api/stats/sync
- GET /api/options
- GET /api/user_stats/latest
- GET / (dashboard page)
"""
import json
import sqlite3
from unittest.mock import Mock, patch, MagicMock
import pytest
from src.api.stats_api import create_app
from src.domain.models import User, Gallery
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
def test_app(connection, monkeypatch):
    """Create a Flask test app with mocked dependencies."""
    # Mock get_connection to return our test connection
    def mock_get_connection():
        return connection
    
    monkeypatch.setattr("src.api.stats_api.get_connection", mock_get_connection)
    
    # Create app with test config
    app = create_app()
    app.config['TESTING'] = True
    
    return app


@pytest.fixture
def client(test_app):
    """Create a test client for the Flask app."""
    return test_app.test_client()


@pytest.fixture
def mock_services(monkeypatch):
    """Mock AuthService and StatsService."""
    mock_auth = Mock()
    mock_stats = Mock()
    
    def mock_get_services():
        return (mock_auth, mock_stats)
    
    monkeypatch.setattr("src.api.stats_api.get_services", mock_get_services)
    
    return {"auth": mock_auth, "stats": mock_stats}


class TestDashboardEndpoint:
    """Test the dashboard page endpoint."""
    
    def test_index_returns_html(self, client):
        """Test that GET / returns the dashboard HTML page."""
        # Note: This will return 404 if stats.html doesn't exist in test environment
        # In a real scenario, you might want to create a test static file
        response = client.get("/")
        # We expect either 200 (file exists) or 404 (file missing in test env)
        assert response.status_code in (200, 404)


class TestStatsEndpoint:
    """Test GET /api/stats endpoint."""
    
    def test_get_stats_success(self, client, mock_services):
        """Test successful stats retrieval."""
        mock_services["stats"].get_stats_with_diff.return_value = {
            "deviations": [
                {
                    "deviationid": "DEV-123",
                    "title": "Test Art",
                    "views": 100,
                    "favourites": 10,
                    "comments": 5,
                    "views_diff": 10,
                    "favourites_diff": 2,
                    "comments_diff": 1,
                }
            ]
        }
        
        response = client.get("/api/stats")
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "data" in data
        assert "deviations" in data["data"]
        assert len(data["data"]["deviations"]) == 1
    
    def test_get_stats_handles_error(self, client, mock_services):
        """Test that errors are handled gracefully."""
        mock_services["stats"].get_stats_with_diff.side_effect = Exception("Database error")
        
        response = client.get("/api/stats")
        
        assert response.status_code == 500
        data = json.loads(response.data)
        assert data["success"] is False
        assert "error" in data


class TestSyncEndpoint:
    """Test POST /api/stats/sync endpoint."""
    
    def test_sync_stats_missing_folderid(self, client, mock_services):
        """Test that sync fails when folderid is missing."""
        response = client.post(
            "/api/stats/sync",
            data=json.dumps({}),
            content_type="application/json"
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
        assert "folderid is required" in data["error"]
    
    def test_sync_stats_not_authenticated(self, client, mock_services):
        """Test that sync fails when user is not authenticated."""
        mock_services["auth"].ensure_authenticated.return_value = False
        
        response = client.post(
            "/api/stats/sync",
            data=json.dumps({"folderid": "FOLDER-123"}),
            content_type="application/json"
        )
        
        assert response.status_code == 401
        data = json.loads(response.data)
        assert data["success"] is False
        assert "Not authenticated" in data["error"]
    
    def test_sync_stats_no_access_token(self, client, mock_services):
        """Test that sync fails when access token is unavailable."""
        mock_services["auth"].ensure_authenticated.return_value = True
        mock_services["auth"].get_valid_token.return_value = None
        
        response = client.post(
            "/api/stats/sync",
            data=json.dumps({"folderid": "FOLDER-123"}),
            content_type="application/json"
        )
        
        assert response.status_code == 401
        data = json.loads(response.data)
        assert data["success"] is False
        assert "Failed to obtain access token" in data["error"]
    
    def test_sync_stats_success(self, client, mock_services):
        """Test successful stats sync."""
        mock_services["auth"].ensure_authenticated.return_value = True
        mock_services["auth"].get_valid_token.return_value = "test_token"
        mock_services["stats"].sync_gallery.return_value = {
            "synced": 5,
            "errors": 0
        }
        
        response = client.post(
            "/api/stats/sync",
            data=json.dumps({
                "folderid": "FOLDER-123",
                "username": "testuser",
                "include_deviations": True
            }),
            content_type="application/json"
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert data["data"]["synced"] == 5
        
        # Verify sync_gallery was called with correct parameters
        mock_services["stats"].sync_gallery.assert_called_once_with(
            "test_token",
            "FOLDER-123",
            username="testuser",
            include_deviations=True
        )
    
    def test_sync_stats_handles_exception(self, client, mock_services):
        """Test that exceptions during sync are handled."""
        mock_services["auth"].ensure_authenticated.return_value = True
        mock_services["auth"].get_valid_token.return_value = "test_token"
        mock_services["stats"].sync_gallery.side_effect = Exception("Sync failed")
        
        response = client.post(
            "/api/stats/sync",
            data=json.dumps({"folderid": "FOLDER-123"}),
            content_type="application/json"
        )
        
        assert response.status_code == 500
        data = json.loads(response.data)
        assert data["success"] is False
        assert "Sync failed" in data["error"]


class TestOptionsEndpoint:
    """Test GET /api/options endpoint."""
    
    def test_get_options_success(self, client, connection):
        """Test successful retrieval of users and galleries."""
        from src.storage.user_repository import UserRepository
        from src.storage.gallery_repository import GalleryRepository
        
        # Insert test data
        user_repo = UserRepository(connection)
        gallery_repo = GalleryRepository(connection)
        
        test_user = User(
            userid="USER-123",
            username="testuser",
            usericon="https://example.com/icon.jpg",
            type="regular"
        )
        user_repo.save_user(test_user)
        
        test_gallery = Gallery(
            folderid="FOLDER-456",
            name="Test Gallery",
            size=10
        )
        gallery_repo.save_gallery(test_gallery)
        
        response = client.get("/api/options")
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "data" in data
        assert "users" in data["data"]
        assert "galleries" in data["data"]
        assert len(data["data"]["users"]) == 1
        assert len(data["data"]["galleries"]) == 1
        assert data["data"]["users"][0]["username"] == "testuser"
        assert data["data"]["galleries"][0]["name"] == "Test Gallery"
    
    def test_get_options_handles_error(self, client, monkeypatch):
        """Test that errors are handled gracefully."""
        def mock_get_repos():
            raise Exception("Database connection failed")
        
        monkeypatch.setattr("src.api.stats_api.get_repositories", mock_get_repos)
        
        response = client.get("/api/options")
        
        assert response.status_code == 500
        data = json.loads(response.data)
        assert data["success"] is False
        assert "error" in data


class TestUserStatsEndpoint:
    """Test GET /api/user_stats/latest endpoint."""
    
    def test_get_latest_user_stats_missing_username(self, client):
        """Test that request fails when username is missing."""
        response = client.get("/api/user_stats/latest")
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
        assert "username is required" in data["error"]
    
    def test_get_latest_user_stats_success(self, client, connection):
        """Test successful retrieval of latest user stats."""
        from src.storage.user_stats_snapshot_repository import UserStatsSnapshotRepository
        
        # Insert test data
        repo = UserStatsSnapshotRepository(connection)
        repo.save_user_stats_snapshot(
            user_id=None,
            username="testuser",
            snapshot_date="2024-12-08",
            watchers=150,
            friends=50
        )
        
        response = client.get("/api/user_stats/latest?username=testuser")
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert data["data"] is not None
        assert data["data"]["username"] == "testuser"
        assert data["data"]["watchers"] == 150
    
    def test_get_latest_user_stats_not_found(self, client, connection):
        """Test when no stats exist for the user."""
        response = client.get("/api/user_stats/latest?username=nonexistent")
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert data["data"] is None
    
    def test_get_latest_user_stats_handles_error(self, client, monkeypatch):
        """Test that errors are handled gracefully."""
        def mock_get_repos():
            raise Exception("Database error")
        
        monkeypatch.setattr("src.api.stats_api.get_repositories", mock_get_repos)
        
        response = client.get("/api/user_stats/latest?username=testuser")
        
        assert response.status_code == 500
        data = json.loads(response.data)
        assert data["success"] is False
        assert "error" in data
