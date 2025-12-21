"""Repository for gallery management following DDD and SOLID principles."""
from datetime import datetime
from typing import Optional

from ..domain.models import Gallery
from .base_repository import BaseRepository


class GalleryRepository(BaseRepository):
    """
    Repository for managing DeviantArt galleries.
    
    Single Responsibility: Handles ONLY gallery persistence.
    Follows DDD: Gallery is a domain entity with its own lifecycle.
    """
    
    def save_gallery(self, gallery: Gallery) -> int:
        """
        Save a new gallery to database or update if exists.
        
        Args:
            gallery: Gallery object
            
        Returns:
            Gallery ID
        """
        # Check if gallery with this folderid already exists
        existing = self.get_gallery_by_folderid(gallery.folderid)
        
        if existing:
            # Update existing gallery
            self.conn.execute(
                """
                UPDATE galleries SET
                    name = ?,
                    parent = ?,
                    size = ?,
                    sync_enabled = ?,
                    updated_at = ?
                WHERE folderid = ?
                """,
                (
                    gallery.name,
                    gallery.parent,
                    gallery.size,
                    1 if gallery.sync_enabled else 0,
                    datetime.now().isoformat(),
                    gallery.folderid
                )
            )
            self.conn.commit()
            return existing.gallery_db_id
        else:
            # Insert new gallery
            cursor = self.conn.execute(
                """
                INSERT INTO galleries (
                    folderid, name, parent, size, sync_enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    gallery.folderid,
                    gallery.name,
                    gallery.parent,
                    gallery.size,
                    1 if gallery.sync_enabled else 0,
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                )
            )
            self.conn.commit()
            gallery.gallery_db_id = cursor.lastrowid
            return cursor.lastrowid
    
    def get_gallery_by_id(self, gallery_id: int) -> Optional[Gallery]:
        """
        Get gallery by internal database ID.
        
        Args:
            gallery_id: Internal database ID
            
        Returns:
            Gallery object or None if not found
        """
        cursor = self.conn.execute(
            """
            SELECT id, folderid, name, parent, size, sync_enabled, created_at, updated_at
            FROM galleries
            WHERE id = ?
            """,
            (gallery_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return self._row_to_gallery(row)
    
    def get_gallery_by_folderid(self, folderid: str) -> Optional[Gallery]:
        """
        Get gallery by DeviantArt folder UUID.
        
        Args:
            folderid: DeviantArt folder UUID
            
        Returns:
            Gallery object or None if not found
        """
        cursor = self.conn.execute(
            """
            SELECT id, folderid, name, parent, size, sync_enabled, created_at, updated_at
            FROM galleries
            WHERE folderid = ?
            """,
            (folderid,)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return self._row_to_gallery(row)
    
    def get_all_galleries(self) -> list[Gallery]:
        """
        Get all galleries.
        
        Returns:
            List of all Gallery objects
        """
        cursor = self.conn.execute(
            """
            SELECT id, folderid, name, parent, size, sync_enabled, created_at, updated_at
            FROM galleries
            ORDER BY name
            """
        )
        
        return [self._row_to_gallery(row) for row in cursor.fetchall()]
    
    def update_sync_enabled(self, folderid: str, sync_enabled: bool) -> bool:
        """
        Update sync_enabled flag for a gallery.

        Args:
            folderid: DeviantArt folder UUID
            sync_enabled: New sync_enabled value

        Returns:
            True if updated successfully, False if gallery not found
        """
        cursor = self.conn.execute(
            """
            UPDATE galleries
            SET sync_enabled = ?, updated_at = ?
            WHERE folderid = ?
            """,
            (1 if sync_enabled else 0, datetime.now().isoformat(), folderid)
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def _row_to_gallery(self, row: tuple) -> Gallery:
        """
        Convert database row to Gallery object.

        Args:
            row: Database row tuple

        Returns:
            Gallery object
        """
        return Gallery(
            folderid=row[1],
            name=row[2],
            parent=row[3],
            size=row[4],
            sync_enabled=bool(row[5]),
            gallery_db_id=row[0],
            created_at=datetime.fromisoformat(row[6]),
            updated_at=datetime.fromisoformat(row[7])
        )
