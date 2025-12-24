"""Repository for deviation comment logs using SQLAlchemy Core."""

from sqlalchemy import func, insert, select

from .base_repository import BaseRepository
from .deviation_comment_tables import deviation_comment_logs
from ..domain.models import DeviationCommentLog, DeviationCommentLogStatus


class DeviationCommentLogRepository(BaseRepository):
    """Provides persistence for deviation comment logs."""

    def add_log(
        self,
        message_id: int,
        deviationid: str,
        status: DeviationCommentLogStatus,
        deviation_url: str | None = None,
        author_username: str | None = None,
        commentid: str | None = None,
        comment_text: str | None = None,
        error_message: str | None = None,
    ) -> int:
        """Add new log entry for a deviation comment.

        Args:
            message_id: Template message ID.
            deviationid: DeviantArt deviation UUID.
            status: Send status (sent/failed).
            deviation_url: DeviantArt deviation URL (optional).
            author_username: DeviantArt author username (optional).
            commentid: DeviantArt comment ID (if successful).
            comment_text: Rendered comment text (optional).
            error_message: Error message (if failed).

        Returns:
            log_id of created entry.
        """
        stmt = insert(deviation_comment_logs).values(
            message_id=message_id,
            deviationid=deviationid,
            deviation_url=deviation_url,
            author_username=author_username,
            commentid=commentid,
            comment_text=comment_text,
            status=status.value,
            error_message=error_message,
        )

        return self._insert_returning_id(
            stmt, returning_col=deviation_comment_logs.c.log_id
        )

    def get_logs(
        self,
        limit: int = 100,
        status: DeviationCommentLogStatus | None = None,
        offset: int = 0,
    ) -> list[DeviationCommentLog]:
        """Get logs with optional status filter.

        Args:
            limit: Max results to return.
            status: Optional status filter.
            offset: Offset for pagination.

        Returns:
            List of DeviationCommentLog objects.
        """
        stmt = select(
            deviation_comment_logs.c.log_id,
            deviation_comment_logs.c.message_id,
            deviation_comment_logs.c.deviationid,
            deviation_comment_logs.c.deviation_url,
            deviation_comment_logs.c.author_username,
            deviation_comment_logs.c.commentid,
            deviation_comment_logs.c.comment_text,
            deviation_comment_logs.c.status,
            deviation_comment_logs.c.error_message,
            deviation_comment_logs.c.sent_at,
        ).order_by(deviation_comment_logs.c.sent_at.desc())

        if status is not None:
            stmt = stmt.where(deviation_comment_logs.c.status == status.value)

        stmt = stmt.limit(limit).offset(offset)

        result = self._execute_core(stmt)
        rows = result.fetchall()

        return [
            DeviationCommentLog(
                log_id=row[0],
                message_id=row[1],
                deviationid=row[2],
                deviation_url=row[3],
                author_username=row[4],
                commentid=row[5],
                comment_text=row[6],
                status=DeviationCommentLogStatus(row[7]),
                error_message=row[8],
                sent_at=row[9],
            )
            for row in rows
        ]

    def get_commented_deviationids(self) -> set[str]:
        """Return deviation IDs that have been successfully commented.

        Returns:
            Set of deviation IDs.
        """
        stmt = select(deviation_comment_logs.c.deviationid).where(
            deviation_comment_logs.c.status == DeviationCommentLogStatus.SENT.value
        )

        result = self._execute_core(stmt)
        rows = result.fetchall()

        return {row[0] for row in rows if row[0]}

    def get_stats_by_template(self) -> dict[int, dict[str, int]]:
        """Get log statistics grouped by template ID.

        Returns:
            Dictionary keyed by message_id with sent/failed/total counts.
        """
        stmt = (
            select(
                deviation_comment_logs.c.message_id,
                deviation_comment_logs.c.status,
                func.count(),
            )
            .group_by(deviation_comment_logs.c.message_id, deviation_comment_logs.c.status)
        )

        result = self._execute_core(stmt)
        rows = result.fetchall()

        stats: dict[int, dict[str, int]] = {}
        for message_id, status, count in rows:
            entry = stats.setdefault(
                int(message_id),
                {"sent": 0, "failed": 0, "total": 0},
            )
            if status == DeviationCommentLogStatus.SENT.value:
                entry["sent"] = int(count)
            elif status == DeviationCommentLogStatus.FAILED.value:
                entry["failed"] = int(count)
            entry["total"] = entry["sent"] + entry["failed"]

        return stats
