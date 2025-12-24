"""Service for posting comments under deviations."""

from __future__ import annotations

import random
from logging import Logger
from typing import Optional

import requests

from ..domain.models import DeviationCommentLogStatus, DeviationCommentMessage
from ..storage.deviation_comment_log_repository import (
    DeviationCommentLogRepository,
)
from ..storage.deviation_comment_message_repository import (
    DeviationCommentMessageRepository,
)
from ..storage.deviation_comment_queue_repository import (
    DeviationCommentQueueRepository,
)
from .http_client import DeviantArtHttpClient
from .message_randomizer import randomize_template
from .base_worker_service import BaseWorkerService


class CommentPosterService(BaseWorkerService):
    """Post comments for deviations from the queue."""

    COMMENT_URL = (
        "https://www.deviantart.com/api/v1/oauth2/comments/post/deviation/"
        "{deviationid}"
    )
    FAVE_URL = "https://www.deviantart.com/api/v1/oauth2/collections/fave"
    DEVIATION_URL = "https://www.deviantart.com/api/v1/oauth2/deviation/{deviationid}"
    MAX_CONSECUTIVE_FAILURES = 5
    MAX_ATTEMPTS = 3

    def __init__(
        self,
        message_repo: DeviationCommentMessageRepository,
        queue_repo: DeviationCommentQueueRepository,
        log_repo: DeviationCommentLogRepository,
        logger: Logger,
        token_repo=None,
        http_client: Optional[DeviantArtHttpClient] = None,
    ) -> None:
        # Call BaseWorkerService.__init__, which calls BaseService.__init__
        # This initializes logger, http_client, and config property
        super().__init__(logger, token_repo, http_client)

        self.message_repo = message_repo
        self.queue_repo = queue_repo
        self.log_repo = log_repo

    def _validate_worker_start(self) -> dict[str, object]:
        """Validate conditions before starting worker.

        Returns:
            Dictionary with validation result:
            - If valid: {"valid": True}
            - If invalid: {"valid": False, "message": "error description"}
        """
        queue_stats = self.queue_repo.get_stats()
        if queue_stats.get("pending", 0) == 0:
            return {"valid": False, "message": "Queue is empty. Collect first."}

        # Note: template_id validation moved to start_worker override
        # since it's a parameter-specific check
        active_messages = self.message_repo.get_active_messages()
        if not active_messages:
            return {"valid": False, "message": "No active templates found."}

        return {"valid": True}

    def start_worker(
        self, access_token: str, template_id: int | None = None
    ) -> dict[str, object]:
        """Start background worker thread with optional template selection.

        Args:
            access_token: OAuth access token for posting comments.
            template_id: Optional template ID to force selection.

        Returns:
            Status dictionary: {success, message}.
        """
        # Additional validation for template_id parameter
        if template_id is not None:
            template = self.message_repo.get_message_by_id(template_id)
            if template is None:
                return {"success": False, "message": "Template not found"}
            if not template.is_active:
                return {"success": False, "message": "Template is not active"}

        # Call base class start_worker
        return super().start_worker(access_token, template_id)

    def get_worker_status(self) -> dict[str, object]:
        """Get worker and queue status.

        Extends base worker status with queue-specific statistics.

        Returns:
            Dictionary with worker status including queue_stats
        """
        # Get base worker status from BaseWorkerService
        status = super().get_worker_status()

        # Add queue-specific statistics
        queue_stats = self.queue_repo.get_stats()
        status["queue_stats"] = queue_stats

        return status

    def _select_template(self, template_id: int | None):
        """Select a template by ID or choose a random active one."""
        if template_id is not None:
            template = self.message_repo.get_message_by_id(template_id)
            if template and template.is_active:
                return template
            return None

        active_messages = self.message_repo.get_active_messages()
        if not active_messages:
            return None

        return random.choice(active_messages)

    def _render_comment(self, body: str) -> str:
        """Render template body with randomized synonyms."""
        return randomize_template(body)

    def _check_deviation_exists(
        self, access_token: str, deviationid: str
    ) -> bool:
        """
        Check if deviation exists on DeviantArt before commenting.

        Args:
            access_token: OAuth access token
            deviationid: Deviation ID to check

        Returns:
            True if deviation exists (HTTP 200), False if deleted (HTTP 500/404)
        """
        try:
            url = self.DEVIATION_URL.format(deviationid=deviationid)
            self.execute_with_token_refresh(
                self.http_client.get,
                url,
                params={"access_token": access_token},
                timeout=30
            )
            self.logger.debug(
                "Deviation %s exists and is accessible", deviationid
            )
            return True
        except requests.HTTPError as e:
            response = getattr(e, "response", None)
            status_code = getattr(response, "status_code", None)
            if status_code in (404, 500):
                self.logger.debug(
                    "Deviation %s appears to be deleted (HTTP %s)",
                    deviationid,
                    status_code,
                )
                return False
            # Other HTTP errors - treat as temporary, allow retry
            self.logger.warning(
                "Deviation check failed with HTTP %s for %s, treating as accessible",
                status_code,
                deviationid,
            )
            return True
        except Exception as e:  # noqa: BLE001
            # Network errors, timeouts - treat as temporary, allow retry
            self.logger.warning(
                "Deviation check failed for %s: %s, treating as accessible",
                deviationid,
                str(e),
            )
            return True

    def _post_comment(
        self,
        access_token: str,
        deviationid: str,
        body: str,
        commentid: str | None = None,
    ):
        """Post comment to DeviantArt."""
        data = {"body": body, "access_token": access_token}
        if commentid:
            data["commentid"] = commentid

        url = self.COMMENT_URL.format(deviationid=deviationid)
        return self.execute_with_token_refresh(
            self.http_client.post,
            url,
            data=data,
            timeout=30
        )

    def _fave_deviation(
        self,
        access_token: str,
        deviationid: str,
    ) -> bool:
        """
        Fave deviation on DeviantArt.

        Args:
            access_token: OAuth access token
            deviationid: Deviation ID to fave

        Returns:
            True if faved successfully, False otherwise
        """
        try:
            self.execute_with_token_refresh(
                self.http_client.post,
                self.FAVE_URL,
                data={"deviationid": deviationid, "access_token": access_token},
                timeout=30,
            )
            self.logger.info("Auto-faved deviation: %s", deviationid)
            return True
        except Exception as e:
            # Ошибки фаворинга не должны ломать комментирование
            self.logger.warning(
                "Failed to auto-fave deviation %s: %s",
                deviationid,
                str(e),
            )
            return False

    def _handle_success(
        self,
        queue_item: dict[str, object],
        template: DeviationCommentMessage,
        comment_text: str,
        commentid: str | None,
        access_token: str,
    ) -> None:
        """Handle success by updating queue and logs."""
        deviationid = str(queue_item.get("deviationid"))
        message_id = template.message_id
        if message_id is None:
            self.logger.error("Template missing message_id, cannot log success")
            return

        self.log_repo.add_log(
            message_id=message_id,
            deviationid=deviationid,
            deviation_url=queue_item.get("deviation_url"),
            author_username=queue_item.get("author_username"),
            commentid=commentid,
            comment_text=comment_text,
            status=DeviationCommentLogStatus.SENT,
        )
        self.queue_repo.mark_commented(deviationid)

        with self._stats_lock:
            self._worker_stats["processed"] += 1
            self._worker_stats["consecutive_failures"] = 0

        # Auto-fave deviation after successful comment
        self._fave_deviation(access_token, deviationid)

    def _is_non_retryable_http_error(self, error: requests.HTTPError) -> bool:
        """Return True for HTTP 4xx errors (excluding 429)."""
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int) and 400 <= status_code < 500:
            return status_code != 429
        return False

    def _is_deleted_deviation_error(self, error: requests.HTTPError) -> bool:
        """
        Check if HTTP error indicates that deviation was deleted on DeviantArt.
        
        HTTP 404 and 500 errors typically mean the deviation no longer exists.
        
        Returns:
            True if deviation was likely deleted.
        """
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
        return status_code in (404, 500)

    def _handle_deleted_deviation(
        self,
        queue_item: dict[str, object],
        template_id: int,
        comment_text: str,
        error_msg: str,
    ) -> None:
        """
        Handle case when deviation was deleted on DeviantArt.
        
        Removes item from queue and logs with DELETED status.
        """
        deviationid = str(queue_item.get("deviationid"))
        
        # Remove from queue (deviation no longer exists)
        self.queue_repo.remove_by_ids([deviationid])
        self.logger.info(
            "Deviation %s removed from queue (deleted on DeviantArt)",
            deviationid,
        )
        
        # Log as DELETED
        self.log_repo.add_log(
            message_id=template_id,
            deviationid=deviationid,
            deviation_url=queue_item.get("deviation_url"),
            author_username=queue_item.get("author_username"),
            comment_text=comment_text,
            status=DeviationCommentLogStatus.DELETED,
            error_message=error_msg,
        )
        
        with self._stats_lock:
            self._worker_stats["errors"] += 1
            self._worker_stats["consecutive_failures"] += 1
            self._worker_stats["last_error"] = error_msg

    def _handle_failure(
        self,
        queue_item: dict[str, object],
        template_id: int,
        comment_text: str,
        error_msg: str,
        *,
        non_retryable: bool,
    ) -> None:
        """Handle failure by updating queue and logs."""
        deviationid = str(queue_item.get("deviationid"))
        attempts = int(queue_item.get("attempts") or 0)
        next_attempt = attempts + 1

        if non_retryable or next_attempt >= self.MAX_ATTEMPTS:
            self.queue_repo.mark_failed(deviationid, error_msg)
        else:
            self.queue_repo.bump_attempt(deviationid, error_msg)

        self.log_repo.add_log(
            message_id=template_id,
            deviationid=deviationid,
            deviation_url=queue_item.get("deviation_url"),
            author_username=queue_item.get("author_username"),
            commentid=None,
            comment_text=comment_text,
            status=DeviationCommentLogStatus.FAILED,
            error_message=error_msg,
        )

        with self._stats_lock:
            self._worker_stats["errors"] += 1
            self._worker_stats["consecutive_failures"] += 1
            self._worker_stats["last_error"] = error_msg

    def _worker_loop(self, access_token: str, template_id: int | None) -> None:
        """Background worker loop."""
        self.logger.info("Comment worker loop started")
        try:
            while not self._stop_flag.is_set():
                queue_item = self.queue_repo.get_one_pending()
                if not queue_item:
                    delay = self.http_client.get_recommended_delay()
                    if self._interruptible_sleep(delay):
                        break
                    continue

                deviationid = str(queue_item.get("deviationid"))
                template = self._select_template(template_id)
                if not template:
                    self.logger.error("No active templates available, stopping worker")
                    break

                message_id = template.message_id
                if message_id is None:
                    self.logger.error("Template missing message_id, stopping worker")
                    break

                comment_text = self._render_comment(template.body)

                # Check if deviation exists before waiting for broadcast delay
                if not self._check_deviation_exists(access_token, deviationid):
                    # Deviation is deleted (404/500), skip without waiting
                    error_msg = f"Deviation check failed: appears to be deleted (HTTP 404/500)"
                    self.logger.info(
                        "Skipping deleted deviation %s without broadcast delay",
                        deviationid,
                    )
                    self._handle_deleted_deviation(
                        queue_item,
                        message_id,
                        comment_text,
                        error_msg,
                    )
                    # Continue to next item immediately (no delay needed for deleted deviations)
                    continue

                broadcast_delay = self._get_broadcast_delay()
                author_username = queue_item.get("author_username", "unknown")
                self.logger.info(
                    "Waiting %d seconds before commenting on deviation by %s",
                    broadcast_delay,
                    author_username,
                )
                if self._interruptible_sleep(broadcast_delay):
                    break

                try:
                    response = self._post_comment(
                        access_token=access_token,
                        deviationid=deviationid,
                        body=comment_text,
                    )

                    commentid = None
                    try:
                        response_data = response.json()
                    except ValueError:
                        response_data = None

                    if isinstance(response_data, dict):
                        commentid = response_data.get("commentid")

                    self._handle_success(
                        queue_item,
                        template,
                        comment_text,
                        commentid,
                        access_token,
                    )

                    delay = self.http_client.get_recommended_delay()
                    if self._interruptible_sleep(delay):
                        break
                    continue

                except requests.HTTPError as e:
                    error_msg = self._format_http_error(e)
                    
                    # Check if deviation was deleted (HTTP 500)
                    if self._is_deleted_deviation_error(e):
                        self.logger.warning(
                            "Deviation %s appears to be deleted on DeviantArt (HTTP 500): %s",
                            deviationid,
                            error_msg,
                        )
                        self._handle_deleted_deviation(
                            queue_item,
                            message_id,
                            comment_text,
                            error_msg,
                        )
                        # Continue to next item (no retry needed)
                        delay = self.http_client.get_recommended_delay()
                        if self._interruptible_sleep(delay):
                            break
                        continue
                    
                    # Check for critical errors that require immediate worker stop
                    if self._is_critical_error(e):
                        self.logger.critical(
                            "CRITICAL ERROR DETECTED: %s - Stopping worker immediately to prevent escalating sanctions from DeviantArt",
                            error_msg,
                        )
                        non_retryable = True
                        self._handle_failure(
                            queue_item,
                            message_id,
                            comment_text,
                            error_msg,
                            non_retryable=non_retryable,
                        )
                        break
                    
                    non_retryable = self._is_non_retryable_http_error(e)
                    self._handle_failure(
                        queue_item,
                        message_id,
                        comment_text,
                        error_msg,
                        non_retryable=non_retryable,
                    )

                except requests.RequestException as e:
                    error_msg = f"Request failed after retries: {str(e)}"
                    self._handle_failure(
                        queue_item,
                        message_id,
                        comment_text,
                        error_msg,
                        non_retryable=False,
                    )

                except Exception as e:  # noqa: BLE001
                    error_msg = f"Unexpected error: {str(e)}"
                    self._handle_failure(
                        queue_item,
                        message_id,
                        comment_text,
                        error_msg,
                        non_retryable=False,
                    )

                with self._stats_lock:
                    consecutive_failures = self._worker_stats["consecutive_failures"]

                if consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                    self.logger.critical(
                        "Worker stopped: %d consecutive failures reached (limit: %d)",
                        consecutive_failures,
                        self.MAX_CONSECUTIVE_FAILURES,
                    )
                    break

                delay = self.http_client.get_recommended_delay()
                if self._interruptible_sleep(delay):
                    break
        finally:
            self._worker_running = False
            self.logger.info("Comment worker loop stopped")
