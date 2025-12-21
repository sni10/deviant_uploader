"""Tests for PostgreSQL adapter and connection abstraction."""

from __future__ import annotations

from sqlalchemy import insert, select, text

from src.storage.adapters import SQLAlchemyAdapter
from src.storage.adapters.base import DatabaseAdapter
from src.storage.base_repository import DBConnection
from src.storage.database import get_database_adapter
from src.storage.models import User as UserModel


class TestSQLAlchemyConnection:
    """Test SQLAlchemyConnection wrapper implements DBConnection protocol."""

    def test_connection_implements_protocol(self, db_conn):
        """Return object should satisfy DBConnection protocol."""

        assert isinstance(db_conn, DBConnection)

    def test_connection_execute_text(self, db_conn):
        """Execute raw SQL via SQLAlchemy text()."""

        result = db_conn.execute("SELECT 1")
        assert result.scalar_one() == 1

        result = db_conn.execute(text("SELECT :a + :b"), {"a": 2, "b": 3})
        assert result.scalar_one() == 5

    def test_connection_commit(self, db_conn):
        """Commit should persist changes inside the test schema."""

        users = UserModel.__table__
        db_conn.execute(
            insert(users).values(userid="u-1", username="name", type="regular")
        )
        db_conn.commit()

        result = db_conn.execute(select(users.c.username).where(users.c.userid == "u-1"))
        assert result.scalar_one() == "name"


class TestSQLAlchemyAdapter:
    """Test SQLAlchemyAdapter implementation."""

    def test_adapter_implements_protocol(self, database_url):
        """Adapter should satisfy DatabaseAdapter protocol."""

        adapter = SQLAlchemyAdapter(database_url)
        assert isinstance(adapter, DatabaseAdapter)


class TestDatabaseFactory:
    """Test database factory function returns Postgres adapter."""

    def test_get_database_adapter_returns_sqlalchemy_adapter(self, monkeypatch, database_url):
        """Factory should return SQLAlchemyAdapter in Postgres-only mode."""

        class MockConfig:
            def __init__(self, url: str):
                self.database_url = url

        monkeypatch.setattr(
            "src.config.get_config", lambda: MockConfig(database_url)
        )

        adapter = get_database_adapter()
        assert isinstance(adapter, SQLAlchemyAdapter)
