"""SQLAlchemy database adapter implementation for PostgreSQL."""

from typing import Any
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from ..base_repository import DBConnection
from ..models import Base
from ..feed_tables import metadata as feed_metadata


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
    
    def execute(self, sql: str, parameters: Any | None = None):
        """Execute a SQL statement and return a result proxy.
        
        Args:
            sql: SQL statement to execute
            parameters: Optional parameters for the SQL statement
            
        Returns:
            Result proxy object with query results
        """
        if parameters is None:
            result = self._session.execute(text(sql))
        else:
            # Convert tuple parameters to dict for SQLAlchemy 2.0 style
            if isinstance(parameters, (tuple, list)):
                # For positional parameters, we need to convert to named params
                # SQLAlchemy text() requires named parameters
                # We'll use numeric placeholders that repositories already use
                result = self._session.execute(text(sql), parameters)
            else:
                result = self._session.execute(text(sql), parameters)
        return result
    
    def commit(self) -> None:
        """Commit the current transaction."""
        self._session.commit()
    
    def close(self) -> None:
        """Close the database session."""
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
        
        # Create engine with connection pooling disabled for simplicity
        # In production, you may want to configure pooling appropriately
        self.engine = create_engine(
            database_url,
            poolclass=NullPool,
            echo=False  # Set to True for SQL debugging
        )
        
        # Create session factory
        self.SessionFactory = sessionmaker(bind=self.engine)
    
    def initialize(self) -> None:
        """Initialize database schema and run migrations.

        This method creates all tables defined in the SQLAlchemy models.
        For production use with migrations, this should be replaced with
        Alembic migration logic.
        """
        # Create all tables defined in ORM models
        Base.metadata.create_all(self.engine)

        # Create all tables defined in Core metadata (feed tables)
        feed_metadata.create_all(self.engine)
    
    def get_connection(self) -> DBConnection:
        """Create and return a new SQLAlchemy session wrapped as DBConnection.
        
        Returns:
            SQLAlchemyConnection wrapper implementing DBConnection protocol
        """
        session = self.SessionFactory()
        return SQLAlchemyConnection(session)
