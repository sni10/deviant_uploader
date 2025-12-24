"""Service for posting comments under deviations."""

from __future__ import annotations

import random
import threading
import time
from logging import Logger
from typing import Optional

import requests

from ..config.settings import get_config
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


class CommentPosterService:
    """Post comments for deviations from the queue."""

    COMMENT_URL = (
        "https://www.deviantart.com/api/v1/oauth2/comments/post/deviation/"
        "{deviationid}"
    )
    FAVE_URL = "https://www.deviantart.com/api/v1/oauth2/collections/fave"
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
        config: Optional[object] = None,
    ) -> None:
        self.message_repo = message_repo
        self.queue_repo = queue_repo
        self.log_repo = log_repo
        self.logger = logger
        self.http_client = http_client or DeviantArtHttpClient(
            logger=logger, token_repo=token_repo
        )
        self._config = config

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

    @property
    def config(self):
        """Lazy-load config if not provided during initialization."""
        if self._config is None:
            self._config = get_config()
        return self._config

    def _is_worker_alive(self) -> bool:
        """Return True if the background worker thread is alive."""
        return bool(self._worker_thread and self._worker_thread.is_alive())

    def start_worker(
        self, access_token: str, template_id: int | None = None
    ) -> dict[str, object]:
        """Start background worker thread.

        Args:
            access_token: OAuth access token for posting comments.
            template_id: Optional template ID to force selection.

        Returns:
            Status dictionary: {success, message}.
        """
        if self._is_worker_alive():
            return {"success": False, "message": "Worker already running"}

        queue_stats = self.queue_repo.get_stats()
        if queue_stats.get("pending", 0) == 0:
            return {"success": False, "message": "Queue is empty. Collect first."}

        if template_id is not None:
            template = self.message_repo.get_message_by_id(template_id)
            if template is None:
                return {"success": False, "message": "Template not found"}
            if not template.is_active:
                return {"success": False, "message": "Template is not active"}
        else:
            active_messages = self.message_repo.get_active_messages()
            if not active_messages:
                return {
                    "success": False,
                    "message": "No active templates found.",
                }

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
            args=(access_token, template_id),
            daemon=True,
        )
        self._worker_running = True
        self._worker_thread.start()

        self.logger.info("Comment worker started")
        return {"success": True, "message": "Worker started"}

    def stop_worker(self) -> dict[str, object]:
        """Stop background worker thread.

        Returns:
            Status dictionary: {success, message}.
        """
        if not self._is_worker_alive():
            self._worker_running = False
            return {"success": False, "message": "Worker not running"}

        self._stop_flag.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=10)

        self._worker_running = self._is_worker_alive()

        if self._worker_running:
            self.logger.warning("Worker stop requested but still running")
            return {"success": True, "message": "Stop requested"}

        self.logger.info("Comment worker stopped")
        return {"success": True, "message": "Worker stopped"}

    def get_worker_status(self) -> dict[str, object]:
        """Get worker and queue status."""
        running = self._is_worker_alive()
        if not running:
            self._worker_running = False

        queue_stats = self.queue_repo.get_stats()

        with self._stats_lock:
            return {
                "running": running,
                "processed": self._worker_stats["processed"],
                "errors": self._worker_stats["errors"],
                "last_error": self._worker_stats["last_error"],
                "consecutive_failures": self._worker_stats["consecutive_failures"],
                "queue_stats": queue_stats,
            }

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

    def _get_broadcast_delay(self) -> int:
        """Generate random delay for broadcasting (in seconds).

        Returns:
            Random delay in seconds between min and max configured values
        """
        min_delay = self.config.broadcast_min_delay_seconds
        max_delay = self.config.broadcast_max_delay_seconds
        delay = random.randint(min_delay, max_delay)
        self.logger.debug(
            "Generated broadcast delay: %d seconds (range: %d-%d)",
            delay,
            min_delay,
            max_delay,
        )
        return delay

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
        return self.http_client.post(url, data=data, timeout=30)

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
            self.http_client.post(
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

    def _format_http_error(self, error: requests.HTTPError) -> str:
        """Format HTTP error with response details when available."""
        response = getattr(error, "response", None)
        if response is None:
            return str(error)

        status_code = getattr(response, "status_code", None)
        error_payload: object | None
        try:
            error_payload = response.json()
        except Exception:  # noqa: BLE001
            error_payload = None

        error_desc = None
        error_code = None
        error_name = None
        if isinstance(error_payload, dict):
            error_desc = error_payload.get("error_description")
            error_code = error_payload.get("error_code")
            error_name = error_payload.get("error")

        parts = [f"HTTP {status_code}"]
        if error_name:
            parts.append(str(error_name))
        if error_code is not None:
            parts.append(f"code={error_code}")
        if error_desc:
            parts.append(str(error_desc))

        return ": ".join([parts[0], " ".join(parts[1:])]) if len(parts) > 1 else parts[0]

    def _is_non_retryable_http_error(self, error: requests.HTTPError) -> bool:
        """Return True for HTTP 4xx errors (excluding 429)."""
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int) and 400 <= status_code < 500:
            return status_code != 429
        return False

    def _is_critical_error(self, error: requests.HTTPError) -> bool:
        """
        Check if HTTP error is critical and requires immediate worker stop.
        
        Critical errors include:
        - Spam detection by DeviantArt
        - Account restrictions or bans
        - Other policy violations
        
        Returns:
            True if worker should stop immediately to prevent escalating sanctions.
        """
        response = getattr(error, "response", None)
        if response is None:
            return False

        try:
            error_payload = response.json()
        except Exception:  # noqa: BLE001
            return False

        if not isinstance(error_payload, dict):
            return False

        # Check error_description for spam-related keywords
        error_desc = error_payload.get("error_description", "")
        if isinstance(error_desc, str):
            error_desc_lower = error_desc.lower()
            # Spam detection
            if "spam" in error_desc_lower:
                return True
            # Account restrictions
            if "banned" in error_desc_lower or "suspended" in error_desc_lower:
                return True
            # Rate limit abuse (different from normal 429)
            if "abuse" in error_desc_lower or "violation" in error_desc_lower:
                return True

        return False

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
                    if self._stop_flag.wait(timeout=delay):
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

                broadcast_delay = self._get_broadcast_delay()
                author_username = queue_item.get("author_username", "unknown")
                self.logger.info(
                    "Waiting %d seconds before commenting on deviation by %s",
                    broadcast_delay,
                    author_username,
                )
                if self._stop_flag.wait(timeout=broadcast_delay):
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
                    if self._stop_flag.wait(timeout=delay):
                        break
                    continue

                except requests.HTTPError as e:
                    error_msg = self._format_http_error(e)
                    
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
                if self._stop_flag.wait(timeout=delay):
                    break
        finally:
            self._worker_running = False
            self.logger.info("Comment worker loop stopped")
