"""Repository for daily deviation statistics snapshots."""

from .base_repository import BaseRepository


class StatsSnapshotRepository(BaseRepository):
    """Provides persistence for daily deviation statistics snapshots.
    
    This repository handles the `stats_snapshots` table which stores
    historical daily snapshots of deviation metrics (views, favourites, comments).
    """

    def save_snapshot(
        self,
        deviationid: str,
        snapshot_date: str,
        views: int,
        favourites: int,
        comments: int,
    ) -> int:
        """Upsert a daily snapshot (by deviationid + date).
        
        Args:
            deviationid: DeviantArt deviation UUID
            snapshot_date: Snapshot date in YYYY-MM-DD format
            views: View count on this date
            favourites: Favourite count on this date
            comments: Comment count on this date
            
        Returns:
            Row ID of inserted/updated record
        """
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

    def get_snapshots_for_deviation(
        self, deviationid: str, limit: int = 30
    ) -> list[dict]:
        """Return snapshot history for deviation (latest first).
        
        Args:
            deviationid: DeviantArt deviation UUID
            limit: Maximum number of snapshots to return (default: 30)
            
        Returns:
            List of dictionaries with snapshot fields, ordered by date descending
        """
        cursor = self.conn.execute(
            """
            SELECT 
                id, deviationid, snapshot_date, views, favourites, comments,
                created_at, updated_at
            FROM stats_snapshots
            WHERE deviationid = ?
            ORDER BY snapshot_date DESC
            LIMIT ?
            """,
            (deviationid, limit),
        )
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
