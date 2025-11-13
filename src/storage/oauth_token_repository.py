"""Repository for OAuth token management following DDD and SOLID principles."""
from datetime import datetime, timedelta
from typing import Optional

from .base_repository import BaseRepository


class OAuthTokenRepository(BaseRepository):
    """
    Repository for managing OAuth tokens.
    
    Single Responsibility: Handles ONLY OAuth token persistence.
    Follows DDD: Token is part of authentication domain.
    """
    
    def save_token(
        self,
        access_token: str,
        refresh_token: str,
        expires_in: int,
        token_type: str = "Bearer",
        scope: Optional[str] = None
    ) -> int:
        """
        Save OAuth token to database.
        
        Args:
            access_token: Access token
            refresh_token: Refresh token
            expires_in: Token lifetime in seconds
            token_type: Token type (default: Bearer)
            scope: Token scope
            
        Returns:
            Token ID
        """
        expires_at = datetime.now() + timedelta(seconds=expires_in)
        
        # Delete old tokens (we only keep the latest)
        self.conn.execute("DELETE FROM oauth_tokens")
        
        cursor = self.conn.execute(
            """
            INSERT INTO oauth_tokens (
                access_token, refresh_token, token_type, expires_at, scope,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                access_token,
                refresh_token,
                token_type,
                expires_at.isoformat(),
                scope,
                datetime.now().isoformat(),
                datetime.now().isoformat()
            )
        )
        self.conn.commit()
        return cursor.lastrowid
    
    def get_token(self) -> Optional[dict]:
        """
        Get the current OAuth token.
        
        Returns:
            Token dict with keys: access_token, refresh_token, expires_at, token_type, scope
            None if no token exists
        """
        cursor = self.conn.execute(
            """
            SELECT access_token, refresh_token, token_type, expires_at, scope
            FROM oauth_tokens
            ORDER BY id DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return {
            "access_token": row[0],
            "refresh_token": row[1],
            "token_type": row[2],
            "expires_at": datetime.fromisoformat(row[3]),
            "scope": row[4]
        }
    
    def is_token_expired(self) -> bool:
        """
        Check if the current token is expired or about to expire.
        
        Returns:
            True if token is expired or will expire in the next 5 minutes
        """
        token = self.get_token()
        if not token:
            return True
        
        # Consider token expired if it expires in the next 5 minutes
        return datetime.now() + timedelta(minutes=5) >= token["expires_at"]
