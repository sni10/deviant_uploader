"""Repository for deviation management following DDD and SOLID principles."""
import json
from datetime import datetime
from typing import Optional

from sqlalchemy import desc, insert, select, update

from ..domain.models import Deviation, UploadStatus
from .base_repository import BaseRepository
from .models import Deviation as DeviationModel


class DeviationRepository(BaseRepository):
    """
    Repository for managing DeviantArt deviations (artwork uploads).
    
    Single Responsibility: Handles ONLY deviation persistence.
    Follows DDD: Deviation is the core domain entity of this application.
    """
    
    def save_deviation(self, deviation: Deviation) -> int:
        """
        Save a new deviation to database.
        
        Args:
            deviation: Deviation object
            
        Returns:
            Deviation ID
        """
        table = DeviationModel.__table__

        stmt = (
            insert(table)
            .values(
                filename=deviation.filename,
                title=deviation.title,
                file_path=deviation.file_path,
                status=deviation.status.value,
                is_mature=1 if deviation.is_mature else 0,
                mature_level=deviation.mature_level,
                mature_classification=(
                    json.dumps(deviation.mature_classification)
                    if deviation.mature_classification
                    else None
                ),
                feature=1 if deviation.feature else 0,
                allow_comments=1 if deviation.allow_comments else 0,
                display_resolution=deviation.display_resolution,
                tags=json.dumps(deviation.tags) if deviation.tags else None,
                allow_free_download=1 if deviation.allow_free_download else 0,
                add_watermark=1 if deviation.add_watermark else 0,
                is_ai_generated=1 if deviation.is_ai_generated else 0,
                noai=1 if deviation.noai else 0,
                artist_comments=deviation.artist_comments,
                original_url=deviation.original_url,
                is_dirty=1 if deviation.is_dirty else 0,
                stack=deviation.stack,
                stackid=deviation.stackid,
                itemid=deviation.itemid,
                gallery_id=deviation.gallery_id,
                deviationid=deviation.deviationid,
                url=deviation.url,
                error=deviation.error,
                created_at=deviation.created_at,
                uploaded_at=deviation.uploaded_at,
                published_time=deviation.published_time,
            )
            .returning(table.c.id)
        )

        deviation_id = int(self._execute(stmt).scalar_one())
        self.conn.commit()
        deviation.deviation_id = deviation_id
        return deviation_id
    
    def update_deviation(self, deviation: Deviation) -> None:
        """
        Update an existing deviation in database.
        
        Args:
            deviation: Deviation object with deviation_id set
        """
        if not deviation.deviation_id:
            raise ValueError("Deviation must have deviation_id set for update")
        
        table = DeviationModel.__table__

        stmt = (
            update(table)
            .where(table.c.id == deviation.deviation_id)
            .values(
                title=deviation.title,
                status=deviation.status.value,
                is_mature=1 if deviation.is_mature else 0,
                mature_level=deviation.mature_level,
                mature_classification=(
                    json.dumps(deviation.mature_classification)
                    if deviation.mature_classification
                    else None
                ),
                feature=1 if deviation.feature else 0,
                allow_comments=1 if deviation.allow_comments else 0,
                display_resolution=deviation.display_resolution,
                tags=json.dumps(deviation.tags) if deviation.tags else None,
                allow_free_download=1 if deviation.allow_free_download else 0,
                add_watermark=1 if deviation.add_watermark else 0,
                is_ai_generated=1 if deviation.is_ai_generated else 0,
                noai=1 if deviation.noai else 0,
                artist_comments=deviation.artist_comments,
                is_dirty=1 if deviation.is_dirty else 0,
                itemid=deviation.itemid,
                gallery_id=deviation.gallery_id,
                deviationid=deviation.deviationid,
                url=deviation.url,
                error=deviation.error,
                uploaded_at=deviation.uploaded_at,
            )
        )

        self._execute(stmt)
        self.conn.commit()
    
    def get_deviation_by_id(self, deviation_id: int) -> Optional[Deviation]:
        """
        Get deviation by ID.
        
        Args:
            deviation_id: Deviation ID
            
        Returns:
            Deviation object or None if not found
        """
        table = DeviationModel.__table__
        stmt = select(table).where(table.c.id == deviation_id)
        row = self._execute(stmt).mappings().first()
        return None if row is None else self._row_to_deviation(dict(row))
    
    def get_deviation_by_filename(self, filename: str) -> Optional[Deviation]:
        """
        Get deviation by filename.
        
        Args:
            filename: Filename
            
        Returns:
            Deviation object or None if not found
        """
        table = DeviationModel.__table__
        stmt = select(table).where(table.c.filename == filename)
        row = self._execute(stmt).mappings().first()
        return None if row is None else self._row_to_deviation(dict(row))
    
    def get_deviations_by_status(self, status: UploadStatus) -> list[Deviation]:
        """
        Get all deviations with specified status.
        
        Args:
            status: Upload status
            
        Returns:
            List of Deviation objects
        """
        table = DeviationModel.__table__
        stmt = (
            select(table)
            .where(table.c.status == status.value)
            .order_by(table.c.created_at)
        )
        return [self._row_to_deviation(dict(r)) for r in self._execute(stmt).mappings().all()]
    
    def get_all_deviations(self) -> list[Deviation]:
        """
        Get all deviations.
        
        Returns:
            List of all Deviation objects
        """
        table = DeviationModel.__table__
        stmt = select(table).order_by(desc(table.c.created_at))
        return [self._row_to_deviation(dict(r)) for r in self._execute(stmt).mappings().all()]
    
    def recover_uploading_deviations(self) -> int:
        """
        Reset deviations stuck in 'uploading' status back to 'new'.
        
        This should be called on startup to recover from crashes.
        
        Returns:
            Number of deviations recovered
        """
        table = DeviationModel.__table__
        stmt = (
            update(table)
            .where(table.c.status == UploadStatus.UPLOADING.value)
            .values(status=UploadStatus.NEW.value)
        )
        result = self._execute(stmt)
        self.conn.commit()
        return int(result.rowcount or 0)
    
    def _row_to_deviation(self, row: dict) -> Deviation:
        """
        Convert database row to Deviation object.
        
        Args:
            row: Database row mapping
            
        Returns:
            Deviation object
        """
        # Parse JSON fields - handle None, empty strings, and invalid JSON
        mature_class_str = (row.get("mature_classification") or "").strip()
        try:
            mature_classification = json.loads(mature_class_str) if mature_class_str else []
        except json.JSONDecodeError:
            mature_classification = []
        
        tags_str = (row.get("tags") or "").strip()
        try:
            tags = json.loads(tags_str) if tags_str else []
        except json.JSONDecodeError:
            tags = []
        
        def _dt(value: object) -> datetime | None:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            return datetime.fromisoformat(str(value))

        status_value = row.get("status")
        try:
            status = UploadStatus(status_value)
        except ValueError:
            status = UploadStatus.NEW

        return Deviation(
            filename=row.get("filename"),
            title=row.get("title"),
            file_path=row.get("file_path"),
            status=status,
            is_mature=bool(row.get("is_mature")),
            mature_level=row.get("mature_level"),
            mature_classification=mature_classification,
            feature=bool(row.get("feature")),
            allow_comments=bool(row.get("allow_comments")),
            display_resolution=row.get("display_resolution") or 0,
            tags=tags,
            allow_free_download=bool(row.get("allow_free_download")),
            add_watermark=bool(row.get("add_watermark")),
            is_ai_generated=bool(row.get("is_ai_generated")),
            noai=bool(row.get("noai")),
            artist_comments=row.get("artist_comments"),
            original_url=row.get("original_url"),
            is_dirty=bool(row.get("is_dirty")),
            stack=row.get("stack"),
            stackid=row.get("stackid"),
            itemid=row.get("itemid"),
            gallery_id=row.get("gallery_id"),
            deviationid=row.get("deviationid"),
            url=row.get("url"),
            error=row.get("error"),
            created_at=_dt(row.get("created_at")) or datetime.now(),
            uploaded_at=_dt(row.get("uploaded_at")),
            published_time=row.get("published_time"),
            deviation_id=row.get("id"),
        )

    def update_published_time_by_deviationid(
        self, deviationid: str, published_time: Optional[str]
    ) -> None:
        """Update published_time for an existing deviation by its DeviantArt ID.

        This is used by stats sync when enriching existing uploads with
        data from the /deviation/{deviationid} endpoint.
        """

        table = DeviationModel.__table__
        stmt = (
            update(table)
            .where(table.c.deviationid == deviationid)
            .values(published_time=published_time)
        )
        self._execute(stmt)
        self.conn.commit()
