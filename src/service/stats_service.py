"""Service for fetching and persisting deviation statistics."""
from datetime import date
import re
from logging import Logger
from typing import Optional

import requests

from ..storage.stats_repository import StatsRepository


class StatsService:
    """Coordinates DeviantArt stats collection."""

    BASE_URL = "https://www.deviantart.com/api/v1/oauth2"

    def __init__(self, stats_repository: StatsRepository, logger: Logger):
        self.stats_repository = stats_repository
        self.logger = logger

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

            response = requests.get(url, params=params)
            response.raise_for_status()
            payload = response.json()

            results = payload.get("results", [])
            all_items.extend(results)

            if not payload.get("has_more"):
                break
            next_offset = payload.get("next_offset")
            if next_offset is None:
                break
            offset = next_offset

        return all_items

    def _fetch_metadata(self, access_token: str, deviationids: list[str]) -> list[dict]:
        """Batch fetch metadata with extended fields and stats (ext_stats forces max batch size 10)."""

        url = f"{self.BASE_URL}/deviation/metadata"
        all_meta: list[dict] = []

        # DeviantArt limits ext_stats batches to 10 items
        batch_size = 10

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

            response = requests.get(url, params=params)
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:  # noqa: BLE001
                # Include response text to ease debugging of API rejections
                self.logger.error(
                    "Metadata fetch failed: %s", response.text or response.reason
                )
                raise exc

            payload = response.json()
            all_meta.extend(payload.get("metadata", []))

        return all_meta

    def sync_gallery(self, access_token: str, folderid: str, username: Optional[str] = None) -> dict:
        """Fetch gallery deviations, pull stats, persist current and snapshot."""

        today = date.today().isoformat()
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

        if not deviation_map:
            return {"synced": 0, "date": today}

        metadata = self._fetch_metadata(access_token, list(deviation_map.keys()))
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

            self.stats_repository.save_deviation_stats(
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

            self.stats_repository.save_snapshot(
                deviationid=deviationid,
                snapshot_date=today,
                views=stats.get("views", 0),
                favourites=stats.get("favourites", 0),
                comments=stats.get("comments", 0),
            )

            self.stats_repository.save_metadata(
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

        return {"synced": len(deviation_map), "date": today}

    def get_stats_with_diff(self) -> list[dict]:
        """Return current stats with deltas vs yesterday."""

        stats = self.stats_repository.get_all_stats_with_previous()
        for row in stats:
            row["views_diff"] = row["views"] - row["yesterday_views"]
            row["favourites_diff"] = row["favourites"] - row["yesterday_favourites"]
            row["comments_diff"] = row["comments"] - row["yesterday_comments"]
            # Use stored URL from DB; fall back to constructed URL if missing
            if not row.get("url"):
                row["url"] = self._build_deviation_url(row)
        return stats