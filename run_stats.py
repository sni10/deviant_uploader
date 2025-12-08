"""Run the stats dashboard server."""

from src.api.stats_api import create_app


if __name__ == "__main__":
    print("Starting Stats Dashboard on http://localhost:5000")
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)