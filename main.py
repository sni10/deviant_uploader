"""Main entry point for DeviantArt image uploader."""
import logging
import sys
from pathlib import Path

from src.config import get_config
from src.log.logger import setup_logger
from src.storage import create_repositories
from src.service.auth_service import AuthService
from src.service.uploader import UploaderService


def main():
    """Main application entry point."""
    # Initialize configuration
    try:
        config = get_config()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("\nPlease set the following environment variables:")
        print("  DA_CLIENT_ID - Your DeviantArt application client ID")
        print("  DA_CLIENT_SECRET - Your DeviantArt application client secret")
        print("\nOptional variables:")
        print("  DA_REDIRECT_URI - OAuth redirect URI (default: http://localhost:8080/callback)")
        print("  DA_SCOPES - OAuth scopes (default: stash publish)")
        print("  DATABASE_PATH - Database file path (default: data/deviant.db)")
        print("  UPLOAD_DIR - Upload directory (default: upload)")
        print("  DONE_DIR - Done directory (default: upload/done)")
        print("  LOG_DIR - Log directory (default: logs)")
        print("  LOG_LEVEL - Log level (default: INFO)")
        return 1
    
    # Convert log level string to logging constant
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    
    # Setup logger
    logger = setup_logger(
        name="deviant",
        log_dir=config.log_dir,
        level=log_level
    )
    
    logger.info("=" * 60)
    logger.info("DeviantArt Image Uploader Starting")
    logger.info("=" * 60)
    
    # Initialize repositories (following DDD and SOLID principles)
    user_repo, token_repo, gallery_repo, deviation_repo, stats_repo = create_repositories()
    logger.info(f"Database initialized: {config.database_type}")
    
    # Initialize services with proper dependency injection
    auth_service = AuthService(token_repo, logger)
    uploader_service = UploaderService(deviation_repo, gallery_repo, auth_service, logger)
    
    # Ensure authentication
    logger.info("Checking authentication...")
    if not auth_service.ensure_authenticated():
        logger.error("Authentication failed. Cannot proceed.")
        token_repo.close()
        return 1
    
    logger.info("Authentication successful!")
    
    # Process uploads
    logger.info(f"Scanning upload folder: {config.upload_dir}")
    stats = uploader_service.process_uploads()
    
    # Log results
    logger.info("=" * 60)
    logger.info("Upload Process Complete")
    logger.info(f"Total files: {stats['total']}")
    logger.info(f"Successful: {stats['successful']}")
    logger.info(f"Failed: {stats['failed']}")
    logger.info("=" * 60)
    
    # Cleanup (all repositories share same connection)
    token_repo.close()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
