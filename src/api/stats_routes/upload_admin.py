"""Upload admin API routes."""

from __future__ import annotations

from collections.abc import Callable

from flask import Flask, g, jsonify, request

from ...domain.models import UploadPreset


def register_upload_admin_routes(
    app: Flask,
    *,
    get_upload_services: Callable[[], tuple[object, object, object]],
    get_repositories: Callable[[], tuple[object, ...]],
) -> None:
    """Register upload admin endpoints."""

    @app.route("/api/admin/scan", methods=["POST"])
    def scan_files():
        """Scan upload folder and create draft deviations."""
        try:
            uploader_service, _preset_repo, _deviation_repo = get_upload_services()
            drafts = uploader_service.scan_and_create_drafts()

            result = []
            for draft in drafts:
                result.append(
                    {
                        "id": draft.deviation_id,
                        "filename": draft.filename,
                        "title": draft.title,
                        "file_path": draft.file_path,
                        "status": (
                            draft.status.value
                            if hasattr(draft.status, "value")
                            else draft.status
                        ),
                        "itemid": draft.itemid,
                        "deviationid": draft.deviationid,
                        "url": draft.url,
                    }
                )

            return jsonify({"success": True, "drafts": result, "count": len(result)})
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Scan failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/admin/drafts", methods=["GET"])
    def get_drafts():
        """Get all draft deviations from database."""
        try:
            _uploader_service, _preset_repo, deviation_repo = get_upload_services()

            all_deviations = deviation_repo.get_all_deviations()

            result = []
            for dev in all_deviations:
                result.append(
                    {
                        "id": dev.deviation_id,
                        "filename": dev.filename,
                        "title": dev.title,
                        "file_path": dev.file_path,
                        "status": (
                            dev.status.value if hasattr(dev.status, "value") else dev.status
                        ),
                        "itemid": dev.itemid,
                        "deviationid": dev.deviationid,
                        "url": dev.url,
                        "error": dev.error,
                        "tags": dev.tags,
                        "is_mature": dev.is_mature,
                    }
                )

            return jsonify(
                {"success": True, "deviations": result, "count": len(result)}
            )
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Get drafts failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/admin/galleries", methods=["GET"])
    def get_galleries_for_admin():
        """Get all galleries for dropdown selection."""
        try:
            (
                _user_repo,
                _token_repo,
                gallery_repo,
                _deviation_repo,
                _deviation_stats_repo,
                _stats_snapshot_repo,
                _user_stats_snapshot_repo,
                _deviation_metadata_repo,
            ) = get_repositories()
            galleries = gallery_repo.get_all_galleries()

            result = []
            for gallery in galleries:
                result.append(
                    {
                        "id": gallery.gallery_db_id,
                        "folderid": gallery.folderid,
                        "name": gallery.name,
                        "size": gallery.size,
                        "parent": gallery.parent,
                    }
                )

            return jsonify({"success": True, "galleries": result, "count": len(result)})
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Get galleries failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/admin/presets", methods=["GET"])
    def get_presets():
        """Get all presets for dropdown."""
        try:
            _uploader_service, preset_repo, _deviation_repo = get_upload_services()
            presets = preset_repo.get_all_presets()

            result = []
            for preset in presets:
                result.append(
                    {
                        "id": preset.preset_id,
                        "name": preset.name,
                        "description": preset.description,
                        "base_title": preset.base_title,
                        "title_increment_start": preset.title_increment_start,
                        "last_used_increment": preset.last_used_increment,
                        "is_default": preset.is_default,
                        "tags": preset.tags,
                        "is_mature": preset.is_mature,
                        "gallery_folderid": preset.gallery_folderid,
                    }
                )

            return jsonify({"success": True, "presets": result, "count": len(result)})
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Get presets failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/admin/presets", methods=["POST"])
    def save_preset():
        """Save or update a preset."""
        try:
            data = request.get_json()

            if not data.get("name") or not data.get("base_title"):
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Name and base_title are required",
                        }
                    ),
                    400,
                )

            _uploader_service, preset_repo, _deviation_repo = get_upload_services()

            preset = UploadPreset(
                name=data["name"],
                description=data.get("description"),
                base_title=data["base_title"],
                title_increment_start=data.get("title_increment_start", 1),
                last_used_increment=data.get("last_used_increment", 1),
                artist_comments=data.get("artist_comments"),
                tags=data.get("tags", []),
                is_ai_generated=data.get("is_ai_generated", True),
                noai=data.get("noai", False),
                is_dirty=data.get("is_dirty", False),
                is_mature=data.get("is_mature", False),
                mature_level=data.get("mature_level"),
                mature_classification=data.get("mature_classification", []),
                feature=data.get("feature", True),
                allow_comments=data.get("allow_comments", True),
                display_resolution=data.get("display_resolution", 0),
                allow_free_download=data.get("allow_free_download", False),
                add_watermark=data.get("add_watermark", False),
                gallery_folderid=data.get("gallery_folderid"),
                is_default=data.get("is_default", False),
            )

            preset_id = preset_repo.save_preset(preset)

            return jsonify(
                {
                    "success": True,
                    "preset_id": preset_id,
                    "message": "Preset saved successfully",
                }
            )
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Save preset failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/admin/apply-preset", methods=["POST"])
    def apply_preset():
        """Apply preset to selected deviations."""
        try:
            data = request.get_json()
            preset_id = data.get("preset_id")
            deviation_ids = data.get("deviation_ids", [])

            if not preset_id or not deviation_ids:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "preset_id and deviation_ids required",
                        }
                    ),
                    400,
                )

            uploader_service, preset_repo, deviation_repo = get_upload_services()

            preset = preset_repo.get_preset_by_id(preset_id)
            if not preset:
                return jsonify({"success": False, "error": "Preset not found"}), 404

            applied = []
            for dev_id in deviation_ids:
                deviation = deviation_repo.get_deviation_by_id(dev_id)
                if deviation:
                    increment = preset_repo.increment_preset_counter(preset_id)
                    uploader_service.apply_preset_to_deviation(deviation, preset, increment)
                    deviation_repo.update_deviation(deviation)
                    applied.append(dev_id)

            return jsonify({"success": True, "applied": applied, "count": len(applied)})
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Apply preset failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/admin/stash", methods=["POST"])
    def stash_selected():
        """Stash selected deviations."""
        try:
            data = request.get_json()
            deviation_ids = data.get("deviation_ids", [])
            preset_id = data.get("preset_id")

            if not deviation_ids or not preset_id:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "deviation_ids and preset_id required",
                        }
                    ),
                    400,
                )

            uploader_service, preset_repo, _deviation_repo = get_upload_services()

            preset = preset_repo.get_preset_by_id(preset_id)
            if not preset:
                return jsonify({"success": False, "error": "Preset not found"}), 404

            results = uploader_service.batch_stash(deviation_ids, preset)

            return jsonify({"success": True, "results": results})
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Stash failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/admin/publish", methods=["POST"])
    def publish_selected():
        """Publish stashed deviations."""
        try:
            data = request.get_json()
            deviation_ids = data.get("deviation_ids", [])

            if not deviation_ids:
                return jsonify({"success": False, "error": "deviation_ids required"}), 400

            uploader_service, _preset_repo, _deviation_repo = get_upload_services()

            results = uploader_service.batch_publish(deviation_ids)

            return jsonify({"success": True, "results": results})
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Publish failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/admin/upload", methods=["POST"])
    def upload_selected():
        """Upload selected deviations (stash + publish)."""
        try:
            data = request.get_json()
            deviation_ids = data.get("deviation_ids", [])
            preset_id = data.get("preset_id")

            if not deviation_ids or not preset_id:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "deviation_ids and preset_id required",
                        }
                    ),
                    400,
                )

            uploader_service, preset_repo, _deviation_repo = get_upload_services()

            preset = preset_repo.get_preset_by_id(preset_id)
            if not preset:
                return jsonify({"success": False, "error": "Preset not found"}), 404

            results = uploader_service.batch_upload(deviation_ids, preset)

            return jsonify({"success": True, "results": results})
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Upload failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/admin/delete", methods=["POST"])
    def delete_selected():
        """Delete deviations and files."""
        try:
            data = request.get_json()
            deviation_ids = data.get("deviation_ids", [])

            if not deviation_ids:
                return jsonify({"success": False, "error": "deviation_ids required"}), 400

            uploader_service, _preset_repo, _deviation_repo = get_upload_services()

            deleted = []
            failed = []

            for dev_id in deviation_ids:
                if uploader_service.delete_deviation_and_file(dev_id):
                    deleted.append(dev_id)
                else:
                    failed.append(dev_id)

            return jsonify(
                {"success": True, "deleted": deleted, "failed": failed, "count": len(deleted)}
            )
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Delete failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500
