"""Tests for WatcherRepository."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.storage.watcher_repository import WatcherRepository
from src.storage.adapters.sqlalchemy_adapter import SQLAlchemyConnection
from src.storage.profile_message_tables import metadata as profile_metadata


@pytest.fixture
def watcher_repo():
    """Create in-memory SQLite WatcherRepository for testing."""
    engine = create_engine("sqlite:///:memory:")
    profile_metadata.create_all(engine)
    
    SessionFactory = sessionmaker(bind=engine)
    session = SessionFactory()
    
    conn = SQLAlchemyConnection(session)
    repo = WatcherRepository(conn)
    yield repo
    session.close()


class TestWatcherRepository:
    """Test WatcherRepository methods."""

    def test_add_or_update_watcher(self, watcher_repo):
        """Test adding a new watcher."""
        watcher_repo.add_or_update_watcher("testuser", "12345")
        
        watchers = watcher_repo.get_all_watchers()
        assert len(watchers) == 1
        assert watchers[0].username == "testuser"
        assert watchers[0].userid == "12345"

    def test_update_existing_watcher(self, watcher_repo):
        """Test updating an existing watcher updates userid and fetched_at."""
        watcher_repo.add_or_update_watcher("testuser", "12345")
        watcher_repo.add_or_update_watcher("testuser", "67890")
        
        watchers = watcher_repo.get_all_watchers()
        assert len(watchers) == 1
        assert watchers[0].username == "testuser"
        assert watchers[0].userid == "67890"

    def test_get_all_watchers(self, watcher_repo):
        """Test retrieving all watchers."""
        watcher_repo.add_or_update_watcher("user1", "111")
        watcher_repo.add_or_update_watcher("user2", "222")
        watcher_repo.add_or_update_watcher("user3", "333")
        
        watchers = watcher_repo.get_all_watchers()
        assert len(watchers) == 3
        usernames = [w.username for w in watchers]
        assert "user1" in usernames
        assert "user2" in usernames
        assert "user3" in usernames

    def test_count_watchers(self, watcher_repo):
        """Test counting watchers."""
        assert watcher_repo.count_watchers() == 0
        
        watcher_repo.add_or_update_watcher("user1", "111")
        assert watcher_repo.count_watchers() == 1
        
        watcher_repo.add_or_update_watcher("user2", "222")
        assert watcher_repo.count_watchers() == 2

    def test_delete_watchers_not_in_list_removes_unfollowed(self, watcher_repo):
        """Test that delete_watchers_not_in_list removes watchers not in the list."""
        # Add 5 watchers
        watcher_repo.add_or_update_watcher("user1", "111")
        watcher_repo.add_or_update_watcher("user2", "222")
        watcher_repo.add_or_update_watcher("user3", "333")
        watcher_repo.add_or_update_watcher("user4", "444")
        watcher_repo.add_or_update_watcher("user5", "555")
        
        assert watcher_repo.count_watchers() == 5
        
        # Keep only user1, user3, user5 (simulate current followers)
        current_followers = ["user1", "user3", "user5"]
        deleted_count = watcher_repo.delete_watchers_not_in_list(current_followers)
        
        # Should delete user2 and user4
        assert deleted_count == 2
        assert watcher_repo.count_watchers() == 3
        
        # Verify remaining watchers
        watchers = watcher_repo.get_all_watchers()
        usernames = [w.username for w in watchers]
        assert "user1" in usernames
        assert "user3" in usernames
        assert "user5" in usernames
        assert "user2" not in usernames
        assert "user4" not in usernames

    def test_delete_watchers_not_in_list_keeps_all_if_all_present(self, watcher_repo):
        """Test that no watchers are deleted if all are in the list."""
        watcher_repo.add_or_update_watcher("user1", "111")
        watcher_repo.add_or_update_watcher("user2", "222")
        watcher_repo.add_or_update_watcher("user3", "333")
        
        current_followers = ["user1", "user2", "user3"]
        deleted_count = watcher_repo.delete_watchers_not_in_list(current_followers)
        
        assert deleted_count == 0
        assert watcher_repo.count_watchers() == 3

    def test_delete_watchers_not_in_list_with_empty_list(self, watcher_repo):
        """Test that all watchers are deleted if list is empty."""
        watcher_repo.add_or_update_watcher("user1", "111")
        watcher_repo.add_or_update_watcher("user2", "222")
        
        deleted_count = watcher_repo.delete_watchers_not_in_list([])
        
        assert deleted_count == 2
        assert watcher_repo.count_watchers() == 0

    def test_delete_watchers_not_in_list_with_no_watchers(self, watcher_repo):
        """Test that delete works correctly when database is empty."""
        deleted_count = watcher_repo.delete_watchers_not_in_list(["user1", "user2"])
        
        assert deleted_count == 0
        assert watcher_repo.count_watchers() == 0
