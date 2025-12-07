"""
Script to fetch and sync user information from DeviantArt to local database.

Usage:
    python fetch_user.py

This script will:
1. Authenticate with DeviantArt
2. Fetch authenticated user information from /user/whoami
3. Fetch extended profile from /user/profile/{username}
4. Store/update user info in the local database
5. Display user information
"""

from src.config import get_config
from src.log.logger import setup_logger
from src.storage import create_repositories
from src.service.auth_service import AuthService
from src.service.user_service import UserService


def main():
    """Main function to fetch and sync user information."""
    # Setup
    config = get_config()
    logger = setup_logger()
    
    # Initialize repositories (following DDD and SOLID principles)
    user_repo, token_repo, gallery_repo, deviation_repo, stats_repo = create_repositories(config.database_path)
    
    # Initialize services with proper dependency injection
    auth_service = AuthService(token_repo, logger)
    user_service = UserService(user_repo, logger)
    
    try:
        logger.info("=" * 80)
        logger.info("User Information Sync Script")
        logger.info("=" * 80)
        
        # Ensure authentication
        logger.info("Authenticating with DeviantArt...")
        if not auth_service.ensure_authenticated():
            logger.error("Authentication failed. Cannot fetch user info.")
            return
        
        # Get valid token
        access_token = auth_service.get_valid_token()
        if not access_token:
            logger.error("Failed to get valid access token")
            return
        
        logger.info("Authentication successful!")
        
        # Sync user information
        logger.info("\nFetching user information from DeviantArt...")
        user = user_service.sync_user(access_token, fetch_extended_profile=True)
        
        if not user:
            logger.error("Failed to sync user information")
            return
        
        logger.info(f"\nSuccessfully synced user: {user.username}")
        
        # Display user information
        user_service.display_user_info(user)
        
        logger.info("\nUser information has been saved to the database.")
        logger.info(f"Database ID: {user.user_db_id}")
        logger.info("\nYou can now use this user_id to link tokens, galleries, and deviations.")
        
    except Exception as e:
        logger.error(f"Error during user sync: {e}", exc_info=True)
    finally:
        # Cleanup (all repositories share same connection)
        user_repo.close()
        logger.info("\nDone!")


if __name__ == "__main__":
    main()
