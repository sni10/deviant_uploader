"""Database adapter factory (PostgreSQL-only)."""

from __future__ import annotations

import os
from pathlib import Path

from .adapters import SQLAlchemyAdapter
from .base_repository import DBConnection


_adapter: SQLAlchemyAdapter | None = None
_adapter_url: str | None = None
_adapter_schema: str | None = None
_initialized: bool = False


def init_database(db_path: str | Path) -> None:
    """Legacy initializer (removed).

    The project is PostgreSQL-only. This function exists only so that any
    remaining legacy callsites fail loudly.
    """

    raise RuntimeError(
        "SQLite backend has been deprecated and removed. "
        "Configure PostgreSQL via DATABASE_URL/DB_* and use get_connection()."
    )


def get_database_adapter():
    """Return the configured PostgreSQL adapter.

    The project is PostgreSQL-only. Connection details are taken from
    `DATABASE_URL` (or assembled from `DB_*` variables) by `src.config`.

    Returns:
        SQLAlchemyAdapter instance.
    """

    from ..config import get_config

    global _adapter, _adapter_url, _adapter_schema, _initialized

    config = get_config()
    if not config.database_url:
        raise ValueError(
            "DATABASE_URL (or DB_* variables) is required for PostgreSQL."
        )

    # Cache adapter instance to avoid re-creating engines/sessions on every call.
    # IMPORTANT: schema is part of the identity. If `DB_SCHEMA` changes, we must
    # recreate adapter and re-run initialization, otherwise sessions may keep an
    # old `search_path` and will read/write to the wrong schema.
    schema = os.getenv("DB_SCHEMA")

    if (
        _adapter is None
        or _adapter_url != config.database_url
        or _adapter_schema != schema
    ):
        _adapter = SQLAlchemyAdapter(config.database_url)
        _adapter_url = config.database_url
        _adapter_schema = schema
        _initialized = False

    return _adapter


def get_connection():
    """
    Convenience function to get a database connection using the configured adapter.
    
    This is the recommended way to obtain database connections in application code.
    It automatically selects the correct backend based on configuration and
    returns a connection implementing the DBConnection protocol.
    
    Returns:
        DBConnection instance compatible with all repositories
        
    Example:
        >>> from src.storage.database import get_connection
        >>> from src.storage.user_repository import UserRepository
        >>> 
        >>> conn = get_connection()
        >>> user_repo = UserRepository(conn)
        >>> # ... use repository
        >>> conn.close()
    """
    global _initialized

    adapter = get_database_adapter()
    if not _initialized:
        adapter.initialize()
        _initialized = True

    return adapter.get_connection()
