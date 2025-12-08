"""Repository for extended deviation metadata."""
import json
from typing import Optional

from .base_repository import BaseRepository


class DeviationMetadataRepository(BaseRepository):
    """Provides persistence for extended deviation metadata.
    
    This repository handles the `deviation_metadata` table which stores
    comprehensive metadata about deviations including description, tags,
    author info, camera data, collections, and detailed statistics.
    """

    def save_metadata(
        self,
        *,
        deviationid: str,
        title: str,
        description: Optional[str],
        license: Optional[str],
        allows_comments: Optional[bool],
        tags: list,
        is_favourited: Optional[bool],
        is_watching: Optional[bool],
        is_mature: Optional[bool],
        mature_level: Optional[str],
        mature_classification: list,
        printid: Optional[str],
        author: Optional[dict],
        creation_time: Optional[str],
        category: Optional[str],
        file_size: Optional[str],
        resolution: Optional[str],
        submitted_with: Optional[dict],
        stats_json: Optional[dict],
        camera: Optional[dict],
        collections: list,
        galleries: list,
        can_post_comment: Optional[bool],
        stats_views_today: Optional[int],
        stats_downloads_today: Optional[int],
        stats_downloads: Optional[int],
        stats_views: Optional[int],
        stats_favourites: Optional[int],
        stats_comments: Optional[int],
    ) -> int:
        """Upsert the extended metadata for a deviation.
        
        Args:
            deviationid: DeviantArt deviation UUID
            title: Deviation title
            description: Deviation description (can be HTML)
            license: License type
            allows_comments: Whether comments are allowed
            tags: List of tag strings
            is_favourited: Whether user favourited this
            is_watching: Whether user is watching this
            is_mature: Mature content flag
            mature_level: Mature content level (strict/moderate/...)
            mature_classification: List of mature classifications
            printid: Print ID if available
            author: Author dict with username, userid, etc.
            creation_time: ISO timestamp of creation
            category: Category path
            file_size: Human-readable file size
            resolution: Resolution string (e.g., "1920x1080")
            submitted_with: App/tool used for submission
            stats_json: Raw stats dict from API
            camera: Camera metadata dict
            collections: List of collection dicts
            galleries: List of gallery dicts
            can_post_comment: Whether user can post comments
            stats_views_today: Views today count
            stats_downloads_today: Downloads today count
            stats_downloads: Total downloads
            stats_views: Total views
            stats_favourites: Total favourites
            stats_comments: Total comments
            
        Returns:
            Row ID of inserted/updated record
        """
        def dumps(value: object) -> Optional[str]:
            """Serialize value to JSON string or None."""
            if value is None:
                return None
            return json.dumps(value, ensure_ascii=False)

        cursor = self.conn.execute(
            """
            INSERT INTO deviation_metadata (
                deviationid, title, description, license, allows_comments, tags, 
                is_favourited, is_watching, is_mature, mature_level, 
                mature_classification, printid, author, creation_time, category,
                file_size, resolution, submitted_with, stats_json, camera, 
                collections, galleries, can_post_comment,
                stats_views_today, stats_downloads_today, stats_downloads, 
                stats_views, stats_favourites, stats_comments,
                created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT(deviationid) DO UPDATE SET
                title=excluded.title,
                description=excluded.description,
                license=excluded.license,
                allows_comments=excluded.allows_comments,
                tags=excluded.tags,
                is_favourited=excluded.is_favourited,
                is_watching=excluded.is_watching,
                is_mature=excluded.is_mature,
                mature_level=excluded.mature_level,
                mature_classification=excluded.mature_classification,
                printid=excluded.printid,
                author=excluded.author,
                creation_time=excluded.creation_time,
                category=excluded.category,
                file_size=excluded.file_size,
                resolution=excluded.resolution,
                submitted_with=excluded.submitted_with,
                stats_json=excluded.stats_json,
                camera=excluded.camera,
                collections=excluded.collections,
                galleries=excluded.galleries,
                can_post_comment=excluded.can_post_comment,
                stats_views_today=excluded.stats_views_today,
                stats_downloads_today=excluded.stats_downloads_today,
                stats_downloads=excluded.stats_downloads,
                stats_views=excluded.stats_views,
                stats_favourites=excluded.stats_favourites,
                stats_comments=excluded.stats_comments,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                deviationid,
                title,
                description,
                license,
                1 if allows_comments else 0 if allows_comments is not None else None,
                dumps(tags),
                1 if is_favourited else 0 if is_favourited is not None else None,
                1 if is_watching else 0 if is_watching is not None else None,
                1 if is_mature else 0 if is_mature is not None else None,
                mature_level,
                dumps(mature_classification),
                printid,
                dumps(author),
                creation_time,
                category,
                file_size,
                resolution,
                dumps(submitted_with),
                dumps(stats_json),
                dumps(camera),
                dumps(collections),
                dumps(galleries),
                1 if can_post_comment else 0 if can_post_comment is not None else None,
                stats_views_today,
                stats_downloads_today,
                stats_downloads,
                stats_views,
                stats_favourites,
                stats_comments,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_metadata(self, deviationid: str) -> Optional[dict]:
        """Retrieve metadata by deviation ID.
        
        Args:
            deviationid: DeviantArt deviation UUID
            
        Returns:
            Dictionary with all metadata fields or None if not found
        """
        cursor = self.conn.execute(
            """
            SELECT 
                id, deviationid, title, description, license, allows_comments, 
                tags, is_favourited, is_watching, is_mature, mature_level, 
                mature_classification, printid, author, creation_time, category,
                file_size, resolution, submitted_with, stats_json, camera, 
                collections, galleries, can_post_comment,
                stats_views_today, stats_downloads_today, stats_downloads, 
                stats_views, stats_favourites, stats_comments,
                created_at, updated_at
            FROM deviation_metadata
            WHERE deviationid = ?
            """,
            (deviationid,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        
        columns = [desc[0] for desc in cursor.description]
        result = dict(zip(columns, row))
        
        # Deserialize JSON fields
        def loads(value: Optional[str]):
            """Deserialize JSON string to Python object or None."""
            if value is None:
                return None
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        
        result["tags"] = loads(result.get("tags")) or []
        result["mature_classification"] = loads(result.get("mature_classification")) or []
        result["author"] = loads(result.get("author"))
        result["submitted_with"] = loads(result.get("submitted_with"))
        result["stats_json"] = loads(result.get("stats_json"))
        result["camera"] = loads(result.get("camera"))
        result["collections"] = loads(result.get("collections")) or []
        result["galleries"] = loads(result.get("galleries")) or []
        
        return result
