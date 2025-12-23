"""Service for broadcasting profile comments to watchers."""

import time
import random
import threading
from logging import Logger
from typing import Optional

import requests

from ..storage.profile_message_repository import ProfileMessageRepository
from ..storage.profile_message_log_repository import ProfileMessageLogRepository
from ..storage.profile_message_queue_repository import ProfileMessageQueueRepository
from ..storage.watcher_repository import WatcherRepository
from ..domain.models import MessageLogStatus, QueueStatus
from ..config.settings import get_config
from .message_randomizer import randomize_template
from .http_client import DeviantArtHttpClient


class ProfileMessageService:
    """Coordinates profile comment broadcasting to watchers."""

    WATCHERS_URL = "https://www.deviantart.com/api/v1/oauth2/user/watchers/{username}"
    PROFILE_COMMENT_URL = "https://www.deviantart.com/api/v1/oauth2/comments/post/profile/{username}"
    MAX_CONSECUTIVE_FAILURES = 5  # Stop worker after this many consecutive failures

    def __init__(
        self,
        message_repo: ProfileMessageRepository,
        log_repo: ProfileMessageLogRepository,
        queue_repo: ProfileMessageQueueRepository,
        watcher_repo: WatcherRepository,
        logger: Logger,
        http_client: Optional[DeviantArtHttpClient] = None,
        config: Optional[object] = None,
    ) -> None:
        self.message_repo = message_repo
        self.log_repo = log_repo
        self.queue_repo = queue_repo
        self.watcher_repo = watcher_repo
        self.logger = logger
        self.http_client = http_client or DeviantArtHttpClient(logger=logger)
        self._config = config

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

        # Watchers queue (filled by fetch_watchers)
        # Each item: {"username": str, "userid": str, "selected": bool}
        self._watchers_queue: list[dict] = []
        self._queue_lock = threading.Lock()

    @property
    def config(self):
        """Lazy-load config if not provided during initialization."""
        if self._config is None:
            self._config = get_config()
        return self._config

    # ========== Watchers Collection ==========

    def _fetch_watchers_from_api(
        self, access_token: str, username: str, max_watchers: int
    ) -> tuple[list[dict], int, bool, bool]:
        """Fetch watchers list from DeviantArt API and upsert into database.

        Args:
            access_token: OAuth access token.
            username: Username to fetch watchers for.
            max_watchers: Maximum number of watchers to fetch.

        Returns:
            Tuple of:
            - watchers_list: List of dicts for in-memory queue
            - watchers_fetched: How many watchers were collected
            - has_more: Whether API indicates more watchers exist beyond fetched
            - fetch_failed: True if HTTP request failed before completion
        """
        offset = 0
        limit = 50  # API limit
        watchers_fetched = 0
        watchers_list: list[dict] = []
        has_more = False
        fetch_failed = False

        self.logger.info(
            "Fetching watchers for %s: max=%s, limit=%s",
            username,
            max_watchers,
            limit,
        )

        while watchers_fetched < max_watchers:
            params = {
                "access_token": access_token,
                "limit": limit,
                "offset": offset,
            }

            try:
                url = self.WATCHERS_URL.format(username=username)
                response = self.http_client.get(url, params=params, timeout=30)
                data = response.json() or {}
            except requests.RequestException as e:
                fetch_failed = True
                self.logger.error("Watchers fetch failed: %s", e)
                break

            if not isinstance(data, dict):
                fetch_failed = True
                self.logger.error("Watchers fetch returned non-dict JSON: %r", data)
                break

            results = data.get("results", [])
            for watcher in results:
                user = watcher.get("user", {}) if isinstance(watcher, dict) else {}
                watcher_username = user.get("username")
                watcher_userid = user.get("userid")

                if watcher_username and watcher_userid:
                    watchers_list.append(
                        {
                            "username": watcher_username,
                            "userid": watcher_userid,
                            "selected": True,  # Selected by default
                        }
                    )

                    # Save to database
                    try:
                        self.watcher_repo.add_or_update_watcher(
                            watcher_username, watcher_userid
                        )
                    except Exception as e:  # noqa: BLE001
                        self.logger.warning(
                            "Failed to save watcher %s: %s", watcher_username, e
                        )

                    watchers_fetched += 1

                if watchers_fetched >= max_watchers:
                    break

            has_more = bool(data.get("has_more", False))
            next_offset = data.get("next_offset")

            if next_offset is not None:
                try:
                    offset = int(next_offset)
                except (TypeError, ValueError):
                    offset += limit
            else:
                offset += limit

            if not has_more or watchers_fetched >= max_watchers:
                break

            # Delay between pages
            delay = self.http_client.get_recommended_delay()
            self.logger.debug(
                "Waiting %s seconds before next watchers page request", delay
            )
            time.sleep(delay)

        return watchers_list, watchers_fetched, has_more, fetch_failed

    def fetch_watchers(
        self, access_token: str, username: str, max_watchers: int = 50
    ) -> dict:
        """Fetch watchers for given user.

        Args:
            access_token: OAuth access token
            username: Username to fetch watchers for
            max_watchers: Maximum number of watchers to fetch

        Returns:
            Dictionary with results: {watchers_count, has_more}
        """
        watchers_list, watchers_fetched, has_more, fetch_failed = (
            self._fetch_watchers_from_api(access_token, username, max_watchers)
        )

        self.logger.info("Fetched %s watchers for %s", watchers_fetched, username)

        # Synchronize database: remove watchers who unfollowed.
        # IMPORTANT: do this only when we have the full list; otherwise we could
        # accidentally delete watchers that are simply beyond max_watchers.
        deleted_count = 0
        pruned = False
        if not fetch_failed and not has_more:
            current_usernames = [w["username"] for w in watchers_list]
            try:
                deleted_count = int(
                    self.watcher_repo.delete_watchers_not_in_list(current_usernames)
                )
                pruned = True
                if deleted_count > 0:
                    self.logger.info(
                        "Removed %s unfollowed watchers from database", deleted_count
                    )
            except Exception as e:  # noqa: BLE001
                self.logger.warning("Failed to synchronize watchers: %s", e)

        # Store in queue
        with self._queue_lock:
            self._watchers_queue = watchers_list

        return {
            "watchers_count": watchers_fetched,
            "has_more": has_more,
            "pruned": pruned,
            "deleted_count": deleted_count,
            "fetch_failed": fetch_failed,
        }

    def prune_unfollowed_watchers(
        self, access_token: str, username: str, max_watchers: int = 500
    ) -> dict:
        """Synchronize saved watchers by removing users who unfollowed.

        This action fetches the current watchers list from DeviantArt, upserts
        those watchers into the database, and deletes database rows for users
        that are no longer present.

        Safety:
            Pruning is executed only if the full list was fetched
            (API returns has_more=False). If max_watchers is too low and
            has_more=True, the method will return pruned=False.

        Args:
            access_token: OAuth access token.
            username: Username to fetch watchers for.
            max_watchers: Maximum number of watchers to fetch.

        Returns:
            Dictionary with results: {watchers_count, has_more, pruned, deleted_count}.
        """

        watchers_list, watchers_fetched, has_more, fetch_failed = (
            self._fetch_watchers_from_api(access_token, username, max_watchers)
        )

        deleted_count = 0
        pruned = False
        if not fetch_failed and not has_more:
            current_usernames = [w["username"] for w in watchers_list]
            deleted_count = int(
                self.watcher_repo.delete_watchers_not_in_list(current_usernames)
            )
            pruned = True

        return {
            "watchers_count": watchers_fetched,
            "has_more": has_more,
            "pruned": pruned,
            "deleted_count": deleted_count,
        }

    # ========== Worker ==========

    def _get_randomized_message(self) -> tuple[int | None, str | None]:
        """Get a random active message template and randomize it.

        Returns:
            Tuple of (message_id, randomized_body) or (None, None) if no active templates
        """
        active_messages = self.message_repo.get_active_messages()
        
        if not active_messages:
            self.logger.warning("No active message templates found")
            return None, None
        
        # Select random active template
        selected_message = random.choice(active_messages)
        
        # Randomize the template body
        randomized_body = randomize_template(selected_message.body)
        
        self.logger.debug(
            "Selected template %s: '%s' -> '%s'",
            selected_message.message_id,
            selected_message.body[:50],
            randomized_body[:50],
        )
        
        return selected_message.message_id, randomized_body

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

    def _is_worker_alive(self) -> bool:
        """Return True if the background worker thread is alive."""
        return bool(self._worker_thread and self._worker_thread.is_alive())

    def start_worker(self, access_token: str) -> dict:
        """Start background worker thread.

        Args:
            access_token: OAuth access token for posting comments

        Returns:
            Status dictionary: {success, message}
        """
        if self._is_worker_alive():
            return {"success": False, "message": "Worker already running"}

        # Reset stale flag if the thread is not alive.
        self._worker_running = False

        # Check if queue has pending entries in DB
        try:
            pending_count = self.queue_repo.get_queue_count(status=QueueStatus.PENDING)
            if pending_count == 0:
                return {"success": False, "message": "No watchers in queue. Fetch watchers first."}
        except Exception as e:
            self.logger.error("Failed to check queue count: %s", e)
            return {"success": False, "message": f"Failed to check queue: {str(e)}"}

        # Check if there are active message templates
        active_messages = self.message_repo.get_active_messages()
        if not active_messages:
            return {"success": False, "message": "No active message templates found. Please activate at least one template."}

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

        self.logger.info("Worker thread started with %s active templates", len(active_messages))
        return {"success": True, "message": "Worker started"}

    def stop_worker(self) -> dict:
        """Stop background worker thread.

        Returns:
            Status dictionary: {success, message}
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
            self.logger.warning("Worker stop requested but thread is still running")
            return {"success": True, "message": "Stop requested"}

        self.logger.info("Worker thread stopped")
        return {"success": True, "message": "Worker stopped"}

    def get_worker_status(self) -> dict:
        """Get worker and queue status.

        Returns:
            Dictionary with: {running, processed, errors, last_error, queue_remaining, send_stats}
        """
        running = self._is_worker_alive()
        if not running:
            # Keep internal flag in sync for callers that still rely on it.
            self._worker_running = False

        # Count pending entries in DB queue
        try:
            queue_remaining = self.queue_repo.get_queue_count(status=QueueStatus.PENDING)
        except Exception as e:
            self.logger.error("Failed to get queue count: %s", e)
            queue_remaining = 0

        send_stats = self.log_repo.get_stats()

        with self._stats_lock:
            return {
                "running": running,
                "processed": self._worker_stats["processed"],
                "errors": self._worker_stats["errors"],
                "last_error": self._worker_stats["last_error"],
                "consecutive_failures": self._worker_stats["consecutive_failures"],
                "queue_remaining": queue_remaining,
                "send_stats": send_stats,
            }

    def clear_queue(self) -> dict:
        """Clear pending entries from persistent queue.

        Returns:
            Status dictionary: {success, cleared_count}
        """
        try:
            cleared = self.queue_repo.clear_queue(status=QueueStatus.PENDING)
            self.logger.info("Cleared %s pending entries from queue", cleared)
            return {"success": True, "cleared_count": cleared}
        except Exception as e:
            error_msg = f"Failed to clear queue: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return {"success": False, "cleared_count": 0, "error": error_msg}

    def remove_selected_from_queue(self) -> dict:
        """Remove all pending entries from persistent queue.

        Note: In DB-backed queue, there's no 'selected' concept.
        This method clears all pending entries.

        Returns:
            Status dictionary: {success, removed_count, remaining_count}
        """
        try:
            removed_count = self.queue_repo.clear_queue(status=QueueStatus.PENDING)
            remaining_count = self.queue_repo.get_queue_count(status=QueueStatus.PENDING)
            
            self.logger.info(
                "Removed %s pending entries from queue (%s remaining)",
                removed_count,
                remaining_count,
            )
            return {
                "success": True,
                "removed_count": removed_count,
                "remaining_count": remaining_count,
            }
        except Exception as e:
            error_msg = f"Failed to remove from queue: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "removed_count": 0,
                "remaining_count": 0,
                "error": error_msg,
            }

    def get_watchers_list(self) -> list[dict]:
        """Get current watchers queue from persistent storage.

        Returns:
            List of watchers: [{"username": str, "userid": str, "selected": bool}]
            Note: 'selected' is always True for pending entries (for UI compatibility)
        """
        try:
            pending_entries = self.queue_repo.get_pending(limit=1000)
            return [
                {
                    "username": entry.recipient_username,
                    "userid": entry.recipient_userid,
                    "selected": True,  # All pending entries are considered "selected"
                }
                for entry in pending_entries
            ]
        except Exception as e:
            self.logger.error("Failed to get watchers list: %s", e, exc_info=True)
            return []

    def update_watcher_selection(self, username: str, selected: bool) -> dict:
        """Update selection status for specific watcher (no-op for DB queue).

        Note: In DB-backed queue, all pending entries are considered selected.
        This method exists for API compatibility but does nothing.

        Args:
            username: Watcher username
            selected: New selection status (ignored)

        Returns:
            Status dictionary: {success, message}
        """
        return {"success": True, "message": f"Selection update not needed for DB queue"}

    def select_all_watchers(self) -> dict:
        """Select all watchers in queue (no-op for DB queue).

        Note: In DB-backed queue, all pending entries are already considered selected.

        Returns:
            Status dictionary: {success, selected_count}
        """
        try:
            count = self.queue_repo.get_queue_count(status=QueueStatus.PENDING)
            return {"success": True, "selected_count": count}
        except Exception as e:
            self.logger.error("Failed to count pending entries: %s", e)
            return {"success": False, "selected_count": 0}

    def deselect_all_watchers(self) -> dict:
        """Deselect all watchers in queue (no-op for DB queue).

        Note: In DB-backed queue, deselecting means removing from queue.
        Use clear_queue() or remove_selected_from_queue() instead.

        Returns:
            Status dictionary: {success, deselected_count}
        """
        # For DB queue, "deselect all" doesn't make sense
        # Return success with 0 count to indicate no action taken
        return {"success": True, "deselected_count": 0}

    def save_watcher_to_db(self, username: str, userid: str) -> dict:
        """Save single watcher to database.

        Args:
            username: Watcher username
            userid: Watcher user ID

        Returns:
            Status dictionary: {success, message}
        """
        try:
            self.watcher_repo.add_or_update_watcher(username, userid)
            self.logger.info("Saved watcher %s to database", username)
            return {"success": True, "message": f"Saved {username} to database"}
        except Exception as e:
            self.logger.error("Failed to save watcher %s: %s", username, e)
            return {"success": False, "message": str(e)}

    def save_selected_to_db(self) -> dict:
        """Save only selected watchers from queue to database.

        Uses upsert to avoid duplicates.

        Returns:
            Status dictionary: {success, saved_count, failed_count, skipped_count}
        """
        saved_count = 0
        failed_count = 0
        skipped_count = 0

        with self._queue_lock:
            watchers_to_save = [w.copy() for w in self._watchers_queue]

        for watcher in watchers_to_save:
            # Only save selected watchers
            if not watcher.get("selected", False):
                skipped_count += 1
                continue

            username = watcher.get("username")
            userid = watcher.get("userid")
            if username and userid:
                try:
                    self.watcher_repo.add_or_update_watcher(username, userid)
                    saved_count += 1
                except Exception as e:
                    self.logger.warning("Failed to save watcher %s: %s", username, e)
                    failed_count += 1

        self.logger.info(
            "Saved %s selected watchers to database (%s failed, %s skipped)",
            saved_count,
            failed_count,
            skipped_count,
        )
        return {
            "success": True,
            "saved_count": saved_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
        }

    def add_saved_watcher_to_queue(self, username: str, userid: str) -> dict:
        """Add saved watcher from database to sending queue.

        Args:
            username: Watcher username
            userid: Watcher user ID

        Returns:
            Status dictionary: {success, message}
        """
        with self._queue_lock:
            # Check if already in queue
            for w in self._watchers_queue:
                if w.get("username") == username:
                    return {
                        "success": False,
                        "message": f"{username} is already in queue",
                    }

            self._watchers_queue.append({
                "username": username,
                "userid": userid,
                "selected": True,
            })

        self.logger.info("Added saved watcher %s to queue", username)
        return {"success": True, "message": f"Added {username} to queue"}

    def add_all_saved_to_queue(self, limit: int = 1000) -> dict:
        """Add all saved watchers from database to persistent queue.

        Filters out watchers who already received messages (sent or failed).

        Args:
            limit: Maximum number of watchers to add

        Returns:
            Status dictionary: {success, added_count, skipped_count, already_sent_count}
        """
        # Get first active message as placeholder (worker will select random message anyway)
        active_messages = self.message_repo.get_active_messages()
        if not active_messages:
            return {
                "success": False,
                "added_count": 0,
                "skipped_count": 0,
                "already_sent_count": 0,
                "message": "No active message templates found",
            }
        
        message_id = active_messages[0].message_id
        
        # Get all recipient_userid who already received messages
        try:
            already_sent_userids = self.log_repo.get_all_recipient_userids()
        except Exception as e:
            self.logger.error("Failed to get sent userids: %s", e, exc_info=True)
            already_sent_userids = set()
        
        saved_watchers = self.watcher_repo.get_all_watchers(limit)
        added_count = 0
        skipped_count = 0
        already_sent_count = 0

        for watcher in saved_watchers:
            # Skip if already sent (in logs)
            if watcher.userid in already_sent_userids:
                already_sent_count += 1
                self.logger.debug(
                    "Skipping %s - already in send history",
                    watcher.username,
                )
                continue

            try:
                # UPSERT: will update if already exists in queue
                self.queue_repo.add_to_queue(
                    message_id=message_id,
                    recipient_username=watcher.username,
                    recipient_userid=watcher.userid,
                    priority=0,
                )
                added_count += 1
            except Exception as e:
                self.logger.warning(
                    "Failed to add %s to queue: %s",
                    watcher.username,
                    e,
                )
                skipped_count += 1

        self.logger.info(
            "Added %s saved watchers to queue (%s skipped, %s already sent)",
            added_count,
            skipped_count,
            already_sent_count,
        )
        return {
            "success": True,
            "added_count": added_count,
            "skipped_count": skipped_count,
            "already_sent_count": already_sent_count,
        }

    def add_selected_saved_to_queue(self, watchers: list[dict]) -> dict:
        """Add selected saved watchers to persistent queue.

        Filters out watchers who already received messages (sent or failed).

        Args:
            watchers: List of watchers to add, each item expects
                {"username": str, "userid": str}

        Returns:
            Status dictionary:
                {success, added_count, skipped_count, invalid_count, already_sent_count}
        """
        if not watchers:
            return {
                "success": True,
                "added_count": 0,
                "skipped_count": 0,
                "invalid_count": 0,
                "already_sent_count": 0,
            }

        # Get first active message as placeholder
        active_messages = self.message_repo.get_active_messages()
        if not active_messages:
            return {
                "success": False,
                "added_count": 0,
                "skipped_count": 0,
                "invalid_count": 0,
                "already_sent_count": 0,
                "message": "No active message templates found",
            }
        
        message_id = active_messages[0].message_id
        
        # Get all recipient_userid who already received messages
        try:
            already_sent_userids = self.log_repo.get_all_recipient_userids()
        except Exception as e:
            self.logger.error("Failed to get sent userids: %s", e, exc_info=True)
            already_sent_userids = set()
        
        added_count = 0
        skipped_count = 0
        invalid_count = 0
        already_sent_count = 0

        for watcher in watchers:
            username = (watcher.get("username") or "").strip()
            userid = (watcher.get("userid") or "").strip()

            if not username or not userid:
                invalid_count += 1
                continue

            # Skip if already sent (in logs)
            if userid in already_sent_userids:
                already_sent_count += 1
                self.logger.debug(
                    "Skipping %s - already in send history",
                    username,
                )
                continue

            try:
                # UPSERT: will update if already exists in queue
                self.queue_repo.add_to_queue(
                    message_id=message_id,
                    recipient_username=username,
                    recipient_userid=userid,
                    priority=0,
                )
                added_count += 1
            except Exception as e:
                self.logger.warning(
                    "Failed to add %s to queue: %s",
                    username,
                    e,
                )
                skipped_count += 1

        self.logger.info(
            "Added %s selected saved watchers to queue (%s skipped, %s invalid, %s already sent)",
            added_count,
            skipped_count,
            invalid_count,
            already_sent_count,
        )

        return {
            "success": True,
            "added_count": added_count,
            "skipped_count": skipped_count,
            "invalid_count": invalid_count,
            "already_sent_count": already_sent_count,
        }

    def retry_failed_messages(self, limit: int = 100) -> dict:
        """Add failed messages back to queue for retry.

        Retrieves failed message logs and adds them to the persistent queue
        with higher priority for retry.

        Args:
            limit: Maximum number of failed messages to retry

        Returns:
            Status dictionary: {success, added_count, skipped_count, message}
        """
        try:
            # Get failed logs from history
            failed_logs = self.log_repo.get_failed_logs(limit=limit)
            
            if not failed_logs:
                return {
                    "success": True,
                    "added_count": 0,
                    "skipped_count": 0,
                    "message": "No failed messages found",
                }

            added_count = 0
            skipped_count = 0
            successfully_added_logs = []

            # Add each failed recipient to queue with high priority
            for log in failed_logs:
                try:
                    # Add to persistent queue with priority=10 (higher than default 0)
                    self.queue_repo.add_to_queue(
                        message_id=log.message_id,
                        recipient_username=log.recipient_username,
                        recipient_userid=log.recipient_userid,
                        priority=10,
                    )
                    added_count += 1
                    successfully_added_logs.append(log)
                except Exception as e:
                    self.logger.warning(
                        "Failed to add %s to retry queue: %s",
                        log.recipient_username,
                        e,
                    )
                    skipped_count += 1

            # Delete failed logs that were successfully added to retry queue
            deleted_count = 0
            if successfully_added_logs:
                try:
                    deleted_count = self.log_repo.delete_failed_logs(successfully_added_logs)
                    self.logger.info(
                        "Deleted %s failed log entries from history",
                        deleted_count,
                    )
                except Exception as e:
                    self.logger.warning(
                        "Failed to delete failed logs: %s",
                        e,
                    )

            self.logger.info(
                "Added %s failed messages to retry queue (%s skipped, %s deleted from history)",
                added_count,
                skipped_count,
                deleted_count,
            )

            return {
                "success": True,
                "added_count": added_count,
                "skipped_count": skipped_count,
                "deleted_count": deleted_count,
                "message": f"Added {added_count} failed messages to retry queue",
            }

        except Exception as e:
            error_msg = f"Failed to retry messages: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "added_count": 0,
                "skipped_count": 0,
                "message": error_msg,
            }

    def _worker_loop(self, access_token: str) -> None:
        """Background worker loop (runs in separate thread)."""
        self.logger.info("Worker loop started with randomized message templates")
        try:
            while not self._stop_flag.is_set():
                # Get next pending entry from DB queue
                try:
                    pending_entries = self.queue_repo.get_pending(limit=1)
                    if not pending_entries:
                        # No more pending entries, stop worker
                        self.logger.info("No more pending entries, stopping worker")
                        break
                    
                    queue_entry = pending_entries[0]
                    username = queue_entry.recipient_username
                    userid = queue_entry.recipient_userid
                    queue_id = queue_entry.queue_id
                    
                    # Mark as processing
                    self.queue_repo.mark_processing(queue_id)
                    
                except Exception as e:
                    self.logger.error("Failed to get next queue entry: %s", e, exc_info=True)
                    break

                if not username or not userid:
                    self.logger.warning("Invalid queue entry: username=%s, userid=%s", username, userid)
                    # Remove invalid entry from queue
                    self.queue_repo.remove_from_queue(queue_id)
                    continue

                # Get randomized message for this send
                message_id, message_body = self._get_randomized_message()
                
                if not message_id or not message_body:
                    self.logger.error("Failed to get randomized message, stopping worker")
                    break

                try:
                    # Apply broadcast delay before sending
                    broadcast_delay = self._get_broadcast_delay()
                    self.logger.info(
                        "Waiting %d seconds before sending to %s",
                        broadcast_delay,
                        username,
                    )
                    time.sleep(broadcast_delay)

                    # Post comment to profile (HTTP client handles retry automatically)
                    url = self.PROFILE_COMMENT_URL.format(username=username)
                    response = self.http_client.post(
                        url,
                        data={"body": message_body, "access_token": access_token},
                        timeout=30,
                    )

                    # Success - HTTP client only returns response if successful
                    response_data = response.json()
                    commentid = response_data.get("commentid")

                    self.log_repo.add_log(
                        message_id=message_id,
                        recipient_username=username,
                        recipient_userid=userid,
                        status=MessageLogStatus.SENT,
                        commentid=commentid,
                    )

                    with self._stats_lock:
                        self._worker_stats["processed"] += 1
                        self._worker_stats["consecutive_failures"] = 0  # Reset on success

                    self.logger.info(
                        "Sent comment to %s (commentid=%s)", username, commentid
                    )

                    # Remove from queue after successful send
                    try:
                        self.queue_repo.remove_from_queue(queue_id)
                    except Exception as e:
                        self.logger.warning("Failed to remove queue entry %s: %s", queue_id, e)

                    # Rate limiting: use recommended delay from HTTP client
                    delay = self.http_client.get_recommended_delay()
                    self.logger.debug(
                        "Waiting %s seconds before next profile comment request",
                        delay,
                    )
                    time.sleep(delay)

                except requests.HTTPError as e:
                    # HTTP error - check if it's critical first
                    error_msg = self._format_http_error(e)
                    
                    # Check for critical errors that require immediate worker stop
                    if self._is_critical_error(e):
                        self.logger.critical(
                            "CRITICAL ERROR DETECTED: %s - Stopping worker immediately to prevent escalating sanctions from DeviantArt",
                            error_msg,
                        )
                        self.log_repo.add_log(
                            message_id=message_id,
                            recipient_username=username,
                            recipient_userid=userid,
                            status=MessageLogStatus.FAILED,
                            error_message=error_msg,
                        )
                        with self._stats_lock:
                            self._worker_stats["errors"] += 1
                            self._worker_stats["consecutive_failures"] += 1
                            self._worker_stats["last_error"] = error_msg
                        # Remove from queue
                        try:
                            self.queue_repo.remove_from_queue(queue_id)
                        except Exception as ex:
                            self.logger.warning("Failed to remove queue entry %s: %s", queue_id, ex)
                        break
                    
                    # Non-critical HTTP error - handle normally
                    self.log_repo.add_log(
                        message_id=message_id,
                        recipient_username=username,
                        recipient_userid=userid,
                        status=MessageLogStatus.FAILED,
                        error_message=error_msg,
                    )

                    with self._stats_lock:
                        self._worker_stats["errors"] += 1
                        self._worker_stats["consecutive_failures"] += 1
                        self._worker_stats["last_error"] = error_msg
                        consecutive_failures = self._worker_stats["consecutive_failures"]

                    self.logger.error(
                        "Failed to send to %s: %s (consecutive failures: %d/%d)",
                        username,
                        error_msg,
                        consecutive_failures,
                        self.MAX_CONSECUTIVE_FAILURES,
                    )

                    # Remove from queue after failed send
                    try:
                        self.queue_repo.remove_from_queue(queue_id)
                    except Exception as ex:
                        self.logger.warning("Failed to remove queue entry %s: %s", queue_id, ex)

                    # Stop worker if too many consecutive failures
                    if consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                        self.logger.critical(
                            "Worker stopped: %d consecutive failures reached (limit: %d)",
                            consecutive_failures,
                            self.MAX_CONSECUTIVE_FAILURES,
                        )
                        break

                    delay = self.http_client.get_recommended_delay()
                    self.logger.debug(
                        "Waiting %s seconds before retry after failure",
                        delay,
                    )
                    time.sleep(delay)

                except requests.RequestException as e:
                    # Non-HTTP request error - handle normally
                    error_msg = f"Request failed after retries: {str(e)}"

                    self.log_repo.add_log(
                        message_id=message_id,
                        recipient_username=username,
                        recipient_userid=userid,
                        status=MessageLogStatus.FAILED,
                        error_message=error_msg,
                    )

                    with self._stats_lock:
                        self._worker_stats["errors"] += 1
                        self._worker_stats["consecutive_failures"] += 1
                        self._worker_stats["last_error"] = error_msg
                        consecutive_failures = self._worker_stats["consecutive_failures"]

                    self.logger.error(
                        "Failed to send to %s: %s (consecutive failures: %d/%d)",
                        username,
                        str(e),
                        consecutive_failures,
                        self.MAX_CONSECUTIVE_FAILURES,
                    )

                    # Remove from queue after failed send
                    try:
                        self.queue_repo.remove_from_queue(queue_id)
                    except Exception as ex:
                        self.logger.warning("Failed to remove queue entry %s: %s", queue_id, ex)

                    # Stop worker if too many consecutive failures
                    if consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                        self.logger.critical(
                            "Worker stopped: %d consecutive failures reached (limit: %d)",
                            consecutive_failures,
                            self.MAX_CONSECUTIVE_FAILURES,
                        )
                        break

                    delay = self.http_client.get_recommended_delay()
                    self.logger.debug(
                        "Waiting %s seconds before retry after failure",
                        delay,
                    )
                    time.sleep(delay)

                except Exception as e:
                    # Unexpected error - log and continue
                    error_msg = f"Unexpected error: {str(e)}"

                    self.log_repo.add_log(
                        message_id=message_id,
                        recipient_username=username,
                        recipient_userid=userid,
                        status=MessageLogStatus.FAILED,
                        error_message=error_msg,
                    )

                    with self._stats_lock:
                        self._worker_stats["errors"] += 1
                        self._worker_stats["last_error"] = error_msg

                    self.logger.exception("Unexpected error for %s", username)
                    
                    # Remove from queue after unexpected error
                    try:
                        self.queue_repo.remove_from_queue(queue_id)
                    except Exception as e:
                        self.logger.warning("Failed to remove queue entry %s: %s", queue_id, e)
                    
                    delay = self.http_client.get_recommended_delay()
                    self.logger.debug(
                        "Waiting %s seconds before continuing after unexpected error",
                        delay,
                    )
                    time.sleep(delay)
        finally:
            self._worker_running = False
            self.logger.info("Worker loop stopped")
