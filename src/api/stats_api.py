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

from pathlib import Path
import logging
from flask import Flask, jsonify, request, send_from_directory, send_file, g

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
from ..storage.preset_repository import PresetRepository
from ..storage.feed_deviation_repository import FeedDeviationRepository
from ..storage.profile_message_repository import ProfileMessageRepository
from ..storage.profile_message_log_repository import ProfileMessageLogRepository
from ..service.auth_service import AuthService
from ..service.stats_service import StatsService
from ..service.uploader import UploaderService
from ..service.mass_fave_service import MassFaveService
from ..service.profile_message_service import ProfileMessageService
from ..domain.models import UploadPreset


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


def get_upload_services():
    """
    Get or create upload-related services for the current request.

    Services are created lazily and tied to the current request's repositories.

    Returns:
        Tuple of (uploader_service, preset_repo, deviation_repo)
    """
    if 'upload_services' not in g:
        (user_repo, token_repo, gallery_repo, deviation_repo,
         deviation_stats_repo, stats_snapshot_repo,
         user_stats_snapshot_repo, deviation_metadata_repo) = get_repositories()
        logger = g.logger

        preset_repo = PresetRepository(g.connection)
        auth_service = AuthService(token_repo, logger)
        uploader_service = UploaderService(
            deviation_repo,
            gallery_repo,
            auth_service,
            preset_repo,
            logger
        )

        g.upload_services = (uploader_service, preset_repo, deviation_repo)

    return g.upload_services


def get_mass_fave_service():
    """
    Get or create mass fave service as application-level singleton.

    The MassFaveService runs a background worker thread that must persist
    beyond individual HTTP requests. Therefore, it uses its own dedicated
    database connection that is NOT closed by teardown_db().

    Returns:
        MassFaveService instance (singleton per application)
    """
    from flask import current_app

    if 'MASS_FAVE_SERVICE' not in current_app.config:
        # Create dedicated connection for the worker (not tied to request lifecycle)
        worker_connection = get_connection()
        feed_deviation_repo = FeedDeviationRepository(worker_connection)
        logger = current_app.config['APP_LOGGER']
        mass_fave_service = MassFaveService(feed_deviation_repo, logger)
        current_app.config['MASS_FAVE_SERVICE'] = mass_fave_service

    return current_app.config['MASS_FAVE_SERVICE']


