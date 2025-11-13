"""Uploader service for DeviantArt submissions."""
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional
import requests

from ..config import get_config
from ..domain.models import Deviation, UploadStatus
from ..storage import DeviationRepository, GalleryRepository
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
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize uploader service.
        
        Args:
            deviation_repository: Repository for deviation persistence
            gallery_repository: Repository for gallery lookups
            auth_service: Authentication service
            logger: Logger instance
        """
        self.config = get_config()
        self.deviation_repository = deviation_repository
        self.gallery_repository = gallery_repository
        self.auth_service = auth_service
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
