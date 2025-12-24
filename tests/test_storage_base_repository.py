"""Tests for storage base repository helpers."""
from __future__ import annotations

from dataclasses import dataclass

from src.storage.base_repository import BaseRepository
from src.storage.deviation_comment_tables import metadata as deviation_comment_metadata
from src.storage.feed_tables import metadata as feed_metadata
from src.storage.models import Base
from src.storage.profile_message_tables import metadata as profile_message_metadata
from src.storage.schema_registry import CORE_METADATA, iter_metadata


@dataclass
class DummyResult:
    """Result stub with scalar/fetchone behavior."""

    scalar_value: object | None = None
    fetchone_value: tuple | None = None
    rowcount: int | None = None
    scalar_called: bool = False
    scalar_one_or_none_called: bool = False

    def scalar(self) -> object | None:
        """Return configured scalar value."""
        self.scalar_called = True
        return self.scalar_value

    def scalar_one_or_none(self) -> object | None:
        """Return configured scalar value and mark call."""
        self.scalar_one_or_none_called = True
        return self.scalar_value

    def fetchone(self) -> tuple | None:
        """Return configured row."""
        return self.fetchone_value


class NoScalarResult:
    """Result stub without scalar methods."""

    def __init__(self, fetchone_value: tuple | None) -> None:
        self.fetchone_value = fetchone_value

    def fetchone(self) -> tuple | None:
        """Return configured row."""
        return self.fetchone_value


class DummyConnection:
    """Connection stub implementing DBConnection protocol."""

    def __init__(self, result: object) -> None:
        self.result = result
        self.executed: list[tuple[object, object | None]] = []
        self.commits = 0

    def execute(self, statement: object, parameters: object | None = None) -> object:
        """Record call and return configured result."""
        self.executed.append((statement, parameters))
        return self.result

    def commit(self) -> None:
        """Record commit calls."""
        self.commits += 1

    def close(self) -> None:
        """No-op close."""
        return None


class DummyRepository(BaseRepository):
    """Concrete repository for testing helpers."""

    pass


class DummyStatement:
    """Statement stub that tracks returning() usage."""

    def __init__(self) -> None:
        self.returning_called_with: object | None = None

    def returning(self, column: object) -> "DummyStatement":
        """Record returning column and return self."""
        self.returning_called_with = column
        return self


class TestBaseRepositoryHelpers:
    """Test BaseRepository helper methods."""

    def test_execute_core_passes_parameters(self) -> None:
        """Execute core passes parameters to connection."""
        result = DummyResult()
        conn = DummyConnection(result)
        repo = DummyRepository(conn)

        returned = repo._execute_core("stmt", {"a": 1})

        assert returned is result
        assert conn.executed == [("stmt", {"a": 1})]

    def test_execute_and_commit_commits(self) -> None:
        """Execute-and-commit issues a commit."""
        result = DummyResult()
        conn = DummyConnection(result)
        repo = DummyRepository(conn)

        returned = repo._execute_and_commit("stmt")

        assert returned is result
        assert conn.executed == [("stmt", None)]
        assert conn.commits == 1

    def test_scalar_prefers_scalar_method(self) -> None:
        """Scalar uses scalar() when available."""
        result = DummyResult(scalar_value=42, fetchone_value=(99,))
        conn = DummyConnection(result)
        repo = DummyRepository(conn)

        value = repo._scalar("stmt")

        assert value == 42
        assert result.scalar_called is True
        assert result.scalar_one_or_none_called is False

    def test_scalar_falls_back_to_fetchone(self) -> None:
        """Scalar falls back to fetchone when scalar() is missing."""
        result = NoScalarResult(fetchone_value=("value",))
        conn = DummyConnection(result)
        repo = DummyRepository(conn)

        value = repo._scalar("stmt")

        assert value == "value"

    def test_rowcount_returns_zero_when_missing(self) -> None:
        """Rowcount helper returns zero when attribute is missing."""
        repo = DummyRepository(DummyConnection(DummyResult()))

        assert repo._rowcount(object()) == 0

    def test_rowcount_returns_value(self) -> None:
        """Rowcount helper returns rowcount value."""
        repo = DummyRepository(DummyConnection(DummyResult()))
        result = DummyResult(rowcount=5)

        assert repo._rowcount(result) == 5

    def test_insert_returning_id_uses_returning(self) -> None:
        """Insert-returning helper executes returning and commits."""
        result = DummyResult(fetchone_value=(7,))
        conn = DummyConnection(result)
        repo = DummyRepository(conn)
        stmt = DummyStatement()

        returned_id = repo._insert_returning_id(stmt, returning_col="id")

        assert returned_id == 7
        assert stmt.returning_called_with == "id"
        assert conn.commits == 1


class TestSchemaRegistry:
    """Test schema registry helpers."""

    def test_iter_metadata_includes_all(self) -> None:
        """Registry yields ORM and Core metadata."""
        all_metadata = list(iter_metadata())

        assert all_metadata[0] is Base.metadata
        assert feed_metadata in all_metadata
        assert profile_message_metadata in all_metadata
        assert deviation_comment_metadata in all_metadata
        assert list(CORE_METADATA) == [
            feed_metadata,
            profile_message_metadata,
            deviation_comment_metadata,
        ]
