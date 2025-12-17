"""Repository for profile message send logs using SQLAlchemy Core."""

from sqlalchemy import select, insert, func
from .base_repository import BaseRepository
from .profile_message_tables import profile_message_logs
from ..domain.models import ProfileMessageLog, MessageLogStatus


class ProfileMessageLogRepository(BaseRepository):
    """Provides persistence for profile message send logs."""

    def _execute_core(self, statement):
        """Execute SQLAlchemy Core statement and return result.

        Handles both SQLAlchemy connections and raw SQLite connections.
        """
        if hasattr(self.conn, '_session'):
            return self.conn._session.execute(statement)
        else:
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

        result = self._execute_core(stmt)
        self.conn.commit()

        # Get last inserted id
        if hasattr(result, 'inserted_primary_key'):
            return result.inserted_primary_key[0]
        else:
            # For SQLite
            return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def get_logs_by_message_id(self, message_id: int, limit: int = 100, offset: int = 0) -> list[ProfileMessageLog]:
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

    def get_all_logs(self, limit: int = 100, offset: int = 0) -> list[ProfileMessageLog]:
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
            base_query = base_query.where(profile_message_logs.c.message_id == message_id)

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
