"""Flask routes for serving HTML pages and static assets."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, send_from_directory


def register_pages_routes(app: Flask, *, static_dir: Path) -> None:
    """Register HTML pages and static asset routes."""

    @app.route("/")
    def index():
        """Serve dashboard page."""
        return send_from_directory(static_dir, "stats.html")

    @app.route("/static/<path:filename>")
    def serve_static(filename: str):
        """Serve static assets."""
        return send_from_directory(static_dir, filename)

    @app.route("/charts.html")
    def charts_page():
        """Serve charts visualization page."""
        return send_from_directory(static_dir, "charts.html")

    @app.route("/upload_admin.html")
    def upload_admin_html():
        """Serve upload admin HTML page."""
        return send_from_directory(static_dir, "upload_admin.html")

    @app.route("/admin/upload")
    def upload_admin_page():
        """Serve upload admin HTML page (alternative URL)."""
        return send_from_directory(static_dir, "upload_admin.html")

    @app.route("/mass_fave.html")
    def mass_fave_page():
        """Serve Auto Fave admin page."""
        return send_from_directory(static_dir, "mass_fave.html")

    @app.route("/profile_broadcast.html")
    def profile_broadcast_page():
        """Serve Profile Message Broadcasting page."""
        return send_from_directory(static_dir, "profile_broadcast.html")

    @app.route("/auto_comment.html")
    def auto_comment_page():
        """Serve Auto Comment page."""
        return send_from_directory(static_dir, "auto_comment.html")
