"""Tests for database connectivity and basic query execution."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from src.storage.database import get_connection


class TestDatabaseConnectivity:
    """Test basic database connectivity and query execution."""

    def test_database_connection_available(self) -> None:
        """Test that database connection can be established."""
        conn = get_connection()

        try:
            assert conn is not None, "Connection should not be None"
        finally:
            conn.close()

    def test_database_can_execute_simple_query(self) -> None:
        """Test that database can execute a simple SELECT query."""
        conn = get_connection()

        try:
            # Execute simple query (works for both SQLite and PostgreSQL)
            result = conn.execute(text("SELECT 1 AS test_value"))

            # Fetch result
            row = result.fetchone()

            # Verify result
            assert row is not None, "Query should return a row"
            assert row[0] == 1, "Query should return value 1"

        finally:
            conn.close()

    def test_database_can_commit_transaction(self) -> None:
        """Test that database can commit a transaction."""
        conn = get_connection()

        try:
            # Execute a query
            conn.execute(text("SELECT 1"))

            # Attempt to commit
            conn.commit()

            # If we reach here, commit succeeded
            assert True

        finally:
            conn.close()
