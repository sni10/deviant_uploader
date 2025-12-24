"""Mass-fave (auto-fave) API routes."""

from __future__ import annotations

from collections.abc import Callable

from flask import Flask, g, jsonify, request


def register_mass_fave_routes(
    app: Flask,
    *,
    get_services: Callable[[], tuple[object, object]],
    get_mass_fave_service: Callable[[], object],
) -> None:
    """Register mass-fave endpoints."""

    @app.route("/api/mass-fave/collect", methods=["POST"])
    def collect_feed():
        """Collect deviations from feed and add to queue."""
        try:
            data = request.get_json() or {}
            pages = int(data.get("pages", 5))

            if pages < 1 or pages > 20:
                return (
                    jsonify({"success": False, "error": "Pages must be between 1 and 20"}),
                    400,
                )

            auth_service, _stats_service = get_services()

            if not auth_service.ensure_authenticated():
                return jsonify({"success": False, "error": "Not authenticated"}), 401

            access_token = auth_service.get_valid_token()
            if not access_token:
                return (
                    jsonify({"success": False, "error": "Failed to obtain access token"}),
                    401,
                )

            mass_fave_service = get_mass_fave_service()
            result = mass_fave_service.collect_from_feed(access_token, pages)

            return jsonify({"success": True, "data": result})
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Feed collection failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/mass-fave/worker/start", methods=["POST"])
    def start_worker():
        """Start background worker to process fave queue."""
        try:
            auth_service, _stats_service = get_services()

            if not auth_service.ensure_authenticated():
                return jsonify({"success": False, "error": "Not authenticated"}), 401

            access_token = auth_service.get_valid_token()
            if not access_token:
                return (
                    jsonify({"success": False, "error": "Failed to obtain access token"}),
                    401,
                )

            mass_fave_service = get_mass_fave_service()
            result = mass_fave_service.start_worker(access_token, auth_service=auth_service)

            return jsonify(result)
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Worker start failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/mass-fave/worker/stop", methods=["POST"])
    def stop_worker():
        """Stop background worker."""
        try:
            mass_fave_service = get_mass_fave_service()
            result = mass_fave_service.stop_worker()

            return jsonify(result)
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Worker stop failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/mass-fave/status", methods=["GET"])
    def get_worker_status():
        """Get worker and queue status."""
        try:
            mass_fave_service = get_mass_fave_service()
            status = mass_fave_service.get_worker_status()

            return jsonify({"success": True, "data": status})
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Get worker status failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/mass-fave/reset-failed", methods=["POST"])
    def reset_failed_deviations():
        """Reset all failed deviations back to pending status."""
        try:
            mass_fave_service = get_mass_fave_service()
            result = mass_fave_service.reset_failed_deviations()

            return jsonify(result)
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Reset failed deviations failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500
