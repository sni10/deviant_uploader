"""Repository for profile message queue using SQLAlchemy Core."""

from sqlalchemy import select, insert, update, delete, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .base_repository import BaseRepository
from .profile_message_tables import profile_message_queue
from ..domain.models import ProfileMessageQueue, QueueStatus


class ProfileMessageQueueRepository(BaseRepository):
    """Provides persistence for profile message queue."""

    def _execute_core(self, statement):
        """Execute SQLAlchemy Core statement and return result.

        Handles both SQLAlchemy connections and raw SQLite connections.
        """
        if hasattr(self.conn, "_session"):
            # Use the DBConnection wrapper to ensure thread-safety and
            # automatic rollback on DBAPI/SQLAlchemy errors.
            return self.conn.execute(statement)

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

    def add_to_queue(
        self,
        message_id: int,
        recipient_username: str,
        recipient_userid: str,
        priority: int = 0,
    ) -> int:
        """Add entry to queue with UPSERT (prevents duplicates).

        If entry already exists for same message_id and recipient_userid,
        updates status to 'pending' and priority to maximum of new and existing.

        Args:
            message_id: Template message ID
            recipient_username: Recipient's DeviantArt username
            recipient_userid: Recipient's DeviantArt user ID
            priority: Priority (higher = processed first)

        Returns:
            queue_id of created or updated entry
        """
        stmt = pg_insert(profile_message_queue).values(
            message_id=message_id,
            recipient_username=recipient_username,
            recipient_userid=recipient_userid,
            status=QueueStatus.PENDING.value,
            priority=priority,
        )

        # On conflict (duplicate message_id + recipient_userid):
        # - Reset status to 'pending' (in case it was 'processing' or 'completed')
        # - Update priority to maximum of new and existing
        # - Update updated_at timestamp
        stmt = stmt.on_conflict_do_update(
            constraint='uq_profile_message_queue_message_recipient',
            set_={
                'status': QueueStatus.PENDING.value,
                'priority': func.greatest(stmt.excluded.priority, profile_message_queue.c.priority),
                'updated_at': func.now(),
            }
        )

        result = self._execute_core(stmt)
        self.conn.commit()

        # Get the queue_id (either inserted or updated)
        if hasattr(result, 'inserted_primary_key') and result.inserted_primary_key:
            return result.inserted_primary_key[0]
        else:
            # For updated rows, need to query back
            select_stmt = select(profile_message_queue.c.queue_id).where(
                (profile_message_queue.c.message_id == message_id) &
                (profile_message_queue.c.recipient_userid == recipient_userid)
            )
            result = self._execute_core(select_stmt)
            row = result.fetchone()
            return row[0] if row else None

    def get_pending(self, limit: int = 100) -> list[ProfileMessageQueue]:
        """Get pending queue entries ordered by priority (highest first) and creation time.

        Args:
            limit: Max results to return

        Returns:
            List of ProfileMessageQueue objects
        """
        stmt = (
            select(
                profile_message_queue.c.queue_id,
                profile_message_queue.c.message_id,
                profile_message_queue.c.recipient_username,
                profile_message_queue.c.recipient_userid,
                profile_message_queue.c.status,
                profile_message_queue.c.priority,
                profile_message_queue.c.created_at,
                profile_message_queue.c.updated_at,
            )
            .where(profile_message_queue.c.status == QueueStatus.PENDING.value)
            .order_by(profile_message_queue.c.priority.desc(), profile_message_queue.c.created_at.asc())
            .limit(limit)
        )

        result = self._execute_core(stmt)
        rows = result.fetchall()

        return [
            ProfileMessageQueue(
                queue_id=row[0],
                message_id=row[1],
                recipient_username=row[2],
                recipient_userid=row[3],
                status=QueueStatus(row[4]),
                priority=row[5],
                created_at=row[6],
                updated_at=row[7],
            )
            for row in rows
        ]

    def mark_processing(self, queue_id: int) -> None:
        """Mark queue entry as processing.

        Args:
            queue_id: Queue entry ID
        """
        stmt = (
            update(profile_message_queue)
            .where(profile_message_queue.c.queue_id == queue_id)
            .values(status=QueueStatus.PROCESSING.value)
        )
        self._execute_core(stmt)
        self.conn.commit()

    def mark_completed(self, queue_id: int) -> None:
        """Mark queue entry as completed.

        Args:
            queue_id: Queue entry ID
        """
        stmt = (
            update(profile_message_queue)
            .where(profile_message_queue.c.queue_id == queue_id)
            .values(status=QueueStatus.COMPLETED.value)
        )
        self._execute_core(stmt)
        self.conn.commit()

    def remove_from_queue(self, queue_id: int) -> None:
        """Remove entry from queue.

        Args:
            queue_id: Queue entry ID
        """
        stmt = delete(profile_message_queue).where(
            profile_message_queue.c.queue_id == queue_id
        )
        self._execute_core(stmt)
        self.conn.commit()

    def clear_queue(self, status: QueueStatus | None = None) -> int:
        """Clear queue entries.

        Args:
            status: Optional status filter (if None, clears all)

        Returns:
            Number of entries removed
        """
        stmt = delete(profile_message_queue)
        if status is not None:
            stmt = stmt.where(profile_message_queue.c.status == status.value)

        result = self._execute_core(stmt)
        self.conn.commit()

        if hasattr(result, 'rowcount'):
            return result.rowcount
        else:
            # For SQLite
            return result.rowcount if hasattr(result, 'rowcount') else 0

    def get_queue_count(self, status: QueueStatus | None = None) -> int:
        """Get count of queue entries.

        Args:
            status: Optional status filter

        Returns:
            Count of entries
        """
        stmt = select(func.count()).select_from(profile_message_queue)
        if status is not None:
            stmt = stmt.where(profile_message_queue.c.status == status.value)

        return self._scalar(stmt) or 0

    def get_all_queue_entries(self, limit: int = 1000) -> list[ProfileMessageQueue]:
        """Get all queue entries.

        Args:
            limit: Max results to return

        Returns:
            List of ProfileMessageQueue objects
        """
        stmt = (
            select(
                profile_message_queue.c.queue_id,
                profile_message_queue.c.message_id,
                profile_message_queue.c.recipient_username,
                profile_message_queue.c.recipient_userid,
                profile_message_queue.c.status,
                profile_message_queue.c.priority,
                profile_message_queue.c.created_at,
                profile_message_queue.c.updated_at,
            )
            .order_by(profile_message_queue.c.priority.desc(), profile_message_queue.c.created_at.asc())
            .limit(limit)
        )

        result = self._execute_core(stmt)
        rows = result.fetchall()

        return [
            ProfileMessageQueue(
                queue_id=row[0],
                message_id=row[1],
                recipient_username=row[2],
                recipient_userid=row[3],
                status=QueueStatus(row[4]),
                priority=row[5],
                created_at=row[6],
                updated_at=row[7],
            )
            for row in rows
        ]
