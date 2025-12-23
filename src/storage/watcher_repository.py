"""Repository for watchers using SQLAlchemy Core."""

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .base_repository import BaseRepository
from .profile_message_tables import watchers
from ..domain.models import Watcher


class WatcherRepository(BaseRepository):
    """Provides persistence for DeviantArt watchers."""

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

    def add_or_update_watcher(self, username: str, userid: str) -> None:
        """Add watcher or update fetched_at if exists.

        Args:
            username: Watcher's DeviantArt username
            userid: Watcher's DeviantArt user ID
        """
        stmt = (
            pg_insert(watchers)
            .values(username=username, userid=userid)
            .on_conflict_do_update(
                index_elements=[watchers.c.username],
                set_={"userid": userid, "fetched_at": func.now()},
            )
            .inline()
        )

        self._execute_core(stmt)
        self.conn.commit()

    def get_all_watchers(self, limit: int = 1000) -> list[Watcher]:
        """Get all watchers ordered by fetched_at DESC.

        Args:
            limit: Maximum number of watchers to return

        Returns:
            List of Watcher objects
        """
        stmt = (
            select(
                watchers.c.watcher_id,
                watchers.c.username,
                watchers.c.userid,
                watchers.c.fetched_at,
            )
            .order_by(watchers.c.fetched_at.desc())
            .limit(limit)
        )

        result = self._execute_core(stmt)
        rows = result.fetchall()

        return [
            Watcher(
                watcher_id=row[0],
                username=row[1],
                userid=row[2],
                fetched_at=row[3],
            )
            for row in rows
        ]

    def count_watchers(self) -> int:
        """Count total watchers in database.

        Returns:
            Total count of watchers
        """
        stmt = select(func.count()).select_from(watchers)
        result = self._execute_core(stmt)

        if hasattr(result, "scalar"):
            return result.scalar() or 0

        row = result.fetchone()
        return row[0] if row else 0

    def delete_watchers_not_in_list(self, usernames: list[str]) -> int:
        """Delete watchers whose usernames are not in the provided list.

        This is used for synchronization: after fetching current watchers
        from DeviantArt API, we remove those who unfollowed.

        Args:
            usernames: List of current watcher usernames to keep

        Returns:
            Number of watchers deleted
        """
        if not usernames:
            # If list is empty, delete all watchers
            stmt = delete(watchers)
        else:
            # Delete watchers not in the list
            stmt = delete(watchers).where(watchers.c.username.notin_(usernames))

        result = self._execute_core(stmt)
        self.conn.commit()

        # Get rowcount
        if hasattr(result, "rowcount"):
            return result.rowcount or 0

        return 0
