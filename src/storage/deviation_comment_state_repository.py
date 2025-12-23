"""Repository for deviation comment collector state using SQLAlchemy Core."""

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .base_repository import BaseRepository
from .deviation_comment_tables import deviation_comment_state


class DeviationCommentStateRepository(BaseRepository):
    """Provides persistence for comment collector state."""

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
        self._execute_core(stmt)
        self.conn.commit()
