"""Repository for watchers using SQLAlchemy Core."""

from sqlalchemy import select, insert, func
from .base_repository import BaseRepository
from .profile_message_tables import watchers
from ..domain.models import Watcher


class WatcherRepository(BaseRepository):
    """Provides persistence for DeviantArt watchers."""

    def _execute_core(self, statement):
        """Execute SQLAlchemy Core statement and return result.

        Handles both SQLAlchemy connections and raw SQLite connections.
        """
        if hasattr(self.conn, '_session'):
            return self.conn._session.execute(statement)
        else:
            compiled = statement.compile(compile_kwargs={"literal_binds": True})
            return self.conn.execute(str(compiled))

    def add_or_update_watcher(self, username: str, userid: str) -> None:
        """Add watcher or update fetched_at if exists.

        Args:
            username: Watcher's DeviantArt username
            userid: Watcher's DeviantArt user ID
        """
        # Check if watcher exists
        stmt = select(watchers.c.watcher_id).where(watchers.c.username == username)
        result = self._execute_core(stmt)
        existing = result.fetchone()

        if existing:
            # Update fetched_at (using raw SQL for SQLite compatibility)
            if hasattr(self.conn, '_session'):
                # SQLAlchemy
                from sqlalchemy import update
                stmt = (
                    update(watchers)
                    .where(watchers.c.username == username)
                    .values(userid=userid, fetched_at=func.now())
                )
                self._execute_core(stmt)
            else:
                # SQLite
                self.conn.execute(
                    "UPDATE watchers SET userid = ?, fetched_at = CURRENT_TIMESTAMP WHERE username = ?",
                    (userid, username)
                )
        else:
            # Insert new watcher
            stmt = insert(watchers).values(username=username, userid=userid)
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
