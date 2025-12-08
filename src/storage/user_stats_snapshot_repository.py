"""Repository for user watcher statistics snapshots."""
from typing import Optional

from .base_repository import BaseRepository


class UserStatsSnapshotRepository(BaseRepository):
    """Provides persistence for user watcher statistics snapshots.
    
    This repository handles the `user_stats_snapshots` table which stores
    daily snapshots of user watchers and friends counts to track evolution over time.
    """

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
        
        Args:
            user_id: Internal DB user ID (can be None if user not yet in DB)
            username: DeviantArt username
            snapshot_date: Snapshot date in YYYY-MM-DD format
            watchers: Watcher count on this date
            friends: Friend count on this date
            
        Returns:
            Row ID of inserted/updated record
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

    def get_latest_user_stats_snapshot(self, username: str) -> Optional[dict]:
        """Return latest watcher snapshot for a given user or ``None``.
        
        The result includes ``profile_url`` joined from the ``users`` table
        when available, so the UI can easily render a link to the DeviantArt
        profile. Also includes yesterday's watchers count to calculate the daily
        diff (watchers_diff).
        
        Args:
            username: DeviantArt username
            
        Returns:
            Dictionary with snapshot fields and watchers_diff, or None if not found
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

    def get_user_stats_history(
        self, username: str, limit: int = 30
    ) -> list[dict]:
        """Return watcher snapshot history for a user (latest first).
        
        Args:
            username: DeviantArt username
            limit: Maximum number of snapshots to return (default: 30)
            
        Returns:
            List of dictionaries with snapshot fields, ordered by date descending
        """
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
