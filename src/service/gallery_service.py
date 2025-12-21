"""
Gallery service for fetching and managing DeviantArt galleries.

This module provides functionality to:
- Fetch gallery folders from DeviantArt API
- Sync galleries to local database
- Retrieve gallery information by various criteria
"""

import time
import requests
from typing import Optional
from logging import Logger

from ..domain.models import Gallery
from ..storage import GalleryRepository
from .http_client import DeviantArtHttpClient


class GalleryService:
    """
    Service for managing DeviantArt gallery folders.
    
    Handles fetching gallery information from DeviantArt API
    and synchronizing with local database.
    
    Follows Single Responsibility Principle: Only manages galleries.
    """
    
    BASE_URL = "https://www.deviantart.com/api/v1/oauth2"
    
    def __init__(
        self,
        gallery_repository: GalleryRepository,
        logger: Logger,
        http_client: Optional[DeviantArtHttpClient] = None,
    ):
        """
        Initialize gallery service.
        
        Args:
            gallery_repository: Gallery repository for database operations
            logger: Logger instance
            http_client: HTTP client for API requests (optional, creates default if not provided)
        """
        self.gallery_repository = gallery_repository
        self.logger = logger
        self.http_client = http_client or DeviantArtHttpClient(logger=logger)
    
    def fetch_galleries(
        self, 
        access_token: str, 
        username: Optional[str] = None,
        calculate_size: bool = True,
        filter_empty: bool = False
    ) -> list[dict]:
        """
        Fetch gallery folders from DeviantArt API.
        
        Args:
            access_token: OAuth access token
            username: Username to fetch galleries for (None = authenticated user)
            calculate_size: Include content count per folder
            filter_empty: Filter out empty galleries
            
        Returns:
            List of gallery folder dictionaries from API
            
        Raises:
            requests.RequestException: If API request fails
        """
        url = f"{self.BASE_URL}/gallery/folders"
        
        params = {
            "access_token": access_token,
            "calculate_size": "true" if calculate_size else "false",
            "filter_empty_folder": "true" if filter_empty else "false",
            "limit": 50
        }
        
        if username:
            params["username"] = username
        
        all_galleries = []
        offset = 0
        has_more = True
        
        self.logger.info("Fetching galleries from DeviantArt API...")
        
        while has_more:
            params["offset"] = offset
            
            try:
                response = self.http_client.get(url, params=params)
                data = response.json()
                
                if "results" in data:
                    all_galleries.extend(data["results"])
                    self.logger.info(f"Fetched {len(data['results'])} galleries (offset: {offset})")
                
                has_more = data.get("has_more", False)
                next_offset = data.get("next_offset")
                
                if has_more and next_offset is not None:
                    offset = next_offset
                    # Rate limiting: wait 3 seconds before next pagination request
                    time.sleep(3)
                else:
                    has_more = False
                    
            except requests.RequestException as e:
                self.logger.error(f"Failed to fetch galleries: {e}")
                raise
        
        self.logger.info(f"Total galleries fetched: {len(all_galleries)}")
        return all_galleries
    
    def sync_galleries(self, access_token: str, username: Optional[str] = None) -> int:
        """
        Fetch galleries from API and sync to database.
        
        Args:
            access_token: OAuth access token
            username: Username to fetch galleries for (None = authenticated user)
            
        Returns:
            Number of galleries synced
        """
        try:
            # Fetch from API
            api_galleries = self.fetch_galleries(access_token, username)
            
            # Sync to database
            synced_count = 0
            for gallery_data in api_galleries:
                gallery = Gallery(
                    folderid=gallery_data["folderid"],
                    name=gallery_data["name"],
                    parent=gallery_data.get("parent"),
                    size=gallery_data.get("size", 0)
                )
                
                self.gallery_repository.save_gallery(gallery)
                synced_count += 1
                self.logger.info(f"Synced gallery: {gallery.name} (UUID: {gallery.folderid})")
            
            self.logger.info(f"Successfully synced {synced_count} galleries to database")
            return synced_count
            
        except Exception as e:
            self.logger.error(f"Failed to sync galleries: {e}")
            raise
    
    def get_gallery_by_id(self, gallery_id: int) -> Optional[Gallery]:
        """
        Get gallery by database ID.
        
        Args:
            gallery_id: Internal database ID
            
        Returns:
            Gallery object or None if not found
        """
        return self.gallery_repository.get_gallery_by_id(gallery_id)
    
    def get_gallery_by_folderid(self, folderid: str) -> Optional[Gallery]:
        """
        Get gallery by DeviantArt folder UUID.
        
        Args:
            folderid: DeviantArt folder UUID
            
        Returns:
            Gallery object or None if not found
        """
        return self.gallery_repository.get_gallery_by_folderid(folderid)
    
    def get_all_galleries(self) -> list[Gallery]:
        """
        Get all galleries from database.
        
        Returns:
            List of all Gallery objects
        """
        return self.gallery_repository.get_all_galleries()
    
    def list_galleries(self) -> None:
        """
        Print all galleries in a readable format.
        
        Useful for console output to see available galleries.
        """
        galleries = self.get_all_galleries()
        
        if not galleries:
            self.logger.info("No galleries found in database")
            return
        
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"Found {len(galleries)} galleries in database:")
        self.logger.info(f"{'='*80}")
        
        for gallery in galleries:
            parent_info = f" (parent: {gallery.parent})" if gallery.parent else ""
            size_info = f" - {gallery.size} items" if gallery.size else ""
            self.logger.info(f"[ID: {gallery.gallery_db_id}] {gallery.name}{size_info}")
            self.logger.info(f"  UUID: {gallery.folderid}{parent_info}")
        
        self.logger.info(f"{'='*80}\n")
