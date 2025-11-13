"""
User service for fetching and managing DeviantArt user information.

This module provides functionality to:
- Fetch authenticated user info from /user/whoami
- Fetch extended profile info from /user/profile/{username}
- Sync user information to local database
"""

import requests
from typing import Optional
from logging import Logger

from ..domain.models import User
from ..storage import UserRepository


class UserService:
    """
    Service for managing DeviantArt user information.
    
    Handles fetching user information from DeviantArt API
    and synchronizing with local database.
    
    Follows Single Responsibility Principle: Only manages user data.
    """
    
    BASE_URL = "https://www.deviantart.com/api/v1/oauth2"
    
    def __init__(self, user_repository: UserRepository, logger: Logger):
        """
        Initialize user service.
        
        Args:
            user_repository: User repository for database operations
            logger: Logger instance
        """
        self.user_repository = user_repository
        self.logger = logger
    
    def fetch_whoami(self, access_token: str) -> Optional[dict]:
        """
        Fetch authenticated user info from /user/whoami endpoint.
        
        Args:
            access_token: OAuth access token
            
        Returns:
            User info dictionary from API or None on failure
            
        Raises:
            requests.RequestException: If API request fails
        """
        url = f"{self.BASE_URL}/user/whoami"
        
        params = {
            "access_token": access_token
        }
        
        try:
            self.logger.info("Fetching authenticated user info from /user/whoami...")
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            self.logger.info(f"Successfully fetched user info for: {data.get('username')}")
            return data
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch user info: {e}")
            raise
    
    def fetch_profile(
        self, 
        access_token: str, 
        username: Optional[str] = None,
        include_collections: bool = False,
        include_galleries: bool = False
    ) -> Optional[dict]:
        """
        Fetch extended user profile from /user/profile/{username} endpoint.
        
        Args:
            access_token: OAuth access token
            username: Username to fetch (None = authenticated user)
            include_collections: Include collection folder info
            include_galleries: Include gallery folder info
            
        Returns:
            Profile info dictionary from API or None on failure
            
        Raises:
            requests.RequestException: If API request fails
        """
        # Use whoami username if not specified
        if not username:
            whoami_data = self.fetch_whoami(access_token)
            if not whoami_data:
                return None
            username = whoami_data['username']
        
        url = f"{self.BASE_URL}/user/profile/{username}"
        
        params = {
            "access_token": access_token,
            "ext_collections": "1" if include_collections else "0",
            "ext_galleries": "1" if include_galleries else "0"
        }
        
        try:
            self.logger.info(f"Fetching profile info for user: {username}...")
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            self.logger.info(f"Successfully fetched profile for: {username}")
            return data
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch profile: {e}")
            raise
    
    def sync_user(
        self, 
        access_token: str, 
        fetch_extended_profile: bool = True
    ) -> Optional[User]:
        """
        Fetch user info from API and sync to database.
        
        This method:
        1. Fetches basic user info from /user/whoami
        2. Optionally fetches extended profile from /user/profile
        3. Combines the data into a User entity
        4. Saves/updates the user in database
        
        Args:
            access_token: OAuth access token
            fetch_extended_profile: Whether to fetch extended profile data
            
        Returns:
            User object or None on failure
        """
        try:
            # Fetch basic user info
            whoami_data = self.fetch_whoami(access_token)
            if not whoami_data:
                self.logger.error("Failed to fetch user info from /user/whoami")
                return None
            
            # Create basic user object
            user = User(
                userid=whoami_data['userid'],
                username=whoami_data['username'],
                usericon=whoami_data['usericon'],
                type=whoami_data['type']
            )
            
            # Fetch extended profile if requested
            if fetch_extended_profile:
                try:
                    profile_data = self.fetch_profile(
                        access_token, 
                        username=whoami_data['username']
                    )
                    
                    if profile_data:
                        # Update user with profile data
                        user.is_watching = profile_data.get('is_watching')
                        user.profile_url = profile_data.get('profile_url')
                        user.user_is_artist = profile_data.get('user_is_artist')
                        user.artist_level = profile_data.get('artist_level')
                        user.artist_specialty = profile_data.get('artist_specialty')
                        user.real_name = profile_data.get('real_name')
                        user.tagline = profile_data.get('tagline')
                        user.country_id = profile_data.get('countryid')
                        user.country = profile_data.get('country')
                        user.website = profile_data.get('website')
                        user.bio = profile_data.get('bio')
                        
                        # Update statistics
                        stats = profile_data.get('stats', {})
                        user.user_deviations = stats.get('user_deviations')
                        user.user_favourites = stats.get('user_favourites')
                        user.user_comments = stats.get('user_comments')
                        user.profile_pageviews = stats.get('profile_pageviews')
                        user.profile_comments = stats.get('profile_comments')
                        
                        self.logger.info(f"Extended profile data added for: {user.username}")
                except Exception as e:
                    self.logger.warning(f"Could not fetch extended profile, continuing with basic info: {e}")
            
            # Save to database
            user_id = self.user_repository.save_user(user)
            user.user_db_id = user_id
            
            self.logger.info(f"User synced to database: {user.username} (DB ID: {user_id})")
            return user
            
        except Exception as e:
            self.logger.error(f"Failed to sync user: {e}")
            raise
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        Get user by database ID.
        
        Args:
            user_id: Internal database ID
            
        Returns:
            User object or None if not found
        """
        return self.user_repository.get_user_by_id(user_id)
    
    def get_user_by_userid(self, userid: str) -> Optional[User]:
        """
        Get user by DeviantArt user UUID.
        
        Args:
            userid: DeviantArt user UUID
            
        Returns:
            User object or None if not found
        """
        return self.user_repository.get_user_by_userid(userid)
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """
        Get user by DeviantArt username.
        
        Args:
            username: DeviantArt username
            
        Returns:
            User object or None if not found
        """
        return self.user_repository.get_user_by_username(username)
    
    def get_current_user(self) -> Optional[User]:
        """
        Get the current/latest user from database.
        
        Useful for getting the authenticated user without API call.
        
        Returns:
            User object or None if no users in database
        """
        users = self.user_repository.get_all_users()
        return users[0] if users else None
    
    def display_user_info(self, user: User) -> None:
        """
        Display user information in a readable format.
        
        Args:
            user: User object to display
        """
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"User Information")
        self.logger.info(f"{'='*80}")
        self.logger.info(f"Username: {user.username}")
        self.logger.info(f"User ID: {user.userid}")
        self.logger.info(f"Type: {user.type}")
        
        if user.real_name:
            self.logger.info(f"Real Name: {user.real_name}")
        
        if user.profile_url:
            self.logger.info(f"Profile: {user.profile_url}")
        
        if user.tagline:
            self.logger.info(f"Tagline: {user.tagline}")
        
        if user.country:
            self.logger.info(f"Country: {user.country}")
        
        if user.website:
            self.logger.info(f"Website: {user.website}")
        
        if user.user_is_artist:
            self.logger.info(f"\nArtist Info:")
            if user.artist_level:
                self.logger.info(f"  Level: {user.artist_level}")
            if user.artist_specialty:
                self.logger.info(f"  Specialty: {user.artist_specialty}")
        
        if user.user_deviations is not None:
            self.logger.info(f"\nStatistics:")
            self.logger.info(f"  Deviations: {user.user_deviations}")
            self.logger.info(f"  Favourites: {user.user_favourites}")
            self.logger.info(f"  Comments: {user.user_comments}")
            self.logger.info(f"  Profile Views: {user.profile_pageviews}")
            self.logger.info(f"  Profile Comments: {user.profile_comments}")
        
        self.logger.info(f"\nDatabase ID: {user.user_db_id}")
        self.logger.info(f"{'='*80}\n")
