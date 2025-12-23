"""Tests for retry failed messages functionality."""

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


def test_retry_failed_messages_empty(service, log_repo, queue_repo):
    """Test retry_failed_messages when no failed logs exist."""
    # Ensure no failed logs
    failed_logs = log_repo.get_failed_logs(limit=10)
    assert len(failed_logs) == 0
    
    # Call retry
    result = service.retry_failed_messages(limit=100)
    
    # Should succeed with 0 added
    assert result["success"] is True
    assert result["added_count"] == 0
    assert result["skipped_count"] == 0
    assert "No failed messages found" in result["message"]
    
    # Queue should be empty
    queue_count = queue_repo.get_queue_count()
    assert queue_count == 0


def test_retry_failed_messages_with_failures(
    service, message_repo, log_repo, queue_repo
):
    """Test retry_failed_messages adds failed logs to queue with high priority."""
    # Create a message template
    message_id = message_repo.create_message(
        title="Test Message",
        body="Test body"
    )
    
    # Add some failed logs
    log_repo.add_log(
        message_id=message_id,
        recipient_username="user1",
        recipient_userid="12345",
        status=MessageLogStatus.FAILED,
        error_message="Network error",
    )
    log_repo.add_log(
        message_id=message_id,
        recipient_username="user2",
        recipient_userid="67890",
        status=MessageLogStatus.FAILED,
        error_message="Rate limit",
    )
    
    # Add a successful log (should not be retried)
    log_repo.add_log(
        message_id=message_id,
        recipient_username="user3",
        recipient_userid="11111",
        status=MessageLogStatus.SENT,
        commentid="abc123",
    )
    
    # Verify failed logs exist
    failed_logs = log_repo.get_failed_logs(limit=10)
    assert len(failed_logs) == 2
    
    # Call retry
    result = service.retry_failed_messages(limit=100)
    
    # Should succeed with 2 added and 2 deleted
    assert result["success"] is True
    assert result["added_count"] == 2
    assert result["skipped_count"] == 0
    assert result["deleted_count"] == 2
    
    # Check queue has 2 entries
    queue_count = queue_repo.get_queue_count()
    assert queue_count == 2
    
    # Check entries have high priority (10)
    pending = queue_repo.get_pending(limit=10)
    assert len(pending) == 2
    
    # All should have priority 10
    for entry in pending:
        assert entry.priority == 10
        assert entry.status == QueueStatus.PENDING
        assert entry.message_id == message_id
    
    # Check usernames match failed logs
    usernames = {entry.recipient_username for entry in pending}
    assert usernames == {"user1", "user2"}
    
    # Verify failed logs were deleted from history
    failed_logs_after = log_repo.get_failed_logs(limit=10)
    assert len(failed_logs_after) == 0
    
    # Verify successful log was NOT deleted
    all_logs = log_repo.get_all_logs(limit=10)
    assert len(all_logs) == 1
    assert all_logs[0].recipient_username == "user3"
    assert all_logs[0].status == MessageLogStatus.SENT


def test_retry_failed_messages_respects_limit(
    service, message_repo, log_repo, queue_repo
):
    """Test retry_failed_messages respects limit parameter."""
    # Create a message template
    message_id = message_repo.create_message(
        title="Test Message",
        body="Test body"
    )
    
    # Add 5 failed logs
    for i in range(5):
        log_repo.add_log(
            message_id=message_id,
            recipient_username=f"user{i}",
            recipient_userid=f"{10000 + i}",
            status=MessageLogStatus.FAILED,
            error_message="Error",
        )
    
    # Verify 5 failed logs exist
    failed_logs_before = log_repo.get_failed_logs(limit=10)
    assert len(failed_logs_before) == 5
    
    # Retry with limit=3
    result = service.retry_failed_messages(limit=3)
    
    # Should add only 3 and delete only 3
    assert result["success"] is True
    assert result["added_count"] == 3
    assert result["deleted_count"] == 3
    
    # Queue should have 3 entries
    queue_count = queue_repo.get_queue_count()
    assert queue_count == 3
    
    # Should have 2 failed logs remaining (5 - 3 = 2)
    failed_logs_after = log_repo.get_failed_logs(limit=10)
    assert len(failed_logs_after) == 2


