"""Entry point for upload admin interface server."""
from src.api.upload_admin_api import create_upload_admin_app
from src.log.logger import setup_logger


def main():
    """Start the upload admin Flask server."""
    logger = setup_logger()
    logger.info("Starting upload admin server...")
    
    app = create_upload_admin_app()
    
    # Run on port 5001 to avoid conflict with stats API (port 5000)
    app.run(
        debug=True,
        host='0.0.0.0',
        port=5001
    )


if __name__ == '__main__':
    main()
