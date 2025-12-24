"""Repository for deviation comment collector state using SQLAlchemy Core."""

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .base_repository import BaseRepository
from .deviation_comment_tables import deviation_comment_state


class DeviationCommentStateRepository(BaseRepository):
    """Provides persistence for comment collector state."""

    def get_state(self, key: str) -> str | None:
        """Get state value by key.

        Args:
            key: State key.

        Returns:
            State value or None if not found.
        """
        stmt = select(deviation_comment_state.c.value).where(
            deviation_comment_state.c.key == key
        )
        result = self._execute_core(stmt)
        row = result.fetchone()
        return row[0] if row else None

    def set_state(self, key: str, value: str) -> None:
        """Set state value by key (upsert).

        Args:
            key: State key.
            value: State value.
        """
        stmt = (
            pg_insert(deviation_comment_state)
            .values(key=key, value=value)
            .on_conflict_do_update(
                index_elements=[deviation_comment_state.c.key],
                set_={"value": value, "updated_at": func.current_timestamp()},
            )
        )
        self._execute_and_commit(stmt)
