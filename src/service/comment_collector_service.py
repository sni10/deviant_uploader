"""Service for collecting deviations for auto-commenting."""

from __future__ import annotations

import time
from logging import Logger
from typing import Optional

import requests

from ..storage.deviation_comment_log_repository import DeviationCommentLogRepository
from ..storage.deviation_comment_queue_repository import (
    DeviationCommentQueueRepository,
)
from ..storage.deviation_comment_state_repository import (
    DeviationCommentStateRepository,
)
from .http_client import DeviantArtHttpClient


class CommentCollectorService:
    """Collect deviations from feeds for auto-commenting."""

    WATCH_FEED_URL = "https://www.deviantart.com/api/v1/oauth2/browse/deviantsyouwatch"
    GLOBAL_FEED_URL = "https://www.deviantart.com/api/v1/oauth2/browse/newest"

    def __init__(
        self,
        queue_repo: DeviationCommentQueueRepository,
        log_repo: DeviationCommentLogRepository,
        state_repo: DeviationCommentStateRepository,
        logger: Logger,
        token_repo=None,
        http_client: Optional[DeviantArtHttpClient] = None,
    ) -> None:
        self.queue_repo = queue_repo
        self.log_repo = log_repo
        self.state_repo = state_repo
        self.logger = logger
        self.http_client = http_client or DeviantArtHttpClient(
            logger=logger, token_repo=token_repo
        )

    def collect_from_watch_feed(
        self, access_token: str, max_pages: int = 5
    ) -> dict[str, int]:
        """Collect deviations from watch feed.

        Args:
            access_token: OAuth access token.
            max_pages: Maximum number of pages to fetch.

        Returns:
            Dictionary with collection results: {pages, deviations_added, offset}.
        """
        return self._collect(
            url=self.WATCH_FEED_URL,
            access_token=access_token,
            offset_key="comment_watch_offset",
            max_pages=max_pages,
            source="watch_feed",
        )

    def collect_from_global_feed(
        self, access_token: str, max_pages: int = 5
    ) -> dict[str, int]:
        """Collect deviations from global newest feed.

        Args:
            access_token: OAuth access token.
            max_pages: Maximum number of pages to fetch.

        Returns:
            Dictionary with collection results: {pages, deviations_added, offset}.
        """
        return self._collect(
            url=self.GLOBAL_FEED_URL,
            access_token=access_token,
            offset_key="comment_global_offset",
            max_pages=max_pages,
            source="global_feed",
        )

    def _collect(
        self,
        *,
        url: str,
        access_token: str,
        offset_key: str,
        max_pages: int,
        source: str,
    ) -> dict[str, int]:
        """Collect deviations from a given feed URL.

        Args:
            url: DeviantArt API feed URL.
            access_token: OAuth access token.
            offset_key: State key for pagination offset.
            max_pages: Maximum number of pages to fetch.
            source: Source identifier stored in queue.

        Returns:
            Dictionary with collection results: {pages, deviations_added, offset}.
        """
        offset = 0
        stored_offset = self.state_repo.get_state(offset_key)
        if stored_offset:
            try:
                offset = int(stored_offset)
            except ValueError:
                self.logger.warning("Invalid offset stored for %s: %s", offset_key, stored_offset)

        pages = 0
        deviations_added = 0
        limit = 50
        commented_ids = self.log_repo.get_commented_deviationids()

        self.logger.info(
            "Starting comment collection: source=%s, max_pages=%s, offset=%s",
            source,
            max_pages,
            offset,
        )

        while pages < max_pages:
            params = {
                "access_token": access_token,
                "limit": limit,
                "offset": offset,
                "mature_content": "true",
            }

            try:
                response = self.http_client.get(url, params=params, timeout=30)
                try:
                    data = response.json() or {}
                except ValueError as e:
                    self.logger.error("Feed response JSON decode failed: %s", e)
                    break
            except requests.RequestException as e:
                self.logger.error("Comment feed fetch failed: %s", e)
                break

            if not isinstance(data, dict):
                self.logger.error("Feed response is not a dict: %r", data)
                break

            results = data.get("results", [])
            current_time = int(time.time())

            for item in results:
                normalized = self._normalize_deviation(item, source, current_time)
                if not normalized:
                    continue

                deviationid = normalized["deviationid"]
                if deviationid in commented_ids:
                    continue

                try:
                    self.queue_repo.add_deviation(**normalized)
                    deviations_added += 1
                except Exception as e:  # noqa: BLE001
                    self.logger.warning(
                        "Failed to add deviation %s to queue: %s",
                        deviationid,
                        e,
                    )

            pages += 1

            has_more = bool(data.get("has_more"))
            next_offset = data.get("next_offset")

            if next_offset is not None:
                try:
                    offset = int(next_offset)
                except (TypeError, ValueError):
                    offset += limit
                self.state_repo.set_state(offset_key, str(offset))

            if not has_more:
                break

            if pages < max_pages:
                delay = self.http_client.get_recommended_delay()
                self.logger.debug(
                    "Waiting %s seconds before next comment feed request",
                    delay,
                )
                time.sleep(delay)

        self.logger.info(
            "Comment collection completed: source=%s, pages=%s, deviations=%s",
            source,
            pages,
            deviations_added,
        )

        return {
            "pages": pages,
            "deviations_added": deviations_added,
            "offset": offset,
        }

    def _normalize_deviation(
        self,
        item: object,
        source: str,
        fallback_ts: int,
    ) -> dict[str, object] | None:
        """Normalize API deviation payload for queue insertion."""
        if not isinstance(item, dict):
            return None

        deviationid = item.get("deviationid")
        if not deviationid:
            return None

        title = item.get("title")
        deviation_url = item.get("url") or item.get("deviation_url")
        author = item.get("author") or item.get("user") or {}

        author_username = None
        author_userid = None
        if isinstance(author, dict):
            author_username = author.get("username")
            author_userid = author.get("userid")

        ts = item.get("published_time", fallback_ts)
        if isinstance(ts, str):
            try:
                ts = int(ts)
            except ValueError:
                ts = fallback_ts
        elif isinstance(ts, (int, float)):
            ts = int(ts)
        else:
            ts = fallback_ts

        return {
            "deviationid": str(deviationid),
            "deviation_url": deviation_url,
            "title": title,
            "author_username": author_username,
            "author_userid": author_userid,
            "source": source,
            "ts": ts,
        }
