"""Pytest fixtures for PostgreSQL-only storage layer."""

from __future__ import annotations

import os
import uuid
from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.storage.adapters.sqlalchemy_adapter import SQLAlchemyConnection
from src.storage.feed_tables import metadata as feed_metadata
from src.storage.models import Base
from src.storage.profile_message_tables import metadata as profile_message_metadata


@pytest.fixture(scope="session", autouse=True)
def _set_required_env_defaults() -> None:
    """Ensure required env vars exist for config validation in tests."""

    os.environ.setdefault("DA_CLIENT_ID", "test")
    os.environ.setdefault("DA_CLIENT_SECRET", "test")


@pytest.fixture(scope="session")
def database_url() -> str:
    """Return PostgreSQL URL for tests.

    Tests require `DATABASE_URL` or sufficient `DB_*` variables.
    """

    from src.config import get_config

    url = get_config().database_url
    if not url:
        pytest.skip("DATABASE_URL/DB_* is not configured")
    return url


@pytest.fixture()
def pg_engine(database_url: str):
    """Create a SQLAlchemy Engine for PostgreSQL."""

    return create_engine(database_url)


@pytest.fixture()
def pg_schema(pg_engine) -> Iterator[str]:
    """Create an isolated schema per test and drop it afterwards."""

    schema = f"test_{uuid.uuid4().hex}"
    with pg_engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    try:
        yield schema
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))


@pytest.fixture()
def db_conn(pg_engine, pg_schema: str) -> Iterator[SQLAlchemyConnection]:
    """Return a DBConnection bound to a per-test schema."""

    SessionFactory = sessionmaker(bind=pg_engine)
    session = SessionFactory()
    session.execute(text(f"SET search_path TO {pg_schema}"))

    # Create schema objects inside the isolated schema.
    with pg_engine.begin() as conn:
        conn.execute(text(f"SET search_path TO {pg_schema}"))
        Base.metadata.create_all(bind=conn)
        feed_metadata.create_all(bind=conn)
        profile_message_metadata.create_all(bind=conn)

    try:
        yield SQLAlchemyConnection(session)
    finally:
        session.close()
