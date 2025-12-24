"""Tests for APIPaginationHelper utility."""
import pytest
from unittest.mock import Mock, patch, call
from logging import Logger

from src.service.api_pagination_helper import APIPaginationHelper
from src.service.http_client import DeviantArtHttpClient


class TestAPIPaginationHelper:
    """Test APIPaginationHelper pagination logic."""

    def test_initialization(self):
        """Test helper initialization."""
        http_client = Mock(spec=DeviantArtHttpClient)
        logger = Mock(spec=Logger)

        helper = APIPaginationHelper(http_client=http_client, logger=logger)

        assert helper.http_client is http_client
        assert helper.logger is logger

    def test_paginate_single_page(self):
        """Test pagination with single page of results."""
        http_client = Mock(spec=DeviantArtHttpClient)
        logger = Mock(spec=Logger)

        # Mock response
        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [{"id": 1}, {"id": 2}, {"id": 3}],
            "has_more": False,
        }
        http_client.get.return_value = mock_response
        http_client.get_recommended_delay.return_value = 0.001

        helper = APIPaginationHelper(http_client, logger)

        with patch("src.service.api_pagination_helper.time.sleep"):
            items = list(
                helper.paginate(
                    url="https://api.example.com/items",
                    access_token="test_token",
                    limit=50,
                )
            )

        # Verify results
        assert len(items) == 3
        assert items[0] == {"id": 1}
        assert items[1] == {"id": 2}
        assert items[2] == {"id": 3}

        # Verify HTTP call
        http_client.get.assert_called_once_with(
            "https://api.example.com/items",
            params={"access_token": "test_token", "limit": 50, "offset": 0},
            timeout=30,
        )

    def test_paginate_multiple_pages(self):
        """Test pagination with multiple pages."""
        http_client = Mock(spec=DeviantArtHttpClient)
        logger = Mock(spec=Logger)

        # Mock responses for 3 pages
        page1_response = Mock()
        page1_response.json.return_value = {
            "results": [{"id": 1}, {"id": 2}],
            "has_more": True,
            "next_offset": 2,
        }

        page2_response = Mock()
        page2_response.json.return_value = {
            "results": [{"id": 3}, {"id": 4}],
            "has_more": True,
            "next_offset": 4,
        }

        page3_response = Mock()
        page3_response.json.return_value = {
            "results": [{"id": 5}],
            "has_more": False,
        }

        http_client.get.side_effect = [
            page1_response,
            page2_response,
            page3_response,
        ]
        http_client.get_recommended_delay.return_value = 0.001

        helper = APIPaginationHelper(http_client, logger)

        with patch("src.service.api_pagination_helper.time.sleep") as mock_sleep:
            items = list(
                helper.paginate(
                    url="https://api.example.com/items",
                    access_token="test_token",
                    limit=2,
                )
            )

        # Verify results
        assert len(items) == 5
        assert [item["id"] for item in items] == [1, 2, 3, 4, 5]

        # Verify HTTP calls
        assert http_client.get.call_count == 3
        assert http_client.get.call_args_list[0][1]["params"]["offset"] == 0
        assert http_client.get.call_args_list[1][1]["params"]["offset"] == 2
        assert http_client.get.call_args_list[2][1]["params"]["offset"] == 4

        # Verify rate limiting (sleep called between pages)
        assert mock_sleep.call_count == 2

    def test_paginate_initial_offset_and_page_callback(self):
        """Test pagination starting offset and page callback metadata."""
        http_client = Mock(spec=DeviantArtHttpClient)
        logger = Mock(spec=Logger)

        page1_response = Mock()
        page1_response.json.return_value = {
            "results": [{"id": 1}],
            "has_more": True,
            "next_offset": 10,
        }

        page2_response = Mock()
        page2_response.json.return_value = {
            "results": [{"id": 2}],
            "has_more": False,
            "next_offset": None,
        }

        http_client.get.side_effect = [page1_response, page2_response]
        http_client.get_recommended_delay.return_value = 0.001

        helper = APIPaginationHelper(http_client, logger)
        page_callback = Mock()

        with patch("src.service.api_pagination_helper.time.sleep"):
            items = list(
                helper.paginate(
                    url="https://api.example.com/items",
                    access_token="test_token",
                    limit=1,
                    initial_offset=100,
                    page_callback=page_callback,
                )
            )

        assert [item["id"] for item in items] == [1, 2]
        assert http_client.get.call_args_list[0][1]["params"]["offset"] == 100
        assert helper.pages_fetched == 2
        assert helper.last_offset == 10

        assert page_callback.call_count == 2
        first_info = page_callback.call_args_list[0][0][0]
        assert first_info["page"] == 1
        assert first_info["offset"] == 10
        assert first_info["has_more"] is True
        assert first_info["next_offset"] == 10

    def test_paginate_respects_max_pages(self):
        """Test that pagination stops at max_pages limit."""
        http_client = Mock(spec=DeviantArtHttpClient)
        logger = Mock(spec=Logger)

        # Mock infinite pages
        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [{"id": 1}],
            "has_more": True,
            "next_offset": 1,
        }
        http_client.get.return_value = mock_response
        http_client.get_recommended_delay.return_value = 0.001

        helper = APIPaginationHelper(http_client, logger)

        with patch("src.service.api_pagination_helper.time.sleep"):
            items = list(
                helper.paginate(
                    url="https://api.example.com/items",
                    access_token="test_token",
                    limit=1,
                    max_pages=3,
                )
            )

        # Should fetch exactly 3 pages
        assert len(items) == 3
        assert http_client.get.call_count == 3

    def test_paginate_with_additional_params(self):
        """Test pagination with additional query parameters."""
        http_client = Mock(spec=DeviantArtHttpClient)
        logger = Mock(spec=Logger)

        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [{"id": 1}],
            "has_more": False,
        }
        http_client.get.return_value = mock_response
        http_client.get_recommended_delay.return_value = 0.001

        helper = APIPaginationHelper(http_client, logger)

        with patch("src.service.api_pagination_helper.time.sleep"):
            items = list(
                helper.paginate(
                    url="https://api.example.com/items",
                    access_token="test_token",
                    limit=50,
                    additional_params={"mature_content": "true", "type": "art"},
                )
            )

        # Verify additional params included
        call_params = http_client.get.call_args[1]["params"]
        assert call_params["access_token"] == "test_token"
        assert call_params["limit"] == 50
        assert call_params["offset"] == 0
        assert call_params["mature_content"] == "true"
        assert call_params["type"] == "art"

    def test_paginate_with_process_item_callback(self):
        """Test pagination with process_item callback."""
        http_client = Mock(spec=DeviantArtHttpClient)
        logger = Mock(spec=Logger)

        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [{"id": 1}, {"id": 2}, {"id": 3}],
            "has_more": False,
        }
        http_client.get.return_value = mock_response
        http_client.get_recommended_delay.return_value = 0.001

        def process_item(item):
            """Transform item by adding 'processed' flag."""
            return {**item, "processed": True}

        helper = APIPaginationHelper(http_client, logger)

        with patch("src.service.api_pagination_helper.time.sleep"):
            items = list(
                helper.paginate(
                    url="https://api.example.com/items",
                    access_token="test_token",
                    limit=50,
                    process_item=process_item,
                )
            )

        # Verify items were processed
        assert len(items) == 3
        assert all(item.get("processed") is True for item in items)

    def test_paginate_process_item_filters_none(self):
        """Test that process_item can filter items by returning None."""
        http_client = Mock(spec=DeviantArtHttpClient)
        logger = Mock(spec=Logger)

        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}],
            "has_more": False,
        }
        http_client.get.return_value = mock_response
        http_client.get_recommended_delay.return_value = 0.001

        def process_item(item):
            """Only return even-numbered items."""
            if item["id"] % 2 == 0:
                return item
            return None

        helper = APIPaginationHelper(http_client, logger)

        with patch("src.service.api_pagination_helper.time.sleep"):
            items = list(
                helper.paginate(
                    url="https://api.example.com/items",
                    access_token="test_token",
                    limit=50,
                    process_item=process_item,
                )
            )

        # Only even IDs should be yielded
        assert len(items) == 2
        assert items[0]["id"] == 2
        assert items[1]["id"] == 4

    def test_paginate_empty_results(self):
        """Test pagination with empty results."""
        http_client = Mock(spec=DeviantArtHttpClient)
        logger = Mock(spec=Logger)

        mock_response = Mock()
        mock_response.json.return_value = {"results": [], "has_more": False}
        http_client.get.return_value = mock_response
        http_client.get_recommended_delay.return_value = 0.001

        helper = APIPaginationHelper(http_client, logger)

        with patch("src.service.api_pagination_helper.time.sleep"):
            items = list(
                helper.paginate(
                    url="https://api.example.com/items",
                    access_token="test_token",
                    limit=50,
                )
            )

        # Should return empty list
        assert len(items) == 0

    def test_paginate_rate_limiting(self):
        """Test that rate limiting delay is applied between pages."""
        http_client = Mock(spec=DeviantArtHttpClient)
        logger = Mock(spec=Logger)

        # Two pages
        page1 = Mock()
        page1.json.return_value = {
            "results": [{"id": 1}],
            "has_more": True,
            "next_offset": 1,
        }

        page2 = Mock()
        page2.json.return_value = {"results": [{"id": 2}], "has_more": False}

        http_client.get.side_effect = [page1, page2]
        http_client.get_recommended_delay.return_value = 2.5

        helper = APIPaginationHelper(http_client, logger)

        with patch("src.service.api_pagination_helper.time.sleep") as mock_sleep:
            items = list(
                helper.paginate(
                    url="https://api.example.com/items",
                    access_token="test_token",
                    limit=1,
                )
            )

        # Verify sleep was called with recommended delay
        mock_sleep.assert_called_once_with(2.5)

    def test_paginate_logs_progress(self):
        """Test that pagination logs progress information."""
        http_client = Mock(spec=DeviantArtHttpClient)
        logger = Mock(spec=Logger)

        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [{"id": 1}],
            "has_more": False,
        }
        http_client.get.return_value = mock_response
        http_client.get_recommended_delay.return_value = 0.001

        helper = APIPaginationHelper(http_client, logger)

        with patch("src.service.api_pagination_helper.time.sleep"):
            items = list(
                helper.paginate(
                    url="https://api.example.com/items",
                    access_token="test_token",
                    limit=50,
                )
            )

        # Verify logging calls
        assert logger.debug.call_count >= 2  # At least page fetch + no more
        assert logger.info.call_count == 1  # Pagination complete

        # Check completion log message
        completion_call = logger.info.call_args[0]
        assert "Pagination complete" in completion_call[0]
