"""Service for fetching and persisting deviation statistics."""
from datetime import date
import re
import threading
import time
from logging import Logger
from typing import Optional
import requests

from sqlalchemy import text

from ..storage.deviation_repository import DeviationRepository
from ..storage.deviation_stats_repository import DeviationStatsRepository
from ..storage.gallery_repository import GalleryRepository
from ..storage.stats_snapshot_repository import StatsSnapshotRepository
from ..storage.user_stats_snapshot_repository import UserStatsSnapshotRepository
from ..storage.deviation_metadata_repository import DeviationMetadataRepository
from .http_client import DeviantArtHttpClient


class StatsService:
    """Coordinates DeviantArt stats collection."""

    BASE_URL = "https://www.deviantart.com/api/v1/oauth2"

    def __init__(
        self,
        deviation_stats_repository: DeviationStatsRepository,
        stats_snapshot_repository: StatsSnapshotRepository,
        user_stats_snapshot_repository: UserStatsSnapshotRepository,
        deviation_metadata_repository: DeviationMetadataRepository,
        deviation_repository: DeviationRepository,
        logger: Logger,
        http_client: Optional[DeviantArtHttpClient] = None,
        gallery_repository: Optional[GalleryRepository] = None,
    ) -> None:
        self.deviation_stats_repo = deviation_stats_repository
        self.stats_snapshot_repo = stats_snapshot_repository
        self.user_stats_snapshot_repo = user_stats_snapshot_repository
        self.deviation_metadata_repo = deviation_metadata_repository
        self.deviation_repository = deviation_repository
        self.gallery_repo = gallery_repository
        self.logger = logger
        self.http_client = http_client or DeviantArtHttpClient(logger=logger)

        # Worker state
        self._worker_thread: Optional[threading.Thread] = None
        self._worker_running = False
        self._stop_flag = threading.Event()
        self._stats_lock = threading.Lock()
        self._worker_stats = {
            "processed_galleries": 0,
            "processed_deviations": 0,
            "errors": 0,
            "last_error": None,
            "current_gallery": None,
        }

    @staticmethod
    def _slugify_title(title: str) -> str:
        """Return a DeviantArt-friendly slug derived from the title."""

        if not title:
            return "art"

        # Replace non-word characters with hyphens, collapse repeats, trim.
        slug = re.sub(r"\W+", "-", title.strip())
        slug = re.sub(r"-+", "-", slug).strip("-")
        return slug or "art"

    def _build_deviation_url(self, row: dict) -> Optional[str]:
        """Construct a public DeviantArt URL from available metadata."""

        author = row.get("author") or {}
        username = author.get("username") if isinstance(author, dict) else None
        deviationid = row.get("deviationid")
        title = row.get("title") or row.get("metadata_title")

        if not username or not deviationid:
            return None

        slug = self._slugify_title(title or "")
        return f"https://www.deviantart.com/{username}/art/{slug}-{deviationid}"

    def _fetch_gallery_items(
        self,
        access_token: str,
        folderid: str,
        limit: int = 24,
        mode: str = "newest",
        username: Optional[str] = None,
    ) -> list[dict]:
        """Fetch deviations from a gallery folder with pagination."""

        url = f"{self.BASE_URL}/gallery/{folderid}"
        offset = 0
        all_items: list[dict] = []

        self.logger.info(
            "Fetching gallery items for folder %s (username=%s, mode=%s)",
            folderid,
            username or "-",
            mode,
        )

        while True:
            params: dict[str, str | int] = {
                "access_token": access_token,
                "offset": offset,
                "limit": min(limit, 24),
                "mode": mode,
                "mature_content": "true",
            }
            if username:
                params["username"] = username

            # HTTP client handles retry automatically
            response = self.http_client.get(url, params=params)
            payload = response.json()

            results = payload.get("results", [])
            all_items.extend(results)

            self.logger.debug(
                "Fetched %d items at offset %d for folder %s",
                len(results),
                offset,
                folderid,
            )

            if not payload.get("has_more"):
                break
            next_offset = payload.get("next_offset")
            if next_offset is None:
                break
            offset = next_offset
            
            # Rate limiting: use recommended delay from HTTP client
            # (respects Retry-After header or uses exponential backoff)
            delay = self.http_client.get_recommended_delay()
            self.logger.debug("Waiting %d seconds before next pagination request", delay)
            time.sleep(delay)

        self.logger.info(
            "Loaded %d deviations from gallery folder %s", len(all_items), folderid
        )

        return all_items

    def _fetch_metadata(self, access_token: str, deviationids: list[str]) -> list[dict]:
        """Batch fetch metadata with extended fields and stats (ext_stats forces max batch size 10)."""

        url = f"{self.BASE_URL}/deviation/metadata"
        all_meta: list[dict] = []

        # DeviantArt limits ext_stats batches to 10 items
        batch_size = 10
        total_batches = (len(deviationids) + batch_size - 1) // batch_size

        self.logger.info(
            "Fetching metadata for %d deviations in %d batches (batch_size=%d)",
            len(deviationids),
            total_batches,
            batch_size,
        )

        for i in range(0, len(deviationids), batch_size):
            batch = deviationids[i : i + batch_size]
            batch_num = (i // batch_size) + 1
            params: dict[str, str | list[str]] = {
                "access_token": access_token,
                "ext_stats": "true",
                "ext_submission": "true",
                "ext_camera": "true",
                "ext_collection": "true",
                "ext_gallery": "true",
                "mature_content": "true",
                "deviationids[]": batch,
            }

            self.logger.info(
                "Fetching metadata batch %d/%d (deviations %d-%d of %d)",
                batch_num,
                total_batches,
                i + 1,
                i + len(batch),
                len(deviationids),
            )

            # HTTP client handles retry automatically
            response = self.http_client.get(url, params=params)
            payload = response.json()
            fetched_count = len(payload.get("metadata", []))
            all_meta.extend(payload.get("metadata", []))

            self.logger.info(
                "Batch %d/%d completed: fetched %d metadata records",
                batch_num,
                total_batches,
                fetched_count,
            )
            
            # Rate limiting: use recommended delay from HTTP client
            # (respects Retry-After header or uses exponential backoff)
            # (skip sleep after the last batch)
            if i + batch_size < len(deviationids):
                delay = self.http_client.get_recommended_delay()
                self.logger.debug("Waiting %d seconds before next batch request", delay)
                time.sleep(delay)

        self.logger.info(
            "Metadata fetch completed: %d total records fetched",
            len(all_meta),
        )

        return all_meta

    def _fetch_deviation_details(
        self, access_token: str, deviationids: list[str]
    ) -> dict[str, dict]:
        """Fetch detailed deviation data (including published_time) per deviation.

        DeviantArt does not provide a true batch endpoint for this call, so we
        iterate over the identifiers but keep the logic encapsulated here. The
        result is a mapping ``deviationid -> payload``.
        """
        details: dict[str, dict] = {}

        self.logger.info(
            "Fetching detailed deviation data for %d deviations", len(deviationids)
        )

        for idx, deviationid in enumerate(deviationids):
            self.logger.debug("Requesting details for deviation %s", deviationid)

            url = f"{self.BASE_URL}/deviation/{deviationid}"
            params: dict[str, str] = {
                "access_token": access_token,
                "mature_content": "true",
                "with_session": "false",
            }

            # HTTP client handles retry automatically
            response = self.http_client.get(url, params=params)
            payload = response.json()
            
            if isinstance(payload, dict):
                self.logger.debug(
                    "Received details for deviation %s (published_time=%s)",
                    deviationid,
                    payload.get("published_time"),
                )
                details[deviationid] = payload
            
            # Rate limiting: use recommended delay from HTTP client
            # (respects Retry-After header or uses exponential backoff)
            # (skip sleep after the last deviation)
            if idx < len(deviationids) - 1:
                delay = self.http_client.get_recommended_delay()
                self.logger.debug("Waiting %d seconds before next deviation request", delay)
                time.sleep(delay)

        return details

    def _snapshot_user_stats(
        self,
        access_token: str,
        username: Optional[str],
        snapshot_date: str,
    ) -> Optional[dict]:
        """Snapshot user.stats (watchers, friends) for the given date.

        Args:
            access_token: OAuth2 access token.
            username: DeviantArt username to fetch profile for.
            snapshot_date: ISO date string (YYYY-MM-DD) for the snapshot.

        Returns:
            Dictionary with username, snapshot_date, watchers, friends, profile_url,
            watchers_diff (daily change), yesterday_watchers; or None if the
            operation failed or username is missing.
        """

        if not username:
            self.logger.info("No username provided; skipping user watcher snapshot")
            return None

        url = f"{self.BASE_URL}/user/profile/{username}"
        params: dict[str, str] = {
            "access_token": access_token,
            "expand": "user.stats",
            "with_session": "false",
        }

        self.logger.info("Fetching user profile for snapshot: %s", username)

        try:
            # HTTP client handles retry automatically
            resp = self.http_client.get(url, params=params, timeout=30)
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Failed to fetch user profile %s: %s", username, exc)
            return None

        user_obj = payload.get("user") or {}
        stats_obj = user_obj.get("stats") or {}

        def _to_int(value: object, default: int = 0) -> int:
            try:
                return int(value)  # type: ignore[arg-type]
            except Exception:  # noqa: BLE001
                return default

        watchers = _to_int(stats_obj.get("watchers"), 0)
        friends = _to_int(stats_obj.get("friends"), 0)
        resolved_username = user_obj.get("username") or username
        profile_url = payload.get("profile_url") or user_obj.get("profile_url")

        self.logger.info(
            "User watchers snapshot for %s on %s: watchers=%d, friends=%d",
            resolved_username,
            snapshot_date,
            watchers,
            friends,
        )

        try:
            # user_id can be left None, we're keying by username
            self.user_stats_snapshot_repo.save_user_stats_snapshot(
                user_id=None,
                username=resolved_username,
                snapshot_date=snapshot_date,
                watchers=watchers,
                friends=friends,
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.error(
                "Failed to persist user stats snapshot for %s: %s",
                resolved_username,
                exc,
            )

        # Fetch the latest snapshot to get watchers_diff calculated by the repository
        latest_snapshot = self.user_stats_snapshot_repo.get_latest_user_stats_snapshot(resolved_username)
        if latest_snapshot:
            # Return the complete snapshot including watchers_diff
            return latest_snapshot

        # Fallback if fetch failed (shouldn't happen normally)
        return {
            "username": resolved_username,
            "snapshot_date": snapshot_date,
            "watchers": watchers,
            "friends": friends,
            "profile_url": profile_url,
            "watchers_diff": 0,
        }

    def sync_gallery(
        self,
        access_token: str,
        folderid: str,
        username: Optional[str] = None,
    ) -> dict:
        """Fetch gallery deviations, pull stats, persist current and snapshot.

        Args:
            access_token: OAuth2 access token.
            folderid: DeviantArt gallery folder identifier.
            username: Optional DeviantArt username (for shared galleries).
            
        Raises:
            requests.RequestException: If too many consecutive HTTP requests fail.
        """

        today = date.today().isoformat()
        self.logger.info(
            "Starting stats sync for folder %s (username=%s)",
            folderid,
            username or "-",
        )

        # Track consecutive failures to stop sync if too many requests fail
        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = 5

        # Snapshot user stats (watchers, friends) BEFORE fetching deviations
        try:
            user_stats_snapshot = self._snapshot_user_stats(access_token, username, today)
            consecutive_failures = 0  # Reset on success
        except requests.RequestException as e:
            consecutive_failures += 1
            self.logger.error(
                "Failed to snapshot user stats (consecutive failures: %d/%d): %s",
                consecutive_failures,
                MAX_CONSECUTIVE_FAILURES,
                str(e),
            )
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                self.logger.critical(
                    "Sync stopped: %d consecutive failures reached (limit: %d)",
                    consecutive_failures,
                    MAX_CONSECUTIVE_FAILURES,
                )
                raise

        try:
            deviations = self._fetch_gallery_items(access_token, folderid, username=username)
            consecutive_failures = 0  # Reset on success
        except requests.RequestException as e:
            consecutive_failures += 1
            self.logger.error(
                "Failed to fetch gallery items (consecutive failures: %d/%d): %s",
                consecutive_failures,
                MAX_CONSECUTIVE_FAILURES,
                str(e),
            )
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                self.logger.critical(
                    "Sync stopped: %d consecutive failures reached (limit: %d)",
                    consecutive_failures,
                    MAX_CONSECUTIVE_FAILURES,
                )
                raise
            # If not at limit yet, return partial results
            return {"synced": 0, "date": today, "user_stats": user_stats_snapshot, "error": str(e)}

        deviation_map: dict[str, dict] = {}
        for item in deviations:
            deviationid = item.get("deviationid")
            if not deviationid:
                continue
            thumbs = item.get("thumbs") or []
            deviation_map[deviationid] = {
                "title": item.get("title") or "Untitled",
                "thumb_url": thumbs[0].get("src") if thumbs else None,
                "is_mature": bool(
                    item.get("is_mature")
                    or item.get("mature_level")
                    or item.get("mature_classification")
                ),
                "url": item.get("url"),
            }

        self.logger.info(
            "Resolved %d deviations with IDs in folder %s",
            len(deviation_map),
            folderid,
        )

        if not deviation_map:
            self.logger.info("No deviations found for folder %s; nothing to sync.", folderid)
            return {"synced": 0, "date": today, "user_stats": user_stats_snapshot}

        keys = list(deviation_map.keys())
        try:
            metadata = self._fetch_metadata(access_token, keys)
            consecutive_failures = 0  # Reset on success
        except requests.RequestException as e:
            consecutive_failures += 1
            self.logger.error(
                "Failed to fetch metadata (consecutive failures: %d/%d): %s",
                consecutive_failures,
                MAX_CONSECUTIVE_FAILURES,
                str(e),
            )
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                self.logger.critical(
                    "Sync stopped: %d consecutive failures reached (limit: %d)",
                    consecutive_failures,
                    MAX_CONSECUTIVE_FAILURES,
                )
                raise
            # If not at limit yet, return partial results
            return {"synced": 0, "date": today, "user_stats": user_stats_snapshot, "error": str(e)}

        for meta in metadata:
            deviationid = meta.get("deviationid")
            stats = meta.get("stats", {}) if meta else {}
            submission = meta.get("submission") or {}
            basic = deviation_map.get(deviationid, {})
            if meta is not None:
                is_mature = bool(
                    meta.get("is_mature")
                    or meta.get("mature_level")
                    or meta.get("mature_classification")
                )
            else:
                is_mature = False

            if not is_mature:
                is_mature = bool(basic.get("is_mature"))

            self.logger.debug(
                "Processing deviation %s: views=%d, favourites=%d, comments=%d",
                deviationid,
                stats.get("views", 0),
                stats.get("favourites", 0),
                stats.get("comments", 0),
            )

            # Save current absolute stats
            current_views = stats.get("views", 0)
            current_favourites = stats.get("favourites", 0)
            current_comments = stats.get("comments", 0)

            self.deviation_stats_repo.save_deviation_stats(
                deviationid=deviationid,
                title=basic.get("title") or meta.get("title") or "Untitled",
                views=current_views,
                favourites=current_favourites,
                comments=current_comments,
                thumb_url=basic.get("thumb_url"),
                gallery_folderid=folderid,
                is_mature=is_mature,
                url=basic.get("url"),
            )

            # Calculate delta: current absolute - cumulative sum of all previous deltas
            # Get all snapshots before today to calculate cumulative baseline
            all_snapshots = self.stats_snapshot_repo.get_snapshots_for_deviation(
                deviationid, limit=10000
            )
            previous_cumulative_views = sum(
                s["views"] for s in all_snapshots if s["snapshot_date"] < today
            )
            previous_cumulative_favourites = sum(
                s["favourites"] for s in all_snapshots if s["snapshot_date"] < today
            )
            previous_cumulative_comments = sum(
                s["comments"] for s in all_snapshots if s["snapshot_date"] < today
            )

            views_delta = current_views - previous_cumulative_views
            favourites_delta = current_favourites - previous_cumulative_favourites
            comments_delta = current_comments - previous_cumulative_comments

            # Save daily delta (not absolute values)
            self.stats_snapshot_repo.save_snapshot(
                deviationid=deviationid,
                snapshot_date=today,
                views=views_delta,
                favourites=favourites_delta,
                comments=comments_delta,
            )

            self.deviation_metadata_repo.save_metadata(
                deviationid=deviationid,
                title=meta.get("title") or basic.get("title") or "Untitled",
                description=meta.get("description"),
                license=meta.get("license"),
                allows_comments=meta.get("allows_comments"),
                tags=meta.get("tags") or [],
                is_favourited=meta.get("is_favourited"),
                is_watching=meta.get("is_watching"),
                is_mature=is_mature,
                mature_level=meta.get("mature_level"),
                mature_classification=meta.get("mature_classification") or [],
                printid=meta.get("printid"),
                author=meta.get("author"),
                creation_time=submission.get("creation_time"),
                category=submission.get("category"),
                file_size=submission.get("file_size"),
                resolution=submission.get("resolution"),
                submitted_with=submission.get("submitted_with"),
                stats_json=stats,
                camera=meta.get("camera"),
                collections=meta.get("collections") or [],
                galleries=meta.get("galleries") or [],
                can_post_comment=meta.get("can_post_comment"),
                stats_views_today=stats.get("views_today"),
                stats_downloads_today=stats.get("downloads_today"),
                stats_downloads=stats.get("downloads"),
                stats_views=stats.get("views"),
                stats_favourites=stats.get("favourites"),
                stats_comments=stats.get("comments"),
            )

            self.logger.debug(
                "Saved stats, snapshot and metadata for deviation %s (title=%r)",
                deviationid,
                basic.get("title") or meta.get("title") or "Untitled",
            )
        self.logger.info(
            "Finished stats sync for folder %s: processed %d deviations",
            folderid,
            len(deviation_map),
        )
        return {
            "synced": len(deviation_map),
            "date": today,
            "user_stats": user_stats_snapshot,
        }

    def get_stats_with_diff(self) -> list[dict]:
        """Return current stats with deltas vs yesterday.

        Note: stats_snapshots now store daily deltas (not cumulative values).
        The 'yesterday_views' field from the join is already a delta.
        """
        stats = self.deviation_stats_repo.get_all_stats_with_previous()
        for row in stats:
            # yesterday_* fields now contain deltas, not cumulative values
            row["views_diff"] = row["yesterday_views"]
            row["favourites_diff"] = row["yesterday_favourites"]
            row["comments_diff"] = row["yesterday_comments"]
            # Use stored URL from DB; fall back to constructed URL if missing
            if not row.get("url"):
                row["url"] = self._build_deviation_url(row)
        return stats

    def get_deviations_list(self) -> list[dict]:
        """Return list of all deviations with basic info for selection UI.

        Returns:
            List of dictionaries with deviationid, title, thumb_url
        """
        stats = self.deviation_stats_repo.get_all_stats_with_previous()
        return [
            {
                "deviationid": row["deviationid"],
                "title": row.get("title") or "Untitled",
                "thumb_url": row.get("thumb_url"),
            }
            for row in stats
        ]

    def get_aggregated_stats(
        self, period_days: int = 7, deviation_ids: list[str] | None = None
    ) -> dict:
        """Return aggregated daily statistics for charts.

        Args:
            period_days: Number of days to include (default: 7)
            deviation_ids: Optional list of deviation IDs to filter (None = all)

        Returns:
            Dictionary with labels (dates) and datasets (views, favourites)
        """
        # PostgreSQL-compatible query (no SQLite-specific `?` placeholders / `date('now', ...)`).
        # `deviation_ids` is optional; when provided we filter using `= ANY(:deviation_ids)`.
        query = text(
            """
            SELECT
                snapshot_date,
                SUM(views) as total_views,
                SUM(favourites) as total_favourites,
                SUM(comments) as total_comments
            FROM stats_snapshots
            WHERE (:deviation_ids IS NULL OR deviationid = ANY(:deviation_ids))
              AND snapshot_date::date >= CURRENT_DATE - (:period_days * INTERVAL '1 day')
            GROUP BY snapshot_date
            ORDER BY snapshot_date ASC
            """
        )

        params = {
            "deviation_ids": deviation_ids if deviation_ids else None,
            "period_days": period_days,
        }

        result = self.stats_snapshot_repo.conn.execute(query, params)
        rows = result.fetchall()

        labels = []
        views_data = []
        favourites_data = []
        comments_data = []

        for row in rows:
            labels.append(row[0])
            views_data.append(row[1] or 0)
            favourites_data.append(row[2] or 0)
            comments_data.append(row[3] or 0)

        return {
            "labels": labels,
            "datasets": {
                "views": views_data,
                "favourites": favourites_data,
                "comments": comments_data,
            },
        }

    def get_user_watchers_history(
        self, username: str, period_days: int = 7
    ) -> dict:
        """Return user watchers history for charts.

        Args:
            username: DeviantArt username
            period_days: Number of days to include (default: 7)

        Returns:
            Dictionary with labels (dates) and datasets (watchers, friends)
        """
        query = text(
            """
            SELECT
                snapshot_date,
                watchers,
                friends
            FROM user_stats_snapshots
            WHERE username = :username
              AND snapshot_date::date >= CURRENT_DATE - (:period_days * INTERVAL '1 day')
            ORDER BY snapshot_date ASC
            """
        )

        result = self.user_stats_snapshot_repo.conn.execute(
            query,
            {"username": username, "period_days": period_days},
        )
        rows = result.fetchall()

        labels = []
        watchers_data = []
        friends_data = []

        for row in rows:
            labels.append(row[0])
            watchers_data.append(row[1] or 0)
            friends_data.append(row[2] or 0)

        return {
            "labels": labels,
            "datasets": {
                "watchers": watchers_data,
                "friends": friends_data,
            },
        }

    # ========== Worker Methods ==========

    def start_worker(self, access_token: str, username: Optional[str] = None) -> dict:
        """Start background worker thread for stats sync.

        Args:
            access_token: OAuth access token for API calls
            username: Optional DeviantArt username for gallery sync

        Returns:
            Status dictionary: {success, message}
        """
        if self._worker_running:
            return {"success": False, "message": "Worker already running"}

        if not self.gallery_repo:
            return {"success": False, "message": "Gallery repository not configured"}

        self._stop_flag.clear()
        with self._stats_lock:
            self._worker_stats = {
                "processed_galleries": 0,
                "processed_deviations": 0,
                "errors": 0,
                "last_error": None,
                "current_gallery": None,
            }

        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            args=(access_token, username),
            daemon=True,
        )
        self._worker_running = True
        self._worker_thread.start()

        self.logger.info("Stats sync worker thread started")
        return {"success": True, "message": "Worker started"}

    def stop_worker(self) -> dict:
        """Stop background worker thread.

        Returns:
            Status dictionary: {success, message}
        """
        if not self._worker_running:
            return {"success": False, "message": "Worker not running"}

        self.logger.info("Stopping stats sync worker...")
        self._stop_flag.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=10)

        self._worker_running = False
        self.logger.info("Stats sync worker thread stopped")
        return {"success": True, "message": "Worker stopped"}

    def get_worker_status(self) -> dict:
        """Get worker status and statistics.

        Returns:
            Dictionary with: {running, processed_galleries, processed_deviations,
                            errors, last_error, current_gallery}
        """
        with self._stats_lock:
            return {
                "running": self._worker_running,
                "processed_galleries": self._worker_stats["processed_galleries"],
                "processed_deviations": self._worker_stats["processed_deviations"],
                "errors": self._worker_stats["errors"],
                "last_error": self._worker_stats["last_error"],
                "current_gallery": self._worker_stats["current_gallery"],
            }

    def _worker_loop(self, access_token: str, username: Optional[str]) -> None:
        """Background worker loop for syncing all enabled galleries."""
        self.logger.info("Stats sync worker loop started")
        try:
            # Get all galleries with sync_enabled=True
            galleries = self.gallery_repo.get_sync_enabled_galleries()
            total_galleries = len(galleries)

            self.logger.info(
                "Found %d galleries with sync enabled",
                total_galleries,
            )

            for idx, gallery in enumerate(galleries):
                # Check stop flag before each gallery
                if self._stop_flag.is_set():
                    self.logger.info("Worker stop requested, exiting loop")
                    break

                folderid = gallery.folderid
                gallery_name = gallery.name or folderid

                with self._stats_lock:
                    self._worker_stats["current_gallery"] = gallery_name

                self.logger.info(
                    "Syncing gallery %d/%d: %s (%s)",
                    idx + 1,
                    total_galleries,
                    gallery_name,
                    folderid,
                )

                try:
                    result = self.sync_gallery(access_token, folderid, username=username)
                    synced_count = result.get("synced", 0)

                    with self._stats_lock:
                        self._worker_stats["processed_galleries"] += 1
                        self._worker_stats["processed_deviations"] += synced_count

                    self.logger.info(
                        "Gallery %s synced: %d deviations",
                        gallery_name,
                        synced_count,
                    )

                except requests.RequestException as e:
                    error_msg = f"Failed to sync gallery {gallery_name}: {str(e)}"
                    with self._stats_lock:
                        self._worker_stats["errors"] += 1
                        self._worker_stats["last_error"] = error_msg
                    self.logger.error(error_msg)

                except Exception as e:
                    error_msg = f"Unexpected error syncing gallery {gallery_name}: {str(e)}"
                    with self._stats_lock:
                        self._worker_stats["errors"] += 1
                        self._worker_stats["last_error"] = error_msg
                    self.logger.exception(error_msg)

                # Wait between galleries with stop_flag check (interruptible)
                if idx < total_galleries - 1:
                    if self._stop_flag.wait(timeout=3):
                        self.logger.info("Worker stop requested during delay")
                        break

            with self._stats_lock:
                self._worker_stats["current_gallery"] = None

            self.logger.info(
                "Stats sync worker completed: %d galleries, %d deviations, %d errors",
                self._worker_stats["processed_galleries"],
                self._worker_stats["processed_deviations"],
                self._worker_stats["errors"],
            )

        finally:
            self._worker_running = False
            self.logger.info("Stats sync worker loop stopped")