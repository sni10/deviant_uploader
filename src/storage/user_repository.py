"""Repository for user management following DDD and SOLID principles."""
from datetime import datetime
from typing import Optional

from ..domain.models import User
from .base_repository import BaseRepository


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
        # Check if user with this userid already exists
        existing = self.get_user_by_userid(user.userid)
        
        if existing:
            # Update existing user
            self.conn.execute(
                """
                UPDATE users SET
                    username = ?,
                    usericon = ?,
                    type = ?,
                    is_watching = ?,
                    profile_url = ?,
                    user_is_artist = ?,
                    artist_level = ?,
                    artist_specialty = ?,
                    real_name = ?,
                    tagline = ?,
                    country_id = ?,
                    country = ?,
                    website = ?,
                    bio = ?,
                    user_deviations = ?,
                    user_favourites = ?,
                    user_comments = ?,
                    profile_pageviews = ?,
                    profile_comments = ?,
                    updated_at = ?
                WHERE userid = ?
                """,
                (
                    user.username,
                    user.usericon,
                    user.type,
                    1 if user.is_watching else 0 if user.is_watching is not None else None,
                    user.profile_url,
                    1 if user.user_is_artist else 0 if user.user_is_artist is not None else None,
                    user.artist_level,
                    user.artist_specialty,
                    user.real_name,
                    user.tagline,
                    user.country_id,
                    user.country,
                    user.website,
                    user.bio,
                    user.user_deviations,
                    user.user_favourites,
                    user.user_comments,
                    user.profile_pageviews,
                    user.profile_comments,
                    datetime.now().isoformat(),
                    user.userid
                )
            )
            self.conn.commit()
            return existing.user_db_id
        else:
            # Insert new user
            cursor = self.conn.execute(
                """
                INSERT INTO users (
                    userid, username, usericon, type,
                    is_watching, profile_url, user_is_artist,
                    artist_level, artist_specialty, real_name,
                    tagline, country_id, country, website, bio,
                    user_deviations, user_favourites, user_comments,
                    profile_pageviews, profile_comments,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user.userid,
                    user.username,
                    user.usericon,
                    user.type,
                    1 if user.is_watching else 0 if user.is_watching is not None else None,
                    user.profile_url,
                    1 if user.user_is_artist else 0 if user.user_is_artist is not None else None,
                    user.artist_level,
                    user.artist_specialty,
                    user.real_name,
                    user.tagline,
                    user.country_id,
                    user.country,
                    user.website,
                    user.bio,
                    user.user_deviations,
                    user.user_favourites,
                    user.user_comments,
                    user.profile_pageviews,
                    user.profile_comments,
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                )
            )
            self.conn.commit()
            user.user_db_id = cursor.lastrowid
            return cursor.lastrowid
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        Get user by internal database ID.
        
        Args:
            user_id: Internal database ID
            
        Returns:
            User object or None if not found
        """
        cursor = self.conn.execute(
            """
            SELECT id, userid, username, usericon, type,
                   is_watching, profile_url, user_is_artist,
                   artist_level, artist_specialty, real_name,
                   tagline, country_id, country, website, bio,
                   user_deviations, user_favourites, user_comments,
                   profile_pageviews, profile_comments,
                   created_at, updated_at
            FROM users
            WHERE id = ?
            """,
            (user_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return self._row_to_user(row)
    
    def get_user_by_userid(self, userid: str) -> Optional[User]:
        """
        Get user by DeviantArt user UUID.
        
        Args:
            userid: DeviantArt user UUID
            
        Returns:
            User object or None if not found
        """
        cursor = self.conn.execute(
            """
            SELECT id, userid, username, usericon, type,
                   is_watching, profile_url, user_is_artist,
                   artist_level, artist_specialty, real_name,
                   tagline, country_id, country, website, bio,
                   user_deviations, user_favourites, user_comments,
                   profile_pageviews, profile_comments,
                   created_at, updated_at
            FROM users
            WHERE userid = ?
            """,
            (userid,)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return self._row_to_user(row)
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """
        Get user by DeviantArt username.
        
        Args:
            username: DeviantArt username
            
        Returns:
            User object or None if not found
        """
        cursor = self.conn.execute(
            """
            SELECT id, userid, username, usericon, type,
                   is_watching, profile_url, user_is_artist,
                   artist_level, artist_specialty, real_name,
                   tagline, country_id, country, website, bio,
                   user_deviations, user_favourites, user_comments,
                   profile_pageviews, profile_comments,
                   created_at, updated_at
            FROM users
            WHERE username = ?
            """,
            (username,)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return self._row_to_user(row)
    
    def get_all_users(self) -> list[User]:
        """
        Get all users.
        
        Returns:
            List of all User objects
        """
        cursor = self.conn.execute(
            """
            SELECT id, userid, username, usericon, type,
                   is_watching, profile_url, user_is_artist,
                   artist_level, artist_specialty, real_name,
                   tagline, country_id, country, website, bio,
                   user_deviations, user_favourites, user_comments,
                   profile_pageviews, profile_comments,
                   created_at, updated_at
            FROM users
            ORDER BY username
            """
        )
        
        return [self._row_to_user(row) for row in cursor.fetchall()]
    
    def _row_to_user(self, row: tuple) -> User:
        """
        Convert database row to User object.
        
        Args:
            row: Database row tuple
            
        Returns:
            User object
        """
        return User(
            userid=row[1],
            username=row[2],
            usericon=row[3],
            type=row[4],
            is_watching=bool(row[5]) if row[5] is not None else None,
            profile_url=row[6],
            user_is_artist=bool(row[7]) if row[7] is not None else None,
            artist_level=row[8],
            artist_specialty=row[9],
            real_name=row[10],
            tagline=row[11],
            country_id=row[12],
            country=row[13],
            website=row[14],
            bio=row[15],
            user_deviations=row[16],
            user_favourites=row[17],
            user_comments=row[18],
            profile_pageviews=row[19],
            profile_comments=row[20],
            created_at=datetime.fromisoformat(row[21]),
            updated_at=datetime.fromisoformat(row[22]),
            user_db_id=row[0]
        )
