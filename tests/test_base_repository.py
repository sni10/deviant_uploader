"""Tests for BaseRepository insert handling."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, insert
from sqlalchemy.exc import IntegrityError

from src.storage.base_repository import BaseRepository


class _FakeOrig(Exception):
    """Fake DBAPI error with pgcode attribute."""

    pgcode = "23505"


class _FakeForeignKeyError(Exception):
    """Fake DBAPI error with non-unique pgcode."""

    pgcode = "23503"


def _create_repo_with_execute_side_effect(side_effect):
    """Create BaseRepository with mocked connection execute."""
    conn = MagicMock()
    conn.execute.side_effect = side_effect
    return BaseRepository(conn), conn


def _create_table():
    """Create a lightweight table for SQLAlchemy statements."""
    metadata = MetaData()
    return Table(
        "example",
        metadata,
        Column("id", Integer, primary_key=True),
    )


def test_insert_returning_id_resyncs_on_unique_violation() -> None:
    """Retry insert after syncing sequence when unique violation occurs."""
    table = _create_table()
    insert_stmt = insert(table).values()
    error = IntegrityError("stmt", {}, _FakeOrig())

    result = MagicMock()
    result.fetchone.return_value = (7,)

    repo, conn = _create_repo_with_execute_side_effect([error, result])

    with patch.object(
        repo,
        "_sync_sequence_for_column",
        return_value=True,
    ) as sync_sequence:
        message_id = repo._insert_returning_id(
            insert_stmt,
            returning_col=table.c.id,
        )

    sync_sequence.assert_called_once_with(table.c.id)
    assert conn.execute.call_count == 2
    conn.commit.assert_called_once()
    assert message_id == 7


def test_insert_returning_id_raises_on_non_unique_violation() -> None:
    """Propagate non-unique integrity errors without sequence sync."""
    table = _create_table()
    insert_stmt = insert(table).values()
    error = IntegrityError("stmt", {}, _FakeForeignKeyError())

    repo, _conn = _create_repo_with_execute_side_effect(error)

    with patch.object(repo, "_sync_sequence_for_column") as sync_sequence:
        with pytest.raises(IntegrityError):
            repo._insert_returning_id(insert_stmt, returning_col=table.c.id)

    sync_sequence.assert_not_called()
