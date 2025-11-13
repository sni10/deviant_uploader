"""Configuration management for DeviantArt uploader."""
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv


class Config:
    """
    Configuration class for DeviantArt uploader.
    Loads settings from environment variables and provides singleton access.
    """
    _instance: Optional['Config'] = None
    
    def __new__(cls):
        """Singleton pattern - only one instance of Config exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize configuration from environment variables."""
        if self._initialized:
            return
            
        # Load .env file if it exists
        load_dotenv()
        
        # DeviantArt API credentials
        self.client_id = os.getenv('DA_CLIENT_ID')
        self.client_secret = os.getenv('DA_CLIENT_SECRET')
        self.redirect_uri = os.getenv('DA_REDIRECT_URI', 'http://localhost:8080/callback')
        
        # OAuth scopes required for browse, stash and publish
        self.scopes = os.getenv('DA_SCOPES', 'browse stash publish')
        
        # Database configuration
        self.database_path = Path(os.getenv('DATABASE_PATH', 'data/deviant.db'))
        
        # Upload directories
        self.upload_dir = Path(os.getenv('UPLOAD_DIR', 'upload'))
        self.done_dir = Path(os.getenv('DONE_DIR', 'upload/done'))
        
        # Logging configuration
        self.log_dir = Path(os.getenv('LOG_DIR', 'logs'))
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        
        # API endpoints
        self.api_base_url = 'https://www.deviantart.com'
        self.oauth_authorize_url = f'{self.api_base_url}/oauth2/authorize'
        self.oauth_token_url = f'{self.api_base_url}/oauth2/token'
        self.api_placebo_url = f'{self.api_base_url}/api/v1/oauth2/placebo'
        self.api_stash_submit_url = f'{self.api_base_url}/api/v1/oauth2/stash/submit'
        self.api_stash_publish_url = f'{self.api_base_url}/api/v1/oauth2/stash/publish'
        
        # Ensure directories exist
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.done_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._initialized = True
        
        # Validate required configuration
        self._validate()
    
    def _validate(self):
        """Validate that required configuration is present."""
        if not self.client_id:
            raise ValueError("DA_CLIENT_ID environment variable is required")
        if not self.client_secret:
            raise ValueError("DA_CLIENT_SECRET environment variable is required")
    
    @classmethod
    def get_instance(cls) -> 'Config':
        """
        Get the singleton instance of Config.
        
        Returns:
            Config instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


# Convenience function to get config instance
def get_config() -> Config:
    """
    Get the configuration instance.
    
    Returns:
        Config instance
    """
    return Config.get_instance()
