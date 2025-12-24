"""Service for auto-faving deviations from feed."""

import random
import time
from logging import Logger
from typing import Optional

import requests

from ..storage.feed_deviation_repository import FeedDeviationRepository
from .api_pagination_helper import APIPaginationHelper
from .http_client import DeviantArtHttpClient
from .base_worker_service import BaseWorkerService


class MassFaveService(BaseWorkerService):
    """Coordinates feed collection and auto-faving workflow."""

    FEED_URL = "https://www.deviantart.com/api/v1/oauth2/browse/deviantsyouwatch"
    FAVE_URL = "https://www.deviantart.com/api/v1/oauth2/collections/fave"
    MAX_CONSECUTIVE_FAILURES = 5  # Stop worker after this many consecutive failures

    def __init__(
        self,
        feed_deviation_repo: FeedDeviationRepository,
        logger: Logger,
        token_repo=None,
        http_client: Optional[DeviantArtHttpClient] = None,
    ) -> None:
        super().__init__(logger, token_repo, http_client)

        self.repo = feed_deviation_repo

    def _get_error_code(self, error: requests.HTTPError) -> int | str | None:
        """Extract error_code from HTTP error payload if available."""
        response = getattr(error, "response", None)
        if response is None:
            return None

        try:
            payload = response.json()
        except Exception:  # noqa: BLE001
            return None

        if not isinstance(payload, dict):
            return None

        return payload.get("error_code")

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
        deviations_added = 0
        limit = 50  # Maximum allowed by API

        self.logger.info(
            "Starting feed collection: max_pages=%s, offset=%s, limit=%s",
            max_pages,
            offset,
            limit,
        )

        pagination = APIPaginationHelper(self.http_client, self.logger)

        def process_deviation(deviation: dict) -> bool | None:
            """Store deviation in queue, returning True when added."""
            deviationid = deviation.get("deviationid")
            if not deviationid:
                return None

            current_time = int(time.time())
            ts = deviation.get("published_time", current_time)
            if isinstance(ts, str):
                try:
                    ts = int(ts)
                except ValueError:
                    ts = current_time

            self.repo.add_deviation(str(deviationid), ts)
            return True

        def update_state(page_info: dict[str, object]) -> None:
            """Persist feed offset after each page."""
            next_offset = page_info.get("next_offset")
            if next_offset is not None:
                self.repo.set_state("feed_offset", str(page_info["offset"]))

        try:
            for _ in pagination.paginate(
                url=self.FEED_URL,
                access_token=access_token,
                limit=limit,
                max_pages=max_pages,
                additional_params={"mature_content": "true"},
                process_item=process_deviation,
                initial_offset=offset,
                page_callback=update_state,
            ):
                deviations_added += 1
        except requests.RequestException as e:
            self.logger.error("Feed fetch failed: %s", e)

        pages = pagination.pages_fetched
        final_offset = (
            pagination.last_offset if pagination.last_offset is not None else offset
        )

        self.logger.info(
            "Feed collection completed: pages=%s, deviations=%s, offset=%s",
            pages,
            deviations_added,
            final_offset,
        )

        return {
            "pages": pages,
            "deviations_added": deviations_added,
            "offset": final_offset,
        }

    # ========== Worker ==========

    def _validate_worker_start(self) -> dict[str, object]:
        """Validate conditions before starting worker.

        Returns:
            Dictionary with validation result:
            - If valid: {"valid": True}
            - If invalid: {"valid": False, "message": "error description"}
        """
        # MassFaveService doesn't require pre-validation
        # Worker will wait if queue is empty
        return {"valid": True}

    def get_worker_status(self) -> dict:
        """Get worker and queue status.

        Returns:
            Dictionary with: {running, processed, errors, last_error, queue_stats}
        """
        status = super().get_worker_status()
        status["queue_stats"] = self.repo.get_stats()
        return status

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
                    if self._interruptible_sleep(2):
                        # Stop flag was set during wait
                        self.logger.info("Worker stop requested during idle wait")
                        break
                    continue

                deviationid = deviation["deviationid"]

                try:
                    # Attempt to fave (automatic token refresh via BaseWorkerService)
                    response = self.execute_with_token_refresh(
                        self.http_client.post,
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
                    if self._interruptible_sleep(delay):
                        # Stop flag was set during wait
                        self.logger.info("Worker stop requested during delay")
                        break

                except requests.HTTPError as e:
                    error_msg = self._format_http_error(e)

                    if self._is_critical_error(e):
                        self.logger.critical(
                            "CRITICAL ERROR DETECTED: %s - Stopping worker immediately to prevent escalating sanctions from DeviantArt",
                            error_msg,
                        )
                        self.repo.mark_failed(deviationid, error_msg)
                        with self._stats_lock:
                            self._worker_stats["errors"] += 1
                            self._worker_stats["last_error"] = error_msg
                            self._worker_stats["consecutive_failures"] += 1
                        break

                    response = getattr(e, "response", None)
                    status_code = getattr(response, "status_code", None)

                    # Non-retryable request errors: delete from queue to avoid
                    # poisoning the worker with permanent failures.
                    if (
                        response is not None
                        and isinstance(status_code, int)
                        and 400 <= status_code < 500
                        and status_code != 429
                    ):
                        error_code = self._get_error_code(e)

                        # Special case: DA rate limit for faving returns HTTP 400
                        # invalid_request with error_code=4. This is retryable, but
                        # we must stop the worker to avoid hammering the API.
                        if status_code == 400 and error_code in (4, "4"):
                            self.repo.bump_attempt(deviationid, error_msg)
                            with self._stats_lock:
                                self._worker_stats["errors"] += 1
                                self._worker_stats["last_error"] = error_msg
                                self._worker_stats["consecutive_failures"] = 0

                            self.logger.warning(
                                "Rate limit detected, leaving deviation pending and stopping worker: %s (%s)",
                                deviationid,
                                error_msg,
                            )
                            break

                        self.repo.delete_deviation(deviationid)
                        with self._stats_lock:
                            self._worker_stats["errors"] += 1
                            self._worker_stats["last_error"] = error_msg
                            self._worker_stats["consecutive_failures"] = 0

                        self.logger.warning(
                            "Skipping and deleting deviation %s: %s",
                            deviationid,
                            error_msg,
                        )
                        continue

                    raise

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
