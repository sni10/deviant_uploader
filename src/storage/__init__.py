"""
Storage layer with database abstraction supporting SQLite and PostgreSQL.

Follows DDD and SOLID principles with separate repositories for each domain entity.
Database backend is selected via DATABASE_TYPE configuration.
"""
from .database import init_database, get_connection, get_database_adapter
from .base_repository import BaseRepository, DBConnection
from .user_repository import UserRepository
from .oauth_token_repository import OAuthTokenRepository
from .gallery_repository import GalleryRepository
from .deviation_repository import DeviationRepository
from .deviation_stats_repository import DeviationStatsRepository
from .stats_snapshot_repository import StatsSnapshotRepository
from .user_stats_snapshot_repository import UserStatsSnapshotRepository
from .deviation_metadata_repository import DeviationMetadataRepository

__all__ = [
    "BaseRepository",
    "DBConnection",
    "UserRepository",
    "OAuthTokenRepository", 
    "GalleryRepository",
    "DeviationRepository",
    "DeviationStatsRepository",
    "StatsSnapshotRepository",
    "UserStatsSnapshotRepository",
    "DeviationMetadataRepository",
    "create_repositories",
    "get_connection",
    "get_database_adapter",
    "init_database",
]


def create_repositories() -> tuple[
    UserRepository, 
    OAuthTokenRepository, 
    GalleryRepository, 
    DeviationRepository,
    DeviationStatsRepository,
    StatsSnapshotRepository,
    UserStatsSnapshotRepository,
    DeviationMetadataRepository
]:
    """
    Factory function to create all repositories with shared database connection.
    
    This ensures all repositories use the same connection and transaction context,
    following the Unit of Work pattern.
    
    The database backend (SQLite or PostgreSQL) is selected automatically based on
    the DATABASE_TYPE configuration setting.
    
    Returns:
        Tuple of (UserRepository, OAuthTokenRepository, GalleryRepository, 
                  DeviationRepository, DeviationStatsRepository, StatsSnapshotRepository,
                  UserStatsSnapshotRepository, DeviationMetadataRepository)
        
    Example:
        >>> (user_repo, token_repo, gallery_repo, deviation_repo,
        ...  deviation_stats_repo, stats_snapshot_repo, 
        ...  user_stats_snapshot_repo, deviation_metadata_repo) = create_repositories()
        >>> # ... use repositories
        >>> token_repo.close()  # All repos share same connection
    """
    conn = get_connection()
    
    user_repo = UserRepository(conn)
    token_repo = OAuthTokenRepository(conn)
    gallery_repo = GalleryRepository(conn)
    deviation_repo = DeviationRepository(conn)
    deviation_stats_repo = DeviationStatsRepository(conn)
    stats_snapshot_repo = StatsSnapshotRepository(conn)
    user_stats_snapshot_repo = UserStatsSnapshotRepository(conn)
    deviation_metadata_repo = DeviationMetadataRepository(conn)
    
    return (
        user_repo, token_repo, gallery_repo, deviation_repo,
        deviation_stats_repo, stats_snapshot_repo,
        user_stats_snapshot_repo, deviation_metadata_repo
    )
