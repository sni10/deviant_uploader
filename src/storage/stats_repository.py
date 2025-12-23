"""Compatibility wrapper repository for stats-related operations.

The project has been migrated to PostgreSQL and the storage layer was split
into specialized repositories:
- `DeviationStatsRepository`
- `StatsSnapshotRepository`
- `UserStatsSnapshotRepository`
- `DeviationMetadataRepository`

`StatsRepository` is kept for backward compatibility with any legacy callsites.
It delegates to the specialized repositories which are implemented via
SQLAlchemy Core.
"""

from __future__ import annotations

from typing import Optional

from .base_repository import BaseRepository
from .deviation_metadata_repository import DeviationMetadataRepository
from .deviation_stats_repository import DeviationStatsRepository
from .stats_snapshot_repository import StatsSnapshotRepository
from .user_stats_snapshot_repository import UserStatsSnapshotRepository


class StatsRepository(BaseRepository):
    """Facade over specialized stats repositories (PostgreSQL/SQLAlchemy Core)."""

    def save_deviation_stats(
        self,
        deviationid: str,
        title: str,
        views: int,
        favourites: int,
        comments: int,
        thumb_url: Optional[str] = None,
        gallery_folderid: Optional[str] = None,
        is_mature: bool = False,
        url: Optional[str] = None,
    ) -> int:
        return DeviationStatsRepository(self.conn).save_deviation_stats(
            deviationid=deviationid,
            title=title,
            views=views,
            favourites=favourites,
            comments=comments,
            thumb_url=thumb_url,
            gallery_folderid=gallery_folderid,
            is_mature=is_mature,
            url=url,
        )

    def save_snapshot(
        self,
        deviationid: str,
        snapshot_date: str,
        views: int,
        favourites: int,
        comments: int,
    ) -> int:
        return StatsSnapshotRepository(self.conn).save_snapshot(
            deviationid=deviationid,
            snapshot_date=snapshot_date,
            views=views,
            favourites=favourites,
            comments=comments,
        )

    def save_user_stats_snapshot(
        self,
        *,
        user_id: Optional[int],
        username: str,
        snapshot_date: str,
        watchers: int,
        friends: int,
    ) -> int:
        return UserStatsSnapshotRepository(self.conn).save_user_stats_snapshot(
            user_id=user_id,
            username=username,
            snapshot_date=snapshot_date,
            watchers=watchers,
            friends=friends,
        )

    def save_metadata(
        self,
        *,
        deviationid: str,
        title: str,
        description: Optional[str],
        license: Optional[str],
        allows_comments: Optional[bool],
        tags: list,
        is_favourited: Optional[bool],
        is_watching: Optional[bool],
        is_mature: Optional[bool],
        mature_level: Optional[str],
        mature_classification: list,
        printid: Optional[str],
        author: Optional[dict],
        creation_time: Optional[str],
        category: Optional[str],
        file_size: Optional[str],
        resolution: Optional[str],
        submitted_with: Optional[dict],
        stats_json: Optional[dict],
        camera: Optional[dict],
        collections: list,
        galleries: list,
        can_post_comment: Optional[bool],
        stats_views_today: Optional[int],
        stats_downloads_today: Optional[int],
        stats_downloads: Optional[int],
        stats_views: Optional[int],
        stats_favourites: Optional[int],
        stats_comments: Optional[int],
    ) -> int:
        return DeviationMetadataRepository(self.conn).save_metadata(
            deviationid=deviationid,
            title=title,
            description=description,
            license=license,
            allows_comments=allows_comments,
            tags=tags,
            is_favourited=is_favourited,
            is_watching=is_watching,
            is_mature=is_mature,
            mature_level=mature_level,
            mature_classification=mature_classification,
            printid=printid,
            author=author,
            creation_time=creation_time,
            category=category,
            file_size=file_size,
            resolution=resolution,
            submitted_with=submitted_with,
            stats_json=stats_json,
            camera=camera,
            collections=collections,
            galleries=galleries,
            can_post_comment=can_post_comment,
            stats_views_today=stats_views_today,
            stats_downloads_today=stats_downloads_today,
            stats_downloads=stats_downloads,
            stats_views=stats_views,
            stats_favourites=stats_favourites,
            stats_comments=stats_comments,
        )

    def get_all_stats_with_previous(self) -> list[dict]:
        return DeviationStatsRepository(self.conn).get_all_stats_with_previous()

    def get_snapshots_for_deviation(self, deviationid: str, limit: int = 30) -> list[dict]:
        return StatsSnapshotRepository(self.conn).get_snapshots_for_deviation(
            deviationid=deviationid,
            limit=limit,
        )

    def get_latest_user_stats_snapshot(self, username: str) -> Optional[dict]:
        return UserStatsSnapshotRepository(self.conn).get_latest_user_stats_snapshot(username)

    def get_user_stats_history(self, username: str, limit: int = 30) -> list[dict]:
        return UserStatsSnapshotRepository(self.conn).get_user_stats_history(
            username=username,
            limit=limit,
        )