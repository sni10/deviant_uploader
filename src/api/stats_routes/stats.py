"""Stats and options API routes for the Flask stats dashboard."""

from __future__ import annotations

from collections.abc import Callable

from flask import Flask, g, jsonify, request


def register_stats_routes(
    app: Flask,
    *,
    get_services: Callable[[], tuple[object, object]],
    get_repositories: Callable[[], tuple[object, ...]],
    get_stats_sync_service: Callable[[], object] | None = None,
) -> None:
    """Register statistics, sync, and options endpoints."""

    @app.route("/api/stats", methods=["GET"])
    def get_stats():
        """Return current stats with diffs."""
        try:
            _auth_service, stats_service = get_services()
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

            if not auth_service.ensure_authenticated():
                return jsonify({"success": False, "error": "Not authenticated"}), 401

            access_token = auth_service.get_valid_token()
            if not access_token:
                return jsonify(
                    {"success": False, "error": "Failed to obtain access token"}
                ), 401

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
            (
                user_repo,
                _token_repo,
                gallery_repo,
                _deviation_repo,
                _deviation_stats_repo,
                _stats_snapshot_repo,
                _user_stats_snapshot_repo,
                _deviation_metadata_repo,
            ) = get_repositories()
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
                                "sync_enabled": gallery.sync_enabled,
                            }
                            for gallery in galleries
                        ],
                    },
                }
            )
        except Exception as exc:  # noqa: BLE001
            g.logger.error("Failed to fetch options", exc_info=exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/galleries/<folderid>/sync", methods=["PUT"])
    def update_gallery_sync(folderid):
        """Update sync_enabled flag for a gallery."""
        try:
            data = request.get_json()
            if not data or "sync_enabled" not in data:
                return jsonify({"success": False, "error": "sync_enabled is required"}), 400

            sync_enabled = bool(data["sync_enabled"])

            (
                _user_repo,
                _token_repo,
                gallery_repo,
                _deviation_repo,
                _deviation_stats_repo,
                _stats_snapshot_repo,
                _user_stats_snapshot_repo,
                _deviation_metadata_repo,
            ) = get_repositories()

            success = gallery_repo.update_sync_enabled(folderid, sync_enabled)
            if not success:
                return jsonify({"success": False, "error": "Gallery not found"}), 404

            return jsonify({"success": True, "data": {"folderid": folderid, "sync_enabled": sync_enabled}})
        except Exception as exc:  # noqa: BLE001
            g.logger.error("Failed to update gallery sync setting", exc_info=exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/user_stats/latest", methods=["GET"])
    def get_latest_user_stats():
        """Return the latest user stats snapshot for a given username."""
        try:
            username = (request.args.get("username") or "").strip()
            if not username:
                return jsonify({"success": False, "error": "username is required"}), 400

            (
                _user_repo,
                _token_repo,
                _gallery_repo,
                _deviation_repo,
                _deviation_stats_repo,
                _stats_snapshot_repo,
                user_stats_snapshot_repo,
                _deviation_metadata_repo,
            ) = get_repositories()
            snapshot = user_stats_snapshot_repo.get_latest_user_stats_snapshot(username)
            return jsonify({"success": True, "data": snapshot})
        except Exception as exc:  # noqa: BLE001
            g.logger.error("Failed to fetch latest user stats", exc_info=exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    # ========== Worker Endpoints ==========

    @app.route("/api/stats/worker/start", methods=["POST"])
    def start_stats_worker():
        """Start the background stats sync worker."""
        if not get_stats_sync_service:
            return jsonify({"success": False, "error": "Worker not configured"}), 500

        try:
            payload = request.get_json(silent=True) or {}
            username = payload.get("username")

            auth_service, _stats_service = get_services()

            if not auth_service.ensure_authenticated():
                return jsonify({"success": False, "error": "Not authenticated"}), 401

            access_token = auth_service.get_valid_token()
            if not access_token:
                return jsonify(
                    {"success": False, "error": "Failed to obtain access token"}
                ), 401

            stats_sync_service = get_stats_sync_service()
            result = stats_sync_service.start_worker(access_token, username=username)
            return jsonify(result)
        except Exception as exc:  # noqa: BLE001
            g.logger.error("Failed to start stats worker", exc_info=exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/stats/worker/stop", methods=["POST"])
    def stop_stats_worker():
        """Stop the background stats sync worker."""
        if not get_stats_sync_service:
            return jsonify({"success": False, "error": "Worker not configured"}), 500

        try:
            stats_sync_service = get_stats_sync_service()
            result = stats_sync_service.stop_worker()
            return jsonify(result)
        except Exception as exc:  # noqa: BLE001
            g.logger.error("Failed to stop stats worker", exc_info=exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/stats/worker/status", methods=["GET"])
    def get_stats_worker_status():
        """Get the status of the background stats sync worker."""
        if not get_stats_sync_service:
            return jsonify({"success": False, "error": "Worker not configured"}), 500

        try:
            stats_sync_service = get_stats_sync_service()
            status = stats_sync_service.get_worker_status()
            return jsonify({"success": True, "data": status})
        except Exception as exc:  # noqa: BLE001
            g.logger.error("Failed to get stats worker status", exc_info=exc)
            return jsonify({"success": False, "error": str(exc)}), 500
