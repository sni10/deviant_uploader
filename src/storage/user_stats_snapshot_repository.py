"""Repository for user watcher statistics snapshots."""

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .base_repository import BaseRepository
from .models import User, UserStatsSnapshot


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
        table = UserStatsSnapshot.__table__

        stmt = (
            pg_insert(table)
            .values(
                user_id=user_id,
                username=username,
                snapshot_date=snapshot_date,
                watchers=watchers,
                friends=friends,
            )
            .on_conflict_do_update(
                index_elements=[table.c.username, table.c.snapshot_date],
                set_={
                    "user_id": user_id,
                    "watchers": watchers,
                    "friends": friends,
                },
            )
            .returning(table.c.id)
        )

        row_id = self._execute(stmt).scalar_one()
        self.conn.commit()
        return int(row_id)

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
        snapshots = UserStatsSnapshot.__table__
        users = User.__table__

        latest_stmt = (
            select(
                snapshots.c.username,
                snapshots.c.snapshot_date,
                snapshots.c.watchers,
                snapshots.c.friends,
                snapshots.c.created_at,
                snapshots.c.updated_at,
                users.c.profile_url,
            )
            .select_from(snapshots.outerjoin(users, users.c.username == snapshots.c.username))
            .where(snapshots.c.username == username)
            .order_by(desc(snapshots.c.snapshot_date), desc(snapshots.c.id))
            .limit(1)
        )
        latest = self._execute(latest_stmt).mappings().first()
        if latest is None:
            return None

        result = dict(latest)

        yesterday_watchers = 0
        snapshot_date = result.get("snapshot_date")
        if snapshot_date:
            try:
                yesterday_date = (
                    date.fromisoformat(snapshot_date) - timedelta(days=1)
                ).isoformat()
            except ValueError:
                yesterday_date = None

            if yesterday_date:
                y_stmt = (
                    select(snapshots.c.watchers)
                    .where(
                        (snapshots.c.username == username)
                        & (snapshots.c.snapshot_date == yesterday_date)
                    )
                    .order_by(desc(snapshots.c.id))
                    .limit(1)
                )
                y_value = self._scalar(y_stmt)
                yesterday_watchers = int(y_value or 0)

        result["yesterday_watchers"] = yesterday_watchers
        watchers = int(result.get("watchers") or 0)
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
        table = UserStatsSnapshot.__table__
        stmt = (
            select(
                table.c.username,
                table.c.snapshot_date,
                table.c.watchers,
                table.c.friends,
                table.c.created_at,
                table.c.updated_at,
            )
            .where(table.c.username == username)
            .order_by(desc(table.c.snapshot_date), desc(table.c.id))
            .limit(limit)
        )

        return [dict(row) for row in self._execute(stmt).mappings().all()]
