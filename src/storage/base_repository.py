"""Base repository abstractions following DDD and SOLID principles."""

from abc import ABC
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DBConnection(Protocol):
    """Abstract database connection used by repositories.

    This protocol defines the minimal surface that repositories rely on.
    It mirrors the SQLAlchemy Session/Connection API used in the storage
    layer so repositories can remain backend-agnostic at call sites.
    """

    def execute(self, statement: Any, parameters: Any | None = None) -> Any:
        """Execute a statement and return a result-like object.

        Repositories primarily execute SQLAlchemy Core statements.
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

    def _execute_core(self, statement: Any, parameters: Any | None = None) -> Any:
        """Execute a SQLAlchemy Core statement using the connection."""

        return self._execute(statement, parameters)

    def _execute_and_commit(
        self, statement: Any, parameters: Any | None = None
    ) -> Any:
        """Execute a statement and commit the transaction."""

        result = self._execute(statement, parameters)
        self._conn.commit()
        return result

    def _fetchone(self, statement: Any, parameters: Any | None = None) -> Any:
        """Execute a statement and fetch one row."""

        result = self._execute(statement, parameters)
        return result.fetchone()

    def _fetchall(self, statement: Any, parameters: Any | None = None) -> Any:
        """Execute a statement and fetch all rows."""

        result = self._execute(statement, parameters)
        return result.fetchall()

    def _scalar(self, statement: Any, parameters: Any | None = None) -> Any:
        """Execute a statement and return scalar value.

        Works with SQLAlchemy result objects.
        """

        result = self._execute(statement, parameters)
        if hasattr(result, "scalar"):
            return result.scalar()
        row = result.fetchone()
        return None if row is None else row[0]

    def _rowcount(self, result: Any) -> int:
        """Return rowcount from a result, if available."""

        if hasattr(result, "rowcount"):
            rowcount = result.rowcount
            return 0 if rowcount is None else int(rowcount)
        return 0

    def _insert_returning_id(
        self, insert_stmt: Any, returning_col: Any | None = None
    ) -> int | None:
        """Execute insert statement with RETURNING and return id."""

        if returning_col is None:
            raise ValueError("returning_col is required for returning id")

        stmt = insert_stmt.returning(returning_col)
        result = self._execute_and_commit(stmt)
        row = result.fetchone()
        return None if row is None else row[0]
