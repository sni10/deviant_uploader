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
from .stats_repository import StatsRepository

__all__ = [
    "BaseRepository",
    "UserRepository",
    "OAuthTokenRepository", 
    "GalleryRepository",
    "DeviationRepository",
    "StatsRepository",
    "create_repositories"
]


def create_repositories(
    db_path: str | Path,
) -> tuple[UserRepository, OAuthTokenRepository, GalleryRepository, DeviationRepository, StatsRepository]:
    """
    Factory function to create all repositories with shared database connection.
    
    This ensures all repositories use the same connection and transaction context,
    following the Unit of Work pattern.
    
    Args:
        db_path: Path to SQLite database file
        
    Returns:
        Tuple of (UserRepository, OAuthTokenRepository, GalleryRepository, DeviationRepository)
    """
    conn = init_database(db_path)
    
    user_repo = UserRepository(conn)
    token_repo = OAuthTokenRepository(conn)
    gallery_repo = GalleryRepository(conn)
    deviation_repo = DeviationRepository(conn)
    stats_repo = StatsRepository(conn)
    
    return user_repo, token_repo, gallery_repo, deviation_repo, stats_repo
