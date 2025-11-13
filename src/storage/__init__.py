"""
Storage layer for SQLite database.

Follows DDD and SOLID principles with separate repositories for each domain entity.
"""
from pathlib import Path
from sqlite3 import Connection

from .database import init_database
from .base_repository import BaseRepository
from .user_repository import UserRepository
from .oauth_token_repository import OAuthTokenRepository
from .gallery_repository import GalleryRepository
from .deviation_repository import DeviationRepository

__all__ = [
    "BaseRepository",
    "UserRepository",
    "OAuthTokenRepository", 
    "GalleryRepository",
    "DeviationRepository",
    "create_repositories"
]


def create_repositories(db_path: str | Path) -> tuple[UserRepository, OAuthTokenRepository, GalleryRepository, DeviationRepository]:
    """
    Factory function to create all repositories with shared database connection.
    
    This ensures all repositories use the same connection and transaction context,
    following the Unit of Work pattern.
    
    Args:
        db_path: Path to SQLite database file
        
    Returns:
        Tuple of (UserRepository, OAuthTokenRepository, GalleryRepository, DeviationRepository)
        
    Example:
        >>> user_repo, token_repo, gallery_repo, deviation_repo = create_repositories("data/deviant.db")
        >>> # Use repositories...
        >>> user_repo.close()  # Closes connection for all repositories
    """
    conn = init_database(db_path)
    
    user_repo = UserRepository(conn)
    token_repo = OAuthTokenRepository(conn)
    gallery_repo = GalleryRepository(conn)
    deviation_repo = DeviationRepository(conn)
    
    return user_repo, token_repo, gallery_repo, deviation_repo
