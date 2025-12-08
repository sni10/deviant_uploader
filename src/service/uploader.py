"""Uploader service for DeviantArt submissions."""
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional
import requests

from ..config import get_config
from ..domain.models import Deviation, UploadStatus, UploadPreset
from ..storage import DeviationRepository, GalleryRepository
from ..storage.preset_repository import PresetRepository
from .auth_service import AuthService


class UploaderService:
    """
    Service for uploading images to DeviantArt.
    
    Follows Single Responsibility Principle: Only manages deviation uploads.
    Uses Dependency Injection: Receives repositories it depends on.
    """
    
    # Supported image extensions
    SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp'}
    
    def __init__(
        self,
        deviation_repository: DeviationRepository,
        gallery_repository: GalleryRepository,
        auth_service: AuthService,
        preset_repository: Optional[PresetRepository] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize uploader service.
        
        Args:
            deviation_repository: Repository for deviation persistence
            gallery_repository: Repository for gallery lookups
            auth_service: Authentication service
            preset_repository: Repository for preset management (optional)
            logger: Logger instance
        """
        self.config = get_config()
        self.deviation_repository = deviation_repository
        self.gallery_repository = gallery_repository
        self.auth_service = auth_service
        self.preset_repository = preset_repository
        self.logger = logger or logging.getLogger(__name__)
    
    def scan_upload_folder(self) -> list[Path]:
        """
        Scan upload folder for images.
        
        Returns:
            List of image file paths
        """
        images = []
        for ext in self.SUPPORTED_EXTENSIONS:
            images.extend(self.config.upload_dir.glob(f'*{ext}'))
            images.extend(self.config.upload_dir.glob(f'*{ext.upper()}'))
        
        self.logger.info(f"Found {len(images)} images in upload folder")
        return images
    
    def load_template(self, template_path: str = "upload_template.json") -> dict:
        """
        Load upload template from JSON file.
        
        Args:
            template_path: Path to template file
            
        Returns:
            Template dictionary
        """
        template_file = Path(template_path)
        
        if not template_file.exists():
            self.logger.warning(f"Template file not found: {template_path}")
            return {}
        
        try:
            with open(template_file, 'r', encoding='utf-8') as f:
                template = json.load(f)
                self.logger.info(f"Loaded template from {template_path}")
                return template
        except Exception as e:
            self.logger.error(f"Failed to load template: {e}")
            return {}
    
    def apply_template_to_deviation(self, deviation: Deviation, template: dict) -> None:
        """
        Apply template settings to deviation.
        
        Args:
            deviation: Deviation to modify
            template: Template dictionary with settings
        """
        # Apply title (can use template or override per file)
        if template.get('title_template'):
            deviation.title = template['title_template']
        
        # Apply tags
        if template.get('tags'):
            deviation.tags = template['tags']
        
        # Apply maturity settings
        deviation.is_mature = template.get('is_mature', False)
        deviation.mature_level = template.get('mature_level')
        deviation.mature_classification = template.get('mature_classification', [])
        
        # Apply AI settings
        deviation.is_ai_generated = template.get('is_ai_generated', False)
        deviation.noai = template.get('noai', False)
        
        # Apply display settings
        deviation.display_resolution = template.get('display_resolution', 0)
        deviation.add_watermark = template.get('add_watermark', False)
        deviation.allow_free_download = template.get('allow_free_download', False)
        
        # Apply interaction settings
        deviation.allow_comments = template.get('allow_comments', True)
        deviation.feature = template.get('feature', True)
        
        # Apply stash submit settings
        if 'artist_comments' in template:
            deviation.artist_comments = template['artist_comments']
        
        if 'original_url' in template:
            deviation.original_url = template['original_url']
        
        if 'is_dirty' in template:
            deviation.is_dirty = template['is_dirty']
        
        if 'stack' in template:
            deviation.stack = template['stack']
        
        if 'stackid' in template:
            deviation.stackid = template['stackid']
        
        # Apply gallery_id from template
        if 'gallery_id' in template:
            deviation.gallery_id = template['gallery_id']
        
        self.logger.info(f"Applied template to {deviation.filename}")
    
    def create_deviation_from_file(self, file_path: Path, template: Optional[dict] = None) -> Deviation:
        """
        Create a Deviation entity from an image file with optional template.
        
        Args:
            file_path: Path to image file
            template: Optional template dictionary
            
        Returns:
            Deviation object
        """
        filename = file_path.name
        title = file_path.stem  # Default title from filename
        
        # Create basic deviation
        deviation = Deviation(
            filename=filename,
            title=title,
            file_path=str(file_path),
            status=UploadStatus.NEW
        )
        
        # Apply template if provided
        if template:
            self.apply_template_to_deviation(deviation, template)
        
        return deviation
    
    def upload_deviation(self, deviation: Deviation) -> bool:
        """
        Upload a deviation to DeviantArt.
        
        This method:
        1. Ensures authentication
        2. Uploads the image (placeholder for stash upload - using itemid directly)
        3. Publishes to DeviantArt using stash/publish endpoint
        4. Updates deviation with results
        5. Saves to database
        6. Moves file to done folder on success
        
        Args:
            deviation: Deviation to upload
            
        Returns:
            True if upload successful, False otherwise
        """
        self.logger.info(f"Starting upload for: {deviation.filename}")
        
        # Ensure we have valid authentication
        if not self.auth_service.ensure_authenticated():
            self.logger.error("Authentication failed, cannot upload")
            deviation.status = UploadStatus.FAILED
            deviation.error = "Authentication failed"
            return False
        
        # Get access token
        access_token = self.auth_service.get_valid_token()
        if not access_token:
            self.logger.error("Failed to get valid access token")
            deviation.status = UploadStatus.FAILED
            deviation.error = "No valid access token"
            return False
        
        # Update status to uploading
        deviation.status = UploadStatus.UPLOADING
        
        # Step 1: Upload to Stash if itemid is not already set
        if not deviation.itemid:
            self.logger.info(f"No itemid set, uploading file to Stash first...")
            if not self.upload_to_stash(deviation, access_token):
                self.logger.error(f"Failed to upload {deviation.filename} to Stash")
                deviation.status = UploadStatus.FAILED
                return False
            self.logger.info(f"File uploaded to Stash successfully with itemid: {deviation.itemid}")
        else:
            self.logger.info(f"Using existing itemid: {deviation.itemid}")
        
        # Step 2: Publish the deviation
        success = self._publish_deviation(deviation, access_token)
        
        if success:
            deviation.status = UploadStatus.DONE
            deviation.uploaded_at = datetime.now()
            self.logger.info(f"Successfully uploaded: {deviation.filename}")
            
            # Move file to done folder
            self._move_to_done(Path(deviation.file_path))
            
            return True
        else:
            deviation.status = UploadStatus.FAILED
            self.logger.error(f"Failed to upload: {deviation.filename}")
            return False
    
    def upload_to_stash(self, deviation: Deviation, access_token: str) -> bool:
        """
        Upload file to DeviantArt Stash using /stash/submit endpoint.
        
        This method uploads the actual file to Stash and retrieves the itemid
        which is required for publishing via /stash/publish.
        
        Args:
            deviation: Deviation object with file_path set
            access_token: Valid OAuth access token
            
        Returns:
            True if upload successful and itemid retrieved, False otherwise
        """
        if not deviation.file_path or not Path(deviation.file_path).exists():
            self.logger.error(f"File not found: {deviation.file_path}")
            deviation.error = "File not found"
            return False
        
        file_path = Path(deviation.file_path)
        
        # Build form data parameters
        data = {
            'access_token': access_token
        }
        
        # Add optional stash submit parameters
        if deviation.title:
            # Limit title to 50 chars as per API spec
            data['title'] = deviation.title[:50]
        
        if deviation.artist_comments:
            data['artist_comments'] = deviation.artist_comments
        
        if deviation.tags:
            data['tags'] = deviation.tags
        
        if deviation.original_url:
            data['original_url'] = deviation.original_url
        
        if deviation.is_dirty:
            data['is_dirty'] = '1'
        
        if deviation.noai:
            data['noai'] = '1'
        
        if deviation.is_ai_generated:
            data['is_ai_generated'] = '1'
        
        if deviation.stack:
            data['stack'] = deviation.stack
        
        if deviation.stackid:
            data['stackid'] = deviation.stackid
        
        try:
            self.logger.info(f"Uploading file to Stash: {file_path.name}")
            
            # Open file and prepare multipart upload
            with open(file_path, 'rb') as f:
                files = {
                    'file': (file_path.name, f, self._get_content_type(file_path))
                }
                
                response = requests.post(
                    self.config.api_stash_submit_url,
                    data=data,
                    files=files
                )
                response.raise_for_status()
            
            result = response.json()
            
            # Check for errors even with 200 status (as per API documentation)
            if result.get('status') == 'success':
                itemid = result.get('itemid')
                if itemid:
                    deviation.itemid = itemid
                    deviation.stack = result.get('stack')
                    deviation.stackid = result.get('stackid')
                    self.logger.info(f"File uploaded to Stash successfully. ItemID: {itemid}")
                    return True
                else:
                    error_msg = "No itemid in response"
                    deviation.error = error_msg
                    self.logger.error(error_msg)
                    return False
            else:
                error_msg = result.get('error_description', result.get('error', 'Unknown error'))
                deviation.error = error_msg
                self.logger.error(f"Stash upload failed: {error_msg}")
                return False
                
        except requests.RequestException as e:
            error_msg = f"Stash upload request failed: {str(e)}"
            deviation.error = error_msg
            self.logger.error(error_msg)
            return False
        except Exception as e:
            error_msg = f"Unexpected error during stash upload: {str(e)}"
            deviation.error = error_msg
            self.logger.error(error_msg)
            return False
    
    def _get_content_type(self, file_path: Path) -> str:
        """
        Get MIME content type for file.
        
        Args:
            file_path: Path to file
            
        Returns:
            MIME type string
        """
        ext = file_path.suffix.lower()
        content_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp'
        }
        return content_types.get(ext, 'application/octet-stream')
    
    def _publish_deviation(self, deviation: Deviation, access_token: str) -> bool:
        """
        Publish deviation using stash/publish endpoint.
        
        Args:
            deviation: Deviation to publish
            access_token: Access token
            
        Returns:
            True if publish successful, False otherwise
        """
        # Build publish parameters
        params = {
            'access_token': access_token,
            'itemid': deviation.itemid,
            'is_mature': 1 if deviation.is_mature else 0,
            'feature': 1 if deviation.feature else 0,
            'allow_comments': 1 if deviation.allow_comments else 0,
            'display_resolution': deviation.display_resolution,
            'allow_free_download': 1 if deviation.allow_free_download else 0,
            'is_ai_generated': 1 if deviation.is_ai_generated else 0,
            'noai': 1 if deviation.noai else 0
        }
        
        # Add optional parameters
        if deviation.mature_level:
            params['mature_level'] = deviation.mature_level
        
        if deviation.mature_classification:
            params['mature_classification'] = deviation.mature_classification
        
        if deviation.tags:
            params['tags'] = deviation.tags
        
        if deviation.add_watermark and deviation.display_resolution > 0:
            params['add_watermark'] = 1
        
        # Resolve gallery UUID from database if gallery_id is set
        if deviation.gallery_id:
            gallery = self.gallery_repository.get_gallery_by_id(deviation.gallery_id)
            if gallery:
                params['galleryids'] = [gallery.folderid]
                self.logger.info(f"Publishing to gallery: {gallery.name} (UUID: {gallery.folderid})")
            else:
                self.logger.warning(f"Gallery with ID {deviation.gallery_id} not found in database")
        
        try:
            self.logger.info(f"Publishing deviation with itemid={deviation.itemid}")
            response = requests.post(
                self.config.api_stash_publish_url,
                data=params
            )
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('status') == 'success':
                deviation.deviationid = result.get('deviationid')
                deviation.url = result.get('url')
                self.logger.info(f"Published successfully: {deviation.url}")
                return True
            else:
                error_msg = result.get('error_description', result.get('error', 'Unknown error'))
                deviation.error = error_msg
                self.logger.error(f"Publish failed: {error_msg}")
                return False
                
        except requests.RequestException as e:
            error_msg = f"Request failed: {str(e)}"
            deviation.error = error_msg
            self.logger.error(error_msg)
            return False
    
    def _move_to_done(self, file_path: Path) -> None:
        """
        Move uploaded file to done folder.
        
        Args:
            file_path: Path to file to move
        """
        try:
            dest_path = self.config.done_dir / file_path.name
            
            # If file already exists in done folder, add timestamp
            if dest_path.exists():
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                stem = dest_path.stem
                suffix = dest_path.suffix
                dest_path = self.config.done_dir / f"{stem}_{timestamp}{suffix}"
            
            shutil.move(str(file_path), str(dest_path))
            self.logger.info(f"Moved file to: {dest_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to move file {file_path}: {e}")
    
    def process_uploads(self, template_path: str = "upload_template.json") -> dict:
        """
        Process all images in upload folder using template.
        
        Args:
            template_path: Path to template JSON file
            
        Returns:
            Dictionary with statistics: total, successful, failed
        """
        self.logger.info("Starting upload process")
        
        # Load template
        template = self.load_template(template_path)
        
        if not template:
            self.logger.warning("No template loaded, using defaults")
        
        # Recover any deviations stuck in uploading status
        recovered = self.deviation_repository.recover_uploading_deviations()
        if recovered > 0:
            self.logger.info(f"Recovered {recovered} deviations from previous crash")
        
        # Scan for images
        image_files = self.scan_upload_folder()
        
        if not image_files:
            self.logger.info("No images found in upload folder")
            return {'total': 0, 'successful': 0, 'failed': 0}
        
        stats = {'total': len(image_files), 'successful': 0, 'failed': 0}
        
        # Process each image
        for image_file in image_files:
            self.logger.info(f"Processing: {image_file.name}")
            
            # Check if already in database
            existing = self.deviation_repository.get_deviation_by_filename(image_file.name)
            if existing:
                self.logger.warning(f"File {image_file.name} already processed, skipping")
                continue
            
            # Create deviation entity with template
            deviation = self.create_deviation_from_file(image_file, template)
            
            # Check for itemid from metadata file (optional - for pre-uploaded files)
            metadata_file = image_file.with_suffix(image_file.suffix + '.json')
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                        if 'itemid' in metadata:
                            deviation.itemid = metadata['itemid']
                            self.logger.info(f"Loaded itemid from metadata: {deviation.itemid}")
                except Exception as e:
                    self.logger.warning(f"Failed to load metadata: {e}")
            
            # Note: itemid is now optional - will be obtained automatically during upload
            
            # Save to database before upload
            self.deviation_repository.save_deviation(deviation)
            
            # Upload
            success = self.upload_deviation(deviation)
            
            # Update in database
            self.deviation_repository.update_deviation(deviation)
            
            if success:
                stats['successful'] += 1
            else:
                stats['failed'] += 1
        
        self.logger.info(f"Upload process completed: {stats}")
        return stats
    
    def upload_single(self, filename: str, itemid: int, **kwargs) -> bool:
        """
        Upload a single file with specified itemid and optional parameters.
        
        This is a convenience method for uploading when you already have a stash itemid.
        
        Args:
            filename: Name of file in upload folder
            itemid: Stash item ID
            **kwargs: Additional deviation parameters (title, is_mature, tags, etc.)
            
        Returns:
            True if upload successful, False otherwise
        """
        file_path = self.config.upload_dir / filename
        
        if not file_path.exists():
            self.logger.error(f"File not found: {filename}")
            return False
        
        # Check if already processed
        existing = self.deviation_repository.get_deviation_by_filename(filename)
        if existing:
            self.logger.warning(f"File {filename} already processed")
            return False
        
        # Create deviation
        deviation = self.create_deviation_from_file(file_path)
        deviation.itemid = itemid
        
        # Apply additional parameters
        for key, value in kwargs.items():
            if hasattr(deviation, key):
                setattr(deviation, key, value)
        
        # Save to database
        self.deviation_repository.save_deviation(deviation)
        
        # Upload
        success = self.upload_deviation(deviation)
        
        # Update in database
        self.deviation_repository.update_deviation(deviation)
        
        return success
    
    # ========== Admin Interface Methods ==========
    
    def scan_and_create_drafts(self) -> list[Deviation]:
        """
        Scan upload folder and create draft deviation records in database.
        
        Checks for existing records to avoid duplicates. Only creates drafts
        for new files not already in database. File extensions are normalized
        to lowercase to prevent duplicates from case differences.
        
        Returns:
            List of all draft deviations (new + existing)
        """
        self.logger.info("Scanning upload folder for draft creation")
        
        # Scan for images
        image_files = self.scan_upload_folder()
        
        drafts = []
        new_count = 0
        seen_files = set()  # Track processed files to avoid duplicates from case
        
        for image_file in image_files:
            # Normalize filename: keep stem as-is, lowercase the extension
            original_stem = image_file.stem
            normalized_ext = image_file.suffix.lower()
            normalized_filename = f"{original_stem}{normalized_ext}"
            
            # Skip if we've already processed this file (case-insensitive)
            if normalized_filename.lower() in seen_files:
                self.logger.debug(f"Skipping duplicate (case): {image_file.name}")
                continue
            seen_files.add(normalized_filename.lower())
            
            # Check if already in database (using normalized filename)
            existing = self.deviation_repository.get_deviation_by_filename(normalized_filename)
            
            if existing:
                # Existing record found: ensure filename normalization and valid absolute file_path
                updated = False
                # Normalize stored filename to use lowercased extension
                if getattr(existing, 'filename', None) and existing.filename != normalized_filename:
                    existing.filename = normalized_filename
                    updated = True

                # Fix file_path if missing or points to non-existent location
                try:
                    existing_path = Path(existing.file_path) if getattr(existing, 'file_path', None) else None
                except Exception:
                    existing_path = None

                if not existing_path or not existing_path.exists():
                    # Use the discovered image_file from scan (absolute path)
                    try:
                        existing.file_path = str(image_file.resolve())
                        updated = True
                        self.logger.info(
                            f"Corrected file path for {normalized_filename} -> {existing.file_path}"
                        )
                    except Exception as fix_exc:
                        self.logger.warning(
                            f"Failed to correct file path for {normalized_filename}: {fix_exc}"
                        )

                if updated:
                    # Persist corrections
                    try:
                        self.deviation_repository.update_deviation(existing)
                    except Exception as upd_exc:
                        self.logger.warning(
                            f"Failed to update deviation record for {normalized_filename}: {upd_exc}"
                        )

                # Add existing record to list
                drafts.append(existing)
                self.logger.debug(f"File {normalized_filename} already in database")
            else:
                # Create new draft deviation with normalized filename
                # Always store absolute file path to avoid later resolution issues
                try:
                    absolute_fp = str(image_file.resolve())
                except Exception:
                    # Fallback to string path if resolve() fails for any reason
                    absolute_fp = str(image_file)

                deviation = Deviation(
                    filename=normalized_filename,
                    title=original_stem,  # Use filename without extension as default title
                    file_path=absolute_fp,
                    status=UploadStatus.DRAFT
                )
                
                # Save to database
                deviation_id = self.deviation_repository.save_deviation(deviation)
                deviation.deviation_id = deviation_id
                drafts.append(deviation)
                new_count += 1
                self.logger.info(f"Created draft for {normalized_filename}")
        
        self.logger.info(f"Scan complete: {new_count} new drafts, {len(drafts) - new_count} existing")
        return drafts
    
    def apply_preset_to_deviation(
        self, 
        deviation: Deviation, 
        preset: UploadPreset,
        increment: int
    ) -> Deviation:
        """
        Apply preset configuration to deviation with incremental title.
        
        Args:
            deviation: Deviation to update
            preset: Preset configuration to apply
            increment: Increment number for title
            
        Returns:
            Updated deviation object
        """
        # Generate title with increment
        deviation.title = f"{preset.base_title} {increment}"
        
        # Apply stash parameters
        deviation.artist_comments = preset.artist_comments
        deviation.tags = preset.tags.copy() if preset.tags else []
        deviation.is_ai_generated = preset.is_ai_generated
        deviation.noai = preset.noai
        deviation.is_dirty = preset.is_dirty
        
        # Apply publish parameters
        deviation.is_mature = preset.is_mature
        deviation.mature_level = preset.mature_level
        deviation.mature_classification = preset.mature_classification.copy() if preset.mature_classification else []
        deviation.feature = preset.feature
        deviation.allow_comments = preset.allow_comments
        deviation.display_resolution = preset.display_resolution
        deviation.allow_free_download = preset.allow_free_download
        deviation.add_watermark = preset.add_watermark
        
        # Apply gallery selection (if gallery_folderid provided, look up internal ID)
        if preset.gallery_folderid:
            gallery = self.gallery_repository.get_gallery_by_folderid(preset.gallery_folderid)
            if gallery:
                deviation.gallery_id = gallery.gallery_db_id
            else:
                self.logger.warning(f"Gallery {preset.gallery_folderid} not found")
        
        self.logger.info(f"Applied preset '{preset.name}' to {deviation.filename} with title '{deviation.title}'")
        return deviation
    
    def batch_stash(
        self, 
        deviation_ids: list[int],
        preset: UploadPreset
    ) -> dict:
        """
        Stash multiple deviations in batch with rate limiting.
        
        Args:
            deviation_ids: List of deviation database IDs
            preset: Preset to apply to deviations
            
        Returns:
            Dictionary with success/failed lists and details
        """
        self.logger.info(f"Starting batch stash for {len(deviation_ids)} deviations")
        
        results = {
            "success": [],
            "failed": []
        }
        
        # Get access token
        access_token = self.auth_service.get_valid_access_token()
        if not access_token:
            self.logger.error("Failed to get valid access token")
            for dev_id in deviation_ids:
                results["failed"].append({"id": dev_id, "error": "Authentication failed"})
            return results
        
        # Process each deviation
        for idx, dev_id in enumerate(deviation_ids, 1):
            try:
                deviation = self.deviation_repository.get_deviation_by_id(dev_id)
                if not deviation:
                    self.logger.warning(f"Deviation {dev_id} not found in database")
                    results["failed"].append({"id": dev_id, "error": "Not found in database"})
                    continue
                
                # Get next increment value and apply preset
                if self.preset_repository:
                    increment = self.preset_repository.increment_preset_counter(preset.preset_id)
                else:
                    increment = preset.last_used_increment
                
                self.apply_preset_to_deviation(deviation, preset, increment)
                
                # Update status to STASHING
                deviation.status = UploadStatus.STASHING
                self.deviation_repository.update_deviation(deviation)
                
                # Perform stash upload
                self.logger.info(f"[{idx}/{len(deviation_ids)}] Stashing {deviation.filename}")
                itemid = self.upload_to_stash(deviation, access_token)
                
                if itemid:
                    deviation.itemid = itemid
                    deviation.status = UploadStatus.STASHED
                    self.deviation_repository.update_deviation(deviation)
                    results["success"].append(dev_id)
                    self.logger.info(f"Successfully stashed {deviation.filename} (itemid: {itemid})")
                else:
                    deviation.status = UploadStatus.FAILED
                    deviation.error = "Stash upload failed"
                    self.deviation_repository.update_deviation(deviation)
                    results["failed"].append({"id": dev_id, "error": "Stash upload failed"})
                    self.logger.error(f"Failed to stash {deviation.filename}")
                
                # Rate limiting: 2 second delay between uploads
                if idx < len(deviation_ids):
                    import time
                    time.sleep(2)
                    
            except Exception as e:
                self.logger.error(f"Exception during stash of deviation {dev_id}: {e}", exc_info=True)
                results["failed"].append({"id": dev_id, "error": str(e)})
        
        self.logger.info(f"Batch stash complete: {len(results['success'])} success, {len(results['failed'])} failed")
        return results
    
    def batch_publish(self, deviation_ids: list[int]) -> dict:
        """
        Publish multiple stashed deviations in batch.
        
        Args:
            deviation_ids: List of deviation database IDs (must have itemid)
            
        Returns:
            Dictionary with success/failed lists and details
        """
        self.logger.info(f"Starting batch publish for {len(deviation_ids)} deviations")
        
        results = {
            "success": [],
            "failed": []
        }
        
        # Get access token
        access_token = self.auth_service.get_valid_access_token()
        if not access_token:
            self.logger.error("Failed to get valid access token")
            for dev_id in deviation_ids:
                results["failed"].append({"id": dev_id, "error": "Authentication failed"})
            return results
        
        # Process each deviation
        for idx, dev_id in enumerate(deviation_ids, 1):
            try:
                deviation = self.deviation_repository.get_deviation_by_id(dev_id)
                if not deviation:
                    self.logger.warning(f"Deviation {dev_id} not found in database")
                    results["failed"].append({"id": dev_id, "error": "Not found in database"})
                    continue
                
                if not deviation.itemid:
                    self.logger.warning(f"Deviation {dev_id} has no itemid, cannot publish")
                    results["failed"].append({"id": dev_id, "error": "No itemid (not stashed)"})
                    continue
                
                # Update status to PUBLISHING
                deviation.status = UploadStatus.PUBLISHING
                self.deviation_repository.update_deviation(deviation)
                
                # Perform publish
                self.logger.info(f"[{idx}/{len(deviation_ids)}] Publishing {deviation.filename}")
                success = self._publish_deviation(deviation, access_token)
                
                if success:
                    deviation.status = UploadStatus.PUBLISHED
                    self.deviation_repository.update_deviation(deviation)
                    results["success"].append(dev_id)
                    self.logger.info(f"Successfully published {deviation.filename}")
                    
                    # Delete file after successful publish
                    if deviation.file_path:
                        try:
                            file_path = Path(deviation.file_path)
                            if file_path.exists():
                                file_path.unlink()
                                self.logger.info(f"Deleted file {deviation.file_path}")
                        except Exception as e:
                            self.logger.warning(f"Failed to delete file {deviation.file_path}: {e}")
                else:
                    deviation.status = UploadStatus.FAILED
                    deviation.error = "Publish failed"
                    self.deviation_repository.update_deviation(deviation)
                    results["failed"].append({"id": dev_id, "error": "Publish failed"})
                    self.logger.error(f"Failed to publish {deviation.filename}")
                
                # Rate limiting: 2 second delay between publishes
                if idx < len(deviation_ids):
                    import time
                    time.sleep(2)
                    
            except Exception as e:
                self.logger.error(f"Exception during publish of deviation {dev_id}: {e}", exc_info=True)
                results["failed"].append({"id": dev_id, "error": str(e)})
        
        self.logger.info(f"Batch publish complete: {len(results['success'])} success, {len(results['failed'])} failed")
        return results
    
    def batch_upload(
        self,
        deviation_ids: list[int],
        preset: UploadPreset
    ) -> dict:
        """
        Upload multiple deviations in batch: stash then publish in one operation.
        
        This combines stash and publish into a single workflow, matching the
        DeviantArt upload process where each file is stashed then immediately
        published before moving to the next file.
        
        Args:
            deviation_ids: List of deviation database IDs
            preset: Preset to apply to deviations
            
        Returns:
            Dictionary with success/failed lists and details
        """
        self.logger.info(f"Starting batch upload for {len(deviation_ids)} deviations")
        
        results = {
            "success": [],
            "failed": []
        }
        
        # Get access token
        access_token = self.auth_service.get_valid_access_token()
        if not access_token:
            self.logger.error("Failed to get valid access token")
            for dev_id in deviation_ids:
                results["failed"].append({"id": dev_id, "error": "Authentication failed"})
            return results
        
        # Process each deviation: stash then publish
        for idx, dev_id in enumerate(deviation_ids, 1):
            try:
                deviation = self.deviation_repository.get_deviation_by_id(dev_id)
                if not deviation:
                    self.logger.warning(f"Deviation {dev_id} not found in database")
                    results["failed"].append({"id": dev_id, "error": "Not found in database"})
                    continue
                
                # Get next increment value and apply preset
                if self.preset_repository:
                    increment = self.preset_repository.increment_preset_counter(preset.preset_id)
                else:
                    increment = preset.last_used_increment
                
                self.apply_preset_to_deviation(deviation, preset, increment)
                
                # Step 1: Stash
                deviation.status = UploadStatus.STASHING
                self.deviation_repository.update_deviation(deviation)
                
                self.logger.info(f"[{idx}/{len(deviation_ids)}] Stashing {deviation.filename}")
                itemid = self.upload_to_stash(deviation, access_token)
                
                if not itemid:
                    deviation.status = UploadStatus.FAILED
                    deviation.error = "Stash upload failed"
                    self.deviation_repository.update_deviation(deviation)
                    results["failed"].append({"id": dev_id, "error": "Stash upload failed"})
                    self.logger.error(f"Failed to stash {deviation.filename}")
                    continue
                
                deviation.itemid = itemid
                deviation.status = UploadStatus.STASHED
                self.deviation_repository.update_deviation(deviation)
                self.logger.info(f"Successfully stashed {deviation.filename} (itemid: {itemid})")
                
                # Step 2: Publish immediately after stash
                deviation.status = UploadStatus.PUBLISHING
                self.deviation_repository.update_deviation(deviation)
                
                self.logger.info(f"[{idx}/{len(deviation_ids)}] Publishing {deviation.filename}")
                success = self._publish_deviation(deviation, access_token)
                
                if success:
                    deviation.status = UploadStatus.PUBLISHED
                    self.deviation_repository.update_deviation(deviation)
                    results["success"].append(dev_id)
                    self.logger.info(f"Successfully published {deviation.filename}")
                    
                    # Delete file after successful publish
                    if deviation.file_path:
                        try:
                            file_path = Path(deviation.file_path)
                            if file_path.exists():
                                file_path.unlink()
                                self.logger.info(f"Deleted file {deviation.file_path}")
                        except Exception as e:
                            self.logger.warning(f"Failed to delete file {deviation.file_path}: {e}")
                else:
                    deviation.status = UploadStatus.FAILED
                    deviation.error = "Publish failed"
                    self.deviation_repository.update_deviation(deviation)
                    results["failed"].append({"id": dev_id, "error": "Publish failed"})
                    self.logger.error(f"Failed to publish {deviation.filename}")
                
                # Rate limiting: 2 second delay between uploads
                if idx < len(deviation_ids):
                    import time
                    time.sleep(2)
                    
            except Exception as e:
                self.logger.error(f"Exception during upload of deviation {dev_id}: {e}", exc_info=True)
                results["failed"].append({"id": dev_id, "error": str(e)})
        
        self.logger.info(f"Batch upload complete: {len(results['success'])} success, {len(results['failed'])} failed")
        return results
    
    def delete_deviation_and_file(self, deviation_id: int) -> bool:
        """
        Delete deviation record from database and its associated file.
        
        Args:
            deviation_id: Database ID of deviation to delete
            
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            deviation = self.deviation_repository.get_deviation_by_id(deviation_id)
            if not deviation:
                self.logger.warning(f"Deviation {deviation_id} not found")
                return False
            
            # Delete file if it exists
            if deviation.file_path:
                file_path = Path(deviation.file_path)
                if file_path.exists():
                    file_path.unlink()
                    self.logger.info(f"Deleted file {deviation.file_path}")
            
            # Delete database record
            success = self.deviation_repository.delete_deviation(deviation_id)
            if success:
                self.logger.info(f"Deleted deviation {deviation_id} ({deviation.filename})")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to delete deviation {deviation_id}: {e}", exc_info=True)
            return False
