"""SQLite database adapter implementation (deprecated).

This project has migrated to PostgreSQL and no longer supports SQLite.
The module is kept only to provide a clear error if imported by legacy code.
"""

raise RuntimeError(
    "SQLite backend has been deprecated and removed. "
    "Configure PostgreSQL via DATABASE_URL/DB_* and use SQLAlchemyAdapter."
)

import sqlite3
from pathlib import Path
from typing import Any

from ..base_repository import DBConnection


class SQLiteConnection:
    """Wrapper around sqlite3.Connection implementing DBConnection protocol.
    
    This wrapper ensures that sqlite3.Connection conforms to the DBConnection
    protocol expected by repositories, allowing seamless switching between
    different database backends.
    """
    
    def __init__(self, conn: sqlite3.Connection):
        """Initialize SQLite connection wrapper.
        
        Args:
            conn: Native sqlite3.Connection object
        """
        self._conn = conn
    
    def execute(self, sql: str, parameters: Any | None = None) -> sqlite3.Cursor:
        """Execute a SQL statement and return a cursor.
        
        Args:
            sql: SQL statement to execute
            parameters: Optional parameters for the SQL statement
            
        Returns:
            Cursor object with query results
        """
        if parameters is None:
            return self._conn.execute(sql)
        return self._conn.execute(sql, parameters)
    
    def commit(self) -> None:
        """Commit the current transaction."""
        self._conn.commit()
    
    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()


class SQLiteAdapter:
    """Database adapter for SQLite backend.
    
    This adapter wraps the existing SQLite database logic from database.py,
    providing a consistent interface through the DatabaseAdapter protocol.
    """
    
    def __init__(self, db_path: str | Path):
        """Initialize SQLite adapter.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._connection: SQLiteConnection | None = None
    
    def initialize(self) -> None:
        """Initialize database schema and run migrations.
        
        This method:
        - Creates the database file and parent directories
        - Creates all tables from the schema
        - Runs migration logic to add missing columns
        """
        # Import here to avoid circular dependency
        from ..database import DATABASE_SCHEMA, _migrate_database
        
        # Ensure data directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Connect and enable foreign keys
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Initialize schema
        conn.executescript(DATABASE_SCHEMA)
        conn.commit()
        
        # Run migrations
        _migrate_database(conn)
        
        # Close initialization connection
        conn.close()
    
    def get_connection(self) -> DBConnection:
        """Create and return a new SQLite connection.
        
        Returns:
            SQLiteConnection wrapper implementing DBConnection protocol
        """
        # Create new connection
        # check_same_thread=False is required for Flask compatibility
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Wrap in our protocol-compliant wrapper
        return SQLiteConnection(conn)
