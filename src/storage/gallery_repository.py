"""Repository for gallery management following DDD and SOLID principles."""
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..domain.models import Gallery
from .base_repository import BaseRepository
from .models import Gallery as GalleryModel


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
        table = GalleryModel.__table__

        values = {
            "folderid": gallery.folderid,
            "name": gallery.name,
            "parent": gallery.parent,
            "size": gallery.size,
            "sync_enabled": 1 if gallery.sync_enabled else 0,
        }

        stmt = (
            pg_insert(table)
            .values(**values)
            .on_conflict_do_update(index_elements=[table.c.folderid], set_=values)
            .returning(table.c.id)
        )

        gallery_id = int(self._execute(stmt).scalar_one())
        self.conn.commit()
        gallery.gallery_db_id = gallery_id
        return gallery_id
    
    def get_gallery_by_id(self, gallery_id: int) -> Optional[Gallery]:
        """
        Get gallery by internal database ID.
        
        Args:
            gallery_id: Internal database ID
            
        Returns:
            Gallery object or None if not found
        """
        table = GalleryModel.__table__
        stmt = select(table).where(table.c.id == gallery_id)
        row = self._execute(stmt).mappings().first()
        return None if row is None else self._row_to_gallery(dict(row))
    
    def get_gallery_by_folderid(self, folderid: str) -> Optional[Gallery]:
        """
        Get gallery by DeviantArt folder UUID.
        
        Args:
            folderid: DeviantArt folder UUID
            
        Returns:
            Gallery object or None if not found
        """
        table = GalleryModel.__table__
        stmt = select(table).where(table.c.folderid == folderid)
        row = self._execute(stmt).mappings().first()
        return None if row is None else self._row_to_gallery(dict(row))
    
    def get_all_galleries(self) -> list[Gallery]:
        """
        Get all galleries.
        
        Returns:
            List of all Gallery objects
        """
        table = GalleryModel.__table__
        stmt = select(table).order_by(table.c.name)
        return [self._row_to_gallery(dict(r)) for r in self._execute(stmt).mappings().all()]

    def get_sync_enabled_galleries(self) -> list[Gallery]:
        """
        Get all galleries with sync_enabled=True.
        
        Returns:
            List of Gallery objects with sync enabled
        """
        table = GalleryModel.__table__
        stmt = select(table).where(table.c.sync_enabled == 1).order_by(table.c.name)
        return [self._row_to_gallery(dict(r)) for r in self._execute(stmt).mappings().all()]
    
    def update_sync_enabled(self, folderid: str, sync_enabled: bool) -> bool:
        """
        Update sync_enabled flag for a gallery.

        Args:
            folderid: DeviantArt folder UUID
            sync_enabled: New sync_enabled value

        Returns:
            True if updated successfully, False if gallery not found
        """
        table = GalleryModel.__table__
        stmt = (
            update(table)
            .where(table.c.folderid == folderid)
            .values(sync_enabled=1 if sync_enabled else 0, updated_at=datetime.now())
        )
        result = self._execute(stmt)
        self.conn.commit()
        return (result.rowcount or 0) > 0

    def _row_to_gallery(self, row: dict) -> Gallery:
        """
        Convert database row to Gallery object.

        Args:
            row: Database row mapping

        Returns:
            Gallery object
        """
        def _dt(value: object) -> datetime | None:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            return datetime.fromisoformat(str(value))

        return Gallery(
            folderid=row.get("folderid"),
            name=row.get("name"),
            parent=row.get("parent"),
            size=row.get("size"),
            sync_enabled=bool(row.get("sync_enabled")),
            gallery_db_id=row.get("id"),
            created_at=_dt(row.get("created_at")) or datetime.now(),
            updated_at=_dt(row.get("updated_at")) or datetime.now(),
        )
