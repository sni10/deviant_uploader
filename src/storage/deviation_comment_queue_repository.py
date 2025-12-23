"""Repository for deviation comment queue using SQLAlchemy Core."""

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .base_repository import BaseRepository
from .deviation_comment_tables import deviation_comment_queue
from ..domain.models import (
    DeviationCommentQueueItem,
    DeviationCommentQueueStatus,
)


class DeviationCommentQueueRepository(BaseRepository):
    """Provides persistence for deviation comment queue."""

    def _execute_core(self, statement):
        """Execute SQLAlchemy Core statement and return result.

        Handles both SQLAlchemy connections and raw SQLite connections.
        """
        if hasattr(self.conn, "execute"):
            try:
                return self.conn.execute(statement)
            except TypeError:
                pass

        compiled = statement.compile(compile_kwargs={"literal_binds": True})
        return self.conn.execute(str(compiled))

    def _scalar(self, statement) -> int | str | None:
        """Execute statement and return first column of the first row."""
        result = self._execute_core(statement)

        if hasattr(result, "scalar"):
            return result.scalar()

        row = result.fetchone()
        if row is None:
            return None
        return row[0]

    def add_deviation(
        self,
        deviationid: str,
        ts: int,
        source: str,
        title: str | None = None,
        author_username: str | None = None,
        author_userid: str | None = None,
        deviation_url: str | None = None,
    ) -> None:
        """Add deviation to queue (or update timestamp if exists).

        Args:
            deviationid: DeviantArt deviation UUID.
            ts: Unix timestamp from feed event.
            source: Source identifier (watch_feed/global_feed).
            title: Deviation title (optional).
            author_username: DeviantArt author username (optional).
            author_userid: DeviantArt author user ID (optional).
            deviation_url: DeviantArt deviation URL (optional).
        """
        insert_stmt = pg_insert(deviation_comment_queue).values(
            deviationid=deviationid,
            deviation_url=deviation_url,
            title=title,
            author_username=author_username,
            author_userid=author_userid,
            source=source,
            ts=ts,
            status=DeviationCommentQueueStatus.PENDING.value,
        )

        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[deviation_comment_queue.c.deviationid],
            set_={
                "ts": func.greatest(
                    deviation_comment_queue.c.ts, insert_stmt.excluded.ts
                ),
                "deviation_url": func.coalesce(
                    insert_stmt.excluded.deviation_url,
                    deviation_comment_queue.c.deviation_url,
                ),
                "title": func.coalesce(
                    insert_stmt.excluded.title, deviation_comment_queue.c.title
                ),
                "author_username": func.coalesce(
                    insert_stmt.excluded.author_username,
                    deviation_comment_queue.c.author_username,
                ),
                "author_userid": func.coalesce(
                    insert_stmt.excluded.author_userid,
                    deviation_comment_queue.c.author_userid,
                ),
                "updated_at": func.current_timestamp(),
            },
        )

        self._execute_core(stmt)
        self.conn.commit()

    def get_one_pending(self) -> dict[str, object] | None:
        """Get one pending deviation (newest by timestamp).

        Returns:
            Dictionary with deviation fields, or None if queue is empty.
        """
        stmt = (
            select(
                deviation_comment_queue.c.deviationid,
                deviation_comment_queue.c.deviation_url,
                deviation_comment_queue.c.title,
                deviation_comment_queue.c.author_username,
                deviation_comment_queue.c.author_userid,
                deviation_comment_queue.c.source,
                deviation_comment_queue.c.ts,
                deviation_comment_queue.c.status,
                deviation_comment_queue.c.attempts,
                deviation_comment_queue.c.last_error,
                deviation_comment_queue.c.created_at,
                deviation_comment_queue.c.updated_at,
            )
            .where(
                deviation_comment_queue.c.status
                == DeviationCommentQueueStatus.PENDING.value
            )
            .order_by(deviation_comment_queue.c.ts.desc())
            .limit(1)
        )

        result = self._execute_core(stmt)
        row = result.fetchone()
        if row is None:
            return None

        return {
            "deviationid": row[0],
            "deviation_url": row[1],
            "title": row[2],
            "author_username": row[3],
            "author_userid": row[4],
            "source": row[5],
            "ts": row[6],
            "status": row[7],
            "attempts": row[8],
            "last_error": row[9],
            "created_at": row[10],
            "updated_at": row[11],
        }

    def get_pending(self, limit: int = 100) -> list[DeviationCommentQueueItem]:
        """Get pending queue entries ordered by timestamp.

        Args:
            limit: Max results to return.

        Returns:
            List of DeviationCommentQueueItem objects.
        """
        return self.get_queue(
            status=DeviationCommentQueueStatus.PENDING,
            limit=limit,
        )

    def get_queue(
        self,
        status: DeviationCommentQueueStatus | None = None,
        limit: int = 100,
    ) -> list[DeviationCommentQueueItem]:
        """Get queue entries by status ordered by timestamp.

        Args:
            status: Optional status filter.
            limit: Max results to return.

        Returns:
            List of DeviationCommentQueueItem objects.
        """
        stmt = select(
            deviation_comment_queue.c.deviationid,
            deviation_comment_queue.c.deviation_url,
            deviation_comment_queue.c.title,
            deviation_comment_queue.c.author_username,
            deviation_comment_queue.c.author_userid,
            deviation_comment_queue.c.source,
            deviation_comment_queue.c.ts,
            deviation_comment_queue.c.status,
            deviation_comment_queue.c.attempts,
            deviation_comment_queue.c.last_error,
            deviation_comment_queue.c.created_at,
            deviation_comment_queue.c.updated_at,
        ).order_by(deviation_comment_queue.c.ts.desc())

        if status is not None:
            stmt = stmt.where(deviation_comment_queue.c.status == status.value)

        stmt = stmt.limit(limit)

        result = self._execute_core(stmt)
        rows = result.fetchall()

        return [
            DeviationCommentQueueItem(
                deviationid=row[0],
                deviation_url=row[1],
                title=row[2],
                author_username=row[3],
                author_userid=row[4],
                source=row[5],
                ts=row[6],
                status=DeviationCommentQueueStatus(row[7]),
                attempts=row[8],
                last_error=row[9],
                created_at=row[10],
                updated_at=row[11],
            )
            for row in rows
        ]

    def mark_commented(self, deviationid: str) -> None:
        """Mark deviation as successfully commented.

        Args:
            deviationid: DeviantArt deviation UUID.
        """
        stmt = (
            update(deviation_comment_queue)
            .where(deviation_comment_queue.c.deviationid == deviationid)
            .values(
                status=DeviationCommentQueueStatus.COMMENTED.value,
                last_error=None,
                updated_at=func.current_timestamp(),
            )
        )
        self._execute_core(stmt)
        self.conn.commit()

    def mark_failed(self, deviationid: str, error: str) -> None:
        """Mark deviation as permanently failed.

        Args:
            deviationid: DeviantArt deviation UUID.
            error: Error message.
        """
        stmt = (
            update(deviation_comment_queue)
            .where(deviation_comment_queue.c.deviationid == deviationid)
            .values(
                status=DeviationCommentQueueStatus.FAILED.value,
                attempts=deviation_comment_queue.c.attempts + 1,
                last_error=error[:500],
                updated_at=func.current_timestamp(),
            )
        )
        self._execute_core(stmt)
        self.conn.commit()

    def bump_attempt(self, deviationid: str, error: str) -> None:
        """Increment attempt counter (keeps status as pending).

        Args:
            deviationid: DeviantArt deviation UUID.
            error: Error message.
        """
        stmt = (
            update(deviation_comment_queue)
            .where(deviation_comment_queue.c.deviationid == deviationid)
            .values(
                attempts=deviation_comment_queue.c.attempts + 1,
                last_error=error[:500],
                updated_at=func.current_timestamp(),
            )
        )
        self._execute_core(stmt)
        self.conn.commit()

    def reset_failed_to_pending(self) -> int:
        """Reset all failed deviations back to pending status.

        Returns:
            Number of reset rows.
        """
        stmt = (
            update(deviation_comment_queue)
            .where(
                deviation_comment_queue.c.status
                == DeviationCommentQueueStatus.FAILED.value
            )
            .values(
                status=DeviationCommentQueueStatus.PENDING.value,
                attempts=0,
                last_error=None,
                updated_at=func.current_timestamp(),
            )
        )
        result = self._execute_core(stmt)
        self.conn.commit()

        if hasattr(result, "rowcount"):
            return result.rowcount
        return 0

    def clear_queue(self, status: DeviationCommentQueueStatus | None = None) -> int:
        """Clear queue (optionally by status).

        Args:
            status: If specified, only delete deviations with this status.

        Returns:
            Number of deleted rows.
        """
        if status:
            stmt = delete(deviation_comment_queue).where(
                deviation_comment_queue.c.status == status.value
            )
        else:
            stmt = delete(deviation_comment_queue)

        result = self._execute_core(stmt)
        self.conn.commit()

        if hasattr(result, "rowcount"):
            return result.rowcount
        return 0

    def remove_by_ids(self, deviationids: list[str]) -> int:
        """Remove queue entries by deviation IDs.

        Args:
            deviationids: List of deviation IDs to remove.

        Returns:
            Number of deleted rows.
        """
        if not deviationids:
            return 0

        stmt = delete(deviation_comment_queue).where(
            deviation_comment_queue.c.deviationid.in_(deviationids)
        )
        result = self._execute_core(stmt)
        self.conn.commit()

        if hasattr(result, "rowcount"):
            return result.rowcount
        return 0

    def get_stats(self) -> dict[str, int]:
        """Get queue statistics.

        Returns:
            Dictionary with counts: {pending, commented, failed, total}.
        """
        stmt_pending = select(func.count()).select_from(
            deviation_comment_queue
        ).where(
            deviation_comment_queue.c.status
            == DeviationCommentQueueStatus.PENDING.value
        )
        stmt_commented = select(func.count()).select_from(
            deviation_comment_queue
        ).where(
            deviation_comment_queue.c.status
            == DeviationCommentQueueStatus.COMMENTED.value
        )
        stmt_failed = select(func.count()).select_from(
            deviation_comment_queue
        ).where(
            deviation_comment_queue.c.status
            == DeviationCommentQueueStatus.FAILED.value
        )
        stmt_total = select(func.count()).select_from(deviation_comment_queue)

        pending = self._scalar(stmt_pending) or 0
        commented = self._scalar(stmt_commented) or 0
        failed = self._scalar(stmt_failed) or 0
        total = self._scalar(stmt_total) or 0

        return {
            "pending": pending,
            "commented": commented,
            "failed": failed,
            "total": total,
        }

    def get_recent_commented(self, limit: int = 50) -> list[DeviationCommentQueueItem]:
        """Get recently commented queue entries.

        Args:
            limit: Max results to return.

        Returns:
            List of DeviationCommentQueueItem objects.
        """
        return self.get_queue(
            status=DeviationCommentQueueStatus.COMMENTED,
            limit=limit,
        )
