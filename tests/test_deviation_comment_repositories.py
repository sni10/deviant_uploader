"""Tests for deviation comment repositories."""

from __future__ import annotations

from src.domain.models import (
    DeviationCommentLogStatus,
    DeviationCommentQueueStatus,
)
from src.storage.deviation_comment_log_repository import (
    DeviationCommentLogRepository,
)
from src.storage.deviation_comment_message_repository import (
    DeviationCommentMessageRepository,
)
from src.storage.deviation_comment_queue_repository import (
    DeviationCommentQueueRepository,
)
from src.storage.deviation_comment_state_repository import (
    DeviationCommentStateRepository,
)


def test_deviation_comment_message_repository_crud(db_conn) -> None:
    """Create, update, and delete deviation comment templates."""
    repo = DeviationCommentMessageRepository(db_conn)

    message_id = repo.create_message("Title", "Body")
    message = repo.get_message_by_id(message_id)

    assert message is not None
    assert message.title == "Title"
    assert message.body == "Body"
    assert message.is_active is True

    repo.update_message(message_id, title="Updated", body="New", is_active=False)
    updated = repo.get_message_by_id(message_id)

    assert updated is not None
    assert updated.title == "Updated"
    assert updated.body == "New"
    assert updated.is_active is False

    repo.delete_message(message_id)
    assert repo.get_message_by_id(message_id) is None


def test_deviation_comment_queue_repository_upsert_preserves_status(db_conn) -> None:
    """Upsert should update timestamp but keep commented status."""
    repo = DeviationCommentQueueRepository(db_conn)

    repo.add_deviation("dev1", ts=100, source="watch_feed", title="First")
    pending = repo.get_one_pending()

    assert pending is not None
    assert pending["deviationid"] == "dev1"

    repo.mark_commented("dev1")
    repo.add_deviation("dev1", ts=200, source="watch_feed", title="Updated")

    commented = repo.get_recent_commented(limit=10)
    assert len(commented) == 1
    assert commented[0].deviationid == "dev1"
    assert commented[0].status == DeviationCommentQueueStatus.COMMENTED


def test_deviation_comment_queue_repository_stats_and_clear(db_conn) -> None:
    """Queue stats and clear operations should report expected counts."""
    repo = DeviationCommentQueueRepository(db_conn)

    repo.add_deviation("dev1", ts=10, source="watch_feed")
    repo.add_deviation("dev2", ts=20, source="global_feed")
    repo.mark_failed("dev2", "failed")

    stats = repo.get_stats()
    assert stats["pending"] == 1
    assert stats["failed"] == 1
    assert stats["total"] == 2

    cleared = repo.clear_queue(status=DeviationCommentQueueStatus.PENDING)
    assert cleared == 1

    stats = repo.get_stats()
    assert stats["pending"] == 0
    assert stats["failed"] == 1


def test_deviation_comment_state_repository_roundtrip(db_conn) -> None:
    """State repository should store and retrieve values."""
    repo = DeviationCommentStateRepository(db_conn)

    assert repo.get_state("comment_watch_offset") is None
    repo.set_state("comment_watch_offset", "50")
    assert repo.get_state("comment_watch_offset") == "50"


def test_deviation_comment_log_repository_stats(db_conn) -> None:
    """Log repository should track sent and failed counts."""
    message_repo = DeviationCommentMessageRepository(db_conn)
    log_repo = DeviationCommentLogRepository(db_conn)

    message_id = message_repo.create_message("Title", "Body")

    log_repo.add_log(
        message_id=message_id,
        deviationid="dev1",
        status=DeviationCommentLogStatus.SENT,
        comment_text="Hi",
    )
    log_repo.add_log(
        message_id=message_id,
        deviationid="dev2",
        status=DeviationCommentLogStatus.FAILED,
        comment_text="Hi",
        error_message="nope",
    )

    commented_ids = log_repo.get_commented_deviationids()
    assert commented_ids == {"dev1"}

    stats = log_repo.get_stats_by_template()
    assert stats[message_id]["sent"] == 1
    assert stats[message_id]["failed"] == 1
    assert stats[message_id]["total"] == 2
