"""Run the combined stats dashboard and upload admin server."""

from src.api.stats_api import create_app


if __name__ == "__main__":
    print("Starting DeviantArt Admin Server on http://localhost:5000")
    print("  - Stats Dashboard: http://localhost:5000/")
    print("  - Charts:          http://localhost:5000/charts.html")
    print("  - Upload Admin:    http://localhost:5000/upload_admin.html")
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)