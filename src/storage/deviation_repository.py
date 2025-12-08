"""Repository for deviation management following DDD and SOLID principles."""
import json
from datetime import datetime
from typing import Optional

from ..domain.models import Deviation, UploadStatus
from .base_repository import BaseRepository


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
        cursor = self.conn.execute(
            """
            INSERT INTO deviations (
                filename, title, file_path, status,
                is_mature, mature_level, mature_classification,
                feature, allow_comments, display_resolution,
                tags, allow_free_download, add_watermark,
                is_ai_generated, noai,
                artist_comments, original_url, is_dirty, stack, stackid,
                itemid, gallery_id, deviationid, url, error,
                created_at, uploaded_at, published_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                deviation.filename,
                deviation.title,
                deviation.file_path,
                deviation.status.value,
                1 if deviation.is_mature else 0,
                deviation.mature_level,
                json.dumps(deviation.mature_classification)
                if deviation.mature_classification
                else None,
                1 if deviation.feature else 0,
                1 if deviation.allow_comments else 0,
                deviation.display_resolution,
                json.dumps(deviation.tags) if deviation.tags else None,
                1 if deviation.allow_free_download else 0,
                1 if deviation.add_watermark else 0,
                1 if deviation.is_ai_generated else 0,
                1 if deviation.noai else 0,
                deviation.artist_comments,
                deviation.original_url,
                1 if deviation.is_dirty else 0,
                deviation.stack,
                deviation.stackid,
                deviation.itemid,
                deviation.gallery_id,
                deviation.deviationid,
                deviation.url,
                deviation.error,
                deviation.created_at.isoformat(),
                deviation.uploaded_at.isoformat() if deviation.uploaded_at else None,
                deviation.published_time,
            ),
        )
        self.conn.commit()
        deviation.deviation_id = cursor.lastrowid
        return cursor.lastrowid
    
    def update_deviation(self, deviation: Deviation) -> None:
        """
        Update an existing deviation in database.
        
        Args:
            deviation: Deviation object with deviation_id set
        """
        if not deviation.deviation_id:
            raise ValueError("Deviation must have deviation_id set for update")
        
        self.conn.execute(
            """
            UPDATE deviations SET
                status = ?,
                itemid = ?,
                gallery_id = ?,
                deviationid = ?,
                url = ?,
                error = ?,
                uploaded_at = ?
            WHERE id = ?
            """,
            (
                deviation.status.value,
                deviation.itemid,
                deviation.gallery_id,
                deviation.deviationid,
                deviation.url,
                deviation.error,
                deviation.uploaded_at.isoformat() if deviation.uploaded_at else None,
                deviation.deviation_id
            )
        )
        self.conn.commit()
    
    def get_deviation_by_id(self, deviation_id: int) -> Optional[Deviation]:
        """
        Get deviation by ID.
        
        Args:
            deviation_id: Deviation ID
            
        Returns:
            Deviation object or None if not found
        """
        cursor = self.conn.execute(
            """
            SELECT id, filename, title, file_path, status,
                   is_mature, mature_level, mature_classification,
                   feature, allow_comments, display_resolution,
                   tags, allow_free_download, add_watermark,
                   is_ai_generated, noai,
                   artist_comments, original_url, is_dirty, stack, stackid,
                   itemid, gallery_id, deviationid, url, error,
                   created_at, uploaded_at, published_time
            FROM deviations
            WHERE id = ?
            """,
            (deviation_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return self._row_to_deviation(row)
    
    def get_deviation_by_filename(self, filename: str) -> Optional[Deviation]:
        """
        Get deviation by filename.
        
        Args:
            filename: Filename
            
        Returns:
            Deviation object or None if not found
        """
        cursor = self.conn.execute(
            """
            SELECT id, filename, title, file_path, status,
                   is_mature, mature_level, mature_classification,
                   feature, allow_comments, display_resolution,
                   tags, allow_free_download, add_watermark,
                   is_ai_generated, noai,
                   artist_comments, original_url, is_dirty, stack, stackid,
                   itemid, gallery_id, deviationid, url, error,
                   created_at, uploaded_at, published_time
            FROM deviations
            WHERE filename = ?
            """,
            (filename,)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return self._row_to_deviation(row)
    
    def get_deviations_by_status(self, status: UploadStatus) -> list[Deviation]:
        """
        Get all deviations with specified status.
        
        Args:
            status: Upload status
            
        Returns:
            List of Deviation objects
        """
        cursor = self.conn.execute(
            """
            SELECT id, filename, title, file_path, status,
                   is_mature, mature_level, mature_classification,
                   feature, allow_comments, display_resolution,
                   tags, allow_free_download, add_watermark,
                   is_ai_generated, noai,
                   artist_comments, original_url, is_dirty, stack, stackid,
                   itemid, gallery_id, deviationid, url, error,
                   created_at, uploaded_at, published_time
            FROM deviations
            WHERE status = ?
            ORDER BY created_at
            """,
            (status.value,)
        )
        
        return [self._row_to_deviation(row) for row in cursor.fetchall()]
    
    def get_all_deviations(self) -> list[Deviation]:
        """
        Get all deviations.
        
        Returns:
            List of all Deviation objects
        """
        cursor = self.conn.execute(
            """
            SELECT id, filename, title, file_path, status,
                   is_mature, mature_level, mature_classification,
                   feature, allow_comments, display_resolution,
                   tags, allow_free_download, add_watermark,
                   is_ai_generated, noai,
                   artist_comments, original_url, is_dirty, stack, stackid,
                   itemid, gallery_id, deviationid, url, error,
                   created_at, uploaded_at, published_time
            FROM deviations
            ORDER BY created_at DESC
            """
        )
        
        return [self._row_to_deviation(row) for row in cursor.fetchall()]
    
    def recover_uploading_deviations(self) -> int:
        """
        Reset deviations stuck in 'uploading' status back to 'new'.
        
        This should be called on startup to recover from crashes.
        
        Returns:
            Number of deviations recovered
        """
        cursor = self.conn.execute(
            """
            UPDATE deviations
            SET status = ?
            WHERE status = ?
            """,
            (UploadStatus.NEW.value, UploadStatus.UPLOADING.value)
        )
        self.conn.commit()
        return cursor.rowcount
    
    def _row_to_deviation(self, row: tuple) -> Deviation:
        """
        Convert database row to Deviation object.
        
        Args:
            row: Database row tuple
            
        Returns:
            Deviation object
        """
        return Deviation(
            filename=row[1],
            title=row[2],
            file_path=row[3],
            status=UploadStatus(row[4]),
            is_mature=bool(row[5]),
            mature_level=row[6],
            mature_classification=json.loads(row[7]) if row[7] else [],
            feature=bool(row[8]),
            allow_comments=bool(row[9]),
            display_resolution=row[10],
            tags=json.loads(row[11]) if row[11] else [],
            allow_free_download=bool(row[12]),
            add_watermark=bool(row[13]),
            is_ai_generated=bool(row[14]),
            noai=bool(row[15]),
            artist_comments=row[16],
            original_url=row[17],
            is_dirty=bool(row[18]),
            stack=row[19],
            stackid=row[20],
            itemid=row[21],
            gallery_id=row[22],
            deviationid=row[23],
            url=row[24],
            error=row[25],
            created_at=datetime.fromisoformat(row[26]),
            uploaded_at=datetime.fromisoformat(row[27]) if row[27] else None,
            published_time=row[28],
            deviation_id=row[0],
        )

    def update_published_time_by_deviationid(
        self, deviationid: str, published_time: Optional[str]
    ) -> None:
        """Update published_time for an existing deviation by its DeviantArt ID.

        This is used by stats sync when enriching existing uploads with
        data from the /deviation/{deviationid} endpoint.
        """

        self.conn.execute(
            """
            UPDATE deviations
            SET published_time = ?
            WHERE deviationid = ?
            """,
            (published_time, deviationid),
        )
        self.conn.commit()
