"""Tests for add_to_queue filtering logic (exclude already sent watchers)."""

import pytest
from src.storage.profile_message_repository import ProfileMessageRepository
from src.storage.profile_message_log_repository import ProfileMessageLogRepository
from src.storage.profile_message_queue_repository import ProfileMessageQueueRepository
from src.storage.watcher_repository import WatcherRepository
from src.service.profile_message_service import ProfileMessageService
from src.domain.models import MessageLogStatus, QueueStatus
from src.log.logger import setup_logger


@pytest.fixture
def service(db_conn):
    """Create ProfileMessageService with test repositories."""
    message_repo = ProfileMessageRepository(db_conn)
    log_repo = ProfileMessageLogRepository(db_conn)
    queue_repo = ProfileMessageQueueRepository(db_conn)
    watcher_repo = WatcherRepository(db_conn)
    logger = setup_logger()
    
    return ProfileMessageService(
        message_repo=message_repo,
        log_repo=log_repo,
        queue_repo=queue_repo,
        watcher_repo=watcher_repo,
        logger=logger,
    )


@pytest.fixture
def message_repo(db_conn):
    """Create ProfileMessageRepository."""
    return ProfileMessageRepository(db_conn)


@pytest.fixture
def log_repo(db_conn):
    """Create ProfileMessageLogRepository."""
    return ProfileMessageLogRepository(db_conn)


@pytest.fixture
def queue_repo(db_conn):
    """Create ProfileMessageQueueRepository."""
    return ProfileMessageQueueRepository(db_conn)


@pytest.fixture
def watcher_repo(db_conn):
    """Create WatcherRepository."""
    return WatcherRepository(db_conn)


def test_add_selected_saved_to_queue_filters_sent(
    service, message_repo, log_repo, queue_repo
):
    """Test add_selected_saved_to_queue filters out watchers with sent logs."""
    # Create active message (is_active=True by default)
    message_id = message_repo.create_message(
        title="Test Message",
        body="Test body"
    )
    
    # Add sent log for user1
    log_repo.add_log(
        message_id=message_id,
        recipient_username="user1",
        recipient_userid="11111",
        status=MessageLogStatus.SENT,
        commentid="abc123",
    )
    
    # Try to add user1 and user2 to queue
    watchers = [
        {"username": "user1", "userid": "11111"},  # Already sent
        {"username": "user2", "userid": "22222"},  # New
    ]
    
    result = service.add_selected_saved_to_queue(watchers)
    
    # Should add only user2, skip user1
    assert result["success"] is True
    assert result["added_count"] == 1
    assert result["already_sent_count"] == 1
    assert result["skipped_count"] == 0
    assert result["invalid_count"] == 0
    
    # Check queue has only user2
    pending = queue_repo.get_pending(limit=10)
    assert len(pending) == 1
    assert pending[0].recipient_username == "user2"
    assert pending[0].recipient_userid == "22222"


def test_add_selected_saved_to_queue_filters_failed(
    service, message_repo, log_repo, queue_repo
):
    """Test add_selected_saved_to_queue filters out watchers with failed logs."""
    # Create active message (is_active=True by default)
    message_id = message_repo.create_message(
        title="Test Message",
        body="Test body"
    )
    
    # Add failed log for user1
    log_repo.add_log(
        message_id=message_id,
        recipient_username="user1",
        recipient_userid="11111",
        status=MessageLogStatus.FAILED,
        error_message="Network error",
    )
    
    # Try to add user1 and user2 to queue
    watchers = [
        {"username": "user1", "userid": "11111"},  # Already failed
        {"username": "user2", "userid": "22222"},  # New
    ]
    
    result = service.add_selected_saved_to_queue(watchers)
    
    # Should add only user2, skip user1
    assert result["success"] is True
    assert result["added_count"] == 1
    assert result["already_sent_count"] == 1
    assert result["skipped_count"] == 0
    
    # Check queue has only user2
    pending = queue_repo.get_pending(limit=10)
    assert len(pending) == 1
    assert pending[0].recipient_username == "user2"


