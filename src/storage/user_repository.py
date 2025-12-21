"""Repository for user management following DDD and SOLID principles."""
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..domain.models import User
from .base_repository import BaseRepository
from .models import User as UserModel


class UserRepository(BaseRepository):
    """
    Repository for managing DeviantArt users.
    
    Single Responsibility: Handles ONLY user persistence.
    Follows DDD: User is a domain entity with its own lifecycle.
    """
    
    def save_user(self, user: User) -> int:
        """
        Save a new user to database or update if exists.
        
        Args:
            user: User object
            
        Returns:
            User ID
        """
        table = UserModel.__table__

        values = {
            "userid": user.userid,
            "username": user.username,
            "usericon": user.usericon,
            "type": user.type,
            "is_watching": (
                1 if user.is_watching else 0 if user.is_watching is not None else None
            ),
            "profile_url": user.profile_url,
            "user_is_artist": (
                1
                if user.user_is_artist
                else 0
                if user.user_is_artist is not None
                else None
            ),
            "artist_level": user.artist_level,
            "artist_specialty": user.artist_specialty,
            "real_name": user.real_name,
            "tagline": user.tagline,
            "country_id": user.country_id,
            "country": user.country,
            "website": user.website,
            "bio": user.bio,
            "user_deviations": user.user_deviations,
            "user_favourites": user.user_favourites,
            "user_comments": user.user_comments,
            "profile_pageviews": user.profile_pageviews,
            "profile_comments": user.profile_comments,
        }

        stmt = (
            pg_insert(table)
            .values(**values)
            .on_conflict_do_update(index_elements=[table.c.userid], set_=values)
            .returning(table.c.id)
        )

        user_db_id = int(self._execute(stmt).scalar_one())
        self.conn.commit()

        user.user_db_id = user_db_id
        return user_db_id
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        Get user by internal database ID.
        
        Args:
            user_id: Internal database ID
            
        Returns:
            User object or None if not found
        """
        table = UserModel.__table__
        stmt = select(table).where(table.c.id == user_id)
        row = self._execute(stmt).mappings().first()
        return None if row is None else self._row_to_user(dict(row))
    
    def get_user_by_userid(self, userid: str) -> Optional[User]:
        """
        Get user by DeviantArt user UUID.
        
        Args:
            userid: DeviantArt user UUID
            
        Returns:
            User object or None if not found
        """
        table = UserModel.__table__
        stmt = select(table).where(table.c.userid == userid)
        row = self._execute(stmt).mappings().first()
        return None if row is None else self._row_to_user(dict(row))
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """
        Get user by DeviantArt username.
        
        Args:
            username: DeviantArt username
            
        Returns:
            User object or None if not found
        """
        table = UserModel.__table__
        stmt = select(table).where(table.c.username == username)
        row = self._execute(stmt).mappings().first()
        return None if row is None else self._row_to_user(dict(row))
    
    def get_all_users(self) -> list[User]:
        """
        Get all users.
        
        Returns:
            List of all User objects
        """
        table = UserModel.__table__
        stmt = select(table).order_by(table.c.username)
        return [self._row_to_user(dict(row)) for row in self._execute(stmt).mappings().all()]
    
    def _row_to_user(self, row: dict) -> User:
        """
        Convert database row to User object.
        
        Args:
            row: Database row mapping
            
        Returns:
            User object
        """
        def _dt(value: object) -> datetime | None:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            return datetime.fromisoformat(str(value))

        return User(
            userid=row.get("userid"),
            username=row.get("username"),
            usericon=row.get("usericon"),
            type=row.get("type"),
            is_watching=bool(row.get("is_watching"))
            if row.get("is_watching") is not None
            else None,
            profile_url=row.get("profile_url"),
            user_is_artist=bool(row.get("user_is_artist"))
            if row.get("user_is_artist") is not None
            else None,
            artist_level=row.get("artist_level"),
            artist_specialty=row.get("artist_specialty"),
            real_name=row.get("real_name"),
            tagline=row.get("tagline"),
            country_id=row.get("country_id"),
            country=row.get("country"),
            website=row.get("website"),
            bio=row.get("bio"),
            user_deviations=row.get("user_deviations"),
            user_favourites=row.get("user_favourites"),
            user_comments=row.get("user_comments"),
            profile_pageviews=row.get("profile_pageviews"),
            profile_comments=row.get("profile_comments"),
            created_at=_dt(row.get("created_at")) or datetime.now(),
            updated_at=_dt(row.get("updated_at")) or datetime.now(),
            user_db_id=row.get("id"),
        )
