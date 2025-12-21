"""Centralized HTTP client for DeviantArt API with retry and rate limiting."""

import time
from logging import Logger
from typing import Any, Optional

import requests


class DeviantArtHttpClient:
    """Centralized HTTP client for all DeviantArt API requests.
    
    Features:
    - Automatic retry with exponential backoff for temporary errors
    - Retry-After header compliance for 429 and 503
    - Centralized error handling and logging
    - Configurable retry limits
    """

    # Retry configuration
    MAX_RETRIES = 5  # Maximum number of retry attempts
    BASE_RETRY_DELAY = 5  # Base delay in seconds for exponential backoff
    MAX_BACKOFF_DELAY = 60  # Maximum backoff delay in seconds

    # HTTP status codes that should trigger retry
    RETRYABLE_STATUS_CODES = {400, 429, 503}

    # Default delay between requests to avoid rate limiting
    DEFAULT_REQUEST_DELAY = 5  # seconds

    def __init__(self, logger: Logger, enable_retry: bool = True) -> None:
        """Initialize HTTP client.
        
        Args:
            logger: Logger instance for request/error logging
            enable_retry: Enable automatic retry logic (default: True)
        """
        self.logger = logger
        self.enable_retry = enable_retry
        # Track last retry delay from rate limiting for proactive waiting
        self._last_retry_delay: int = 0

    def get_recommended_delay(self) -> int:
        """Get recommended delay between requests based on recent rate limiting.
        
        If a rate limit was recently encountered, returns the last retry delay
        used. Otherwise returns the default request delay.
        
        Returns:
            Recommended delay in seconds before next request
        """
        if self._last_retry_delay > 0:
            return self._last_retry_delay
        return self.DEFAULT_REQUEST_DELAY

    def reset_retry_delay(self) -> None:
        """Reset the last retry delay after successful requests without rate limiting."""
        self._last_retry_delay = 0

    def _sleep(self, delay: int, *, reason: str) -> None:
        """Sleep for a given delay.

        Args:
            delay: Delay in seconds.
            reason: Short reason for sleeping (used for debug logging).
        """
        self.logger.debug("Sleeping %s seconds (%s)", delay, reason)
        time.sleep(delay)

    @staticmethod
    def _is_rate_limited_response(response: requests.Response) -> bool:
        """Check if response indicates rate limiting.
        
        DeviantArt API can signal rate limiting via:
        - HTTP 429 status code
        - JSON payload with "error": "user_api_threshold"
        
        Args:
            response: HTTP response object
            
        Returns:
            True if rate limited, False otherwise
        """
        if response.status_code == 429:
            return True

        try:
            data = response.json()
            if isinstance(data, dict) and data.get("error") == "user_api_threshold":
                return True
        except Exception:  # noqa: BLE001
            pass

        return False

    def get(
        self,
        url: str,
        params: Optional[dict[str, Any]] = None,
        timeout: int = 30,
        **kwargs: Any,
    ) -> requests.Response:
        """Execute GET request with retry logic.
        
        Args:
            url: Request URL
            params: Query parameters
            timeout: Request timeout in seconds
            **kwargs: Additional arguments passed to requests.get
            
        Returns:
            Response object
            
        Raises:
            requests.RequestException: After max retries exceeded or non-retryable error
        """

        self.logger.debug(
            "Fetche item %s",
            url,
        )

        return self._request_with_retry(
            method="GET",
            url=url,
            params=params,
            timeout=timeout,
            **kwargs,
        )

    def post(
        self,
        url: str,
        data: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
        files: Optional[dict[str, Any]] = None,
        timeout: int = 30,
        **kwargs: Any,
    ) -> requests.Response:
        """Execute POST request with retry logic.
        
        Args:
            url: Request URL
            data: Form data
            json: JSON data
            files: Files to upload
            timeout: Request timeout in seconds
            **kwargs: Additional arguments passed to requests.post
            
        Returns:
            Response object
            
        Raises:
            requests.RequestException: After max retries exceeded or non-retryable error
        """
        return self._request_with_retry(
            method="POST",
            url=url,
            data=data,
            json=json,
            files=files,
            timeout=timeout,
            **kwargs,
        )

    def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> requests.Response:
        """Execute HTTP request with retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            **kwargs: Arguments passed to requests.request
            
        Returns:
            Response object
            
        Raises:
            requests.RequestException: After max retries exceeded or non-retryable error
        """
        retry_count = 0
        last_exception: Optional[Exception] = None

        while retry_count <= self.MAX_RETRIES:
            try:
                # Log request
                self.logger.debug(
                    "HTTP %s %s (attempt %d/%d)",
                    method,
                    url,
                    retry_count + 1,
                    self.MAX_RETRIES + 1,
                )

                # Execute request
                response = requests.request(method, url, **kwargs)

                # Check for retryable errors (rate limit or temporary errors)
                is_rate_limited = self._is_rate_limited_response(response)
                is_retryable = (
                    response.status_code in self.RETRYABLE_STATUS_CODES
                    or is_rate_limited
                )

                if is_retryable:
                    if not self.enable_retry or retry_count >= self.MAX_RETRIES:
                        # Max retries exceeded or retry disabled
                        self.logger.error(
                            "HTTP %s failed: %s %s (max retries exceeded)",
                            method,
                            response.status_code,
                            response.text[:200],
                        )
                        # For JSON-based rate limits (HTTP 200 with error in body),
                        # raise_for_status() won't raise, so we must raise manually
                        if is_rate_limited and response.status_code < 400:
                            raise requests.RequestException(
                                f"Rate limited after {self.MAX_RETRIES} retries: "
                                f"{response.text[:200]}"
                            )
                        response.raise_for_status()
                        return response

                    # Handle retry
                    retry_count += 1
                    delay = self._calculate_retry_delay(response, retry_count)
                    
                    # Store last retry delay for proactive rate limiting
                    if is_rate_limited:
                        self._last_retry_delay = delay

                    error_type = "rate limited" if is_rate_limited else f"HTTP {response.status_code}"
                    self.logger.warning(
                        "HTTP %s %s: %s (attempt %d/%d), retrying in %d seconds",
                        method,
                        error_type,
                        response.text[:100],
                        retry_count,
                        self.MAX_RETRIES,
                        delay,
                    )

                    self._sleep(delay, reason=f"retry after {error_type}")
                    continue

                # Success or non-retryable error
                if response.status_code >= 400:
                    self.logger.error(
                        "HTTP %s failed: %s %s",
                        method,
                        response.status_code,
                        response.text[:200],
                    )
                    response.raise_for_status()

                self.logger.debug("HTTP %s %s: success", method, url)
                return response

            except requests.RequestException as e:
                last_exception = e

                if not self.enable_retry or retry_count >= self.MAX_RETRIES:
                    # Max retries exceeded or retry disabled
                    self.logger.error(
                        "HTTP %s failed: %s (max retries exceeded)",
                        method,
                        str(e),
                        exc_info=True,
                    )
                    raise

                # Network error - retry with backoff
                retry_count += 1
                delay = self._calculate_backoff_delay(retry_count)

                self.logger.warning(
                    "HTTP %s network error: %s (attempt %d/%d), retrying in %d seconds",
                    method,
                    str(e),
                    retry_count,
                    self.MAX_RETRIES,
                    delay,
                )

                self._sleep(delay, reason="retry after network error")
                continue

        # Should not reach here, but just in case
        if last_exception:
            raise last_exception
        raise requests.RequestException(f"Max retries ({self.MAX_RETRIES}) exceeded")

    def _calculate_retry_delay(
        self, response: requests.Response, retry_count: int
    ) -> int:
        """Calculate delay before retry based on Retry-After header or exponential backoff.
        
        Args:
            response: HTTP response object
            retry_count: Current retry attempt number
            
        Returns:
            Delay in seconds
        """
        # Check for Retry-After header (429, 503)
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                delay = int(retry_after)
                # Cap at MAX_BACKOFF_DELAY
                return min(delay, self.MAX_BACKOFF_DELAY)
            except ValueError:
                # Invalid Retry-After value, fall back to exponential backoff
                self.logger.warning(
                    "Invalid Retry-After header: %s, using exponential backoff",
                    retry_after,
                )

        # Exponential backoff
        return self._calculate_backoff_delay(retry_count)

    def _calculate_backoff_delay(self, retry_count: int) -> int:
        """Calculate exponential backoff delay.
        
        Args:
            retry_count: Current retry attempt number
            
        Returns:
            Delay in seconds (BASE_RETRY_DELAY * 2^(retry_count-1), capped at MAX_BACKOFF_DELAY)
        """
        delay = self.BASE_RETRY_DELAY * (2 ** (retry_count - 1))
        return min(delay, self.MAX_BACKOFF_DELAY)
