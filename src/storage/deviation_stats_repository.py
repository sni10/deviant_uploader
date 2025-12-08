"""Repository for current deviation statistics."""
from datetime import date, timedelta
import json
from typing import Optional

from .base_repository import BaseRepository


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
        cursor = self.conn.execute(
            """
            INSERT INTO deviation_stats (
                deviationid, title, thumb_url, is_mature, views, favourites, 
                comments, gallery_folderid, url, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(deviationid) DO UPDATE SET
                title=excluded.title,
                thumb_url=excluded.thumb_url,
                is_mature=excluded.is_mature,
                views=excluded.views,
                favourites=excluded.favourites,
                comments=excluded.comments,
                gallery_folderid=excluded.gallery_folderid,
                url=excluded.url,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                deviationid,
                title,
                thumb_url,
                1 if is_mature else 0,
                views,
                favourites,
                comments,
                gallery_folderid,
                url,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_deviation_stats(self, deviationid: str) -> Optional[dict]:
        """Retrieve deviation stats by deviation ID.
        
        Args:
            deviationid: DeviantArt deviation UUID
            
        Returns:
            Dictionary with stats fields or None if not found
        """
        cursor = self.conn.execute(
            """
            SELECT 
                id, deviationid, title, thumb_url, is_mature, views, 
                favourites, comments, gallery_folderid, url, 
                created_at, updated_at
            FROM deviation_stats
            WHERE deviationid = ?
            """,
            (deviationid,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))

    def get_all_deviation_stats(self) -> list[dict]:
        """Retrieve all deviation stats ordered by views descending.
        
        Returns:
            List of dictionaries with stats fields
        """
        cursor = self.conn.execute(
            """
            SELECT 
                id, deviationid, title, thumb_url, is_mature, views, 
                favourites, comments, gallery_folderid, url, 
                created_at, updated_at
            FROM deviation_stats
            ORDER BY views DESC
            """
        )
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_all_stats_with_previous(self) -> list[dict]:
        """Return all current stats plus yesterday snapshot and metadata for diffs.
        
        This method joins deviation_stats, stats_snapshots, and deviation_metadata
        to provide a complete view for the stats dashboard with daily deltas.
        
        Returns:
            List of dictionaries with stats, yesterday's values, and metadata
        """
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        cursor = self.conn.execute(
            """
            SELECT
                ds.deviationid,
                ds.title,
                ds.thumb_url,
                ds.is_mature,
                ds.views,
                ds.favourites,
                ds.comments,
                ds.gallery_folderid,
                ds.url,
                ds.updated_at,
                COALESCE(ss.views, 0) AS yesterday_views,
                COALESCE(ss.favourites, 0) AS yesterday_favourites,
                COALESCE(ss.comments, 0) AS yesterday_comments,
                dm.description,
                dm.license,
                dm.allows_comments,
                dm.tags,
                dm.is_favourited,
                dm.is_watching,
                dm.mature_level,
                dm.mature_classification,
                dm.printid,
                dm.author,
                dm.creation_time,
                dm.category,
                dm.file_size,
                dm.resolution,
                dm.submitted_with,
                dm.stats_json,
                dm.camera,
                dm.collections,
                dm.galleries,
                dm.can_post_comment,
                dm.stats_views_today,
                dm.stats_downloads_today,
                dm.stats_downloads,
                dm.stats_views,
                dm.stats_favourites,
                dm.stats_comments
            FROM deviation_stats ds
            LEFT JOIN stats_snapshots ss
                ON ss.deviationid = ds.deviationid
                AND ss.snapshot_date = ?
            LEFT JOIN deviation_metadata dm
                ON dm.deviationid = ds.deviationid
            ORDER BY ds.views DESC
            """,
            (yesterday,),
        )

        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

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
