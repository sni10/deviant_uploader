"""Repository for profile message send logs using SQLAlchemy Core."""

from sqlalchemy import select, insert, delete, func
from .base_repository import BaseRepository
from .profile_message_tables import profile_message_logs
from ..domain.models import ProfileMessageLog, MessageLogStatus


class ProfileMessageLogRepository(BaseRepository):
    """Provides persistence for profile message send logs."""

    def add_log(
        self,
        message_id: int,
        recipient_username: str,
        recipient_userid: str,
        status: MessageLogStatus,
        commentid: str | None = None,
        error_message: str | None = None,
    ) -> int:
        """Add new log entry for sent message.

        Args:
            message_id: Template message ID
            recipient_username: Recipient's DeviantArt username
            recipient_userid: Recipient's DeviantArt user ID
            status: Send status (sent/failed)
            commentid: DeviantArt comment ID (if successful)
            error_message: Error message (if failed)

        Returns:
            log_id of created entry
        """
        stmt = insert(profile_message_logs).values(
            message_id=message_id,
            recipient_username=recipient_username,
            recipient_userid=recipient_userid,
            commentid=commentid,
            status=status.value,
            error_message=error_message,
        )

        return self._insert_returning_id(
            stmt, returning_col=profile_message_logs.c.log_id
        )

    def get_logs_by_message_id(
        self, message_id: int, limit: int = 100, offset: int = 0
    ) -> list[ProfileMessageLog]:
        """Get logs for specific message template.

        Args:
            message_id: Message template ID
            limit: Max results to return
            offset: Offset for pagination

        Returns:
            List of ProfileMessageLog objects
        """
        stmt = (
            select(
                profile_message_logs.c.log_id,
                profile_message_logs.c.message_id,
                profile_message_logs.c.recipient_username,
                profile_message_logs.c.recipient_userid,
                profile_message_logs.c.commentid,
                profile_message_logs.c.status,
                profile_message_logs.c.error_message,
                profile_message_logs.c.sent_at,
            )
            .where(profile_message_logs.c.message_id == message_id)
            .order_by(profile_message_logs.c.sent_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = self._execute_core(stmt)
        rows = result.fetchall()

        return [
            ProfileMessageLog(
                log_id=row[0],
                message_id=row[1],
                recipient_username=row[2],
                recipient_userid=row[3],
                commentid=row[4],
                status=MessageLogStatus(row[5]),
                error_message=row[6],
                sent_at=row[7],
            )
            for row in rows
        ]

    def get_all_logs(
        self, limit: int = 100, offset: int = 0
    ) -> list[ProfileMessageLog]:
        """Get all logs across all messages.

        Args:
            limit: Max results to return
            offset: Offset for pagination

        Returns:
            List of ProfileMessageLog objects
        """
        stmt = (
            select(
                profile_message_logs.c.log_id,
                profile_message_logs.c.message_id,
                profile_message_logs.c.recipient_username,
                profile_message_logs.c.recipient_userid,
                profile_message_logs.c.commentid,
                profile_message_logs.c.status,
                profile_message_logs.c.error_message,
                profile_message_logs.c.sent_at,
            )
            .order_by(profile_message_logs.c.sent_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = self._execute_core(stmt)
        rows = result.fetchall()

        return [
            ProfileMessageLog(
                log_id=row[0],
                message_id=row[1],
                recipient_username=row[2],
                recipient_userid=row[3],
                commentid=row[4],
                status=MessageLogStatus(row[5]),
                error_message=row[6],
                sent_at=row[7],
            )
            for row in rows
        ]

    def get_stats(self, message_id: int | None = None) -> dict:
        """Get statistics for message sends.

        Args:
            message_id: Optional message ID to filter by

        Returns:
            Dictionary with counts: {sent, failed, total}
        """
        base_query = select(func.count()).select_from(profile_message_logs)

        if message_id is not None:
            base_query = base_query.where(
                profile_message_logs.c.message_id == message_id
            )

        stmt_sent = base_query.where(profile_message_logs.c.status == 'sent')
        stmt_failed = base_query.where(profile_message_logs.c.status == 'failed')

        sent = self._scalar(stmt_sent) or 0
        failed = self._scalar(stmt_failed) or 0
        total = sent + failed

        return {
            "sent": sent,
            "failed": failed,
            "total": total,
        }

    def count_logs_by_message(self, message_id: int) -> int:
        """Count total logs for a message.

        Args:
            message_id: Message template ID

        Returns:
            Count of log entries
        """
        stmt = select(func.count()).select_from(profile_message_logs).where(
            profile_message_logs.c.message_id == message_id
        )
        return self._scalar(stmt) or 0

    def get_failed_logs(
        self, limit: int = 1000, offset: int = 0
    ) -> list[ProfileMessageLog]:
        """Get all failed message logs.

        Args:
            limit: Max results to return
            offset: Offset for pagination

        Returns:
            List of ProfileMessageLog objects with status=FAILED
        """
        stmt = (
            select(
                profile_message_logs.c.log_id,
                profile_message_logs.c.message_id,
                profile_message_logs.c.recipient_username,
                profile_message_logs.c.recipient_userid,
                profile_message_logs.c.commentid,
                profile_message_logs.c.status,
                profile_message_logs.c.error_message,
                profile_message_logs.c.sent_at,
            )
            .where(profile_message_logs.c.status == MessageLogStatus.FAILED.value)
            .order_by(profile_message_logs.c.sent_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = self._execute_core(stmt)
        rows = result.fetchall()

        return [
            ProfileMessageLog(
                log_id=row[0],
                message_id=row[1],
                recipient_username=row[2],
                recipient_userid=row[3],
                commentid=row[4],
                status=MessageLogStatus(row[5]),
                error_message=row[6],
                sent_at=row[7],
            )
            for row in rows
        ]

    def delete_failed_logs(self, failed_logs: list[ProfileMessageLog]) -> int:
        """Delete failed log entries.

        Args:
            failed_logs: List of ProfileMessageLog objects to delete

        Returns:
            Number of deleted records
        """
        if not failed_logs:
            return 0

        log_ids = [log.log_id for log in failed_logs]

        stmt = delete(profile_message_logs).where(
            profile_message_logs.c.log_id.in_(log_ids)
        )

        result = self._execute_and_commit(stmt)
        return self._rowcount(result)

    def get_all_recipient_userids(self) -> set[str]:
        """Get all unique recipient_userid values from logs.

        Returns:
            Set of recipient_userid strings (both sent and failed)
        """
        stmt = select(profile_message_logs.c.recipient_userid).distinct()

        result = self._execute_core(stmt)
        rows = result.fetchall()

        return {row[0] for row in rows if row[0]}
