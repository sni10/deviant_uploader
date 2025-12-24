"""Repository for profile message templates using SQLAlchemy Core."""

from sqlalchemy import select, insert, update, delete, func
from .base_repository import BaseRepository
from .profile_message_tables import profile_messages
from ..domain.models import ProfileMessage


class ProfileMessageRepository(BaseRepository):
    """Provides persistence for profile message templates."""

    def create_message(self, title: str, body: str) -> int:
        """Create new profile message template.

        Args:
            title: Message template title
            body: Message body text

        Returns:
            message_id of created template
        """
        stmt = insert(profile_messages).values(title=title, body=body, is_active=True)
        return self._insert_returning_id(
            stmt, returning_col=profile_messages.c.message_id
        )

    def get_message_by_id(self, message_id: int) -> ProfileMessage | None:
        """Get message template by ID.

        Args:
            message_id: Message template ID

        Returns:
            ProfileMessage or None if not found
        """
        stmt = select(
            profile_messages.c.message_id,
            profile_messages.c.title,
            profile_messages.c.body,
            profile_messages.c.is_active,
            profile_messages.c.created_at,
            profile_messages.c.updated_at,
        ).where(profile_messages.c.message_id == message_id)

        result = self._execute_core(stmt)
        row = result.fetchone()

        if row is None:
            return None

        return ProfileMessage(
            message_id=row[0],
            title=row[1],
            body=row[2],
            is_active=bool(row[3]),
            created_at=row[4],
            updated_at=row[5],
        )

    def get_all_messages(self) -> list[ProfileMessage]:
        """Get all message templates.

        Returns:
            List of ProfileMessage objects
        """
        stmt = select(
            profile_messages.c.message_id,
            profile_messages.c.title,
            profile_messages.c.body,
            profile_messages.c.is_active,
            profile_messages.c.created_at,
            profile_messages.c.updated_at,
        ).order_by(profile_messages.c.created_at.desc())

        result = self._execute_core(stmt)
        rows = result.fetchall()

        return [
            ProfileMessage(
                message_id=row[0],
                title=row[1],
                body=row[2],
                is_active=bool(row[3]),
                created_at=row[4],
                updated_at=row[5],
            )
            for row in rows
        ]

    def get_active_messages(self) -> list[ProfileMessage]:
        """Get only active message templates.

        Returns:
            List of active ProfileMessage objects
        """
        stmt = select(
            profile_messages.c.message_id,
            profile_messages.c.title,
            profile_messages.c.body,
            profile_messages.c.is_active,
            profile_messages.c.created_at,
            profile_messages.c.updated_at,
        ).where(
            profile_messages.c.is_active == True
        ).order_by(profile_messages.c.created_at.desc())

        result = self._execute_core(stmt)
        rows = result.fetchall()

        return [
            ProfileMessage(
                message_id=row[0],
                title=row[1],
                body=row[2],
                is_active=bool(row[3]),
                created_at=row[4],
                updated_at=row[5],
            )
            for row in rows
        ]

    def update_message(
        self,
        message_id: int,
        title: str | None = None,
        body: str | None = None,
        is_active: bool | None = None,
    ) -> None:
        """Update message template.

        Args:
            message_id: Message ID to update
            title: New title (optional)
            body: New body (optional)
            is_active: New active status (optional)
        """
        values: dict[str, object] = {}
        if title is not None:
            values["title"] = title
        if body is not None:
            values["body"] = body
        if is_active is not None:
            values["is_active"] = is_active

        if not values:
            return

        values["updated_at"] = func.current_timestamp()

        stmt = update(profile_messages).where(
            profile_messages.c.message_id == message_id
        ).values(**values)

        self._execute_and_commit(stmt)

    def delete_message(self, message_id: int) -> None:
        """Delete message template.

        Args:
            message_id: Message ID to delete
        """
        stmt = delete(profile_messages).where(
            profile_messages.c.message_id == message_id
        )
        self._execute_and_commit(stmt)
