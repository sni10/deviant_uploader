"""
Script to fetch and sync galleries from DeviantArt to local database.

Usage:
    python fetch_galleries.py

This script will:
1. Authenticate with DeviantArt
2. Fetch all gallery folders from your account
3. Store/update them in the local database
4. Display a list of all galleries with their IDs
"""

from src.config import get_config
from src.log.logger import setup_logger
from src.storage import create_repositories
from src.service.auth_service import AuthService
from src.service.gallery_service import GalleryService


def main():
    """Main function to fetch and sync galleries."""
    # Setup
    config = get_config()
    logger = setup_logger()
    
    # Initialize repositories (following DDD and SOLID principles)
    user_repo, token_repo, gallery_repo, deviation_repo, stats_repo = create_repositories()
    
    # Initialize services with proper dependency injection
    auth_service = AuthService(token_repo, logger)
    gallery_service = GalleryService(gallery_repo, logger)
    
    try:
        logger.info("=" * 80)
        logger.info("Gallery Sync Script")
        logger.info("=" * 80)
        
        # Ensure authentication
        logger.info("Authenticating with DeviantArt...")
        if not auth_service.ensure_authenticated():
            logger.error("Authentication failed. Cannot fetch galleries.")
            return
        
        # Get valid token
        access_token = auth_service.get_valid_token()
        if not access_token:
            logger.error("Failed to get valid access token")
            return
        
        logger.info("Authentication successful!")
        
        # Sync galleries
        logger.info("\nFetching galleries from DeviantArt...")
        synced_count = gallery_service.sync_galleries(access_token)
        
        logger.info(f"\nSuccessfully synced {synced_count} galleries!")
        
        # Display all galleries
        logger.info("\n" + "=" * 80)
        logger.info("Available Galleries")
        logger.info("=" * 80)
        gallery_service.list_galleries()
        
        logger.info("\nYou can now use these gallery IDs in your upload_template.json")
        logger.info("Set 'gallery_id' to the [ID: X] value from the list above")
        
    except Exception as e:
        logger.error(f"Error during gallery sync: {e}", exc_info=True)
    finally:
        # Cleanup (all repositories share same connection)
        token_repo.close()
        logger.info("\nDone!")


if __name__ == "__main__":
    main()
