"""Flask API for stats dashboard and upload admin interface.

Provides endpoints:
- GET /api/stats       → current deviation stats with daily diffs
- POST /api/stats/sync → trigger sync for a gallery folder (body: {"folderid": "...", "username": "optional"})
- GET /api/admin/*     → upload admin API endpoints
- GET /upload_admin.html → upload admin interface

Serves static pages:
- `/` → stats.html (statistics dashboard)
- `/upload_admin.html` → upload_admin.html (upload interface)

Architecture:
- Uses Flask application factory pattern (create_app)
- Per-request database connections via Flask's g object
- Proper connection cleanup in teardown_appcontext
"""

import logging
from pathlib import Path

from flask import Flask, g

from .stats_routes import (
    register_charts_routes,
    register_mass_fave_routes,
    register_pages_routes,
    register_profile_message_routes,
    register_stats_routes,
    register_thumbnail_routes,
    register_upload_admin_routes,
)
from ..config import Config, get_config
from ..log.logger import setup_logger
from ..storage import get_connection
from ..storage.deviation_metadata_repository import DeviationMetadataRepository
from ..storage.feed_deviation_repository import FeedDeviationRepository
from ..storage.gallery_repository import GalleryRepository
from ..storage.oauth_token_repository import OAuthTokenRepository
from ..storage.preset_repository import PresetRepository
from ..storage.profile_message_log_repository import ProfileMessageLogRepository
from ..storage.profile_message_repository import ProfileMessageRepository
from ..storage.deviation_repository import DeviationRepository
from ..storage.deviation_stats_repository import DeviationStatsRepository
from ..storage.stats_snapshot_repository import StatsSnapshotRepository
from ..storage.user_repository import UserRepository
from ..storage.user_stats_snapshot_repository import UserStatsSnapshotRepository
from ..storage.watcher_repository import WatcherRepository
from ..service.auth_service import AuthService
from ..service.mass_fave_service import MassFaveService
from ..service.profile_message_service import ProfileMessageService
from ..service.stats_service import StatsService
from ..service.uploader import UploaderService


# Resolve paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = PROJECT_ROOT / "static"


def get_repositories() -> tuple[
    UserRepository,
    OAuthTokenRepository,
    GalleryRepository,
    DeviationRepository,
    DeviationStatsRepository,
    StatsSnapshotRepository,
    UserStatsSnapshotRepository,
    DeviationMetadataRepository,
]:
    """Get or create repositories for the current request.

    Uses Flask's g object to store per-request database connection and repositories.
    Creates them lazily on first access within a request.

    Returns:
        Tuple of (user_repo, token_repo, gallery_repo, deviation_repo,
        deviation_stats_repo, stats_snapshot_repo, user_stats_snapshot_repo,
        deviation_metadata_repo)
    """
    if "repositories" not in g:
        # Create new connection for this request
        conn = get_connection()
        g.connection = conn

        # Create repositories with this connection
        user_repo = UserRepository(conn)
        token_repo = OAuthTokenRepository(conn)
        gallery_repo = GalleryRepository(conn)
        deviation_repo = DeviationRepository(conn)
        deviation_stats_repo = DeviationStatsRepository(conn)
        stats_snapshot_repo = StatsSnapshotRepository(conn)
        user_stats_snapshot_repo = UserStatsSnapshotRepository(conn)
        deviation_metadata_repo = DeviationMetadataRepository(conn)

        g.repositories = (
            user_repo,
            token_repo,
            gallery_repo,
            deviation_repo,
            deviation_stats_repo,
            stats_snapshot_repo,
            user_stats_snapshot_repo,
            deviation_metadata_repo,
        )

    return g.repositories


def get_services() -> tuple[AuthService, StatsService]:
    """Get or create services for the current request.

    Services are created lazily and tied to the current request's repositories.

    Returns:
        Tuple of (auth_service, stats_service)
    """
    if "services" not in g:
        (
            _user_repo,
            token_repo,
            _gallery_repo,
            deviation_repo,
            deviation_stats_repo,
            stats_snapshot_repo,
            user_stats_snapshot_repo,
            deviation_metadata_repo,
        ) = get_repositories()
        logger = g.logger

        auth_service = AuthService(token_repo, logger)
        stats_service = StatsService(
            deviation_stats_repo,
            stats_snapshot_repo,
            user_stats_snapshot_repo,
            deviation_metadata_repo,
            deviation_repo,
            logger,
        )

        g.services = (auth_service, stats_service)

    return g.services


def get_upload_services() -> tuple[UploaderService, PresetRepository, DeviationRepository]:
    """Get or create upload-related services for the current request.

    Services are created lazily and tied to the current request's repositories.

    Returns:
        Tuple of (uploader_service, preset_repo, deviation_repo)
    """
    if "upload_services" not in g:
        (
            _user_repo,
            token_repo,
            gallery_repo,
            deviation_repo,
            _deviation_stats_repo,
            _stats_snapshot_repo,
            _user_stats_snapshot_repo,
            _deviation_metadata_repo,
        ) = get_repositories()
        logger = g.logger

        preset_repo = PresetRepository(g.connection)
        auth_service = AuthService(token_repo, logger)
        uploader_service = UploaderService(
            deviation_repo,
            gallery_repo,
            auth_service,
            preset_repo,
            logger,
        )

        g.upload_services = (uploader_service, preset_repo, deviation_repo)

    return g.upload_services


