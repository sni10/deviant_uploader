"""Repository for current deviation statistics."""

from datetime import date, timedelta
import json
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .base_repository import BaseRepository
from .models import DeviationMetadata, DeviationStats, StatsSnapshot


class DeviationStatsRepository(BaseRepository):
    """Provides persistence for current deviation statistics.
    
    This repository handles the `deviation_stats` table which stores
    the most recent metrics (views, favourites, comments) for each deviation.
    """

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
        """Upsert current deviation stats.
        
        Args:
            deviationid: DeviantArt deviation UUID
            title: Deviation title
            views: View count
            favourites: Favourite count
            comments: Comment count
            thumb_url: Thumbnail URL
            gallery_folderid: DeviantArt gallery folder UUID
            is_mature: Mature content flag
            url: Public deviation URL
            
        Returns:
            Row ID of inserted/updated record
        """
        table = DeviationStats.__table__

        values = {
            "deviationid": deviationid,
            "title": title,
            "thumb_url": thumb_url,
            "is_mature": 1 if is_mature else 0,
            "views": views,
            "favourites": favourites,
            "comments": comments,
            "gallery_folderid": gallery_folderid,
            "url": url,
        }

        stmt = (
            pg_insert(table)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[table.c.deviationid],
                set_=values,
            )
            .returning(table.c.id)
        )

        row_id = self._execute(stmt).scalar_one()
        self.conn.commit()
        return int(row_id)

    def get_deviation_stats(self, deviationid: str) -> Optional[dict]:
        """Retrieve deviation stats by deviation ID.
        
        Args:
            deviationid: DeviantArt deviation UUID
            
        Returns:
            Dictionary with stats fields or None if not found
        """
        table = DeviationStats.__table__
        stmt = select(table).where(table.c.deviationid == deviationid)
        row = self._execute(stmt).mappings().first()
        return None if row is None else dict(row)

    def get_all_deviation_stats(self) -> list[dict]:
        """Retrieve all deviation stats ordered by views descending.
        
        Returns:
            List of dictionaries with stats fields
        """
        table = DeviationStats.__table__
        stmt = select(table).order_by(desc(table.c.views))
        return [dict(row) for row in self._execute(stmt).mappings().all()]

    def get_all_stats_with_previous(self) -> list[dict]:
        """Return all current stats plus yesterday snapshot and metadata for diffs.
        
        This method joins deviation_stats, stats_snapshots, and deviation_metadata
        to provide a complete view for the stats dashboard with daily deltas.
        
        Returns:
            List of dictionaries with stats, yesterday's values, and metadata
        """
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        ds = DeviationStats.__table__
        ss = StatsSnapshot.__table__
        dm = DeviationMetadata.__table__

        stmt = (
            select(
                ds.c.deviationid,
                ds.c.title,
                ds.c.thumb_url,
                ds.c.is_mature,
                ds.c.views,
                ds.c.favourites,
                ds.c.comments,
                ds.c.gallery_folderid,
                ds.c.url,
                ds.c.updated_at,
                func.coalesce(ss.c.views, 0).label("yesterday_views"),
                func.coalesce(ss.c.favourites, 0).label("yesterday_favourites"),
                func.coalesce(ss.c.comments, 0).label("yesterday_comments"),
                dm.c.description,
                dm.c.license,
                dm.c.allows_comments,
                dm.c.tags,
                dm.c.is_favourited,
                dm.c.is_watching,
                dm.c.mature_level,
                dm.c.mature_classification,
                dm.c.printid,
                dm.c.author,
                dm.c.creation_time,
                dm.c.category,
                dm.c.file_size,
                dm.c.resolution,
                dm.c.submitted_with,
                dm.c.stats_json,
                dm.c.camera,
                dm.c.collections,
                dm.c.galleries,
                dm.c.can_post_comment,
                dm.c.stats_views_today,
                dm.c.stats_downloads_today,
                dm.c.stats_downloads,
                dm.c.stats_views,
                dm.c.stats_favourites,
                dm.c.stats_comments,
            )
            .select_from(
                ds.outerjoin(
                    ss,
                    (ss.c.deviationid == ds.c.deviationid)
                    & (ss.c.snapshot_date == yesterday),
                ).outerjoin(dm, dm.c.deviationid == ds.c.deviationid)
            )
            .order_by(desc(ds.c.views))
        )

        rows = [dict(row) for row in self._execute(stmt).mappings().all()]

        def loads(value: Optional[str]):
            if value is None:
                return None
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None

        for row in rows:
            row["tags"] = loads(row.get("tags")) or []
            row["mature_classification"] = loads(row.get("mature_classification")) or []
            row["author"] = loads(row.get("author"))
            row["submitted_with"] = loads(row.get("submitted_with"))
            row["stats_json"] = loads(row.get("stats_json"))
            row["camera"] = loads(row.get("camera"))
            row["collections"] = loads(row.get("collections")) or []
            row["galleries"] = loads(row.get("galleries")) or []

        return rows
