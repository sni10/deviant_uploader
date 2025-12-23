"""SQLAlchemy database adapter implementation for PostgreSQL."""

import os
import threading
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from ..base_repository import DBConnection
from ..models import Base
from ..feed_tables import metadata as feed_metadata
from ..profile_message_tables import metadata as profile_message_metadata
from ..deviation_comment_tables import metadata as deviation_comment_metadata


class SQLAlchemyConnection:
    """Wrapper around SQLAlchemy Session implementing DBConnection protocol.
    
    This wrapper makes SQLAlchemy sessions compatible with the DBConnection
    protocol expected by repositories, allowing repositories to work seamlessly
    with both SQLite and PostgreSQL backends.
    """
    
    def __init__(self, session: Session):
        """Initialize SQLAlchemy connection wrapper.
        
        Args:
            session: SQLAlchemy session object
        """
        self._session = session
        # SQLAlchemy Session is not thread-safe.
        # Background workers + HTTP handlers may share the same connection wrapper
        # (e.g., singleton services). Protect concurrent operations.
        self._lock = threading.RLock()
    
    def execute(self, statement: Any, parameters: Any | None = None) -> Any:
        """Execute a statement and return a SQLAlchemy Result.

        Repositories should pass SQLAlchemy Core statements. String SQL is still
        supported via `sqlalchemy.text()` for legacy paths.
        """

        with self._lock:
            try:
                if isinstance(statement, str):
                    stmt = text(statement)
                else:
                    stmt = statement

                if parameters is None:
                    return self._session.execute(stmt)
                return self._session.execute(stmt, parameters)
            except SQLAlchemyError:
                # When a DBAPI error occurs (e.g. PostgreSQL InFailedSqlTransaction),
                # the Session is left in a failed state until rollback().
                self._session.rollback()
                raise
    
    def commit(self) -> None:
        """Commit the current transaction."""
        with self._lock:
            try:
                self._session.commit()
            except SQLAlchemyError:
                self._session.rollback()
                raise
    
    def close(self) -> None:
        """Close the database session."""
        with self._lock:
            self._session.close()


class SQLAlchemyAdapter:
    """Database adapter for PostgreSQL backend using SQLAlchemy.
    
    This adapter provides PostgreSQL support through SQLAlchemy ORM,
    implementing the DatabaseAdapter protocol for seamless backend switching.
    """
    
    def __init__(self, database_url: str):
        """Initialize SQLAlchemy adapter.
        
        Args:
            database_url: PostgreSQL connection URL 
                         (e.g., 'postgresql://user:pass@localhost/dbname')
        """
        self.database_url = database_url

        # Optional schema selection.
        # If someone runs Postgres with a non-default `search_path` (or even an
        # empty one), DDL like `CREATE TABLE ...` will fail with
        # `psycopg2.errors.InvalidSchemaName: no schema has been selected to create in`.
        # Default to `public` to match typical PostgreSQL setups.
        self.schema = os.getenv("DB_SCHEMA", "main")
        
        # Create engine with connection pooling disabled for simplicity
        # In production, you may want to configure pooling appropriately
        self.engine = create_engine(
            database_url,
            poolclass=NullPool,
            echo=False  # Set to True for SQL debugging
        )

        # Ensure every new physical connection uses our schema.
        # This is critical with `NullPool` and long-lived Sessions: a Session
        # may provision a new DBAPI connection later, and without this hook it
        # would fall back to the server default `search_path` (often `public`).
        event.listen(self.engine, "connect", self._on_connect)
        
        # Create session factory
        self.SessionFactory = sessionmaker(bind=self.engine)

    def _on_connect(self, dbapi_connection, _connection_record) -> None:
        """Set `search_path` for every new DBAPI connection."""

        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"SET search_path TO {self.schema}")
        finally:
            cursor.close()
    
    def initialize(self) -> None:
        """Initialize database schema and run migrations.

        This method creates all tables defined in the SQLAlchemy models.
        For production use with migrations, this should be replaced with
        Alembic migration logic.
        """
        # Ensure schema exists and set search_path for DDL.
        with self.engine.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {self.schema}"))
            conn.execute(text(f"SET search_path TO {self.schema}"))

            # Create all tables defined in ORM models
            Base.metadata.create_all(bind=conn)

            # Create all tables defined in Core metadata (feed tables)
            feed_metadata.create_all(bind=conn)

            # Create all tables defined in Core metadata (profile message tables)
            profile_message_metadata.create_all(bind=conn)

            # Create all tables defined in Core metadata (deviation comment tables)
            deviation_comment_metadata.create_all(bind=conn)
    
    def get_connection(self) -> DBConnection:
        """Create and return a new SQLAlchemy session wrapped as DBConnection.
        
        Returns:
            SQLAlchemyConnection wrapper implementing DBConnection protocol
        """
        session = self.SessionFactory()
        # Make sure runtime SELECT/INSERT/UPDATE see the correct schema.
        session.execute(text(f"SET search_path TO {self.schema}"))
        return SQLAlchemyConnection(session)
