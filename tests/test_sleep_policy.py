"""Tests for the project's sleep/delay policy.

All service-layer sleeps must use the centralized HTTP client's
`get_recommended_delay()` to respect API rate limiting.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestSleepPolicy:
    """Validate that services use HTTP client's recommended delay."""

    @patch("src.service.api_pagination_helper.time.sleep", autospec=True)
    def test_profile_message_service_fetch_watchers_uses_recommended_delay(
        self, sleep_mock: MagicMock
    ) -> None:
        """`fetch_watchers` should sleep using `http_client.get_recommended_delay()`."""

        from src.service.profile_message_service import ProfileMessageService

        message_repo = MagicMock()
        log_repo = MagicMock()
        queue_repo = MagicMock()
        watcher_repo = MagicMock()
        logger = MagicMock()

        http_client = MagicMock()
        http_client.get_recommended_delay.return_value = 7

        resp1 = MagicMock()
        resp1.json.return_value = {
            "results": [{"user": {"username": "u1", "userid": "1"}}],
            "has_more": True,
            "next_offset": 50,
        }
        resp2 = MagicMock()
        resp2.json.return_value = {
            "results": [],
            "has_more": False,
            "next_offset": None,
        }
        http_client.get.side_effect = [resp1, resp2]

        service = ProfileMessageService(
            message_repo=message_repo,
            log_repo=log_repo,
            queue_repo=queue_repo,
            watcher_repo=watcher_repo,
            logger=logger,
            http_client=http_client,
        )

        service.fetch_watchers(access_token="token", username="me", max_watchers=100)

        http_client.get_recommended_delay.assert_called_once_with()
        sleep_mock.assert_called_once_with(7)

    @patch("src.service.api_pagination_helper.time.sleep", autospec=True)
    def test_gallery_service_fetch_galleries_uses_recommended_delay(
        self, sleep_mock: MagicMock
    ) -> None:
        """`fetch_galleries` should sleep using `http_client.get_recommended_delay()`."""

        from src.service.gallery_service import GalleryService

        gallery_repo = MagicMock()
        logger = MagicMock()

        http_client = MagicMock()
        http_client.get_recommended_delay.return_value = 9

        resp1 = MagicMock()
        resp1.json.return_value = {
            "results": [{"folderid": "f1"}],
            "has_more": True,
            "next_offset": 50,
        }
        resp2 = MagicMock()
        resp2.json.return_value = {
            "results": [],
            "has_more": False,
            "next_offset": None,
        }
        http_client.get.side_effect = [resp1, resp2]

        service = GalleryService(
            gallery_repository=gallery_repo,
            logger=logger,
            http_client=http_client,
        )

        service.fetch_galleries(access_token="token")

        http_client.get_recommended_delay.assert_called_once_with()
        sleep_mock.assert_called_once_with(9)

    @patch("src.service.api_pagination_helper.time.sleep", autospec=True)
    def test_mass_fave_service_collect_from_feed_uses_recommended_delay(
        self, sleep_mock: MagicMock
    ) -> None:
        """`collect_from_feed` should sleep using `http_client.get_recommended_delay()`."""

        from src.service.mass_fave_service import MassFaveService

        repo = MagicMock()
        logger = MagicMock()

        http_client = MagicMock()
        http_client.get_recommended_delay.return_value = 11

        resp1 = MagicMock()
        resp1.json.return_value = {
            "results": [{"deviationid": "d1", "published_time": 1}],
            "has_more": True,
            "next_offset": 50,
        }
        resp2 = MagicMock()
        resp2.json.return_value = {
            "results": [],
            "has_more": False,
            "next_offset": None,
        }
        http_client.get.side_effect = [resp1, resp2]

        service = MassFaveService(feed_deviation_repo=repo, logger=logger, http_client=http_client)
        service.collect_from_feed(access_token="token", max_pages=2)

        http_client.get_recommended_delay.assert_called_once_with()
        sleep_mock.assert_called_once_with(11)
