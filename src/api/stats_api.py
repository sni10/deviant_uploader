"""Flask API for stats dashboard (browse-only, no uploads).

Provides two endpoints:
- GET /api/stats       → current deviation stats with daily diffs
- POST /api/stats/sync → trigger sync for a gallery folder (body: {"folderid": "...", "username": "optional"})

Serves the static dashboard page at `/` from the project-level `static/stats.html`.
"""

from pathlib import Path
import logging
from flask import Flask, jsonify, request, send_from_directory

from ..config import get_config
from ..log.logger import setup_logger
from ..storage import create_repositories
from ..service.auth_service import AuthService
from ..service.stats_service import StatsService


# Resolve paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = PROJECT_ROOT / "static"


config = get_config()
log_level = getattr(logging, config.log_level.upper(), logging.INFO)
logger = setup_logger(name="stats_api", log_dir=config.log_dir, level=log_level)

# Create repositories and services (shared DB connection)
user_repo, token_repo, gallery_repo, deviation_repo, stats_repo = create_repositories(
    config.database_path
)
auth_service = AuthService(token_repo, logger)
stats_service = StatsService(stats_repo, deviation_repo, logger)


app = Flask(__name__, static_folder=str(STATIC_DIR))


@app.route("/")
def index():
    """Serve dashboard page."""
    return send_from_directory(STATIC_DIR, "stats.html")


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """Return current stats with diffs."""
    try:
        data = stats_service.get_stats_with_diff()
        return jsonify({"success": True, "data": data})
    except Exception as exc:  # noqa: BLE001 (surface error to caller)
        logger.error("Failed to fetch stats", exc_info=exc)
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
        logger.error("Failed to sync stats", exc_info=exc)
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/options", methods=["GET"])
def get_options():
    """Return user and gallery options from the database."""

    try:
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
        logger.error("Failed to fetch options", exc_info=exc)
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/user_stats/latest", methods=["GET"])
def get_latest_user_stats():
    """Return the latest user stats snapshot for a given username."""
    try:
        username = (request.args.get("username") or "").strip()
        if not username:
            return jsonify({"success": False, "error": "username is required"}), 400

        snapshot = stats_repo.get_latest_user_stats_snapshot(username)
        return jsonify({"success": True, "data": snapshot})
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to fetch latest user stats", exc_info=exc)
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/static/<path:filename>")
def serve_static(filename: str):
    """Serve other static assets if needed."""
    return send_from_directory(STATIC_DIR, filename)


def get_app() -> Flask:
    """Expose app for external runners (e.g., gunicorn)."""
    return app


__all__ = ["app", "get_app"]