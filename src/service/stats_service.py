"""Service for fetching and persisting deviation statistics."""
from datetime import date
import re
import time
from logging import Logger
from typing import Optional

import requests

from ..storage.deviation_repository import DeviationRepository
from ..storage.deviation_stats_repository import DeviationStatsRepository
from ..storage.stats_snapshot_repository import StatsSnapshotRepository
from ..storage.user_stats_snapshot_repository import UserStatsSnapshotRepository
from ..storage.deviation_metadata_repository import DeviationMetadataRepository


class StatsService:
    """Coordinates DeviantArt stats collection."""

    BASE_URL = "https://www.deviantart.com/api/v1/oauth2"
    # Maximum number of exponential backoff retries on DeviantArt rate limits
    # (HTTP 429 / user_api_threshold). This controls how many times we will
    # wait and retry a single /deviation/{id} call before giving up for the
    # current sync run.
    RATE_LIMIT_MAX_RETRIES = 10
    RATE_LIMIT_INITIAL_DELAY = 1.0  # seconds

    def __init__(
        self,
        deviation_stats_repository: DeviationStatsRepository,
        stats_snapshot_repository: StatsSnapshotRepository,
        user_stats_snapshot_repository: UserStatsSnapshotRepository,
        deviation_metadata_repository: DeviationMetadataRepository,
        deviation_repository: DeviationRepository,
        logger: Logger,
    ) -> None:
        self.deviation_stats_repo = deviation_stats_repository
        self.stats_snapshot_repo = stats_snapshot_repository
        self.user_stats_snapshot_repo = user_stats_snapshot_repository
        self.deviation_metadata_repo = deviation_metadata_repository
        self.deviation_repository = deviation_repository
        self.logger = logger

    @staticmethod
    def _is_rate_limited_response(response: requests.Response) -> bool:  # type: ignore[type-arg]
        """Return True if the DeviantArt API signalled a rate limit.

        The DeviantArt API can communicate rate limiting either via an HTTP
        429 status code or via a JSON payload with ``error`` set to
        ``"user_api_threshold"`` while still returning another 4xx/5xx code.
        """

        if getattr(response, "status_code", None) == 429:
            return True

        try:
            data = response.json()
        except Exception:  # noqa: BLE001
            return False

        if isinstance(data, dict) and data.get("error") == "user_api_threshold":
            return True

        return False

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
        rate_limited = False

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

            attempts = 0
            delay = self.RATE_LIMIT_INITIAL_DELAY

            while True:
                response = requests.get(url, params=params)
                try:
                    response.raise_for_status()
                except requests.HTTPError as exc:  # noqa: BLE001
                    is_rate_limited = self._is_rate_limited_response(response)

                    if is_rate_limited and attempts < self.RATE_LIMIT_MAX_RETRIES:
                        attempts += 1
                        self.logger.warning(
                            "Gallery fetch rate-limited for folder %s at offset %s "
                            "(attempt %s/%s), backing off for %.1f seconds.",
                            folderid,
                            offset,
                            attempts,
                            self.RATE_LIMIT_MAX_RETRIES,
                            delay,
                        )
                        time.sleep(delay)
                        delay *= 2
                        continue

                    if is_rate_limited:
                        self.logger.error(
                            "Gallery fetch rate-limited for folder %s at offset %s "
                            "after %s attempts: %s",
                            folderid,
                            offset,
                            attempts + 1,
                            response.text or response.reason,
                        )
                        rate_limited = True
                        break

                    # Non rate-limit error: keep previous behaviour and surface
                    # the HTTPError to the caller.
                    self.logger.error(
                        "Gallery fetch failed for folder %s at offset %s: %s",
                        folderid,
                        offset,
                        response.text or response.reason,
                    )
                    raise exc

                break

            if rate_limited:
                break

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

        self.logger.info(
            "Loaded %d deviations from gallery folder %s", len(all_items), folderid
        )

        return all_items

    def _fetch_metadata(self, access_token: str, deviationids: list[str]) -> list[dict]:
        """Batch fetch metadata with extended fields and stats (ext_stats forces max batch size 10)."""

        url = f"{self.BASE_URL}/deviation/metadata"
        all_meta: list[dict] = []
        rate_limited = False

        # DeviantArt limits ext_stats batches to 10 items
        batch_size = 10

        self.logger.info("Fetching metadata for %d deviations", len(deviationids))

        for i in range(0, len(deviationids), batch_size):
            batch = deviationids[i : i + batch_size]
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

            self.logger.debug(
                "Fetching metadata batch %d-%d (size=%d)",
                i,
                i + len(batch) - 1,
                len(batch),
            )

            attempts = 0
            delay = self.RATE_LIMIT_INITIAL_DELAY

            while True:
                response = requests.get(url, params=params)
                try:
                    response.raise_for_status()
                except requests.HTTPError as exc:  # noqa: BLE001
                    is_rate_limited = self._is_rate_limited_response(response)

                    if is_rate_limited and attempts < self.RATE_LIMIT_MAX_RETRIES:
                        attempts += 1
                        self.logger.warning(
                            "Metadata fetch rate-limited for batch starting at %d "
                            "(attempt %d/%d), backing off for %.1f seconds.",
                            i,
                            attempts,
                            self.RATE_LIMIT_MAX_RETRIES,
                            delay,
                        )
                        time.sleep(delay)
                        delay *= 2
                        continue

                    if is_rate_limited:
                        self.logger.error(
                            "Metadata fetch rate-limited for batch starting at %d "
                            "after %d attempts: %s",
                            i,
                            attempts + 1,
                            response.text or response.reason,
                        )
                        rate_limited = True
                        break

                    # Non rate-limit error: preserve previous behaviour and
                    # surface the HTTPError to the caller.
                    self.logger.error(
                        "Metadata fetch failed for batch starting at %d: %s",
                        i,
                        response.text or response.reason,
                    )
                    raise exc

                break

            if rate_limited:
                break

            payload = response.json()
            all_meta.extend(payload.get("metadata", []))

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
        rate_limited = False

        self.logger.info(
            "Fetching detailed deviation data for %d deviations", len(deviationids)
        )

        for deviationid in deviationids:
            if rate_limited:
                # Once DeviantArt has signalled a user-level rate limit, we
                # stop issuing further detail requests in this sync run.
                break

            self.logger.debug("Requesting details for deviation %s", deviationid)

            url = f"{self.BASE_URL}/deviation/{deviationid}"
            params: dict[str, str] = {
                "access_token": access_token,
                "mature_content": "true",
                "with_session": "false",
            }

            attempts = 0
            delay = self.RATE_LIMIT_INITIAL_DELAY

            while True:
                response = requests.get(url, params=params)
                try:
                    response.raise_for_status()
                except requests.HTTPError:  # noqa: BLE001
                    # Detect DeviantArt adaptive rate limit (HTTP 429 or
                    # user_api_threshold error payload).
                    is_rate_limited = response.status_code == 429
                    payload_json: dict | None = None
                    try:
                        data = response.json()
                        if isinstance(data, dict):
                            payload_json = data
                    except Exception:  # noqa: BLE001
                        payload_json = None

                    if (
                        not is_rate_limited
                        and isinstance(payload_json, dict)
                        and payload_json.get("error") == "user_api_threshold"
                    ):
                        is_rate_limited = True

                    if is_rate_limited and attempts < self.RATE_LIMIT_MAX_RETRIES:
                        attempts += 1
                        self.logger.warning(
                            "Deviation fetch rate-limited for %s (attempt %s/%s), "
                            "backing off for %.1f seconds.",
                            deviationid,
                            attempts,
                            self.RATE_LIMIT_MAX_RETRIES,
                            delay,
                        )
                        time.sleep(delay)
                        delay *= 2
                        continue

                    if is_rate_limited:
                        # Exhausted backoff attempts for this deviation; stop
                        # the whole detail pass for the current sync run.
                        self.logger.error(
                            "Deviation fetch rate-limited at %s after %s attempts: %s",
                            deviationid,
                            attempts + 1,
                            response.text or response.reason,
                        )
                        rate_limited = True
                        break

                    # Non rate-limit error: log and continue with next
                    # deviation without retries.
                    self.logger.error(
                        "Deviation fetch failed for %s: %s",
                        deviationid,
                        response.text or response.reason,
                    )
                    break

                payload = response.json()
                if isinstance(payload, dict):
                    self.logger.debug(
                        "Received details for deviation %s (published_time=%s)",
                        deviationid,
                        payload.get("published_time"),
                    )
                    details[deviationid] = payload
                break

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
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Failed to fetch user profile %s: %s", username, exc)
            return None

        try:
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Invalid JSON in user profile for %s: %s", username, exc)
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
        include_deviations: bool = False,
    ) -> dict:
        """Fetch gallery deviations, pull stats, persist current and snapshot.

        Args:
            access_token: OAuth2 access token.
            folderid: DeviantArt gallery folder identifier.
            username: Optional DeviantArt username (for shared galleries).
            include_deviations: If True, also fetch /deviation/{id} details and
            enrich the local deviations table (heavier, more API calls).
        """

        today = date.today().isoformat()
        self.logger.info(
            "Starting stats sync for folder %s (username=%s, include_deviations=%s)",
            folderid,
            username or "-",
            include_deviations,
        )

        # Snapshot user stats (watchers, friends) BEFORE fetching deviations
        user_stats_snapshot = self._snapshot_user_stats(access_token, username, today)

        deviations = self._fetch_gallery_items(access_token, folderid, username=username)

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
        metadata = self._fetch_metadata(access_token, keys)
        deviation_details: dict[str, dict]
        if include_deviations:
            deviation_details = self._fetch_deviation_details(access_token, keys)
        else:
            deviation_details = {}
        for meta in metadata:
            deviationid = meta.get("deviationid")
            stats = meta.get("stats", {}) if meta else {}
            submission = meta.get("submission") or {}
            basic = deviation_map.get(deviationid, {})
            details = deviation_details.get(deviationid, {}) if include_deviations else {}
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

            self.deviation_stats_repo.save_deviation_stats(
                deviationid=deviationid,
                title=basic.get("title") or meta.get("title") or "Untitled",
                views=stats.get("views", 0),
                favourites=stats.get("favourites", 0),
                comments=stats.get("comments", 0),
                thumb_url=basic.get("thumb_url"),
                gallery_folderid=folderid,
                is_mature=is_mature,
                url=basic.get("url"),
            )

            self.stats_snapshot_repo.save_snapshot(
                deviationid=deviationid,
                snapshot_date=today,
                views=stats.get("views", 0),
                favourites=stats.get("favourites", 0),
                comments=stats.get("comments", 0),
            )

            # Optionally enrich the deviations table with publication time from
            # /deviation/{deviationid}. This may be expensive, so it is only
            # executed when explicitly requested by the caller.
            if include_deviations:
                published_time = details.get("published_time") if details else None
                if published_time is not None:
                    try:
                        self.deviation_repository.update_published_time_by_deviationid(
                            deviationid, published_time
                        )
                        self.logger.info(
                            "Updated deviation %s published_time to %s",
                            deviationid,
                            published_time,
                        )
                    except Exception as exc:  # noqa: BLE001
                        self.logger.error(
                            "Failed to update published_time for deviation %s: %s",
                            deviationid,
                            exc,
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
        """Return current stats with deltas vs yesterday."""

        stats = self.deviation_stats_repo.get_all_stats_with_previous()
        for row in stats:
            row["views_diff"] = row["views"] - row["yesterday_views"]
            row["favourites_diff"] = row["favourites"] - row["yesterday_favourites"]
            row["comments_diff"] = row["comments"] - row["yesterday_comments"]
            # Use stored URL from DB; fall back to constructed URL if missing
            if not row.get("url"):
                row["url"] = self._build_deviation_url(row)
        return stats