def get_mass_fave_service() -> MassFaveService:
    """Get or create mass fave service as application-level singleton.

    The MassFaveService runs a background worker thread that must persist
    beyond individual HTTP requests. Therefore, it uses its own dedicated
    database connection that is NOT closed by teardown_db().

    Returns:
        MassFaveService instance (singleton per application)
    """
    from flask import current_app

    if "MASS_FAVE_SERVICE" not in current_app.config:
        # Create dedicated connection for the worker (not tied to request lifecycle)
        worker_connection = get_connection()
        feed_deviation_repo = FeedDeviationRepository(worker_connection)
        logger = current_app.config["APP_LOGGER"]
        mass_fave_service = MassFaveService(feed_deviation_repo, logger)
        current_app.config["MASS_FAVE_SERVICE"] = mass_fave_service

    return current_app.config["MASS_FAVE_SERVICE"]


def get_stats_sync_service() -> StatsService:
    """Get or create stats sync service as application-level singleton.

    The StatsService worker runs a background thread that must persist
    beyond individual HTTP requests. Therefore, it uses its own dedicated
    database connections that are NOT closed by teardown_db().

    Returns:
        StatsService instance (singleton per application)
    """
    from flask import current_app

    if "STATS_SYNC_SERVICE" not in current_app.config:
        # Create dedicated connections for the worker (not tied to request lifecycle)
        worker_connection = get_connection()
        deviation_stats_repo = DeviationStatsRepository(worker_connection)
        stats_snapshot_repo = StatsSnapshotRepository(worker_connection)
        user_stats_snapshot_repo = UserStatsSnapshotRepository(worker_connection)
        deviation_metadata_repo = DeviationMetadataRepository(worker_connection)
        deviation_repo = DeviationRepository(worker_connection)
        gallery_repo = GalleryRepository(worker_connection)
        logger = current_app.config["APP_LOGGER"]

        stats_service = StatsService(
            deviation_stats_repo,
            stats_snapshot_repo,
            user_stats_snapshot_repo,
            deviation_metadata_repo,
            deviation_repo,
            logger,
            gallery_repository=gallery_repo,
        )
        current_app.config["STATS_SYNC_SERVICE"] = stats_service

    return current_app.config["STATS_SYNC_SERVICE"]


def get_profile_message_service() -> ProfileMessageService:
    """Get or create profile message service as application-level singleton.

    The ProfileMessageService runs a background worker thread that must persist
    beyond individual HTTP requests. Therefore, it uses its own dedicated
    database connections that are NOT closed by teardown_db().

    Returns:
        ProfileMessageService instance (singleton per application)
    """
    from flask import current_app

    if "PROFILE_MESSAGE_SERVICE" not in current_app.config:
        # Create dedicated connections for the worker (not tied to request lifecycle)
        worker_conn1 = get_connection()
        worker_conn2 = get_connection()
        worker_conn3 = get_connection()
        message_repo = ProfileMessageRepository(worker_conn1)
        log_repo = ProfileMessageLogRepository(worker_conn2)
        watcher_repo = WatcherRepository(worker_conn3)
        logger = current_app.config["APP_LOGGER"]
        profile_message_service = ProfileMessageService(
            message_repo, log_repo, watcher_repo, logger
        )
        current_app.config["PROFILE_MESSAGE_SERVICE"] = profile_message_service

    return current_app.config["PROFILE_MESSAGE_SERVICE"]


def create_app(config: Config | None = None) -> Flask:
    """Create and configure the combined Flask application.

    Creates and configures the Flask application with proper dependency injection
    and per-request resource management.

    Args:
        config: Optional Config instance. If None, uses get_config().

    Returns:
        Configured Flask application instance.

    Example:
        >>> app = create_app()
        >>> app.run(host="0.0.0.0", port=5000)
    """
    # Initialize config
    if config is None:
        config = get_config()

    # Setup logger for this app instance
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logger = setup_logger(name="stats_api", log_dir=config.log_dir, level=log_level)

    # Create Flask app
    app = Flask(__name__, static_folder=str(STATIC_DIR))

    # Store config and logger in app context for access in requests
    app.config["APP_CONFIG"] = config
    app.config["APP_LOGGER"] = logger

    @app.before_request
    def before_request():
        """Set up request context with logger."""
        g.logger = app.config["APP_LOGGER"]

    @app.teardown_appcontext
    def teardown_db(exception=None):
        """Close database connection at the end of request."""
        conn = g.pop("connection", None)
        if conn is not None:
            conn.close()
            if exception:
                g.logger.warning("Request ended with exception: %s", exception)

    register_pages_routes(app, static_dir=STATIC_DIR)
    register_stats_routes(
        app,
        get_services=get_services,
        get_repositories=get_repositories,
        get_stats_sync_service=get_stats_sync_service,
    )
    register_charts_routes(app, get_services=get_services)
    register_upload_admin_routes(
        app,
        get_upload_services=get_upload_services,
        get_repositories=get_repositories,
    )
    register_mass_fave_routes(
        app,
        get_services=get_services,
        get_mass_fave_service=get_mass_fave_service,
    )
    register_profile_message_routes(
        app,
        get_services=get_services,
        get_profile_message_service=get_profile_message_service,
    )
    register_thumbnail_routes(
        app,
        config=config,
        project_root=PROJECT_ROOT,
        get_upload_services=get_upload_services,
    )
    return app


def get_app() -> Flask:
    """
    Expose app for external runners (e.g., gunicorn).
    
    Returns:
        Flask application instance created via factory
    """
    return create_app()


__all__ = ["create_app", "get_app"]
