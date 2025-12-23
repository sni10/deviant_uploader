"""Repository for upload preset management following DDD and SOLID principles."""
import json
from datetime import datetime
from typing import Optional

from sqlalchemy import delete, desc, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..domain.models import UploadPreset
from .base_repository import BaseRepository
from .models import UploadPreset as UploadPresetModel


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
        table = UploadPresetModel.__table__

        values = {
            "name": preset.name,
            "description": preset.description,
            "base_title": preset.base_title,
            "title_increment_start": preset.title_increment_start,
            "last_used_increment": preset.last_used_increment,
            "artist_comments": preset.artist_comments,
            "tags": json.dumps(preset.tags) if preset.tags else None,
            "is_ai_generated": 1 if preset.is_ai_generated else 0,
            "noai": 1 if preset.noai else 0,
            "is_dirty": 1 if preset.is_dirty else 0,
            "is_mature": 1 if preset.is_mature else 0,
            "mature_level": preset.mature_level,
            "mature_classification": (
                json.dumps(preset.mature_classification)
                if preset.mature_classification
                else None
            ),
            "feature": 1 if preset.feature else 0,
            "allow_comments": 1 if preset.allow_comments else 0,
            "display_resolution": preset.display_resolution,
            "allow_free_download": 1 if preset.allow_free_download else 0,
            "add_watermark": 1 if preset.add_watermark else 0,
            "gallery_folderid": preset.gallery_folderid,
            "is_default": 1 if preset.is_default else 0,
        }

        stmt = (
            pg_insert(table)
            .values(**values)
            .on_conflict_do_update(index_elements=[table.c.name], set_=values)
            .returning(table.c.id)
        )

        preset_id = int(self._execute(stmt).scalar_one())
        self.conn.commit()
        preset.preset_id = preset_id
        return preset_id
    
    def get_preset_by_id(self, preset_id: int) -> Optional[UploadPreset]:
        """
        Get preset by database ID.
        
        Args:
            preset_id: Database ID
            
        Returns:
            UploadPreset object or None if not found
        """
        table = UploadPresetModel.__table__
        stmt = select(table).where(table.c.id == preset_id)
        row = self._execute(stmt).mappings().first()
        return None if row is None else self._row_to_preset(dict(row))
    
    def get_preset_by_name(self, name: str) -> Optional[UploadPreset]:
        """
        Get preset by name.
        
        Args:
            name: Preset name
            
        Returns:
            UploadPreset object or None if not found
        """
        table = UploadPresetModel.__table__
        stmt = select(table).where(table.c.name == name)
        row = self._execute(stmt).mappings().first()
        return None if row is None else self._row_to_preset(dict(row))
    
    def get_all_presets(self) -> list[UploadPreset]:
        """
        Get all presets from database.
        
        Returns:
            List of UploadPreset objects
        """
        table = UploadPresetModel.__table__
        stmt = select(table).order_by(table.c.name)
        return [self._row_to_preset(dict(r)) for r in self._execute(stmt).mappings().all()]
    
    def get_default_preset(self) -> Optional[UploadPreset]:
        """
        Get the default preset.
        
        Returns:
            UploadPreset object or None if no default set
        """
        table = UploadPresetModel.__table__
        stmt = select(table).where(table.c.is_default == 1).limit(1)
        row = self._execute(stmt).mappings().first()
        return None if row is None else self._row_to_preset(dict(row))
    
    def delete_preset(self, preset_id: int) -> bool:
        """
        Delete preset by ID.
        
        Args:
            preset_id: Database ID
            
        Returns:
            True if deleted, False if not found
        """
        table = UploadPresetModel.__table__
        result = self._execute(delete(table).where(table.c.id == preset_id))
        self.conn.commit()
        return (result.rowcount or 0) > 0
    
    def increment_preset_counter(self, preset_id: int) -> int:
        """
        Increment last_used_increment counter for preset.
        
        Args:
            preset_id: Database ID
            
        Returns:
            New counter value
        """
        preset = self.get_preset_by_id(preset_id)
        if not preset:
            raise ValueError(f"Preset with id {preset_id} not found")

        new_value = preset.last_used_increment + 1

        table = UploadPresetModel.__table__
        stmt = (
            update(table)
            .where(table.c.id == preset_id)
            .values(last_used_increment=new_value, updated_at=datetime.now())
        )
        self._execute(stmt)
        self.conn.commit()

        return new_value
    
    def _row_to_preset(self, row: dict) -> UploadPreset:
        """
        Convert database row to UploadPreset object.
        
        Args:
            row: Database row mapping
            
        Returns:
            UploadPreset object
        """
        # Parse JSON fields - handle None, empty strings, and invalid JSON
        tags_str = (row.get("tags") or "").strip()
        try:
            tags = json.loads(tags_str) if tags_str else []
        except json.JSONDecodeError:
            tags = []
        
        mature_class_str = (row.get("mature_classification") or "").strip()
        try:
            mature_classification = json.loads(mature_class_str) if mature_class_str else []
        except json.JSONDecodeError:
            mature_classification = []
        
        def _dt(value: object) -> datetime | None:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            return datetime.fromisoformat(str(value))

        return UploadPreset(
            name=row.get("name"),
            description=row.get("description"),
            base_title=row.get("base_title"),
            title_increment_start=row.get("title_increment_start") or 1,
            last_used_increment=row.get("last_used_increment") or 1,
            artist_comments=row.get("artist_comments"),
            tags=tags,
            is_ai_generated=bool(row.get("is_ai_generated")),
            noai=bool(row.get("noai")),
            is_dirty=bool(row.get("is_dirty")),
            is_mature=bool(row.get("is_mature")),
            mature_level=row.get("mature_level"),
            mature_classification=mature_classification,
            feature=bool(row.get("feature")),
            allow_comments=bool(row.get("allow_comments")),
            display_resolution=row.get("display_resolution") or 0,
            allow_free_download=bool(row.get("allow_free_download")),
            add_watermark=bool(row.get("add_watermark")),
            gallery_folderid=row.get("gallery_folderid"),
            preset_id=row.get("id"),
            is_default=bool(row.get("is_default")),
            created_at=_dt(row.get("created_at")) or datetime.now(),
            updated_at=_dt(row.get("updated_at")) or datetime.now(),
        )
