"""Base protocol for database adapters."""

from typing import Protocol, runtime_checkable
from ..base_repository import DBConnection


@runtime_checkable
class DatabaseAdapter(Protocol):
    """Protocol defining the interface for database adapters.
    
    This protocol enables switching between different database backends
    (SQLite, PostgreSQL via SQLAlchemy) without changing repository code.
    
    Each adapter is responsible for:
    - Initializing the database schema
    - Creating connections that implement the DBConnection protocol
    - Managing backend-specific configuration
    """
    
    def initialize(self) -> None:
        """Initialize the database schema and run any necessary migrations.
        
        This method should:
        - Create necessary tables if they don't exist
        - Run any pending migrations
        - Set up indexes and constraints
        
        Raises:
            Exception: If initialization fails
        """
        ...
    
    def get_connection(self) -> DBConnection:
        """Create and return a new database connection.
        
        The returned connection must implement the DBConnection protocol,
        providing at minimum:
        - execute(sql, parameters) method
        - commit() method
        - close() method
        
        Returns:
            A connection object implementing DBConnection protocol
            
        Raises:
            Exception: If connection cannot be established
        """
        ...
