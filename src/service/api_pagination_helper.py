"""Helper utility for DeviantArt API offset-based pagination.

This module provides a reusable pattern for paginating through DeviantArt API
results with proper rate limiting and error handling.
"""
from __future__ import annotations

import time
from logging import Logger
from typing import Any, Callable, Generator

from src.service.http_client import DeviantArtHttpClient


class APIPaginationHelper:
    """Helper for DeviantArt API offset-based pagination.

    Provides a reusable pattern for paginating through API results
    with proper rate limiting and error handling.
    """

    def __init__(
        self,
        http_client: DeviantArtHttpClient,
        logger: Logger,
    ):
        """Initialize pagination helper.

        Args:
            http_client: DeviantArt HTTP client for API requests
            logger: Logger instance
        """
        self.http_client = http_client
        self.logger = logger
        self.last_offset: int | None = None
        self.pages_fetched = 0

    def paginate(
        self,
        url: str,
        access_token: str,
        limit: int = 50,
        max_pages: int | None = None,
        additional_params: dict | None = None,
        process_item: Callable[[dict], Any] | None = None,
        initial_offset: int = 0,
        page_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> Generator[dict, None, None]:
        """Paginate through DeviantArt API endpoint.

        Args:
            url: API endpoint URL
            access_token: OAuth access token
            limit: Items per page (default: 50)
            max_pages: Maximum pages to fetch (None = unlimited)
            additional_params: Additional query parameters
            process_item: Optional callback to process each item before
                yielding
            initial_offset: Starting offset for pagination
            page_callback: Optional callback invoked after each page

        Yields:
            Individual items from API results

        Example:
            ```python
            pagination = APIPaginationHelper(http_client, logger)
            for item in pagination.paginate(
                url="https://www.deviantart.com/api/v1/oauth2/browse/home",
                access_token=token,
                limit=50,
                max_pages=10,
            ):
                # Process item
                process_deviation(item)
            ```
        """
        offset = int(initial_offset)
        pages = 0
        has_more = True
        self.pages_fetched = 0
        self.last_offset = offset

        while (max_pages is None or pages < max_pages) and has_more:
            params = {
                "access_token": access_token,
                "limit": limit,
                "offset": offset,
            }
            if additional_params:
                params.update(additional_params)

            self.logger.debug(
                "Fetching page %d (offset=%d, limit=%d)",
                pages + 1,
                offset,
                limit,
            )

            response = self.http_client.get(url, params=params, timeout=30)
            data = response.json() or {}

            # Yield results
            results = data.get("results", [])
            for item in results:
                if process_item:
                    processed = process_item(item)
                    if processed is not None:
                        yield processed
                else:
                    yield item

            pages += 1
            has_more = bool(data.get("has_more"))
            next_offset = data.get("next_offset")

            if next_offset is not None:
                try:
                    offset = int(next_offset)
                except (TypeError, ValueError):
                    offset += limit
                    self.logger.warning(
                        "Invalid next_offset %r; falling back to offset %d",
                        next_offset,
                        offset,
                    )

            self.pages_fetched = pages
            self.last_offset = offset

            if page_callback:
                page_callback(
                    {
                        "page": pages,
                        "offset": offset,
                        "has_more": has_more,
                        "next_offset": next_offset,
                        "results_count": len(results),
                    }
                )

            if not has_more:
                self.logger.debug("No more pages available")
                break

            # Rate limiting delay
            delay = self.http_client.get_recommended_delay()
            self.logger.debug("Waiting %s seconds before next page", delay)
            time.sleep(delay)

        self.logger.info(
            "Pagination complete: %d pages fetched, final offset=%d",
            pages,
            offset,
        )
