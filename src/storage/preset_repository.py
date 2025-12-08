"""Repository for upload preset management following DDD and SOLID principles."""
import json
from datetime import datetime
from typing import Optional

from ..domain.models import UploadPreset
from .base_repository import BaseRepository


class PresetRepository(BaseRepository):
    """
    Repository for managing upload presets.
    
    Single Responsibility: Handles ONLY preset persistence.
    Follows DDD: UploadPreset is a domain entity with its own lifecycle.
    """
    
    def save_preset(self, preset: UploadPreset) -> int:
        """
        Save a new preset to database or update if exists.
        
        Args:
            preset: UploadPreset object
            
        Returns:
            Preset ID
        """
        # Check if preset with this name already exists
        existing = self.get_preset_by_name(preset.name)
        
        # Convert lists to JSON strings
        tags_json = json.dumps(preset.tags) if preset.tags else None
        mature_classification_json = json.dumps(preset.mature_classification) if preset.mature_classification else None
        
        if existing:
            # Update existing preset
            self.conn.execute(
                """
                UPDATE upload_presets SET
                    description = ?,
                    base_title = ?,
                    title_increment_start = ?,
                    last_used_increment = ?,
                    artist_comments = ?,
                    tags = ?,
                    is_ai_generated = ?,
                    noai = ?,
                    is_dirty = ?,
                    is_mature = ?,
                    mature_level = ?,
                    mature_classification = ?,
                    feature = ?,
                    allow_comments = ?,
                    display_resolution = ?,
                    allow_free_download = ?,
                    add_watermark = ?,
                    gallery_folderid = ?,
                    is_default = ?,
                    updated_at = ?
                WHERE name = ?
                """,
                (
                    preset.description,
                    preset.base_title,
                    preset.title_increment_start,
                    preset.last_used_increment,
                    preset.artist_comments,
                    tags_json,
                    1 if preset.is_ai_generated else 0,
                    1 if preset.noai else 0,
                    1 if preset.is_dirty else 0,
                    1 if preset.is_mature else 0,
                    preset.mature_level,
                    mature_classification_json,
                    1 if preset.feature else 0,
                    1 if preset.allow_comments else 0,
                    preset.display_resolution,
                    1 if preset.allow_free_download else 0,
                    1 if preset.add_watermark else 0,
                    preset.gallery_folderid,
                    1 if preset.is_default else 0,
                    datetime.now().isoformat(),
                    preset.name
                )
            )
            self.conn.commit()
            return existing.preset_id
        else:
            # Insert new preset
            cursor = self.conn.execute(
                """
                INSERT INTO upload_presets (
                    name, description, base_title,
                    title_increment_start, last_used_increment,
                    artist_comments, tags, is_ai_generated, noai, is_dirty,
                    is_mature, mature_level, mature_classification,
                    feature, allow_comments, display_resolution,
                    allow_free_download, add_watermark,
                    gallery_folderid, is_default,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    preset.name,
                    preset.description,
                    preset.base_title,
                    preset.title_increment_start,
                    preset.last_used_increment,
                    preset.artist_comments,
                    tags_json,
                    1 if preset.is_ai_generated else 0,
                    1 if preset.noai else 0,
                    1 if preset.is_dirty else 0,
                    1 if preset.is_mature else 0,
                    preset.mature_level,
                    mature_classification_json,
                    1 if preset.feature else 0,
                    1 if preset.allow_comments else 0,
                    preset.display_resolution,
                    1 if preset.allow_free_download else 0,
                    1 if preset.add_watermark else 0,
                    preset.gallery_folderid,
                    1 if preset.is_default else 0,
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                )
            )
            self.conn.commit()
            return cursor.lastrowid
    
    def get_preset_by_id(self, preset_id: int) -> Optional[UploadPreset]:
        """
        Get preset by database ID.
        
        Args:
            preset_id: Database ID
            
        Returns:
            UploadPreset object or None if not found
        """
        cursor = self.conn.execute(
            """
            SELECT * FROM upload_presets WHERE id = ?
            """,
            (preset_id,)
        )
        row = cursor.fetchone()
        
        if row:
            return self._row_to_preset(row)
        return None
    
    def get_preset_by_name(self, name: str) -> Optional[UploadPreset]:
        """
        Get preset by name.
        
        Args:
            name: Preset name
            
        Returns:
            UploadPreset object or None if not found
        """
        cursor = self.conn.execute(
            """
            SELECT * FROM upload_presets WHERE name = ?
            """,
            (name,)
        )
        row = cursor.fetchone()
        
        if row:
            return self._row_to_preset(row)
        return None
    
    def get_all_presets(self) -> list[UploadPreset]:
        """
        Get all presets from database.
        
        Returns:
            List of UploadPreset objects
        """
        cursor = self.conn.execute(
            """
            SELECT * FROM upload_presets ORDER BY name
            """
        )
        rows = cursor.fetchall()
        
        return [self._row_to_preset(row) for row in rows]
    
    def get_default_preset(self) -> Optional[UploadPreset]:
        """
        Get the default preset.
        
        Returns:
            UploadPreset object or None if no default set
        """
        cursor = self.conn.execute(
            """
            SELECT * FROM upload_presets WHERE is_default = 1 LIMIT 1
            """
        )
        row = cursor.fetchone()
        
        if row:
            return self._row_to_preset(row)
        return None
    
    def delete_preset(self, preset_id: int) -> bool:
        """
        Delete preset by ID.
        
        Args:
            preset_id: Database ID
            
        Returns:
            True if deleted, False if not found
        """
        cursor = self.conn.execute(
            """
            DELETE FROM upload_presets WHERE id = ?
            """,
            (preset_id,)
        )
        self.conn.commit()
        return cursor.rowcount > 0
    
    def increment_preset_counter(self, preset_id: int) -> int:
        """
        Increment last_used_increment counter for preset.
        
        Args:
            preset_id: Database ID
            
        Returns:
            New counter value
        """
        # Get current value
        preset = self.get_preset_by_id(preset_id)
        if not preset:
            raise ValueError(f"Preset with id {preset_id} not found")
        
        new_value = preset.last_used_increment + 1
        
        # Update counter
        self.conn.execute(
            """
            UPDATE upload_presets 
            SET last_used_increment = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_value, datetime.now().isoformat(), preset_id)
        )
        self.conn.commit()
        
        return new_value
    
    def _row_to_preset(self, row: tuple) -> UploadPreset:
        """
        Convert database row to UploadPreset object.
        
        Args:
            row: Database row tuple
            
        Returns:
            UploadPreset object
        """
        # Parse JSON fields
        tags = json.loads(row[6]) if row[6] else []
        mature_classification = json.loads(row[12]) if row[12] else []
        
        return UploadPreset(
            name=row[1],
            description=row[2],
            base_title=row[3],
            title_increment_start=row[4],
            last_used_increment=row[5],
            artist_comments=row[7],
            tags=tags,
            is_ai_generated=bool(row[8]),
            noai=bool(row[9]),
            is_dirty=bool(row[10]),
            is_mature=bool(row[11]),
            mature_level=row[13],
            mature_classification=mature_classification,
            feature=bool(row[14]),
            allow_comments=bool(row[15]),
            display_resolution=row[16],
            allow_free_download=bool(row[17]),
            add_watermark=bool(row[18]),
            gallery_folderid=row[19],
            preset_id=row[0],
            is_default=bool(row[20]),
            created_at=datetime.fromisoformat(row[21]) if row[21] else datetime.now(),
            updated_at=datetime.fromisoformat(row[22]) if row[22] else datetime.now()
        )
