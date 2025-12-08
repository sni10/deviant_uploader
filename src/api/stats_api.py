"""Flask API for stats dashboard (browse-only, no uploads).

Provides two endpoints:
- GET /api/stats       → current deviation stats with daily diffs
- POST /api/stats/sync → trigger sync for a gallery folder (body: {"folderid": "...", "username": "optional"})

Serves the static dashboard page at `/` from the project-level `static/stats.html`.

Architecture:
- Uses Flask application factory pattern (create_app)
- Per-request database connections via Flask's g object
- Proper connection cleanup in teardown_appcontext
"""

from pathlib import Path
import logging
from flask import Flask, jsonify, request, send_from_directory, g

from ..config import get_config, Config
from ..log.logger import setup_logger
from ..storage import get_connection
from ..storage.user_repository import UserRepository
from ..storage.oauth_token_repository import OAuthTokenRepository
from ..storage.gallery_repository import GalleryRepository
from ..storage.deviation_repository import DeviationRepository
from ..storage.deviation_stats_repository import DeviationStatsRepository
from ..storage.stats_snapshot_repository import StatsSnapshotRepository
from ..storage.user_stats_snapshot_repository import UserStatsSnapshotRepository
from ..storage.deviation_metadata_repository import DeviationMetadataRepository
from ..service.auth_service import AuthService
from ..service.stats_service import StatsService


# Resolve paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = PROJECT_ROOT / "static"


def get_repositories():
    """
    Get or create repositories for the current request.
    
    Uses Flask's g object to store per-request database connection and repositories.
    Creates them lazily on first access within a request.
    
    Returns:
        Tuple of (user_repo, token_repo, gallery_repo, deviation_repo, 
                  deviation_stats_repo, stats_snapshot_repo, 
                  user_stats_snapshot_repo, deviation_metadata_repo)
    """
    if 'repositories' not in g:
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
            user_repo, token_repo, gallery_repo, deviation_repo,
            deviation_stats_repo, stats_snapshot_repo, 
            user_stats_snapshot_repo, deviation_metadata_repo
        )
    
    return g.repositories


def get_services():
    """
    Get or create services for the current request.
    
    Services are created lazily and tied to the current request's repositories.
    
    Returns:
        Tuple of (auth_service, stats_service)
    """
    if 'services' not in g:
        (user_repo, token_repo, gallery_repo, deviation_repo,
         deviation_stats_repo, stats_snapshot_repo, 
         user_stats_snapshot_repo, deviation_metadata_repo) = get_repositories()
        logger = g.logger
        
        auth_service = AuthService(token_repo, logger)
        stats_service = StatsService(
            deviation_stats_repo,
            stats_snapshot_repo,
            user_stats_snapshot_repo,
            deviation_metadata_repo,
            deviation_repo,
            logger
        )
        
        g.services = (auth_service, stats_service)
    
    return g.services


def create_app(config: Config = None) -> Flask:
    """
    Flask application factory.
    
    Creates and configures the Flask application with proper dependency injection
    and per-request resource management.
    
    Args:
        config: Optional Config instance. If None, uses get_config()
        
    Returns:
        Configured Flask application instance
        
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
    app.config['APP_CONFIG'] = config
    app.config['APP_LOGGER'] = logger
    
    @app.before_request
    def before_request():
        """Set up request context with logger."""
        g.logger = app.config['APP_LOGGER']
    
    @app.teardown_appcontext
    def teardown_db(exception=None):
        """Close database connection at the end of request."""
        conn = g.pop('connection', None)
        if conn is not None:
            conn.close()
            if exception:
                g.logger.warning(f"Request ended with exception: {exception}")
    
    @app.route("/")
    def index():
        """Serve dashboard page."""
        return send_from_directory(STATIC_DIR, "stats.html")

    @app.route("/api/stats", methods=["GET"])
    def get_stats():
        """Return current stats with diffs."""
        try:
            auth_service, stats_service = get_services()
            data = stats_service.get_stats_with_diff()
            return jsonify({"success": True, "data": data})
        except Exception as exc:  # noqa: BLE001 (surface error to caller)
            g.logger.error("Failed to fetch stats", exc_info=exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/stats/sync", methods=["POST"])
    def sync_stats():
        """Trigger sync from DeviantArt for a given gallery folder."""
        try:
            payload = request.get_json(silent=True) or {}
            folderid = (payload.get("folderid") or "").strip()
            username = payload.get("username")
            include_deviations = bool(payload.get("include_deviations"))

            if not folderid:
                return jsonify({"success": False, "error": "folderid is required"}), 400

            auth_service, stats_service = get_services()

            # Ensure authentication (refreshes if needed; may prompt user if absent)
            if not auth_service.ensure_authenticated():
                return jsonify({"success": False, "error": "Not authenticated"}), 401

            access_token = auth_service.get_valid_token()
            if not access_token:
                return jsonify({"success": False, "error": "Failed to obtain access token"}), 401

            result = stats_service.sync_gallery(
                access_token,
                folderid,
                username=username,
                include_deviations=include_deviations,
            )
            return jsonify({"success": True, "data": result})
        except Exception as exc:  # noqa: BLE001 (surface error to caller)
            g.logger.error("Failed to sync stats", exc_info=exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/options", methods=["GET"])
    def get_options():
        """Return user and gallery options from the database."""
        try:
            user_repo, token_repo, gallery_repo, deviation_repo, stats_repo = get_repositories()
            users = user_repo.get_all_users()
            galleries = gallery_repo.get_all_galleries()

            return jsonify(
                {
                    "success": True,
                    "data": {
                        "users": [
                            {
                                "id": user.user_db_id,
                                "username": user.username,
                                "userid": user.userid,
                            }
                            for user in users
                        ],
                        "galleries": [
                            {
                                "id": gallery.gallery_db_id,
                                "folderid": gallery.folderid,
                                "name": gallery.name,
                                "size": gallery.size,
                                "parent": gallery.parent,
                            }
                            for gallery in galleries
                        ],
                    }
                }
            )
        except Exception as exc:  # noqa: BLE001
            g.logger.error("Failed to fetch options", exc_info=exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/user_stats/latest", methods=["GET"])
    def get_latest_user_stats():
        """Return the latest user stats snapshot for a given username."""
        try:
            username = (request.args.get("username") or "").strip()
            if not username:
                return jsonify({"success": False, "error": "username is required"}), 400

            user_repo, token_repo, gallery_repo, deviation_repo, stats_repo = get_repositories()
            snapshot = stats_repo.get_latest_user_stats_snapshot(username)
            return jsonify({"success": True, "data": snapshot})
        except Exception as exc:  # noqa: BLE001
            g.logger.error("Failed to fetch latest user stats", exc_info=exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/static/<path:filename>")
    def serve_static(filename: str):
        """Serve other static assets if needed."""
        return send_from_directory(STATIC_DIR, filename)
    
    return app


def get_app() -> Flask:
    """
    Expose app for external runners (e.g., gunicorn).
    
    Returns:
        Flask application instance created via factory
    """
    return create_app()


__all__ = ["create_app", "get_app"]