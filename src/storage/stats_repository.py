"""Repository for deviation statistics, snapshots, and extended metadata."""
from datetime import date, timedelta
import json
from typing import Optional

from .base_repository import BaseRepository


class StatsRepository(BaseRepository):
    """Provides persistence for deviation stats, metadata, and daily snapshots.

    Besides per-deviation statistics, this repository also stores daily user
    watcher snapshots in the ``user_stats_snapshots`` table. These are used to
    track how the number of watchers (and friends) evolves over time.
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
        """Upsert current deviation stats."""

        cursor = self.conn.execute(
            """
            INSERT INTO deviation_stats (
                deviationid, title, thumb_url, is_mature, views, favourites, comments, gallery_folderid, url, updated_at
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

    def save_snapshot(
        self,
        deviationid: str,
        snapshot_date: str,
        views: int,
        favourites: int,
        comments: int,
    ) -> int:
        """Upsert a daily snapshot (by deviationid + date)."""

        cursor = self.conn.execute(
            """
            INSERT INTO stats_snapshots (
                deviationid, snapshot_date, views, favourites, comments, updated_at
            ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(deviationid, snapshot_date) DO UPDATE SET
                views=excluded.views,
                favourites=excluded.favourites,
                comments=excluded.comments,
                updated_at=CURRENT_TIMESTAMP
            """,
            (deviationid, snapshot_date, views, favourites, comments),
        )
        self.conn.commit()
        return cursor.lastrowid

    # ------------------------------------------------------------------
    # User watcher snapshots
    # ------------------------------------------------------------------

    def save_user_stats_snapshot(
        self,
        *,
        user_id: Optional[int],
        username: str,
        snapshot_date: str,
        watchers: int,
        friends: int,
    ) -> int:
        """Upsert a daily watcher snapshot for a user.

        Snapshots are uniquely identified by ``(username, snapshot_date)`` so
        re-running the sync on the same day will just update the existing row.
        """

        cursor = self.conn.execute(
            """
            INSERT INTO user_stats_snapshots (
                user_id,
                username,
                snapshot_date,
                watchers,
                friends,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(username, snapshot_date) DO UPDATE SET
                user_id = excluded.user_id,
                watchers = excluded.watchers,
                friends = excluded.friends,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, username, snapshot_date, watchers, friends),
        )
        self.conn.commit()
        return cursor.lastrowid

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
        """Upsert the extended metadata for a deviation."""

        def dumps(value: object) -> Optional[str]:
            if value is None:
                return None
            return json.dumps(value, ensure_ascii=False)

        cursor = self.conn.execute(
            """
            INSERT INTO deviation_metadata (
                deviationid, title, description, license, allows_comments, tags, is_favourited, is_watching,
                is_mature, mature_level, mature_classification, printid, author, creation_time, category,
                file_size, resolution, submitted_with, stats_json, camera, collections, galleries, can_post_comment,
                stats_views_today, stats_downloads_today, stats_downloads, stats_views, stats_favourites, stats_comments,
                created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT(deviationid) DO UPDATE SET
                title=excluded.title,
                description=excluded.description,
                license=excluded.license,
                allows_comments=excluded.allows_comments,
                tags=excluded.tags,
                is_favourited=excluded.is_favourited,
                is_watching=excluded.is_watching,
                is_mature=excluded.is_mature,
                mature_level=excluded.mature_level,
                mature_classification=excluded.mature_classification,
                printid=excluded.printid,
                author=excluded.author,
                creation_time=excluded.creation_time,
                category=excluded.category,
                file_size=excluded.file_size,
                resolution=excluded.resolution,
                submitted_with=excluded.submitted_with,
                stats_json=excluded.stats_json,
                camera=excluded.camera,
                collections=excluded.collections,
                galleries=excluded.galleries,
                can_post_comment=excluded.can_post_comment,
                stats_views_today=excluded.stats_views_today,
                stats_downloads_today=excluded.stats_downloads_today,
                stats_downloads=excluded.stats_downloads,
                stats_views=excluded.stats_views,
                stats_favourites=excluded.stats_favourites,
                stats_comments=excluded.stats_comments,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                deviationid,
                title,
                description,
                license,
                1 if allows_comments else 0 if allows_comments is not None else None,
                dumps(tags),
                1 if is_favourited else 0 if is_favourited is not None else None,
                1 if is_watching else 0 if is_watching is not None else None,
                1 if is_mature else 0 if is_mature is not None else None,
                mature_level,
                dumps(mature_classification),
                printid,
                dumps(author),
                creation_time,
                category,
                file_size,
                resolution,
                dumps(submitted_with),
                dumps(stats_json),
                dumps(camera),
                dumps(collections),
                dumps(galleries),
                1 if can_post_comment else 0 if can_post_comment is not None else None,
                stats_views_today,
                stats_downloads_today,
                stats_downloads,
                stats_views,
                stats_favourites,
                stats_comments,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_all_stats_with_previous(self) -> list[dict]:
        """Return all current stats plus yesterday snapshot and metadata for diffs."""

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

    def get_snapshots_for_deviation(self, deviationid: str, limit: int = 30) -> list[dict]:
        """Return snapshot history for deviation (latest first)."""

        cursor = self.conn.execute(
            """
            SELECT *
            FROM stats_snapshots
            WHERE deviationid = ?
            ORDER BY snapshot_date DESC
            LIMIT ?
            """,
            (deviationid, limit),
        )
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # User watcher snapshot queries
    # ------------------------------------------------------------------

    def get_latest_user_stats_snapshot(self, username: str) -> Optional[dict]:
        """Return latest watcher snapshot for a given user or ``None``.

        The result includes ``profile_url`` joined from the ``users`` table
        when available, so the UI can easily render a link to the DeviantArt
        profile. Also includes yesterday's watchers count to calculate the daily
        diff (watchers_diff).
        """

        cursor = self.conn.execute(
            """
            SELECT
                s.username,
                s.snapshot_date,
                s.watchers,
                s.friends,
                s.created_at,
                s.updated_at,
                u.profile_url,
                y.watchers AS yesterday_watchers
            FROM user_stats_snapshots AS s
            LEFT JOIN users AS u ON u.username = s.username
            LEFT JOIN user_stats_snapshots AS y
                ON y.username = s.username
                AND y.snapshot_date = date(s.snapshot_date, '-1 day')
            WHERE s.username = ?
            ORDER BY s.snapshot_date DESC, s.id DESC
            LIMIT 1
            """,
            (username,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        columns = [desc[0] for desc in cursor.description]
        result = dict(zip(columns, row))
        
        # Calculate watchers_diff (today - yesterday)
        watchers = result.get("watchers") or 0
        yesterday_watchers = result.get("yesterday_watchers") or 0
        result["watchers_diff"] = watchers - yesterday_watchers
        
        return result

    def get_user_stats_history(self, username: str, limit: int = 30) -> list[dict]:
        """Return watcher snapshot history for a user (latest first)."""

        cursor = self.conn.execute(
            """
            SELECT
                username,
                snapshot_date,
                watchers,
                friends,
                created_at,
                updated_at
            FROM user_stats_snapshots
            WHERE username = ?
            ORDER BY snapshot_date DESC, id DESC
            LIMIT ?
            """,
            (username, limit),
        )
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]