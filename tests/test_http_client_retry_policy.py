"""Tests for DeviantArtHttpClient retry policy.

The client must only retry rate-limit / transient conditions, and must not retry
client-side request errors such as HTTP 400.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests


class TestDeviantArtHttpClientRetryPolicy:
    """Validate DeviantArtHttpClient retry rules."""

    @patch("src.service.http_client.time.sleep", autospec=True)
    @patch("src.service.http_client.requests.request", autospec=True)
    def test_http_400_is_not_retried(
        self, request_mock: MagicMock, sleep_mock: MagicMock
    ) -> None:
        """HTTP 400 should raise immediately without retrying or sleeping."""

        from src.service.http_client import DeviantArtHttpClient

        logger = MagicMock()
        client = DeviantArtHttpClient(logger=logger, enable_retry=True)

        response = MagicMock()
        response.status_code = 400
        response.headers = {}
        response.text = '{"error":"invalid_request"}'
        response.json.return_value = {
            "error": "invalid_request",
            "error_code": 7,
            "error_description": "Deviation can not be favourited.",
        }
        response.raise_for_status.side_effect = requests.HTTPError(
            "400 Client Error", response=response
        )

        request_mock.return_value = response

        with pytest.raises(requests.HTTPError):
            client.post("https://example.test/fave", data={"k": "v"})

        assert request_mock.call_count == 1
        sleep_mock.assert_not_called()
