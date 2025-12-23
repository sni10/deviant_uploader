"""Repository for daily deviation statistics snapshots."""

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .base_repository import BaseRepository
from .models import StatsSnapshot


class StatsSnapshotRepository(BaseRepository):
    """Provides persistence for daily deviation statistics snapshots.

    This repository handles the `stats_snapshots` table which stores
    historical daily snapshots of deviation metrics (views, favourites, comments).

    IMPORTANT: Snapshots store DAILY DELTAS (increments), not cumulative values.
    To get cumulative stats, sum all snapshots up to the target date.
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

        IMPORTANT: This method expects DAILY DELTAS (increments), not cumulative values.
        For example, if total views went from 100 to 150, pass views=50 (the delta).

        Args:
            deviationid: DeviantArt deviation UUID
            snapshot_date: Snapshot date in YYYY-MM-DD format
            views: Daily view increment (delta) for this date
            favourites: Daily favourite increment (delta) for this date
            comments: Daily comment increment (delta) for this date

        Returns:
            Row ID of inserted/updated record
        """
        table = StatsSnapshot.__table__

        stmt = (
            pg_insert(table)
            .values(
                deviationid=deviationid,
                snapshot_date=snapshot_date,
                views=views,
                favourites=favourites,
                comments=comments,
            )
            .on_conflict_do_update(
                index_elements=[table.c.deviationid, table.c.snapshot_date],
                set_={
                    "views": views,
                    "favourites": favourites,
                    "comments": comments,
                },
            )
            .returning(table.c.id)
        )

        row_id = self._execute(stmt).scalar_one()
        self.conn.commit()
        return int(row_id)

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
        table = StatsSnapshot.__table__
        stmt = (
            select(
                table.c.id,
                table.c.deviationid,
                table.c.snapshot_date,
                table.c.views,
                table.c.favourites,
                table.c.comments,
                table.c.created_at,
                table.c.updated_at,
            )
            .where(table.c.deviationid == deviationid)
            .order_by(desc(table.c.snapshot_date))
            .limit(limit)
        )

        return [dict(row) for row in self._execute(stmt).mappings().all()]

    def get_latest_snapshot(self, deviationid: str) -> dict | None:
        """Get the most recent snapshot for a deviation.

        Args:
            deviationid: DeviantArt deviation UUID

        Returns:
            Dictionary with snapshot fields, or None if no snapshots exist
        """
        table = StatsSnapshot.__table__
        stmt = (
            select(
                table.c.id,
                table.c.deviationid,
                table.c.snapshot_date,
                table.c.views,
                table.c.favourites,
                table.c.comments,
                table.c.created_at,
                table.c.updated_at,
            )
            .where(table.c.deviationid == deviationid)
            .order_by(desc(table.c.snapshot_date))
            .limit(1)
        )
        return self._execute(stmt).mappings().first()
