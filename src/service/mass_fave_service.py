"""Service for auto-faving deviations from feed."""

import time
import random
import threading
from logging import Logger
from typing import Optional

import requests

from ..storage.feed_deviation_repository import FeedDeviationRepository
from .http_client import DeviantArtHttpClient


class MassFaveService:
    """Coordinates feed collection and auto-faving workflow."""

    FEED_URL = "https://www.deviantart.com/api/v1/oauth2/browse/deviantsyouwatch"
    FAVE_URL = "https://www.deviantart.com/api/v1/oauth2/collections/fave"
    MAX_CONSECUTIVE_FAILURES = 5  # Stop worker after this many consecutive failures

    def __init__(
        self,
        feed_deviation_repo: FeedDeviationRepository,
        logger: Logger,
        http_client: Optional[DeviantArtHttpClient] = None,
    ) -> None:
        self.repo = feed_deviation_repo
        self.logger = logger
        self.http_client = http_client or DeviantArtHttpClient(logger=logger)

        # Worker state
        self._worker_thread: Optional[threading.Thread] = None
        self._worker_running = False
        self._stop_flag = threading.Event()
        self._worker_stats = {
            "processed": 0,
            "errors": 0,
            "last_error": None,
            "consecutive_failures": 0,
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
                response = self.http_client.get(self.FEED_URL, params=params, timeout=30)
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
                delay = self.http_client.get_recommended_delay()
                self.logger.debug(
                    "Waiting %s seconds before next feed page request",
                    delay,
                )
                time.sleep(delay)

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
            self._worker_stats = {
                "processed": 0,
                "errors": 0,
                "last_error": None,
                "consecutive_failures": 0,
            }

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
                "consecutive_failures": self._worker_stats["consecutive_failures"],
                "queue_stats": queue_stats,
            }

    def reset_failed_deviations(self) -> dict:
        """Reset all failed deviations back to pending status.

        Returns:
            Dictionary with reset count: {success, reset_count}
        """
        try:
            reset_count = self.repo.reset_failed_to_pending()
            self.logger.info("Reset %d failed deviations to pending", reset_count)
            return {"success": True, "reset_count": reset_count}
        except Exception as e:
            self.logger.error("Failed to reset deviations: %s", e)
            return {"success": False, "error": str(e)}

    def _worker_loop(self, access_token: str) -> None:
        """Background worker loop (runs in separate thread)."""
        self.logger.info("Worker loop started")
        try:
            while not self._stop_flag.is_set():
                deviation = self.repo.get_one_pending()

                if not deviation:
                    # Queue empty, wait with stop_flag check (interruptible sleep)
                    if self._stop_flag.wait(timeout=2):
                        # Stop flag was set during wait
                        self.logger.info("Worker stop requested during idle wait")
                        break
                    continue

                deviationid = deviation["deviationid"]

                try:
                    # Attempt to fave (HTTP client handles retry automatically)
                    response = self.http_client.post(
                        self.FAVE_URL,
                        data={"deviationid": deviationid, "access_token": access_token},
                        timeout=30,
                    )

                    # Success - HTTP client only returns response if successful
                    self.repo.mark_faved(deviationid)
                    with self._stats_lock:
                        self._worker_stats["processed"] += 1
                        self._worker_stats["consecutive_failures"] = 0  # Reset on success
                    self.logger.info("Faved: %s", deviationid)

                    # Random delay with stop_flag check (interruptible sleep)
                    delay = random.uniform(2, 10)
                    if self._stop_flag.wait(timeout=delay):
                        # Stop flag was set during wait
                        self.logger.info("Worker stop requested during delay")
                        break

                except requests.RequestException as e:
                    # HTTP client already retried - this is final failure
                    error_msg = f"Request failed after retries: {str(e)}"
                    self.repo.mark_failed(deviationid, error_msg)
                    with self._stats_lock:
                        self._worker_stats["errors"] += 1
                        self._worker_stats["consecutive_failures"] += 1
                        self._worker_stats["last_error"] = error_msg
                        consecutive_failures = self._worker_stats["consecutive_failures"]

                    self.logger.error(
                        "Failed to fave %s: %s (consecutive failures: %d/%d)",
                        deviationid,
                        str(e),
                        consecutive_failures,
                        self.MAX_CONSECUTIVE_FAILURES,
                    )

                    # Stop worker if too many consecutive failures
                    if consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                        self.logger.critical(
                            "Worker stopped: %d consecutive failures reached (limit: %d)",
                            consecutive_failures,
                            self.MAX_CONSECUTIVE_FAILURES,
                        )
                        break

                    # Wait with stop_flag check (interruptible sleep)
                    if self._stop_flag.wait(timeout=2):
                        self.logger.info("Worker stop requested during error delay")
                        break

                except Exception as e:
                    # Unexpected error - mark failed and continue
                    error_msg = f"Unexpected error: {str(e)}"
                    self.repo.mark_failed(deviationid, error_msg)
                    with self._stats_lock:
                        self._worker_stats["errors"] += 1
                        self._worker_stats["last_error"] = error_msg
                    self.logger.exception("Unexpected error for %s", deviationid)
                    # Wait with stop_flag check (interruptible sleep)
                    if self._stop_flag.wait(timeout=2):
                        self.logger.info("Worker stop requested after unexpected error")
                        break
        finally:
            self._worker_running = False
            self.logger.info("Worker loop stopped")
