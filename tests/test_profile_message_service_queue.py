"""Tests for ProfileMessageService queue utilities."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.service.profile_message_service import ProfileMessageService


class TestProfileMessageServiceQueue:
    """Test in-memory watchers queue operations."""

    def _create_service(self) -> ProfileMessageService:
        message_repo = MagicMock()
        log_repo = MagicMock()
        watcher_repo = MagicMock()
        logger = MagicMock()

        return ProfileMessageService(
            message_repo=message_repo,
            log_repo=log_repo,
            watcher_repo=watcher_repo,
            logger=logger,
        )

    def test_remove_selected_from_queue_removes_only_selected(self) -> None:
        """Remove selected should drop only items with selected=True."""
        service = self._create_service()
        service._watchers_queue = [
            {"username": "a", "userid": "1", "selected": True},
            {"username": "b", "userid": "2", "selected": False},
            {"username": "c", "userid": "3", "selected": True},
        ]

        result = service.remove_selected_from_queue()

        assert result["success"] is True
        assert result["removed_count"] == 2
        assert result["remaining_count"] == 1
        assert service.get_watchers_list() == [
            {"username": "b", "userid": "2", "selected": False}
        ]

    def test_remove_selected_from_queue_when_none_selected(self) -> None:
        """Remove selected should be a no-op when nothing is selected."""
        service = self._create_service()
        service._watchers_queue = [
            {"username": "a", "userid": "1", "selected": False},
            {"username": "b", "userid": "2", "selected": False},
        ]

        result = service.remove_selected_from_queue()

        assert result["success"] is True
        assert result["removed_count"] == 0
        assert result["remaining_count"] == 2
        assert [w["username"] for w in service.get_watchers_list()] == ["a", "b"]

    def test_add_selected_saved_to_queue_adds_skips_and_invalid(self) -> None:
        """Bulk add should add new watchers, skip duplicates, count invalid."""
        service = self._create_service()
        service._watchers_queue = [
            {"username": "exists", "userid": "1", "selected": False},
        ]

        result = service.add_selected_saved_to_queue(
            [
                {"username": "exists", "userid": "1"},
                {"username": "new", "userid": "2"},
                {"username": "new", "userid": "2"},
                {"username": "", "userid": "3"},
            ]
        )

        assert result["success"] is True
        assert result["added_count"] == 1
        assert result["skipped_count"] == 2
        assert result["invalid_count"] == 1

        queue = service.get_watchers_list()
        assert [w["username"] for w in queue] == ["exists", "new"]
        assert queue[1]["selected"] is True

    def test_add_selected_saved_to_queue_empty_is_noop(self) -> None:
        """Bulk add should return zeros for empty input."""
        service = self._create_service()

        result = service.add_selected_saved_to_queue([])

        assert result == {
            "success": True,
            "added_count": 0,
            "skipped_count": 0,
            "invalid_count": 0,
        }
