"""Charts API routes for the Flask stats dashboard."""

from __future__ import annotations

from collections.abc import Callable

from flask import Flask, g, jsonify, request


def register_charts_routes(
    app: Flask,
    *,
    get_services: Callable[[], tuple[object, object]],
) -> None:
    """Register chart-related API endpoints."""

    @app.route("/api/charts/deviations", methods=["GET"])
    def get_deviations_for_charts():
        """Return list of all deviations for chart filtering."""
        try:
            _auth_service, stats_service = get_services()
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

            deviation_ids = None
            if deviation_ids_param and deviation_ids_param.strip():
                deviation_ids = [
                    did.strip() for did in deviation_ids_param.split(",") if did.strip()
                ]

            _auth_service, stats_service = get_services()
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

            _auth_service, stats_service = get_services()
            data = stats_service.get_user_watchers_history(username, period_days)
            return jsonify({"success": True, "data": data})
        except Exception as exc:  # noqa: BLE001
            g.logger.error("Failed to fetch user watchers chart data", exc_info=exc)
            return jsonify({"success": False, "error": str(exc)}), 500
