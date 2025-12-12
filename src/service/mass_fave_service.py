"""Service for auto-faving deviations from feed."""

import time
import random
import threading
from logging import Logger
from typing import Optional

import requests

from ..storage.feed_deviation_repository import FeedDeviationRepository


class MassFaveService:
    """Coordinates feed collection and auto-faving workflow."""

    FEED_URL = "https://www.deviantart.com/api/v1/oauth2/browse/deviantsyouwatch"
    FAVE_URL = "https://www.deviantart.com/collections/fave"

    def __init__(
        self,
        feed_deviation_repo: FeedDeviationRepository,
        logger: Logger,
    ) -> None:
        self.repo = feed_deviation_repo
        self.logger = logger

        # Worker state
        self._worker_thread: Optional[threading.Thread] = None
        self._worker_running = False
        self._stop_flag = threading.Event()
        self._worker_stats = {
            "processed": 0,
            "errors": 0,
            "last_error": None,
        }
        self._stats_lock = threading.Lock()

    # ========== Collector ==========

    def collect_from_feed(
        self, access_token: str, max_pages: int = 5
    ) -> dict:
        """Collect new deviations from deviantsyouwatch and add to queue.

        Uses offset-based pagination with limit=50 per page.

        Args:
            access_token: OAuth access token
            max_pages: Maximum number of pages to fetch

        Returns:
            Dictionary with collection results: {pages, deviations_added, offset}
        """
        offset_str = self.repo.get_state("feed_offset")
        offset = int(offset_str) if offset_str else 0
        pages = 0
        deviations_added = 0
        limit = 50  # Maximum allowed by API

        self.logger.info(
            "Starting feed collection: max_pages=%s, offset=%s, limit=%s",
            max_pages,
            offset,
            limit,
        )

        while pages < max_pages:
            params = {
                "access_token": access_token,
                "mature_content": "true",
                "limit": limit,
                "offset": offset,
            }

            try:
                response = requests.get(self.FEED_URL, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
            except requests.RequestException as e:
                self.logger.error("Feed fetch failed: %s", e)
                break

            # Extract deviations from results
            results = data.get("results", [])
            current_time = int(time.time())

            for deviation in results:
                deviationid = deviation.get("deviationid")
                # Use published_time if available, otherwise current timestamp
                ts = deviation.get("published_time", current_time)
                if isinstance(ts, str):
                    # If timestamp is string, try to convert or use current time
                    try:
                        ts = int(ts)
                    except ValueError:
                        ts = current_time

                if deviationid:
                    self.repo.add_deviation(str(deviationid), ts)
                    deviations_added += 1

            pages += 1

            # Update offset for next page
            has_more = bool(data.get("has_more"))
            next_offset = data.get("next_offset")

            if next_offset is not None:
                offset = next_offset
                self.repo.set_state("feed_offset", str(offset))

            if not has_more:
                break

            # Delay between pages to avoid rate limiting
            if pages < max_pages:
                time.sleep(2)

        self.logger.info(
            "Feed collection completed: pages=%s, deviations=%s, offset=%s",
            pages,
            deviations_added,
            offset,
        )

        return {
            "pages": pages,
            "deviations_added": deviations_added,
            "offset": offset,
        }

    # ========== Worker ==========

    def start_worker(self, access_token: str) -> dict:
        """Start background worker thread.

        Args:
            access_token: OAuth access token for faving

        Returns:
            Status dictionary: {success, message}
        """
        if self._worker_running:
            return {"success": False, "message": "Worker already running"}

        self._stop_flag.clear()
        with self._stats_lock:
            self._worker_stats = {"processed": 0, "errors": 0, "last_error": None}

        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            args=(access_token,),
            daemon=True,
        )
        self._worker_running = True
        self._worker_thread.start()

        self.logger.info("Worker thread started")
        return {"success": True, "message": "Worker started"}

    def stop_worker(self) -> dict:
        """Stop background worker thread.

        Returns:
            Status dictionary: {success, message}
        """
        if not self._worker_running:
            return {"success": False, "message": "Worker not running"}

        self._stop_flag.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=10)

        self._worker_running = False
        self.logger.info("Worker thread stopped")
        return {"success": True, "message": "Worker stopped"}

    def get_worker_status(self) -> dict:
        """Get worker and queue status.

        Returns:
            Dictionary with: {running, processed, errors, last_error, queue_stats}
        """
        queue_stats = self.repo.get_stats()

        with self._stats_lock:
            return {
                "running": self._worker_running,
                "processed": self._worker_stats["processed"],
                "errors": self._worker_stats["errors"],
                "last_error": self._worker_stats["last_error"],
                "queue_stats": queue_stats,
            }

    def _worker_loop(self, access_token: str) -> None:
        """Background worker loop (runs in separate thread)."""
        self.logger.info("Worker loop started")

        while not self._stop_flag.is_set():
            deviation = self.repo.get_one_pending()

            if not deviation:
                # Queue empty, sleep and continue
                time.sleep(2)
                continue

            deviationid = deviation["deviationid"]

            try:
                # Attempt to fave
                response = requests.post(
                    self.FAVE_URL,
                    data={"deviationid": deviationid, "access_token": access_token},
                    timeout=30,
                )

                if response.status_code == 200:
                    # Success
                    self.repo.mark_faved(deviationid)
                    with self._stats_lock:
                        self._worker_stats["processed"] += 1
                    self.logger.info("Faved: %s", deviationid)

                    # Random delay to avoid rate limiting
                    time.sleep(random.uniform(2, 10))

                elif response.status_code == 429:
                    # Rate limited - check Retry-After header
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = int(retry_after)
                            delay = min(delay, 60)  # Cap at 60 seconds
                        except ValueError:
                            delay = 5
                    else:
                        delay = 5

                    self.repo.bump_attempt(deviationid, f"429 rate limited, retry after {delay}s")
                    self.logger.warning(
                        "Rate limited for %s, backing off for %s seconds", deviationid, delay
                    )
                    time.sleep(delay)

                else:
                    # Other error - mark failed
                    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                    self.repo.mark_failed(deviationid, error_msg)
                    with self._stats_lock:
                        self._worker_stats["errors"] += 1
                        self._worker_stats["last_error"] = error_msg
                    self.logger.error("Failed to fave %s: %s", deviationid, error_msg)
                    time.sleep(2)

            except requests.RequestException as e:
                # Network error - bump attempt and retry
                error_msg = f"Network error: {str(e)}"
                self.repo.bump_attempt(deviationid, error_msg)
                with self._stats_lock:
                    self._worker_stats["errors"] += 1
                    self._worker_stats["last_error"] = error_msg
                self.logger.error("Network error for %s: %s", deviationid, e)
                time.sleep(5)

            except Exception as e:
                # Unexpected error - mark failed and continue
                error_msg = f"Unexpected error: {str(e)}"
                self.repo.mark_failed(deviationid, error_msg)
                with self._stats_lock:
                    self._worker_stats["errors"] += 1
                    self._worker_stats["last_error"] = error_msg
                self.logger.exception("Unexpected error for %s", deviationid)
                time.sleep(2)

        self.logger.info("Worker loop stopped")
