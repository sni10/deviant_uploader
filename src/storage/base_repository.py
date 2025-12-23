"""Base repository abstractions following DDD and SOLID principles."""

from abc import ABC
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DBConnection(Protocol):
    """Abstract database connection used by repositories.

    This protocol defines the minimal surface that repositories rely on.
    It intentionally mirrors the subset of :class:`sqlite3.Connection`
    that is used in the current codebase so the storage layer can be
    switched to another backend (for example, SQLAlchemy/PostgreSQL)
    without changing repository logic.
    """

    def execute(self, statement: Any, parameters: Any | None = None) -> Any:
        """Execute a statement and return a result-like object.

        In PostgreSQL-only mode, repositories primarily execute SQLAlchemy Core
        statements.
        """

    def commit(self) -> None:
        """Commit the current transaction."""

    def close(self) -> None:
        """Close the underlying database connection."""


class BaseRepository(ABC):
    """Abstract base repository providing common database operations.

    Follows SOLID principles:
    - Single Responsibility: Base functionality for all repositories.
    - Open/Closed: Open for extension, closed for modification.
    - Liskov Substitution: All repositories can be used via this base type.
    - Interface Segregation: Only common operations in base.
    - Dependency Inversion: Depends on an abstract ``DBConnection``.
    """

    def __init__(self, conn: DBConnection):
        """Initialize repository with database connection.

        Args:
            conn: Database connection object implementing :class:`DBConnection`.
        """

        self._conn = conn

    @property
    def conn(self) -> DBConnection:
        """Return the associated database connection abstraction."""

        return self._conn

    def close(self) -> None:
        """Close the underlying database connection, if present.

        Note:
            In production, connection management should ideally be handled
            by a connection pool or context manager at a higher level.
        """

        if self._conn:
            self._conn.close()

    def _execute(self, statement: Any, parameters: Any | None = None) -> Any:
        """Execute a statement using the underlying connection."""

        return self._conn.execute(statement, parameters)

    def _scalar(self, statement: Any, parameters: Any | None = None) -> Any:
        """Execute a statement and return scalar value.

        Works with SQLAlchemy result objects.
        """

        result = self._execute(statement, parameters)
        if hasattr(result, "scalar_one_or_none"):
            return result.scalar_one_or_none()
        if hasattr(result, "scalar"):
            return result.scalar()
        row = result.fetchone()
        return None if row is None else row[0]
