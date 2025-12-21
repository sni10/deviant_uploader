"""Service for broadcasting profile comments to watchers."""

import time
import random
import threading
from logging import Logger
from typing import Optional

import requests

from ..storage.profile_message_repository import ProfileMessageRepository
from ..storage.profile_message_log_repository import ProfileMessageLogRepository
from ..storage.watcher_repository import WatcherRepository
from ..domain.models import MessageLogStatus
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
        watcher_repo: WatcherRepository,
        logger: Logger,
        http_client: Optional[DeviantArtHttpClient] = None,
    ) -> None:
        self.message_repo = message_repo
        self.log_repo = log_repo
        self.watcher_repo = watcher_repo
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

        # Watchers queue (filled by fetch_watchers)
        # Each item: {"username": str, "userid": str, "selected": bool}
        self._watchers_queue: list[dict] = []
        self._queue_lock = threading.Lock()

    # ========== Watchers Collection ==========

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
        offset = 0
        limit = 50  # API limit
        watchers_fetched = 0
        watchers_list = []

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
                data = response.json()
            except requests.RequestException as e:
                self.logger.error("Watchers fetch failed: %s", e)
                break

            results = data.get("results", [])
            for watcher in results:
                user = watcher.get("user", {})
                watcher_username = user.get("username")
                watcher_userid = user.get("userid")

                if watcher_username and watcher_userid:
                    watchers_list.append({
                        "username": watcher_username,
                        "userid": watcher_userid,
                        "selected": True,  # Selected by default
                    })

                    # Save to database
                    try:
                        self.watcher_repo.add_or_update_watcher(
                            watcher_username, watcher_userid
                        )
                    except Exception as e:
                        self.logger.warning(
                            "Failed to save watcher %s: %s", watcher_username, e
                        )

                    watchers_fetched += 1

                if watchers_fetched >= max_watchers:
                    break

            has_more = data.get("has_more", False)
            next_offset = data.get("next_offset")

            if next_offset is not None:
                offset = next_offset

            if not has_more or watchers_fetched >= max_watchers:
                break

            # Delay between pages
            delay = self.http_client.get_recommended_delay()
            self.logger.debug(
                "Waiting %s seconds before next watchers page request", delay
            )
            time.sleep(delay)

        self.logger.info("Fetched %s watchers for %s", watchers_fetched, username)

        # Synchronize database: remove watchers who unfollowed
        if watchers_list:
            current_usernames = [w["username"] for w in watchers_list]
            try:
                deleted_count = self.watcher_repo.delete_watchers_not_in_list(current_usernames)
                if deleted_count > 0:
                    self.logger.info("Removed %s unfollowed watchers from database", deleted_count)
            except Exception as e:
                self.logger.warning("Failed to synchronize watchers: %s", e)

        # Store in queue
        with self._queue_lock:
            self._watchers_queue = watchers_list

        return {
            "watchers_count": watchers_fetched,
            "has_more": data.get("has_more", False) if watchers_fetched < max_watchers else True,
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

        # Check if queue has watchers
        with self._queue_lock:
            if not self._watchers_queue:
                return {"success": False, "message": "No watchers in queue. Fetch watchers first."}

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

        with self._queue_lock:
            queue_remaining = sum(1 for w in self._watchers_queue if w.get("selected", False))

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
        """Clear watchers queue.

        Returns:
            Status dictionary: {success, cleared_count}
        """
        with self._queue_lock:
            cleared = len(self._watchers_queue)
            self._watchers_queue = []

        self.logger.info("Cleared %s watchers from queue", cleared)
        return {"success": True, "cleared_count": cleared}

    def remove_selected_from_queue(self) -> dict:
        """Remove selected watchers from the in-memory queue.

        Returns:
            Status dictionary: {success, removed_count, remaining_count}
        """
        with self._queue_lock:
            before_count = len(self._watchers_queue)
            self._watchers_queue = [
                w for w in self._watchers_queue if not w.get("selected", False)
            ]
            remaining_count = len(self._watchers_queue)

        removed_count = before_count - remaining_count
        self.logger.info(
            "Removed %s selected watchers from queue (%s remaining)",
            removed_count,
            remaining_count,
        )
        return {
            "success": True,
            "removed_count": removed_count,
            "remaining_count": remaining_count,
        }

    def get_watchers_list(self) -> list[dict]:
        """Get current watchers queue with selection status.

        Returns:
            List of watchers: [{"username": str, "userid": str, "selected": bool}]
        """
        with self._queue_lock:
            return [w.copy() for w in self._watchers_queue]

    def update_watcher_selection(self, username: str, selected: bool) -> dict:
        """Update selection status for specific watcher.

        Args:
            username: Watcher username
            selected: New selection status

        Returns:
            Status dictionary: {success, message}
        """
        with self._queue_lock:
            found = False
            for watcher in self._watchers_queue:
                if watcher.get("username") == username:
                    watcher["selected"] = selected
                    found = True
                    break

        if found:
            return {"success": True, "message": f"Updated selection for {username}"}
        else:
            return {"success": False, "message": f"Watcher {username} not found in queue"}

    def select_all_watchers(self) -> dict:
        """Select all watchers in queue.

        Returns:
            Status dictionary: {success, selected_count}
        """
        with self._queue_lock:
            for watcher in self._watchers_queue:
                watcher["selected"] = True
            count = len(self._watchers_queue)

        self.logger.info("Selected all %s watchers", count)
        return {"success": True, "selected_count": count}

    def deselect_all_watchers(self) -> dict:
        """Deselect all watchers in queue.

        Returns:
            Status dictionary: {success, deselected_count}
        """
        with self._queue_lock:
            for watcher in self._watchers_queue:
                watcher["selected"] = False
            count = len(self._watchers_queue)

        self.logger.info("Deselected all %s watchers", count)
        return {"success": True, "deselected_count": count}

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
        """Add all saved watchers from database to sending queue.

        Args:
            limit: Maximum number of watchers to add

        Returns:
            Status dictionary: {success, added_count, skipped_count}
        """
        saved_watchers = self.watcher_repo.get_all_watchers(limit)
        added_count = 0
        skipped_count = 0

        with self._queue_lock:
            existing_usernames = {w.get("username") for w in self._watchers_queue}

            for watcher in saved_watchers:
                if watcher.username in existing_usernames:
                    skipped_count += 1
                    continue

                self._watchers_queue.append({
                    "username": watcher.username,
                    "userid": watcher.userid,
                    "selected": True,
                })
                added_count += 1

        self.logger.info(
            "Added %s saved watchers to queue (%s skipped as duplicates)",
            added_count,
            skipped_count,
        )
        return {
            "success": True,
            "added_count": added_count,
            "skipped_count": skipped_count,
        }

    def add_selected_saved_to_queue(self, watchers: list[dict]) -> dict:
        """Add selected saved watchers to sending queue.

        Args:
            watchers: List of watchers to add, each item expects
                {"username": str, "userid": str}

        Returns:
            Status dictionary:
                {success, added_count, skipped_count, invalid_count}
        """
        if not watchers:
            return {
                "success": True,
                "added_count": 0,
                "skipped_count": 0,
                "invalid_count": 0,
            }

        added_count = 0
        skipped_count = 0
        invalid_count = 0

        with self._queue_lock:
            existing_usernames = {w.get("username") for w in self._watchers_queue}

            # Prevent duplicates within the same request
            seen_in_request: set[str] = set()

            for watcher in watchers:
                username = (watcher.get("username") or "").strip()
                userid = (watcher.get("userid") or "").strip()

                if not username or not userid:
                    invalid_count += 1
                    continue

                if username in existing_usernames or username in seen_in_request:
                    skipped_count += 1
                    continue

                self._watchers_queue.append(
                    {
                        "username": username,
                        "userid": userid,
                        "selected": True,
                    }
                )
                existing_usernames.add(username)
                seen_in_request.add(username)
                added_count += 1

        self.logger.info(
            "Added %s selected saved watchers to queue (%s skipped, %s invalid)",
            added_count,
            skipped_count,
            invalid_count,
        )

        return {
            "success": True,
            "added_count": added_count,
            "skipped_count": skipped_count,
            "invalid_count": invalid_count,
        }

    def _worker_loop(self, access_token: str) -> None:
        """Background worker loop (runs in separate thread)."""
        self.logger.info("Worker loop started with randomized message templates")
        try:
            while not self._stop_flag.is_set():
                # Get next selected watcher from queue
                with self._queue_lock:
                    # Find first selected watcher
                    selected_watcher = None
                    for i, w in enumerate(self._watchers_queue):
                        if w.get("selected", False):
                            selected_watcher = self._watchers_queue.pop(i)
                            break

                    if not selected_watcher:
                        # No more selected watchers, stop worker
                        self.logger.info("No more selected watchers, stopping worker")
                        break

                    watcher = selected_watcher

                username = watcher.get("username")
                userid = watcher.get("userid")

                if not username or not userid:
                    self.logger.warning("Invalid watcher data: %s", watcher)
                    continue

                # Get randomized message for this send
                message_id, message_body = self._get_randomized_message()
                
                if not message_id or not message_body:
                    self.logger.error("Failed to get randomized message, stopping worker")
                    break

                try:
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

                    # Rate limiting: use recommended delay from HTTP client
                    delay = self.http_client.get_recommended_delay()
                    self.logger.debug(
                        "Waiting %s seconds before next profile comment request",
                        delay,
                    )
                    time.sleep(delay)

                except requests.RequestException as e:
                    # HTTP client already retried - this is final failure
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
                    delay = self.http_client.get_recommended_delay()
                    self.logger.debug(
                        "Waiting %s seconds before continuing after unexpected error",
                        delay,
                    )
                    time.sleep(delay)
        finally:
            self._worker_running = False
            self.logger.info("Worker loop stopped")