def test_queue_repository_basic_operations(queue_repo, message_repo):
    """Test basic queue repository operations."""
    # Create a message
    message_id = message_repo.create_message(
        title="Test",
        body="Body"
    )
    
    # Add to queue
    queue_id = queue_repo.add_to_queue(
        message_id=message_id,
        recipient_username="testuser",
        recipient_userid="99999",
        priority=5,
    )
    
    assert queue_id is not None
    
    # Get pending
    pending = queue_repo.get_pending(limit=10)
    assert len(pending) == 1
    assert pending[0].queue_id == queue_id
    assert pending[0].recipient_username == "testuser"
    assert pending[0].priority == 5
    assert pending[0].status == QueueStatus.PENDING
    
    # Mark processing
    queue_repo.mark_processing(queue_id)
    pending = queue_repo.get_pending(limit=10)
    assert len(pending) == 0  # No longer pending
    
    # Mark completed
    queue_repo.mark_completed(queue_id)
    
    # Get all entries
    all_entries = queue_repo.get_all_queue_entries(limit=10)
    assert len(all_entries) == 1
    assert all_entries[0].status == QueueStatus.COMPLETED


def test_queue_repository_priority_ordering(queue_repo, message_repo):
    """Test queue entries are ordered by priority (highest first)."""
    message_id = message_repo.create_message(
        title="Test",
        body="Body"
    )
    
    # Add entries with different priorities
    queue_repo.add_to_queue(
        message_id=message_id,
        recipient_username="low_priority",
        recipient_userid="1",
        priority=0,
    )
    queue_repo.add_to_queue(
        message_id=message_id,
        recipient_username="high_priority",
        recipient_userid="2",
        priority=10,
    )
    queue_repo.add_to_queue(
        message_id=message_id,
        recipient_username="medium_priority",
        recipient_userid="3",
        priority=5,
    )
    
    # Get pending - should be ordered by priority desc
    pending = queue_repo.get_pending(limit=10)
    assert len(pending) == 3
    
    # Check order: high (10), medium (5), low (0)
    assert pending[0].recipient_username == "high_priority"
    assert pending[0].priority == 10
    assert pending[1].recipient_username == "medium_priority"
    assert pending[1].priority == 5
    assert pending[2].recipient_username == "low_priority"
    assert pending[2].priority == 0


def test_queue_repository_clear_queue(queue_repo, message_repo):
    """Test clearing queue entries."""
    message_id = message_repo.create_message(
        title="Test",
        body="Body"
    )
    
    # Add some entries
    for i in range(3):
        queue_repo.add_to_queue(
            message_id=message_id,
            recipient_username=f"user{i}",
            recipient_userid=f"{i}",
            priority=0,
        )
    
    # Clear all
    cleared = queue_repo.clear_queue()
    assert cleared == 3
    
    # Queue should be empty
    count = queue_repo.get_queue_count()
    assert count == 0


def test_get_failed_logs(log_repo, message_repo):
    """Test get_failed_logs returns only failed logs."""
    message_id = message_repo.create_message(
        title="Test",
        body="Body"
    )
    
    # Add mixed logs
    log_repo.add_log(
        message_id=message_id,
        recipient_username="failed1",
        recipient_userid="1",
        status=MessageLogStatus.FAILED,
        error_message="Error 1",
    )
    log_repo.add_log(
        message_id=message_id,
        recipient_username="sent1",
        recipient_userid="2",
        status=MessageLogStatus.SENT,
        commentid="abc",
    )
    log_repo.add_log(
        message_id=message_id,
        recipient_username="failed2",
        recipient_userid="3",
        status=MessageLogStatus.FAILED,
        error_message="Error 2",
    )
    
    # Get failed logs
    failed = log_repo.get_failed_logs(limit=10)
    
    # Should return only failed logs
    assert len(failed) == 2
    usernames = {log.recipient_username for log in failed}
    assert usernames == {"failed1", "failed2"}
    
    # All should have FAILED status
    for log in failed:
        assert log.status == MessageLogStatus.FAILED
        assert log.error_message is not None
