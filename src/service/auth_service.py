"""Authentication service for DeviantArt OAuth2."""
import logging
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs
from typing import Optional
import requests

from ..config import get_config
from ..storage import OAuthTokenRepository


class AuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback."""
    
    authorization_code: Optional[str] = None
    
    def do_GET(self):
        """Handle GET request for OAuth callback."""
        query_components = parse_qs(urlparse(self.path).query)
        
        if 'code' in query_components:
            AuthCallbackHandler.authorization_code = query_components['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<html><body><h1>Authorization successful!</h1><p>You can close this window.</p></body></html>')
        elif 'error' in query_components:
            error = query_components['error'][0]
            error_desc = query_components.get('error_description', [''])[0]
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(f'<html><body><h1>Authorization failed!</h1><p>Error: {error}</p><p>{error_desc}</p></body></html>'.encode())
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<html><body><h1>Invalid request</h1></body></html>')
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


class AuthService:
    """Service for managing DeviantArt OAuth2 authentication."""
    
    def __init__(self, token_repository: OAuthTokenRepository, logger: Optional[logging.Logger] = None):
        """
        Initialize authentication service.
        
        Args:
            token_repository: OAuth token repository
            logger: Logger instance
        """
        self.config = get_config()
        self.token_repository = token_repository
        self.logger = logger or logging.getLogger(__name__)
    
    def authorize(self) -> bool:
        """
        Perform OAuth2 authorization flow.
        
        Opens browser for user authorization and starts local server to receive callback.
        
        Returns:
            True if authorization successful, False otherwise
        """
        self.logger.info("Starting OAuth2 authorization flow")
        
        # Build authorization URL
        auth_params = {
            'response_type': 'code',
            'client_id': self.config.client_id,
            'redirect_uri': self.config.redirect_uri,
            'scope': self.config.scopes
        }
        auth_url = f"{self.config.oauth_authorize_url}?{urlencode(auth_params)}"
        
        self.logger.info(f"Opening browser for authorization: {auth_url}")
        webbrowser.open(auth_url)
        
        # Start local server to receive callback
        server_address = ('', 8080)  # Listen on port 8080
        httpd = HTTPServer(server_address, AuthCallbackHandler)
        
        self.logger.info("Waiting for authorization callback...")
        httpd.handle_request()  # Handle one request then stop
        
        authorization_code = AuthCallbackHandler.authorization_code
        
        if not authorization_code:
            self.logger.error("Failed to receive authorization code")
            return False
        
        self.logger.info("Authorization code received, exchanging for access token")
        
        # Exchange authorization code for access token
        return self._exchange_code_for_token(authorization_code)
    
    def _exchange_code_for_token(self, code: str) -> bool:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code
            
        Returns:
            True if token exchange successful, False otherwise
        """
        token_params = {
            'grant_type': 'authorization_code',
            'client_id': self.config.client_id,
            'client_secret': self.config.client_secret,
            'redirect_uri': self.config.redirect_uri,
            'code': code
        }
        
        try:
            response = requests.post(self.config.oauth_token_url, data=token_params)
            response.raise_for_status()
            
            token_data = response.json()
            
            if token_data.get('status') == 'success' or 'access_token' in token_data:
                self.logger.info("Access token received successfully")
                
                # Save token to database
                self.token_repository.save_token(
                    access_token=token_data['access_token'],
                    refresh_token=token_data['refresh_token'],
                    expires_in=token_data['expires_in'],
                    token_type=token_data.get('token_type', 'Bearer'),
                    scope=token_data.get('scope')
                )
                
                self.logger.info("Token saved to database")
                return True
            else:
                self.logger.error(f"Token exchange failed: {token_data}")
                return False
                
        except requests.RequestException as e:
            self.logger.error(f"Token exchange request failed: {e}")
            return False
    
    def get_valid_token(self) -> Optional[str]:
        """
        Get a valid access token, refreshing if necessary.
        
        Returns:
            Valid access token or None if not available
        """
        # Check if token exists and is expired
        if self.token_repository.is_token_expired():
            self.logger.info("Token expired or not found, attempting to refresh")
            
            # Try to refresh token
            token = self.token_repository.get_token()
            if token and token.get('refresh_token'):
                if self.refresh_token(token['refresh_token']):
                    token = self.token_repository.get_token()
                    return token['access_token'] if token else None
                else:
                    self.logger.warning("Token refresh failed, need to re-authorize")
                    return None
            else:
                self.logger.warning("No refresh token available, need to authorize")
                return None
        
        # Token is valid
        token = self.token_repository.get_token()
        return token['access_token'] if token else None
    
    def refresh_token(self, refresh_token: str) -> bool:
        """
        Refresh access token using refresh token.
        
        Args:
            refresh_token: Refresh token
            
        Returns:
            True if refresh successful, False otherwise
        """
        self.logger.info("Refreshing access token")
        
        token_params = {
            'grant_type': 'refresh_token',
            'client_id': self.config.client_id,
            'client_secret': self.config.client_secret,
            'refresh_token': refresh_token
        }
        
        try:
            response = requests.post(self.config.oauth_token_url, data=token_params)
            response.raise_for_status()
            
            token_data = response.json()
            
            if token_data.get('status') == 'success' or 'access_token' in token_data:
                self.logger.info("Token refreshed successfully")
                
                # Save new token to database
                self.token_repository.save_token(
                    access_token=token_data['access_token'],
                    refresh_token=token_data['refresh_token'],
                    expires_in=token_data['expires_in'],
                    token_type=token_data.get('token_type', 'Bearer'),
                    scope=token_data.get('scope')
                )
                
                return True
            else:
                self.logger.error(f"Token refresh failed: {token_data}")
                return False
                
        except requests.RequestException as e:
            self.logger.error(f"Token refresh request failed: {e}")
            return False
    
    def validate_token(self, access_token: str) -> bool:
        """
        Validate access token using placebo endpoint.
        
        Args:
            access_token: Access token to validate
            
        Returns:
            True if token is valid, False otherwise
        """
        try:
            response = requests.get(
                self.config.api_placebo_url,
                params={'access_token': access_token}
            )
            response.raise_for_status()
            
            data = response.json()
            return data.get('status') == 'success'
            
        except requests.RequestException as e:
            self.logger.error(f"Token validation failed: {e}")
            return False
    
    def ensure_authenticated(self) -> bool:
        """
        Ensure user is authenticated with valid token.
        
        If no valid token exists, initiates authorization flow.
        
        Returns:
            True if authentication successful, False otherwise
        """
        token = self.get_valid_token()
        
        if token:
            # Validate token with placebo call
            if self.validate_token(token):
                self.logger.info("Token is valid")
                return True
            else:
                self.logger.warning("Token validation failed, attempting refresh")
                # Try to refresh
                token_data = self.token_repository.get_token()
                if token_data and self.refresh_token(token_data['refresh_token']):
                    return True
        
        # Need to authorize
        self.logger.info("No valid token, starting authorization")
        return self.authorize()
