"""Base worker service with common threading and error handling logic.

This module provides a base class for all worker services that run background
threads for processing queues (comments, profile messages, mass faving, etc.).
"""
from __future__ import annotations

import threading
from abc import abstractmethod
from logging import Logger
from typing import Any, Optional

import requests

from src.service.base_service import BaseService
from src.service.http_client import DeviantArtHttpClient


class BaseWorkerService(BaseService):
    """Base class for worker services with common threading logic.

    Inherits from BaseService to provide common initialization (logger,
    http_client, config) plus worker-specific functionality.

    Provides:
    - Thread management (_worker_thread, _stop_flag)
    - Worker statistics tracking
    - Interruptible sleep for graceful shutdown
    - Common error handling methods
    - Template methods for start/stop worker

    Subclasses must implement:
    - _worker_loop(): Main worker loop logic
    - _validate_worker_start(): Pre-start validation checks
    """

    def __init__(
        self,
        logger: Logger,
        token_repo=None,
        http_client: Optional[DeviantArtHttpClient] = None,
    ):
        """Initialize base worker service.

        Args:
            logger: Logger instance for this service
            token_repo: Optional OAuth token repository for HTTP client
            http_client: Optional HTTP client (auto-created if token_repo
                provided and http_client is None)
        """
        # Call BaseService constructor for common initialization
        super().__init__(logger, token_repo, http_client)

        # Thread management
        self._worker_thread: threading.Thread | None = None
        self._stop_flag = threading.Event()
        self._worker_running = False

        # Statistics tracking
        self._stats_lock = threading.Lock()
        self._worker_stats: dict[str, Any] = {
            "processed": 0,
            "errors": 0,
            "last_error": None,
            "consecutive_failures": 0,
        }

        # Auth service for automatic token refresh (set by start_worker)
        self._auth_service = None

    def _is_worker_alive(self) -> bool:
        """Return True if the background worker thread is alive."""
        return bool(self._worker_thread and self._worker_thread.is_alive())

    def _interruptible_sleep(self, delay: float) -> bool:
        """Sleep with ability to be interrupted by stop flag.
        
        This method should be used instead of time.sleep() to allow
        graceful worker shutdown without waiting for full delay.
        
        Args:
            delay: Sleep duration in seconds
            
        Returns:
            True if stop was requested during sleep, False otherwise
        """
        return self._stop_flag.wait(timeout=delay)

    def _format_http_error(self, error: requests.HTTPError) -> str:
        """Format HTTP error with response details when available.
        
        Args:
            error: HTTP error from requests library
            
        Returns:
            Formatted error string with status code and error details
        """
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

    def _is_critical_error(self, error: requests.HTTPError) -> bool:
        """Check if HTTP error is critical and requires immediate worker stop.

        Critical errors include:
        - Spam detection by DeviantArt
        - Account restrictions or bans
        - Other policy violations

        Args:
            error: HTTP error from requests library

        Returns:
            True if worker should stop immediately to prevent escalating sanctions
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

    def _is_expired_token_error(self, error: requests.HTTPError) -> bool:
        """Check if HTTP error indicates expired OAuth token.

        Args:
            error: HTTPError exception

        Returns:
            True if error is HTTP 401 with invalid_token/expired token
        """
        response = getattr(error, "response", None)
        if response is None:
            return False

        if response.status_code != 401:
            return False

        try:
            error_data = response.json()
            error_type = error_data.get("error", "")
            error_desc = error_data.get("error_description", "").lower()

            # Check for expired token indicators
            if error_type == "invalid_token":
                return True
            if "expired" in error_desc:
                return True
        except (ValueError, AttributeError):
            pass

        return False

    def _refresh_access_token(self) -> str | None:
        """Attempt to refresh access token using auth service.

        This method is called automatically when HTTP 401 invalid_token error
        is detected during worker execution. It uses the auth_service passed
        to start_worker() to re-authenticate and obtain a new valid token.

        Returns:
            New access token if successful, None otherwise
        """
        if self._auth_service is None:
            self.logger.error(
                "Cannot refresh token: auth_service not provided to start_worker()"
            )
            return None

        self.logger.info("Attempting to refresh expired OAuth token...")

        try:
            # Re-authenticate to get new token
            if not self._auth_service.ensure_authenticated():
                self.logger.error("Token refresh failed: authentication failed")
                return None

            # Get new valid token
            new_token = self._auth_service.get_valid_token()
            if not new_token:
                self.logger.error("Token refresh failed: could not get valid token")
                return None

            self.logger.info("Successfully refreshed OAuth token")
            return new_token

        except Exception as e:
            self.logger.error(
                "Token refresh failed with exception: %s", e, exc_info=True
            )
            return None

    def execute_with_token_refresh(self, http_call, *args, **kwargs):
        """Execute HTTP call with automatic token refresh on expiration.

        CENTRALIZED method that wraps any HTTP call and automatically handles
        token expiration by refreshing and retrying the request.

        Args:
            http_call: Callable that performs HTTP request
            *args: Positional arguments to pass to http_call
            **kwargs: Keyword arguments to pass to http_call.
                     Must include 'access_token' or 'token' parameter.

        Returns:
            Result from http_call

        Raises:
            requests.HTTPError: If error is not expired token or refresh fails
            Exception: Any other exception from http_call

        Example:
            response = self.execute_with_token_refresh(
                self.http_client.post,
                url,
                data={"body": text, "access_token": token}
            )
        """
        max_retries = 1  # Only retry once after token refresh

        for attempt in range(max_retries + 1):
            try:
                return http_call(*args, **kwargs)

            except requests.HTTPError as e:
                # Check if this is expired token error
                if not self._is_expired_token_error(e):
                    # Not expired token, propagate error
                    raise

                # Expired token detected
                if attempt >= max_retries:
                    # Already retried, can't retry again
                    self.logger.error(
                        "Token refresh retry exhausted, propagating error"
                    )
                    raise

                # Try to refresh token
                self.logger.warning(
                    "Expired token detected in HTTP call, attempting refresh..."
                )
                new_token = self._refresh_access_token()

                if not new_token:
                    # Token refresh failed, propagate error
                    self.logger.error(
                        "Token refresh failed, cannot retry HTTP call"
                    )
                    raise

                # Token refreshed successfully - update token in kwargs/args
                self.logger.info(
                    "Token refreshed successfully, retrying HTTP call..."
                )

                # Update access_token in kwargs if present
                if "data" in kwargs and isinstance(kwargs["data"], dict):
                    if "access_token" in kwargs["data"]:
                        kwargs["data"]["access_token"] = new_token

                # Update access_token in params if present
                if "params" in kwargs and isinstance(kwargs["params"], dict):
                    if "access_token" in kwargs["params"]:
                        kwargs["params"]["access_token"] = new_token

                # Retry the call with updated token
                continue

    @abstractmethod
    def _validate_worker_start(self) -> dict[str, object]:
        """Validate conditions before starting worker.
        
        Subclasses should check:
        - Queue has pending items
        - Required templates/configuration exists
        - Any other service-specific requirements
        
        Returns:
            Dictionary with validation result:
            - If valid: {"valid": True}
            - If invalid: {"valid": False, "message": "error description"}
        """
        pass

    @abstractmethod
    def _worker_loop(self, *args, **kwargs) -> None:
        """Main worker loop that processes queue items.

        This method runs in a separate thread and should:
        - Check self._stop_flag.is_set() regularly
        - Use self._interruptible_sleep() instead of time.sleep()
        - Update self._worker_stats with progress
        - Handle errors appropriately

        Args:
            *args: Service-specific arguments (e.g., access_token)
            **kwargs: Service-specific keyword arguments
        """
        pass

    def _get_broadcast_delay(
        self, min_delay: int | None = None, max_delay: int | None = None
    ) -> int:
        """Generate random delay for broadcasting (in seconds).

        Args:
            min_delay: Minimum delay in seconds (uses config if None)
            max_delay: Maximum delay in seconds (uses config if None)

        Returns:
            Random delay in seconds between min and max configured values
        """
        import random

        min_val = (
            min_delay
            if min_delay is not None
            else self.config.broadcast_min_delay_seconds
        )
        max_val = (
            max_delay
            if max_delay is not None
            else self.config.broadcast_max_delay_seconds
        )
        delay = random.randint(min_val, max_val)
        self.logger.debug(
            "Generated broadcast delay: %d seconds (range: %d-%d)",
            delay,
            min_val,
            max_val,
        )
        return delay

    def get_worker_status(self) -> dict:
        """Get standardized worker and queue status.

        Subclasses can override to add service-specific statistics
        (e.g., queue_size, pending_items).

        Returns:
            Dictionary with worker status:
            - running: bool - worker thread status
            - processed: int - total items processed
            - errors: int - total errors encountered
            - last_error: str | None - last error message
            - consecutive_failures: int - consecutive failures counter
        """
        # Sync running flag with actual thread state
        running = self._is_worker_alive()
        if not running:
            self._worker_running = False

        with self._stats_lock:
            return {
                "running": running,
                "processed": self._worker_stats["processed"],
                "errors": self._worker_stats["errors"],
                "last_error": self._worker_stats["last_error"],
                "consecutive_failures": self._worker_stats[
                    "consecutive_failures"
                ],
            }

    def start_worker(self, *args, auth_service=None, **kwargs) -> dict[str, object]:
        """Start background worker thread with optional automatic token refresh.

        Template method that:
        1. Checks if worker is already running
        2. Stores auth_service for automatic token refresh
        3. Validates pre-conditions via _validate_worker_start()
        4. Initializes worker state
        5. Starts worker thread with _worker_loop()

        Args:
            *args: Service-specific arguments passed to _worker_loop()
            auth_service: Optional AuthService for automatic token refresh on expiration
            **kwargs: Service-specific keyword arguments passed to _worker_loop()

        Returns:
            Status dictionary: {success: bool, message: str}
        """
        if self._is_worker_alive():
            return {"success": False, "message": "Worker already running"}

        # Reset stale flag if thread is not alive
        self._worker_running = False

        # Store auth_service for automatic token refresh in worker loop
        self._auth_service = auth_service

        # Validate pre-conditions
        validation = self._validate_worker_start()
        if not validation.get("valid", False):
            return {
                "success": False,
                "message": validation.get("message", "Validation failed"),
            }

        # Initialize worker state
        self._stop_flag.clear()
        with self._stats_lock:
            self._worker_stats = {
                "processed": 0,
                "errors": 0,
                "last_error": None,
                "consecutive_failures": 0,
            }

        # Start worker thread
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            args=args,
            kwargs=kwargs,
            daemon=True,
        )
        self._worker_running = True
        self._worker_thread.start()

        self.logger.info("Worker thread started")
        return {"success": True, "message": "Worker started"}

    def stop_worker(self) -> dict[str, object]:
        """Stop background worker thread.
        
        Signals the worker to stop via _stop_flag and waits up to 10 seconds
        for graceful shutdown.
        
        Returns:
            Status dictionary: {success: bool, message: str}
        """
        if not self._is_worker_alive():
            self._worker_running = False
            return {"success": False, "message": "Worker not running"}

        self._stop_flag.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=10)

        still_alive = self._is_worker_alive()
        self._worker_running = still_alive

        if still_alive:
            self.logger.warning("Worker stop requested but still running")
            return {"success": True, "message": "Stop requested"}

        self.logger.info("Worker thread stopped")
        return {"success": True, "message": "Worker stopped"}
