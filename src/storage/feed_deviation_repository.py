"""Repository for feed deviations queue and state management using SQLAlchemy Core."""

from sqlalchemy import select, insert, update, delete, func
from .base_repository import BaseRepository
from .feed_tables import feed_state, feed_deviations


class FeedDeviationRepository(BaseRepository):
    """Provides persistence for feed deviations queue and cursor state.

    This repository manages two tables using SQLAlchemy Core:
    - feed_state: Stores cursor and other state for feed collection
    - feed_deviations: Queue of deviations from feed for auto-faving
    """

    def _execute_core(self, statement):
        """Execute SQLAlchemy Core statement and return result.

        Handles both SQLAlchemy connections and raw SQLite connections.
        """
        # Preferred path: use connection wrapper `.execute()`.
        # This keeps thread-safety guarantees (lock) and schema/search_path setup.
        if hasattr(self.conn, "execute"):
            try:
                return self.conn.execute(statement)
            except TypeError:
                # Fallback for legacy adapters that expect SQL string
                pass

        # Legacy fallback (kept only for backward compatibility)
        compiled = statement.compile(compile_kwargs={"literal_binds": True})
        return self.conn.execute(str(compiled))

    def _scalar(self, statement) -> int | str | None:
        """Execute statement and return first column of the first row.

        This method provides compatibility between SQLAlchemy Result objects
        and sqlite3.Cursor objects.
        """
        result = self._execute_core(statement)

        # SQLAlchemy Result
        if hasattr(result, "scalar"):
            return result.scalar()

        # sqlite3.Cursor
        row = result.fetchone()
        if row is None:
            return None
        return row[0]

    # ========== State Management ==========

    def get_state(self, key: str) -> str | None:
        """Get state value by key.

        Args:
            key: State key (e.g., 'feed_offset')

        Returns:
            State value or None if not found
        """
        stmt = select(feed_state.c.value).where(feed_state.c.key == key)
        result = self._execute_core(stmt)
        row = result.fetchone()
        return row[0] if row else None

    def set_state(self, key: str, value: str) -> None:
        """Set state value by key (upsert).

        Args:
            key: State key
            value: State value
        """
        # Check if exists
        existing = self.get_state(key)

        if existing is not None:
            # Update
            stmt = (
                update(feed_state)
                .where(feed_state.c.key == key)
                .values(value=value, updated_at=func.current_timestamp())
            )
        else:
            # Insert
            stmt = insert(feed_state).values(key=key, value=value)

        self._execute_core(stmt)
        self.conn.commit()

    # ========== Deviation Queue Management ==========

    def add_deviation(
        self, deviationid: str, ts: int, status: str = "pending"
    ) -> None:
        """Add deviation to queue (or update timestamp if exists).

        Args:
            deviationid: DeviantArt deviation UUID
            ts: Unix timestamp from feed event
            status: Status (pending/faved/failed), defaults to 'pending'
        """
        # Try to get existing
        stmt = select(feed_deviations.c.ts).where(
            feed_deviations.c.deviationid == deviationid
        )
        result = self._execute_core(stmt)
        existing_row = result.fetchone()

        if existing_row is not None:
            # Update: use max of current and new timestamp
            existing_ts = existing_row[0]
            new_ts = max(existing_ts, ts)
            stmt = (
                update(feed_deviations)
                .where(feed_deviations.c.deviationid == deviationid)
                .values(ts=new_ts, updated_at=func.current_timestamp())
            )
        else:
            # Insert new
            stmt = insert(feed_deviations).values(
                deviationid=deviationid, ts=ts, status=status
            )

        self._execute_core(stmt)
        self.conn.commit()

    def get_one_pending(self) -> dict | None:
        """Get one pending deviation (newest by timestamp).

        Returns:
            Dictionary with deviation fields, or None if queue is empty
        """
        stmt = (
            select(
                feed_deviations.c.deviationid,
                feed_deviations.c.ts,
                feed_deviations.c.status,
                feed_deviations.c.attempts,
                feed_deviations.c.last_error,
                feed_deviations.c.updated_at,
            )
            .where(feed_deviations.c.status == "pending")
            .order_by(feed_deviations.c.ts.desc())
            .limit(1)
        )
        result = self._execute_core(stmt)
        row = result.fetchone()
        if row is None:
            return None

        return {
            "deviationid": row[0],
            "ts": row[1],
            "status": row[2],
            "attempts": row[3],
            "last_error": row[4],
            "updated_at": row[5],
        }

    def mark_faved(self, deviationid: str) -> None:
        """Mark deviation as successfully faved.

        Args:
            deviationid: DeviantArt deviation UUID
        """
        stmt = (
            update(feed_deviations)
            .where(feed_deviations.c.deviationid == deviationid)
            .values(
                status="faved",
                last_error=None,
                updated_at=func.current_timestamp(),
            )
        )
        self._execute_core(stmt)
        self.conn.commit()

    def mark_failed(self, deviationid: str, error: str) -> None:
        """Mark deviation as permanently failed.

        Args:
            deviationid: DeviantArt deviation UUID
            error: Error message
        """
        stmt = (
            update(feed_deviations)
            .where(feed_deviations.c.deviationid == deviationid)
            .values(
                status="failed",
                attempts=feed_deviations.c.attempts + 1,
                last_error=error[:500],
                updated_at=func.current_timestamp(),
            )
        )
        self._execute_core(stmt)
        self.conn.commit()

    def bump_attempt(self, deviationid: str, error: str) -> None:
        """Increment attempt counter (keeps status as pending).

        Args:
            deviationid: DeviantArt deviation UUID
            error: Error message
        """
        stmt = (
            update(feed_deviations)
            .where(feed_deviations.c.deviationid == deviationid)
            .values(
                attempts=feed_deviations.c.attempts + 1,
                last_error=error[:500],
                updated_at=func.current_timestamp(),
            )
        )
        self._execute_core(stmt)
        self.conn.commit()

    def get_stats(self) -> dict:
        """Get queue statistics.

        Returns:
            Dictionary with counts: {pending, faved, failed, total}
        """
        # Separate queries for SQLite compatibility (no FILTER support in older versions)
        stmt_pending = select(func.count()).select_from(feed_deviations).where(
            feed_deviations.c.status == "pending"
        )
        stmt_faved = select(func.count()).select_from(feed_deviations).where(
            feed_deviations.c.status == "faved"
        )
        stmt_failed = select(func.count()).select_from(feed_deviations).where(
            feed_deviations.c.status == "failed"
        )
        stmt_total = select(func.count()).select_from(feed_deviations)

        pending = self._scalar(stmt_pending) or 0
        faved = self._scalar(stmt_faved) or 0
        failed = self._scalar(stmt_failed) or 0
        total = self._scalar(stmt_total) or 0

        return {
            "pending": pending,
            "faved": faved,
            "failed": failed,
            "total": total,
        }

    def clear_queue(self, status: str | None = None) -> int:
        """Clear queue (optionally by status).

        Args:
            status: If specified, only delete deviations with this status

        Returns:
            Number of deleted rows
        """
        if status:
            stmt = delete(feed_deviations).where(feed_deviations.c.status == status)
        else:
            stmt = delete(feed_deviations)

        result = self._execute_core(stmt)
        self.conn.commit()

        # Get rowcount
        if hasattr(result, 'rowcount'):
            return result.rowcount
        return 0

    def delete_deviation(self, deviationid: str) -> int:
        """Delete a deviation from the queue.

        This is used for permanent, non-retryable API errors (e.g., invalid
        deviation that can never be favourited).

        Args:
            deviationid: DeviantArt deviation UUID.

        Returns:
            Number of deleted rows.
        """
        stmt = delete(feed_deviations).where(feed_deviations.c.deviationid == deviationid)
        result = self._execute_core(stmt)
        self.conn.commit()

        if hasattr(result, "rowcount"):
            return result.rowcount
        return 0

    def reset_failed_to_pending(self) -> int:
        """Reset all failed deviations back to pending status.

        Returns:
            Number of reset rows
        """
        stmt = (
            update(feed_deviations)
            .where(feed_deviations.c.status == "failed")
            .values(
                status="pending",
                attempts=0,
                last_error=None,
                updated_at=func.current_timestamp(),
            )
        )
        result = self._execute_core(stmt)
        self.conn.commit()

        # Get rowcount
        if hasattr(result, 'rowcount'):
            return result.rowcount
        return 0