def get_profile_message_service():
    """
    Get or create profile message service as application-level singleton.

    The ProfileMessageService runs a background worker thread that must persist
    beyond individual HTTP requests. Therefore, it uses its own dedicated
    database connections that are NOT closed by teardown_db().

    Returns:
        ProfileMessageService instance (singleton per application)
    """
    from flask import current_app

    if 'PROFILE_MESSAGE_SERVICE' not in current_app.config:
        # Create dedicated connections for the worker (not tied to request lifecycle)
        worker_conn1 = get_connection()
        worker_conn2 = get_connection()
        message_repo = ProfileMessageRepository(worker_conn1)
        log_repo = ProfileMessageLogRepository(worker_conn2)
        logger = current_app.config['APP_LOGGER']
        profile_message_service = ProfileMessageService(message_repo, log_repo, logger)
        current_app.config['PROFILE_MESSAGE_SERVICE'] = profile_message_service

    return current_app.config['PROFILE_MESSAGE_SERVICE']


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
            )
            return jsonify({"success": True, "data": result})
        except Exception as exc:  # noqa: BLE001 (surface error to caller)
            g.logger.error("Failed to sync stats", exc_info=exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/options", methods=["GET"])
    def get_options():
        """Return user and gallery options from the database."""
        try:
            (user_repo, token_repo, gallery_repo, deviation_repo,
             deviation_stats_repo, stats_snapshot_repo, 
             user_stats_snapshot_repo, deviation_metadata_repo) = get_repositories()
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

            (user_repo, token_repo, gallery_repo, deviation_repo,
             deviation_stats_repo, stats_snapshot_repo, 
             user_stats_snapshot_repo, deviation_metadata_repo) = get_repositories()
            snapshot = user_stats_snapshot_repo.get_latest_user_stats_snapshot(username)
            return jsonify({"success": True, "data": snapshot})
        except Exception as exc:  # noqa: BLE001
            g.logger.error("Failed to fetch latest user stats", exc_info=exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/static/<path:filename>")
    def serve_static(filename: str):
        """Serve other static assets if needed."""
        return send_from_directory(STATIC_DIR, filename)

    # ========== CHARTS API ROUTES ==========

    @app.route('/charts.html')
    def charts_page():
        """Serve charts visualization page."""
        return send_from_directory(STATIC_DIR, "charts.html")

    @app.route("/api/charts/deviations", methods=["GET"])
    def get_deviations_for_charts():
        """Return list of all deviations for chart filtering."""
        try:
            auth_service, stats_service = get_services()
            deviations = stats_service.get_deviations_list()
            return jsonify({"success": True, "data": deviations})
        except Exception as exc:  # noqa: BLE001
            g.logger.error("Failed to fetch deviations list", exc_info=exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/charts/aggregated", methods=["GET"])
    def get_aggregated_chart_data():
        """Return aggregated stats for charts.

        Query params:
            period: Number of days (default: 7)
            deviation_ids: Comma-separated deviation IDs (optional)
        """
        try:
            period_days = int(request.args.get("period", 7))
            deviation_ids_param = request.args.get("deviation_ids", "")

            # Parse deviation IDs from comma-separated string
            deviation_ids = None
            if deviation_ids_param and deviation_ids_param.strip():
                deviation_ids = [
                    did.strip()
                    for did in deviation_ids_param.split(",")
                    if did.strip()
                ]

            auth_service, stats_service = get_services()
            data = stats_service.get_aggregated_stats(period_days, deviation_ids)
            return jsonify({"success": True, "data": data})
        except Exception as exc:  # noqa: BLE001
            g.logger.error("Failed to fetch aggregated chart data", exc_info=exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/charts/user-watchers", methods=["GET"])
    def get_user_watchers_chart_data():
        """Return user watchers history for charts.

        Query params:
            username: DeviantArt username (required)
            period: Number of days (default: 7)
        """
        try:
            username = request.args.get("username", "").strip()
            if not username:
                return jsonify({"success": False, "error": "username is required"}), 400

            period_days = int(request.args.get("period", 7))

            auth_service, stats_service = get_services()
            data = stats_service.get_user_watchers_history(username, period_days)
            return jsonify({"success": True, "data": data})
        except Exception as exc:  # noqa: BLE001
            g.logger.error("Failed to fetch user watchers chart data", exc_info=exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    # ========== UPLOAD ADMIN ROUTES ==========
    
    @app.route('/upload_admin.html')
    def upload_admin_html():
        """Serve upload admin HTML page."""
        return send_from_directory(STATIC_DIR, "upload_admin.html")
    
    @app.route('/admin/upload')
    def upload_admin_page():
        """Serve upload admin HTML page (alternative URL)."""
        return send_from_directory(STATIC_DIR, "upload_admin.html")
    
    @app.route('/api/admin/scan', methods=['POST'])
    def scan_files():
        """
        Scan upload folder and create draft deviations.
        
        Returns:
            JSON list of draft deviations with metadata
        """
        try:
            uploader_service, _, _ = get_upload_services()
            drafts = uploader_service.scan_and_create_drafts()
            
            # Convert to JSON-serializable format
            result = []
            for draft in drafts:
                result.append({
                    'id': draft.deviation_id,
                    'filename': draft.filename,
                    'title': draft.title,
                    'file_path': draft.file_path,
                    'status': draft.status.value if hasattr(draft.status, 'value') else draft.status,
                    'itemid': draft.itemid,
                    'deviationid': draft.deviationid,
                    'url': draft.url
                })
            
            return jsonify({
                'success': True,
                'drafts': result,
                'count': len(result)
            })
        except Exception as e:
            g.logger.error(f"Scan failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/admin/drafts', methods=['GET'])
    def get_drafts():
        """
        Get all draft deviations from database.
        
        Returns:
            JSON list of deviations
        """
        try:
            _, _, deviation_repo = get_upload_services()
            
            # Get all deviations (could filter by status if needed)
            all_deviations = deviation_repo.get_all_deviations()
            
            # Convert to JSON-serializable format
            result = []
            for dev in all_deviations:
                result.append({
                    'id': dev.deviation_id,
                    'filename': dev.filename,
                    'title': dev.title,
                    'file_path': dev.file_path,
                    'status': dev.status.value if hasattr(dev.status, 'value') else dev.status,
                    'itemid': dev.itemid,
                    'deviationid': dev.deviationid,
                    'url': dev.url,
                    'error': dev.error,
                    'tags': dev.tags,
                    'is_mature': dev.is_mature
                })
            
            return jsonify({
                'success': True,
                'deviations': result,
                'count': len(result)
            })
        except Exception as e:
            g.logger.error(f"Get drafts failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/admin/galleries', methods=['GET'])
    def get_galleries_for_admin():
        """
        Get all galleries for dropdown selection.
        
        Returns:
            JSON list of galleries
        """
        try:
            (user_repo, token_repo, gallery_repo, deviation_repo,
             deviation_stats_repo, stats_snapshot_repo, 
             user_stats_snapshot_repo, deviation_metadata_repo) = get_repositories()
            galleries = gallery_repo.get_all_galleries()
            
            # Convert to JSON-serializable format
            result = []
            for gallery in galleries:
                result.append({
                    'id': gallery.gallery_db_id,
                    'folderid': gallery.folderid,
                    'name': gallery.name,
                    'size': gallery.size,
                    'parent': gallery.parent
                })
            
            return jsonify({
                'success': True,
                'galleries': result,
                'count': len(result)
            })
        except Exception as e:
            g.logger.error(f"Get galleries failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/admin/presets', methods=['GET'])
    def get_presets():
        """
        Get all presets for dropdown.
        
        Returns:
            JSON list of presets
        """
        try:
            _, preset_repo, _ = get_upload_services()
            presets = preset_repo.get_all_presets()
            
            # Convert to JSON-serializable format
            result = []
            for preset in presets:
                result.append({
                    'id': preset.preset_id,
                    'name': preset.name,
                    'description': preset.description,
                    'base_title': preset.base_title,
                    'title_increment_start': preset.title_increment_start,
                    'last_used_increment': preset.last_used_increment,
                    'is_default': preset.is_default,
                    'tags': preset.tags,
                    'is_mature': preset.is_mature,
                    'gallery_folderid': preset.gallery_folderid
                })
            
            return jsonify({
                'success': True,
                'presets': result,
                'count': len(result)
            })
        except Exception as e:
            g.logger.error(f"Get presets failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/admin/presets', methods=['POST'])
    def save_preset():
        """
        Save or update a preset.
        
        Expects JSON body with preset fields.
        
        Returns:
            JSON with preset ID
        """
        try:
            data = request.get_json()
            
            if not data.get('name') or not data.get('base_title'):
                return jsonify({'success': False, 'error': 'Name and base_title are required'}), 400
            
            _, preset_repo, _ = get_upload_services()
            
            # Create UploadPreset object
            preset = UploadPreset(
                name=data['name'],
                description=data.get('description'),
                base_title=data['base_title'],
                title_increment_start=data.get('title_increment_start', 1),
                last_used_increment=data.get('last_used_increment', 1),
                artist_comments=data.get('artist_comments'),
                tags=data.get('tags', []),
                is_ai_generated=data.get('is_ai_generated', True),
                noai=data.get('noai', False),
                is_dirty=data.get('is_dirty', False),
                is_mature=data.get('is_mature', False),
                mature_level=data.get('mature_level'),
                mature_classification=data.get('mature_classification', []),
                feature=data.get('feature', True),
                allow_comments=data.get('allow_comments', True),
                display_resolution=data.get('display_resolution', 0),
                allow_free_download=data.get('allow_free_download', False),
                add_watermark=data.get('add_watermark', False),
                gallery_folderid=data.get('gallery_folderid'),
                is_default=data.get('is_default', False)
            )
            
            preset_id = preset_repo.save_preset(preset)
            
            return jsonify({
                'success': True,
                'preset_id': preset_id,
                'message': 'Preset saved successfully'
            })
        except Exception as e:
            g.logger.error(f"Save preset failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/admin/apply-preset', methods=['POST'])
    def apply_preset():
        """
        Apply preset to selected deviations.
        
        Expects JSON: {"preset_id": X, "deviation_ids": [1,2,3]}
        
        Returns:
            JSON with success status
        """
        try:
            data = request.get_json()
            preset_id = data.get('preset_id')
            deviation_ids = data.get('deviation_ids', [])
            
            if not preset_id or not deviation_ids:
                return jsonify({'success': False, 'error': 'preset_id and deviation_ids required'}), 400
            
            uploader_service, preset_repo, deviation_repo = get_upload_services()
            
            # Get preset
            preset = preset_repo.get_preset_by_id(preset_id)
            if not preset:
                return jsonify({'success': False, 'error': 'Preset not found'}), 404
            
            # Apply preset to each deviation
            applied = []
            for dev_id in deviation_ids:
                deviation = deviation_repo.get_deviation_by_id(dev_id)
                if deviation:
                    # Get next increment
                    increment = preset_repo.increment_preset_counter(preset_id)
                    
                    # Apply preset
                    uploader_service.apply_preset_to_deviation(deviation, preset, increment)
                    
                    # Save updated deviation
                    deviation_repo.update_deviation(deviation)
                    applied.append(dev_id)
            
            return jsonify({
                'success': True,
                'applied': applied,
                'count': len(applied)
            })
        except Exception as e:
            g.logger.error(f"Apply preset failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/admin/stash', methods=['POST'])
    def stash_selected():
        """
        Stash selected deviations.
        
        Expects JSON: {"deviation_ids": [1,2,3], "preset_id": X}
        
        Returns:
            JSON with success/failed lists
        """
        try:
            data = request.get_json()
            deviation_ids = data.get('deviation_ids', [])
            preset_id = data.get('preset_id')
            
            if not deviation_ids or not preset_id:
                return jsonify({'success': False, 'error': 'deviation_ids and preset_id required'}), 400
            
            uploader_service, preset_repo, _ = get_upload_services()
            
            # Get preset
            preset = preset_repo.get_preset_by_id(preset_id)
            if not preset:
                return jsonify({'success': False, 'error': 'Preset not found'}), 404
            
            # Perform batch stash
            results = uploader_service.batch_stash(deviation_ids, preset)
            
            return jsonify({
                'success': True,
                'results': results
            })
        except Exception as e:
            g.logger.error(f"Stash failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/admin/publish', methods=['POST'])
    def publish_selected():
        """
        Publish stashed deviations.
        
        Expects JSON: {"deviation_ids": [1,2,3]}
        
        Returns:
            JSON with success/failed lists
        """
        try:
            data = request.get_json()
            deviation_ids = data.get('deviation_ids', [])
            
            if not deviation_ids:
                return jsonify({'success': False, 'error': 'deviation_ids required'}), 400
            
            uploader_service, _, _ = get_upload_services()
            
            # Perform batch publish
            results = uploader_service.batch_publish(deviation_ids)
            
            return jsonify({
                'success': True,
                'results': results
            })
        except Exception as e:
            g.logger.error(f"Publish failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/admin/upload', methods=['POST'])
    def upload_selected():
        """
        Upload selected deviations (stash + publish in one operation).
        
        Expects JSON: {"deviation_ids": [1,2,3], "preset_id": X}
        
        Returns:
            JSON with success/failed lists
        """
        try:
            data = request.get_json()
            deviation_ids = data.get('deviation_ids', [])
            preset_id = data.get('preset_id')
            
            if not deviation_ids or not preset_id:
                return jsonify({'success': False, 'error': 'deviation_ids and preset_id required'}), 400
            
            uploader_service, preset_repo, _ = get_upload_services()
            
            # Get preset
            preset = preset_repo.get_preset_by_id(preset_id)
            if not preset:
                return jsonify({'success': False, 'error': 'Preset not found'}), 404
            
            # Perform combined upload (stash + publish)
            results = uploader_service.batch_upload(deviation_ids, preset)
            
            return jsonify({
                'success': True,
                'results': results
            })
        except Exception as e:
            g.logger.error(f"Upload failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/admin/delete', methods=['POST'])
    def delete_selected():
        """
        Delete deviations and files.
        
        Expects JSON: {"deviation_ids": [1,2,3]}
        
        Returns:
            JSON with deleted list
        """
        try:
            data = request.get_json()
            deviation_ids = data.get('deviation_ids', [])
            
            if not deviation_ids:
                return jsonify({'success': False, 'error': 'deviation_ids required'}), 400
            
            uploader_service, _, _ = get_upload_services()
            
            deleted = []
            failed = []
            
            for dev_id in deviation_ids:
                if uploader_service.delete_deviation_and_file(dev_id):
                    deleted.append(dev_id)
                else:
                    failed.append(dev_id)
            
            return jsonify({
                'success': True,
                'deleted': deleted,
                'failed': failed,
                'count': len(deleted)
            })
        except Exception as e:
            g.logger.error(f"Delete failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    # ========== AUTO FAVE ROUTES ==========

    @app.route('/mass_fave.html')
    def mass_fave_page():
        """Serve Auto Fave admin page."""
        return send_from_directory(STATIC_DIR, "mass_fave.html")

    @app.route('/api/mass-fave/collect', methods=['POST'])
    def collect_feed():
        """
        Collect deviations from feed and add to queue.

        Expects JSON: {"pages": 5}

        Returns:
            JSON with collection results
        """
        try:
            data = request.get_json() or {}
            pages = int(data.get('pages', 5))

            if pages < 1 or pages > 20:
                return jsonify({'success': False, 'error': 'Pages must be between 1 and 20'}), 400

            auth_service, _ = get_services()

            # Ensure authentication
            if not auth_service.ensure_authenticated():
                return jsonify({'success': False, 'error': 'Not authenticated'}), 401

            access_token = auth_service.get_valid_token()
            if not access_token:
                return jsonify({'success': False, 'error': 'Failed to obtain access token'}), 401

            mass_fave_service = get_mass_fave_service()
            result = mass_fave_service.collect_from_feed(access_token, pages)

            return jsonify({'success': True, 'data': result})
        except Exception as e:
            g.logger.error(f"Feed collection failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/mass-fave/worker/start', methods=['POST'])
    def start_worker():
        """
        Start background worker to process fave queue.

        Returns:
            JSON with start status
        """
        try:
            auth_service, _ = get_services()

            # Ensure authentication
            if not auth_service.ensure_authenticated():
                return jsonify({'success': False, 'error': 'Not authenticated'}), 401

            access_token = auth_service.get_valid_token()
            if not access_token:
                return jsonify({'success': False, 'error': 'Failed to obtain access token'}), 401

            mass_fave_service = get_mass_fave_service()
            result = mass_fave_service.start_worker(access_token)

            return jsonify(result)
        except Exception as e:
            g.logger.error(f"Worker start failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/mass-fave/worker/stop', methods=['POST'])
    def stop_worker():
        """
        Stop background worker.

        Returns:
            JSON with stop status
        """
        try:
            mass_fave_service = get_mass_fave_service()
            result = mass_fave_service.stop_worker()

            return jsonify(result)
        except Exception as e:
            g.logger.error(f"Worker stop failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/mass-fave/status', methods=['GET'])
    def get_worker_status():
        """
        Get worker and queue status.

        Returns:
            JSON with status information
        """
        try:
            mass_fave_service = get_mass_fave_service()
            status = mass_fave_service.get_worker_status()

            return jsonify({'success': True, 'data': status})
        except Exception as e:
            g.logger.error(f"Get worker status failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/mass-fave/reset-failed', methods=['POST'])
    def reset_failed_deviations():
        """
        Reset all failed deviations back to pending status.

        Returns:
            JSON with reset count
        """
        try:
            mass_fave_service = get_mass_fave_service()
            result = mass_fave_service.reset_failed_deviations()

            return jsonify(result)
        except Exception as e:
            g.logger.error(f"Reset failed deviations failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    # ========== PROFILE MESSAGE BROADCASTING ROUTES ==========

    @app.route('/profile_broadcast.html')
    def profile_broadcast_page():
        """Serve Profile Message Broadcasting page."""
        return send_from_directory(STATIC_DIR, "profile_broadcast.html")

    @app.route('/api/profile-messages', methods=['GET'])
    def get_profile_messages():
        """Get all profile message templates.

        Returns:
            JSON with list of message templates
        """
        try:
            service = get_profile_message_service()
            messages = service.message_repo.get_all_messages()

            return jsonify({'success': True, 'data': [
                {
                    'message_id': m.message_id,
                    'title': m.title,
                    'body': m.body,
                    'is_active': m.is_active,
                    'created_at': m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ]})
        except Exception as e:
            g.logger.error(f"Get messages failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/profile-messages', methods=['POST'])
    def create_profile_message():
        """Create new profile message template.

        Expects JSON: {"title": "...", "body": "..."}

        Returns:
            JSON with created message ID
        """
        try:
            data = request.get_json() or {}
            title = data.get('title', '').strip()
            body = data.get('body', '').strip()

            if not title or not body:
                return jsonify({'success': False, 'error': 'Title and body are required'}), 400

            service = get_profile_message_service()
            message_id = service.message_repo.create_message(title, body)

            return jsonify({'success': True, 'message_id': message_id})
        except Exception as e:
            g.logger.error(f"Create message failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/profile-messages/<int:message_id>', methods=['PUT'])
    def update_profile_message(message_id):
        """Update profile message template.

        Expects JSON: {"title": "...", "body": "...", "is_active": true/false}

        Returns:
            JSON with success status
        """
        try:
            data = request.get_json() or {}
            title = data.get('title')
            body = data.get('body')
            is_active = data.get('is_active')

            service = get_profile_message_service()
            service.message_repo.update_message(
                message_id,
                title=title.strip() if title else None,
                body=body.strip() if body else None,
                is_active=is_active
            )

            return jsonify({'success': True})
        except Exception as e:
            g.logger.error(f"Update message failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/profile-messages/<int:message_id>', methods=['DELETE'])
    def delete_profile_message(message_id):
        """Delete profile message template.

        Returns:
            JSON with success status
        """
        try:
            service = get_profile_message_service()
            service.message_repo.delete_message(message_id)

            return jsonify({'success': True})
        except Exception as e:
            g.logger.error(f"Delete message failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/profile-messages/fetch-watchers', methods=['POST'])
    def fetch_watchers():
        """Fetch watchers and add to queue.

        Expects JSON: {"username": "...", "max_watchers": 50}

        Returns:
            JSON with fetch results
        """
        try:
            data = request.get_json() or {}
            username = data.get('username', '').strip()
            max_watchers = int(data.get('max_watchers', 50))

            if not username:
                return jsonify({'success': False, 'error': 'Username is required'}), 400

            if max_watchers < 1 or max_watchers > 500:
                return jsonify({'success': False, 'error': 'max_watchers must be between 1 and 500'}), 400

            auth_service, _ = get_services()

            if not auth_service.ensure_authenticated():
                return jsonify({'success': False, 'error': 'Not authenticated'}), 401

            access_token = auth_service.get_valid_token()
            if not access_token:
                return jsonify({'success': False, 'error': 'Failed to obtain access token'}), 401

            service = get_profile_message_service()
            result = service.fetch_watchers(access_token, username, max_watchers)

            return jsonify({'success': True, 'data': result})
        except Exception as e:
            g.logger.error(f"Fetch watchers failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/profile-messages/worker/start', methods=['POST'])
    def start_broadcast_worker():
        """Start worker to broadcast message to watchers queue.

        Expects JSON: {"message_id": 1}

        Returns:
            JSON with start status
        """
        try:
            data = request.get_json() or {}
            message_id = data.get('message_id')

            if not message_id:
                return jsonify({'success': False, 'error': 'message_id is required'}), 400

            auth_service, _ = get_services()

            if not auth_service.ensure_authenticated():
                return jsonify({'success': False, 'error': 'Not authenticated'}), 401

            access_token = auth_service.get_valid_token()
            if not access_token:
                return jsonify({'success': False, 'error': 'Failed to obtain access token'}), 401

            service = get_profile_message_service()
            result = service.start_worker(access_token, message_id)

            return jsonify(result)
        except Exception as e:
            g.logger.error(f"Start broadcast worker failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/profile-messages/worker/stop', methods=['POST'])
    def stop_broadcast_worker():
        """Stop broadcast worker.

        Returns:
            JSON with stop status
        """
        try:
            service = get_profile_message_service()
            result = service.stop_worker()

            return jsonify(result)
        except Exception as e:
            g.logger.error(f"Stop broadcast worker failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/profile-messages/worker/status', methods=['GET'])
    def get_broadcast_worker_status():
        """Get broadcast worker and queue status.

        Returns:
            JSON with status information
        """
        try:
            service = get_profile_message_service()
            status = service.get_worker_status()

            return jsonify({'success': True, 'data': status})
        except Exception as e:
            g.logger.error(f"Get broadcast status failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/profile-messages/queue/clear', methods=['POST'])
    def clear_watchers_queue():
        """Clear watchers queue.

        Returns:
            JSON with cleared count
        """
        try:
            service = get_profile_message_service()
            result = service.clear_queue()

            return jsonify(result)
        except Exception as e:
            g.logger.error(f"Clear queue failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/profile-messages/queue/list', methods=['GET'])
    def get_watchers_list():
        """Get watchers queue with selection status.

        Returns:
            JSON with watchers list
        """
        try:
            service = get_profile_message_service()
            watchers = service.get_watchers_list()

            return jsonify({'success': True, 'data': watchers})
        except Exception as e:
            g.logger.error(f"Get watchers list failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/profile-messages/queue/toggle', methods=['POST'])
    def toggle_watcher_selection():
        """Toggle selection for specific watcher.

        Expects JSON: {"username": "...", "selected": true/false}

        Returns:
            JSON with success status
        """
        try:
            data = request.get_json() or {}
            username = data.get('username', '').strip()
            selected = data.get('selected', False)

            if not username:
                return jsonify({'success': False, 'error': 'Username is required'}), 400

            service = get_profile_message_service()
            result = service.update_watcher_selection(username, selected)

            return jsonify(result)
        except Exception as e:
            g.logger.error(f"Toggle watcher selection failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/profile-messages/queue/select-all', methods=['POST'])
    def select_all_watchers():
        """Select all watchers in queue.

        Returns:
            JSON with selected count
        """
        try:
            service = get_profile_message_service()
            result = service.select_all_watchers()

            return jsonify(result)
        except Exception as e:
            g.logger.error(f"Select all watchers failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/profile-messages/queue/deselect-all', methods=['POST'])
    def deselect_all_watchers():
        """Deselect all watchers in queue.

        Returns:
            JSON with deselected count
        """
        try:
            service = get_profile_message_service()
            result = service.deselect_all_watchers()

            return jsonify(result)
        except Exception as e:
            g.logger.error(f"Deselect all watchers failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/profile-messages/logs', methods=['GET'])
    def get_broadcast_logs():
        """Get broadcast logs.

        Query params:
            message_id: Optional message ID filter
            limit: Max results (default 100)
            offset: Offset for pagination (default 0)

        Returns:
            JSON with log entries
        """
        try:
            message_id = request.args.get('message_id')
            limit = int(request.args.get('limit', 100))
            offset = int(request.args.get('offset', 0))

            service = get_profile_message_service()

            if message_id:
                logs = service.log_repo.get_logs_by_message_id(int(message_id), limit, offset)
            else:
                logs = service.log_repo.get_all_logs(limit, offset)

            return jsonify({'success': True, 'data': [
                {
                    'log_id': log.log_id,
                    'message_id': log.message_id,
                    'recipient_username': log.recipient_username,
                    'recipient_userid': log.recipient_userid,
                    'commentid': log.commentid,
                    'status': log.status.value,
                    'error_message': log.error_message,
                    'sent_at': log.sent_at.isoformat() if log.sent_at else None,
                    'profile_url': f"https://www.deviantart.com/{log.recipient_username}",
                }
                for log in logs
            ]})
        except Exception as e:
            g.logger.error(f"Get logs failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    # ========== UPLOAD ADMIN THUMBNAIL ROUTE ==========

    @app.route('/api/admin/thumbnail/<int:deviation_id>')
    def get_thumbnail(deviation_id):
        """
        Get thumbnail for deviation (serves the image file).

        Args:
            deviation_id: Deviation database ID

        Returns:
            Image file or error
        """
        try:
            _, _, deviation_repo = get_upload_services()
            deviation = deviation_repo.get_deviation_by_id(deviation_id)

            if not deviation:
                return jsonify({'error': 'Deviation not found'}), 404

            # Resolve actual file path robustly
            def _resolve_candidate_from_upload_dir(fname: str) -> Path | None:
                """Find a candidate file in upload_dir by filename (case-insensitive extension)."""
                if not fname:
                    return None
                upload_dir = config.upload_dir
                stem = Path(fname).stem
                suffix = Path(fname).suffix.lower()
                # Try lowered suffix first
                cand = upload_dir / f"{stem}{suffix}"
                if cand.exists():
                    return cand
                # Try common extensions
                for ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
                    cand2 = upload_dir / f"{stem}{ext}"
                    if cand2.exists():
                        return cand2
                return None

            # Preferred path from DB
            file_path = Path(deviation.file_path) if getattr(deviation, 'file_path', None) else None

            # If path is missing or invalid OR points to a known-bad base, rebuild from upload_dir
            # Also handle paths that contain the bad segment anywhere (not only prefix)
            bad_segment = str(PROJECT_ROOT / 'src' / 'api' / 'upload').lower()
            needs_rebuild = (
                file_path is None
                or not file_path.exists()
                or str(file_path).lower().startswith(bad_segment)
                or bad_segment in str(file_path).lower()
                or (file_path and not file_path.is_absolute())
            )

            if needs_rebuild:
                dev_filename = None
                if getattr(deviation, 'filename', None):
                    dev_filename = deviation.filename
                elif file_path:
                    dev_filename = file_path.name

                candidate_path = _resolve_candidate_from_upload_dir(dev_filename)
                # As a last resort, if we had a bad stored path, try by that name as well
                if not candidate_path and file_path is not None:
                    candidate_path = _resolve_candidate_from_upload_dir(file_path.name)

                if candidate_path and candidate_path.exists():
                    file_path = candidate_path
                    # Persist corrected path and filename
                    try:
                        deviation.file_path = str(candidate_path)
                        new_name = candidate_path.name
                        if getattr(deviation, 'filename', None) and deviation.filename != new_name:
                            deviation.filename = new_name
                        deviation_repo.update_deviation(deviation)
                    except Exception as update_exc:
                        g.logger.warning(
                            f"Failed to persist corrected file path for deviation {deviation_id}: {update_exc}"
                        )
                else:
                    return jsonify({'error': 'File not found on disk'}), 404

            # Serve the image file (ensure lowercase MIME type)
            ext = file_path.suffix[1:].lower()
            return send_file(
                str(file_path),
                mimetype=f'image/{ext}',
                as_attachment=False
            )
        except Exception as e:
            g.logger.error(f"Get thumbnail failed: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    return app


def get_app() -> Flask:
    """
    Expose app for external runners (e.g., gunicorn).
    
    Returns:
        Flask application instance created via factory
    """
    return create_app()


__all__ = ["create_app", "get_app"]