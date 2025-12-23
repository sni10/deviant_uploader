"""Repository for OAuth token management following DDD and SOLID principles."""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, desc, insert, select

from .base_repository import BaseRepository
from .models import OAuthToken as OAuthTokenModel


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

        table = OAuthTokenModel.__table__

        # Delete old tokens (we only keep the latest)
        self._execute(delete(table))

        stmt = (
            insert(table)
            .values(
                user_id=None,
                access_token=access_token,
                refresh_token=refresh_token,
                token_type=token_type,
                expires_at=expires_at,
                scope=scope,
            )
            .returning(table.c.id)
        )

        token_id = int(self._execute(stmt).scalar_one())
        self.conn.commit()
        return token_id
    
    def get_token(self) -> Optional[dict]:
        """
        Get the current OAuth token.
        
        Returns:
            Token dict with keys: access_token, refresh_token, expires_at, token_type, scope
            None if no token exists
        """
        table = OAuthTokenModel.__table__
        stmt = (
            select(
                table.c.access_token,
                table.c.refresh_token,
                table.c.token_type,
                table.c.expires_at,
                table.c.scope,
            )
            .order_by(desc(table.c.id))
            .limit(1)
        )

        row = self._execute(stmt).mappings().first()
        if row is None:
            return None

        expires_value = row.get("expires_at")
        if isinstance(expires_value, datetime):
            expires_dt = expires_value
        else:
            expires_dt = datetime.fromisoformat(str(expires_value))

        return {
            "access_token": row.get("access_token"),
            "refresh_token": row.get("refresh_token"),
            "token_type": row.get("token_type"),
            "expires_at": expires_dt,
            "scope": row.get("scope"),
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
    
    def delete_token(self) -> None:
        """
        Delete all OAuth tokens from database.
        
        This is used when a token is detected as expired or invalid
        by the API, allowing the system to re-authenticate automatically.
        """
        table = OAuthTokenModel.__table__
        self._execute(delete(table))
        self.conn.commit()
