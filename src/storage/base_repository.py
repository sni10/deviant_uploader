"""Base repository with common functionality following DDD and SOLID principles."""
from abc import ABC
from sqlite3 import Connection
from pathlib import Path


class BaseRepository(ABC):
    """
    Abstract base repository providing common database operations.
    
    Follows SOLID principles:
    - Single Responsibility: Base functionality for all repositories
    - Open/Closed: Open for extension, closed for modification
    - Liskov Substitution: All repositories can be used through this interface
    - Interface Segregation: Only common operations in base
    - Dependency Inversion: Depends on abstraction (Connection)
    """
    
    def __init__(self, conn: Connection):
        """
        Initialize repository with database connection.
        
        Args:
            conn: SQLite database connection
        """
        self._conn = conn
    
    @property
    def conn(self) -> Connection:
        """Get database connection."""
        return self._conn
    
    def close(self) -> None:
        """
        Close database connection.
        
        Note: In production, connection management should be handled
        by a connection pool or context manager.
        """
        if self._conn:
            self._conn.close()
