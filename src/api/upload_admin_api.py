"""Flask API for upload admin interface."""
import json
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory

from ..config import get_config
from ..log.logger import setup_logger
from ..service.auth_service import AuthService
from ..service.uploader import UploaderService
from ..storage import (
    get_connection,
    DeviationRepository,
    GalleryRepository
)
from ..storage.preset_repository import PresetRepository
from ..domain.models import UploadPreset


# Resolve paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = PROJECT_ROOT / "static"


def create_upload_admin_app():
    """
    Create and configure Flask application for upload admin interface.
    
    Returns:
        Configured Flask app
    """
    app = Flask(__name__, static_folder=str(STATIC_DIR))
    
    config = get_config()
    logger = setup_logger()
    
    # Initialize repositories and services
    def get_services():
        """Get service instances (called per request)."""
        conn = get_connection()
        deviation_repo = DeviationRepository(conn)
        gallery_repo = GalleryRepository(conn)
        preset_repo = PresetRepository(conn)
        auth_service = AuthService(conn)
        uploader_service = UploaderService(
            deviation_repo,
            gallery_repo,
            auth_service,
            preset_repo,
            logger
        )
        return uploader_service, preset_repo, deviation_repo
    
    @app.route('/')
    def index():
        """Redirect to admin page."""
        return send_from_directory(STATIC_DIR, "upload_admin.html")
    
    @app.route('/admin/upload')
    def upload_admin_page():
        """Serve HTML admin page."""
        return send_from_directory(STATIC_DIR, "upload_admin.html")
    
    @app.route('/upload_admin.html')
    def upload_admin_html():
        """Serve HTML admin page (alternative URL for convenience)."""
        return send_from_directory(STATIC_DIR, "upload_admin.html")
    
    @app.route('/api/admin/scan', methods=['POST'])
    def scan_files():
        """
        Scan upload folder and create draft deviations.
        
        Returns:
            JSON list of draft deviations with metadata
        """
        try:
            uploader_service, _, _ = get_services()
            drafts = uploader_service.scan_and_create_drafts()
            
            # Convert to JSON-serializable format
            result = []
            for draft in drafts:
                result.append({
                    'id': draft.deviation_id,
                    'filename': draft.filename,
                    'title': draft.title,
                    'file_path': draft.file_path,
                    'status': draft.status.value if hasattr(draft.status, 'value') else draft.status,
                    'itemid': draft.itemid,
                    'deviationid': draft.deviationid,
                    'url': draft.url
                })
            
            return jsonify({
                'success': True,
                'drafts': result,
                'count': len(result)
            })
        except Exception as e:
            logger.error(f"Scan failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/admin/drafts', methods=['GET'])
    def get_drafts():
        """
        Get all draft deviations from database.
        
        Returns:
            JSON list of deviations
        """
        try:
            _, _, deviation_repo = get_services()
            
            # Get all deviations (could filter by status if needed)
            all_deviations = deviation_repo.get_all_deviations()
            
            # Convert to JSON-serializable format
            result = []
            for dev in all_deviations:
                result.append({
                    'id': dev.deviation_id,
                    'filename': dev.filename,
                    'title': dev.title,
                    'file_path': dev.file_path,
                    'status': dev.status.value if hasattr(dev.status, 'value') else dev.status,
                    'itemid': dev.itemid,
                    'deviationid': dev.deviationid,
                    'url': dev.url,
                    'error': dev.error,
                    'tags': dev.tags,
                    'is_mature': dev.is_mature
                })
            
            return jsonify({
                'success': True,
                'deviations': result,
                'count': len(result)
            })
        except Exception as e:
            logger.error(f"Get drafts failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/admin/presets', methods=['GET'])
    def get_presets():
        """
        Get all presets for dropdown.
        
        Returns:
            JSON list of presets
        """
        try:
            _, preset_repo, _ = get_services()
            presets = preset_repo.get_all_presets()
            
            # Convert to JSON-serializable format
            result = []
            for preset in presets:
                result.append({
                    'id': preset.preset_id,
                    'name': preset.name,
                    'description': preset.description,
                    'base_title': preset.base_title,
                    'title_increment_start': preset.title_increment_start,
                    'last_used_increment': preset.last_used_increment,
                    'is_default': preset.is_default,
                    'tags': preset.tags,
                    'is_mature': preset.is_mature,
                    'gallery_folderid': preset.gallery_folderid
                })
            
            return jsonify({
                'success': True,
                'presets': result,
                'count': len(result)
            })
        except Exception as e:
            logger.error(f"Get presets failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/admin/presets', methods=['POST'])
    def save_preset():
        """
        Save or update a preset.
        
        Expects JSON body with preset fields.
        
        Returns:
            JSON with preset ID
        """
        try:
            data = request.get_json()
            
            if not data.get('name') or not data.get('base_title'):
                return jsonify({'success': False, 'error': 'Name and base_title are required'}), 400
            
            _, preset_repo, _ = get_services()
            
            # Create UploadPreset object
            preset = UploadPreset(
                name=data['name'],
                description=data.get('description'),
                base_title=data['base_title'],
                title_increment_start=data.get('title_increment_start', 1),
                last_used_increment=data.get('last_used_increment', 1),
                artist_comments=data.get('artist_comments'),
                tags=data.get('tags', []),
                is_ai_generated=data.get('is_ai_generated', True),
                noai=data.get('noai', False),
                is_dirty=data.get('is_dirty', False),
                is_mature=data.get('is_mature', False),
                mature_level=data.get('mature_level'),
                mature_classification=data.get('mature_classification', []),
                feature=data.get('feature', True),
                allow_comments=data.get('allow_comments', True),
                display_resolution=data.get('display_resolution', 0),
                allow_free_download=data.get('allow_free_download', False),
                add_watermark=data.get('add_watermark', False),
                gallery_folderid=data.get('gallery_folderid'),
                is_default=data.get('is_default', False)
            )
            
            preset_id = preset_repo.save_preset(preset)
            
            return jsonify({
                'success': True,
                'preset_id': preset_id,
                'message': 'Preset saved successfully'
            })
        except Exception as e:
            logger.error(f"Save preset failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/admin/apply-preset', methods=['POST'])
    def apply_preset():
        """
        Apply preset to selected deviations.
        
        Expects JSON: {"preset_id": X, "deviation_ids": [1,2,3]}
        
        Returns:
            JSON with success status
        """
        try:
            data = request.get_json()
            preset_id = data.get('preset_id')
            deviation_ids = data.get('deviation_ids', [])
            
            if not preset_id or not deviation_ids:
                return jsonify({'success': False, 'error': 'preset_id and deviation_ids required'}), 400
            
            uploader_service, preset_repo, deviation_repo = get_services()
            
            # Get preset
            preset = preset_repo.get_preset_by_id(preset_id)
            if not preset:
                return jsonify({'success': False, 'error': 'Preset not found'}), 404
            
            # Apply preset to each deviation
            applied = []
            for dev_id in deviation_ids:
                deviation = deviation_repo.get_deviation_by_id(dev_id)
                if deviation:
                    # Get next increment
                    increment = preset_repo.increment_preset_counter(preset_id)
                    
                    # Apply preset
                    uploader_service.apply_preset_to_deviation(deviation, preset, increment)
                    
                    # Save updated deviation
                    deviation_repo.update_deviation(deviation)
                    applied.append(dev_id)
            
            return jsonify({
                'success': True,
                'applied': applied,
                'count': len(applied)
            })
        except Exception as e:
            logger.error(f"Apply preset failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/admin/stash', methods=['POST'])
    def stash_selected():
        """
        Stash selected deviations.
        
        Expects JSON: {"deviation_ids": [1,2,3], "preset_id": X}
        
        Returns:
            JSON with success/failed lists
        """
        try:
            data = request.get_json()
            deviation_ids = data.get('deviation_ids', [])
            preset_id = data.get('preset_id')
            
            if not deviation_ids or not preset_id:
                return jsonify({'success': False, 'error': 'deviation_ids and preset_id required'}), 400
            
            uploader_service, preset_repo, _ = get_services()
            
            # Get preset
            preset = preset_repo.get_preset_by_id(preset_id)
            if not preset:
                return jsonify({'success': False, 'error': 'Preset not found'}), 404
            
            # Perform batch stash
            results = uploader_service.batch_stash(deviation_ids, preset)
            
            return jsonify({
                'success': True,
                'results': results
            })
        except Exception as e:
            logger.error(f"Stash failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/admin/publish', methods=['POST'])
    def publish_selected():
        """
        Publish stashed deviations.
        
        Expects JSON: {"deviation_ids": [1,2,3]}
        
        Returns:
            JSON with success/failed lists
        """
        try:
            data = request.get_json()
            deviation_ids = data.get('deviation_ids', [])
            
            if not deviation_ids:
                return jsonify({'success': False, 'error': 'deviation_ids required'}), 400
            
            uploader_service, _, _ = get_services()
            
            # Perform batch publish
            results = uploader_service.batch_publish(deviation_ids)
            
            return jsonify({
                'success': True,
                'results': results
            })
        except Exception as e:
            logger.error(f"Publish failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/admin/delete', methods=['POST'])
    def delete_selected():
        """
        Delete deviations and files.
        
        Expects JSON: {"deviation_ids": [1,2,3]}
        
        Returns:
            JSON with deleted list
        """
        try:
            data = request.get_json()
            deviation_ids = data.get('deviation_ids', [])
            
            if not deviation_ids:
                return jsonify({'success': False, 'error': 'deviation_ids required'}), 400
            
            uploader_service, _, _ = get_services()
            
            deleted = []
            failed = []
            
            for dev_id in deviation_ids:
                if uploader_service.delete_deviation_and_file(dev_id):
                    deleted.append(dev_id)
                else:
                    failed.append(dev_id)
            
            return jsonify({
                'success': True,
                'deleted': deleted,
                'failed': failed,
                'count': len(deleted)
            })
        except Exception as e:
            logger.error(f"Delete failed: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/admin/thumbnail/<int:deviation_id>')
    def get_thumbnail(deviation_id):
        """
        Get thumbnail for deviation (serves the image file).
        
        Args:
            deviation_id: Deviation database ID
            
        Returns:
            Image file or error
        """
        try:
            _, _, deviation_repo = get_services()
            deviation = deviation_repo.get_deviation_by_id(deviation_id)
            
            if not deviation or not deviation.file_path:
                return jsonify({'error': 'Deviation or file not found'}), 404
            
            file_path = Path(deviation.file_path)
            if not file_path.exists():
                return jsonify({'error': 'File not found on disk'}), 404
            
            # Serve the image file
            return send_file(
                str(file_path),
                mimetype=f'image/{file_path.suffix[1:]}',
                as_attachment=False
            )
        except Exception as e:
            logger.error(f"Get thumbnail failed: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    return app


if __name__ == '__main__':
    app = create_upload_admin_app()
    app.run(debug=True, host='0.0.0.0', port=5001)