def test_add_all_saved_to_queue_filters_sent(
    service, message_repo, log_repo, queue_repo, watcher_repo
):
    """Test add_all_saved_to_queue filters out watchers with sent logs."""
    # Create active message (is_active=True by default)
    message_id = message_repo.create_message(
        title="Test Message",
        body="Test body"
    )
    
    # Save 3 watchers to DB
    watcher_repo.add_or_update_watcher("user1", "11111")
    watcher_repo.add_or_update_watcher("user2", "22222")
    watcher_repo.add_or_update_watcher("user3", "33333")
    
    # Add sent log for user1
    log_repo.add_log(
        message_id=message_id,
        recipient_username="user1",
        recipient_userid="11111",
        status=MessageLogStatus.SENT,
        commentid="abc123",
    )
    
    # Add failed log for user2
    log_repo.add_log(
        message_id=message_id,
        recipient_username="user2",
        recipient_userid="22222",
        status=MessageLogStatus.FAILED,
        error_message="Error",
    )
    
    # Add all to queue
    result = service.add_all_saved_to_queue(limit=100)
    
    # Should add only user3, skip user1 and user2
    assert result["success"] is True
    assert result["added_count"] == 1
    assert result["already_sent_count"] == 2
    assert result["skipped_count"] == 0
    
    # Check queue has only user3
    pending = queue_repo.get_pending(limit=10)
    assert len(pending) == 1
    assert pending[0].recipient_username == "user3"
    assert pending[0].recipient_userid == "33333"


def test_add_selected_saved_to_queue_no_logs(
    service, message_repo, queue_repo
):
    """Test add_selected_saved_to_queue when no logs exist."""
    # Create active message (is_active=True by default)
    message_id = message_repo.create_message(
        title="Test Message",
        body="Test body"
    )
    
    # Try to add watchers (no logs exist)
    watchers = [
        {"username": "user1", "userid": "11111"},
        {"username": "user2", "userid": "22222"},
    ]
    
    result = service.add_selected_saved_to_queue(watchers)
    
    # Should add both
    assert result["success"] is True
    assert result["added_count"] == 2
    assert result["already_sent_count"] == 0
    assert result["skipped_count"] == 0
    
    # Check queue has both
    pending = queue_repo.get_pending(limit=10)
    assert len(pending) == 2


def test_get_all_recipient_userids(log_repo, message_repo):
    """Test get_all_recipient_userids returns unique userids."""
    # Create message
    message_id = message_repo.create_message(
        title="Test",
        body="Body"
    )
    
    # Add logs with different statuses
    log_repo.add_log(
        message_id=message_id,
        recipient_username="user1",
        recipient_userid="11111",
        status=MessageLogStatus.SENT,
        commentid="abc",
    )
    log_repo.add_log(
        message_id=message_id,
        recipient_username="user2",
        recipient_userid="22222",
        status=MessageLogStatus.FAILED,
        error_message="Error",
    )
    log_repo.add_log(
        message_id=message_id,
        recipient_username="user1",
        recipient_userid="11111",  # Duplicate
        status=MessageLogStatus.SENT,
        commentid="def",
    )
    
    # Get all recipient userids
    userids = log_repo.get_all_recipient_userids()
    
    # Should return unique userids
    assert isinstance(userids, set)
    assert len(userids) == 2
    assert "11111" in userids
    assert "22222" in userids


def test_add_selected_saved_to_queue_mixed_scenario(
    service, message_repo, log_repo, queue_repo
):
    """Test add_selected_saved_to_queue with mixed valid/invalid/already_sent."""
    # Create active message (is_active=True by default)
    message_id = message_repo.create_message(
        title="Test Message",
        body="Test body"
    )
    
    # Add sent log for user1
    log_repo.add_log(
        message_id=message_id,
        recipient_username="user1",
        recipient_userid="11111",
        status=MessageLogStatus.SENT,
        commentid="abc",
    )
    
    # Try to add mixed watchers
    watchers = [
        {"username": "user1", "userid": "11111"},  # Already sent
        {"username": "user2", "userid": "22222"},  # Valid
        {"username": "", "userid": ""},            # Invalid
        {"username": "user3", "userid": "33333"},  # Valid
    ]
    
    result = service.add_selected_saved_to_queue(watchers)
    
    # Should add user2 and user3, skip user1, mark 1 invalid
    assert result["success"] is True
    assert result["added_count"] == 2
    assert result["already_sent_count"] == 1
    assert result["invalid_count"] == 1
    assert result["skipped_count"] == 0
    
    # Check queue has user2 and user3
    pending = queue_repo.get_pending(limit=10)
    assert len(pending) == 2
    usernames = {entry.recipient_username for entry in pending}
    assert usernames == {"user2", "user3"}
