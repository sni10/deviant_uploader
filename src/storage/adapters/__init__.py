"""Database adapters for different backend types.

This module provides abstractions for switching between SQLite and PostgreSQL
(via SQLAlchemy) backends without changing repository logic.
"""

from .base import DatabaseAdapter
from .sqlite_adapter import SQLiteAdapter, SQLiteConnection
from .sqlalchemy_adapter import SQLAlchemyAdapter, SQLAlchemyConnection

__all__ = [
    'DatabaseAdapter',
    'SQLiteAdapter',
    'SQLiteConnection',
    'SQLAlchemyAdapter',
    'SQLAlchemyConnection',
]
