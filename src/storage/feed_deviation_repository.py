"""Repository for feed deviations queue and state management."""

from .base_repository import BaseRepository


class FeedDeviationRepository(BaseRepository):
    """Provides persistence for feed deviations queue and cursor state.

    This repository manages two tables:
    - feed_state: Stores cursor and other state for feed collection
    - feed_deviations: Queue of deviations from feed for auto-faving
    """

    # ========== State Management ==========

    def get_state(self, key: str) -> str | None:
        """Get state value by key.

        Args:
            key: State key (e.g., 'feed_cursor')

        Returns:
            State value or None if not found
        """
        cursor = self.conn.execute(
            "SELECT value FROM feed_state WHERE key = ?",
            (key,),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def set_state(self, key: str, value: str) -> None:
        """Set state value by key (upsert).

        Args:
            key: State key
            value: State value
        """
        self.conn.execute(
            """
            INSERT INTO feed_state (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )
        self.conn.commit()

    # ========== Deviation Queue Management ==========

    def add_deviation(
        self, deviationid: str, ts: int, status: str = "pending"
    ) -> None:
        """Add deviation to queue (or update if exists).

        Args:
            deviationid: DeviantArt deviation UUID
            ts: Unix timestamp from feed event
            status: Status (pending/faved/failed), defaults to 'pending'
        """
        self.conn.execute(
            """
            INSERT INTO feed_deviations (deviationid, ts, status, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(deviationid) DO UPDATE SET
                ts = GREATEST(feed_deviations.ts, excluded.ts),
                updated_at = CURRENT_TIMESTAMP
            """,
            (deviationid, ts, status),
        )
        self.conn.commit()

    def get_one_pending(self) -> dict | None:
        """Get one pending deviation (newest by timestamp).

        Returns:
            Dictionary with deviation fields, or None if queue is empty
        """
        cursor = self.conn.execute(
            """
            SELECT deviationid, ts, status, attempts, last_error, updated_at
            FROM feed_deviations
            WHERE status = 'pending'
            ORDER BY ts DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))

    def mark_faved(self, deviationid: str) -> None:
        """Mark deviation as successfully faved.

        Args:
            deviationid: DeviantArt deviation UUID
        """
        self.conn.execute(
            """
            UPDATE feed_deviations
            SET status = 'faved', last_error = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE deviationid = ?
            """,
            (deviationid,),
        )
        self.conn.commit()

    def mark_failed(self, deviationid: str, error: str) -> None:
        """Mark deviation as permanently failed.

        Args:
            deviationid: DeviantArt deviation UUID
            error: Error message
        """
        self.conn.execute(
            """
            UPDATE feed_deviations
            SET status = 'failed',
                attempts = attempts + 1,
                last_error = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE deviationid = ?
            """,
            (error[:500], deviationid),
        )
        self.conn.commit()

    def bump_attempt(self, deviationid: str, error: str) -> None:
        """Increment attempt counter (keeps status as pending).

        Args:
            deviationid: DeviantArt deviation UUID
            error: Error message
        """
        self.conn.execute(
            """
            UPDATE feed_deviations
            SET attempts = attempts + 1,
                last_error = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE deviationid = ?
            """,
            (error[:500], deviationid),
        )
        self.conn.commit()

    def get_stats(self) -> dict:
        """Get queue statistics.

        Returns:
            Dictionary with counts: {pending, faved, failed, total}
        """
        cursor = self.conn.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'faved') as faved,
                COUNT(*) FILTER (WHERE status = 'failed') as failed,
                COUNT(*) as total
            FROM feed_deviations
            """
        )
        row = cursor.fetchone()
        if row:
            return {
                "pending": row[0] or 0,
                "faved": row[1] or 0,
                "failed": row[2] or 0,
                "total": row[3] or 0,
            }
        return {"pending": 0, "faved": 0, "failed": 0, "total": 0}

    def clear_queue(self, status: str | None = None) -> int:
        """Clear queue (optionally by status).

        Args:
            status: If specified, only delete deviations with this status

        Returns:
            Number of deleted rows
        """
        if status:
            cursor = self.conn.execute(
                "DELETE FROM feed_deviations WHERE status = ?", (status,)
            )
        else:
            cursor = self.conn.execute("DELETE FROM feed_deviations")
        self.conn.commit()
        return cursor.rowcount
