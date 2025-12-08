"""Configuration management for DeviantArt uploader."""
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv


# Project root directory (parent of src/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


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
        self.database_type = os.getenv('DATABASE_TYPE', 'sqlite').lower()
        database_path_env = os.getenv('DATABASE_PATH', 'data/deviant.db')
        self.database_path = self._resolve_path(database_path_env)
        self.database_url = os.getenv('DATABASE_URL', '')
        
        # Upload directories (resolve to absolute paths from project root)
        upload_dir_env = os.getenv('UPLOAD_DIR', 'upload')
        done_dir_env = os.getenv('DONE_DIR', 'upload/done')
        self.upload_dir = self._resolve_path(upload_dir_env)
        self.done_dir = self._resolve_path(done_dir_env)
        
        # Logging configuration
        log_dir_env = os.getenv('LOG_DIR', 'logs')
        self.log_dir = self._resolve_path(log_dir_env)
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
    
    def _resolve_path(self, path_str: str) -> Path:
        """
        Resolve a path string to an absolute Path.
        
        If the path is already absolute, returns it as-is.
        If relative, resolves it relative to PROJECT_ROOT.
        
        Args:
            path_str: Path string from environment variable
            
        Returns:
            Absolute Path object
        """
        path = Path(path_str)
        if path.is_absolute():
            return path
        return (PROJECT_ROOT / path).resolve()
    
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
