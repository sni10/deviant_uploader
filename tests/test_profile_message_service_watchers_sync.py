"""Tests for ProfileMessageService watchers synchronization/pruning."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.service.profile_message_service import ProfileMessageService


class TestProfileMessageServiceWatchersSync:
    """Validate safe pruning of unfollowed watchers."""

    def _make_service(self, http_client: MagicMock, watcher_repo: MagicMock) -> ProfileMessageService:
        message_repo = MagicMock()
        log_repo = MagicMock()
        log_repo.get_stats.return_value = {"sent": 0, "failed": 0}
        logger = MagicMock()
        return ProfileMessageService(
            message_repo=message_repo,
            log_repo=log_repo,
            watcher_repo=watcher_repo,
            logger=logger,
            http_client=http_client,
        )

    def test_fetch_watchers_does_not_prune_if_has_more_true_and_limit_reached(self) -> None:
        """Do not delete from DB if we did not fetch the full watchers list."""
        http_client = MagicMock()

        resp = MagicMock()
        resp.json.return_value = {
            "results": [
                {"user": {"username": "u1", "userid": "id1"}},
                {"user": {"username": "u2", "userid": "id2"}},
            ],
            "has_more": True,
            "next_offset": 50,
        }
        http_client.get.return_value = resp
        http_client.get_recommended_delay.return_value = 0

        watcher_repo = MagicMock()
        service = self._make_service(http_client=http_client, watcher_repo=watcher_repo)

        result = service.fetch_watchers(
            access_token="token",
            username="me",
            max_watchers=1,
        )

        assert result["has_more"] is True
        assert result["pruned"] is False
        watcher_repo.delete_watchers_not_in_list.assert_not_called()

    def test_fetch_watchers_prunes_when_full_list_fetched(self) -> None:
        """When has_more=False, service may prune watchers absent from API list."""
        http_client = MagicMock()

        resp = MagicMock()
        resp.json.return_value = {
            "results": [
                {"user": {"username": "u1", "userid": "id1"}},
                {"user": {"username": "u2", "userid": "id2"}},
            ],
            "has_more": False,
            "next_offset": None,
        }
        http_client.get.return_value = resp
        http_client.get_recommended_delay.return_value = 0

        watcher_repo = MagicMock()
        watcher_repo.delete_watchers_not_in_list.return_value = 2
        service = self._make_service(http_client=http_client, watcher_repo=watcher_repo)

        result = service.fetch_watchers(
            access_token="token",
            username="me",
            max_watchers=50,
        )

        assert result["has_more"] is False
        assert result["pruned"] is True
        assert result["deleted_count"] == 2
        watcher_repo.delete_watchers_not_in_list.assert_called_once_with(["u1", "u2"])
