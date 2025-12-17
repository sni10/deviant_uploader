"""Thumbnail-serving route for upload admin."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from flask import Flask, g, jsonify, send_file


def register_thumbnail_routes(
    app: Flask,
    *,
    config: object,
    project_root: Path,
    get_upload_services: Callable[[], tuple[object, object, object]],
) -> None:
    """Register thumbnail-serving endpoint."""

    @app.route("/api/admin/thumbnail/<int:deviation_id>")
    def get_thumbnail(deviation_id):
        """Serve thumbnail image for a deviation."""
        try:
            _uploader_service, _preset_repo, deviation_repo = get_upload_services()
            deviation = deviation_repo.get_deviation_by_id(deviation_id)

            if not deviation:
                return jsonify({"error": "Deviation not found"}), 404

            def _resolve_candidate_from_upload_dir(fname: str) -> Path | None:
                """Find a candidate file in upload_dir by filename (case-insensitive extension)."""
                if not fname:
                    return None
                upload_dir = config.upload_dir
                stem = Path(fname).stem
                suffix = Path(fname).suffix.lower()

                cand = upload_dir / f"{stem}{suffix}"
                if cand.exists():
                    return cand

                for ext in [".png", ".jpg", ".jpeg", ".gif", ".bmp"]:
                    cand2 = upload_dir / f"{stem}{ext}"
                    if cand2.exists():
                        return cand2
                return None

            file_path = Path(deviation.file_path) if getattr(deviation, "file_path", None) else None

            bad_segment = str(project_root / "src" / "api" / "upload").lower()
            needs_rebuild = (
                file_path is None
                or not file_path.exists()
                or str(file_path).lower().startswith(bad_segment)
                or bad_segment in str(file_path).lower()
                or (file_path and not file_path.is_absolute())
            )

            if needs_rebuild:
                dev_filename = None
                if getattr(deviation, "filename", None):
                    dev_filename = deviation.filename
                elif file_path:
                    dev_filename = file_path.name

                candidate_path = _resolve_candidate_from_upload_dir(dev_filename)
                if not candidate_path and file_path is not None:
                    candidate_path = _resolve_candidate_from_upload_dir(file_path.name)

                if candidate_path and candidate_path.exists():
                    file_path = candidate_path
                    try:
                        deviation.file_path = str(candidate_path)
                        new_name = candidate_path.name
                        if getattr(deviation, "filename", None) and deviation.filename != new_name:
                            deviation.filename = new_name
                        deviation_repo.update_deviation(deviation)
                    except Exception as update_exc:  # noqa: BLE001
                        g.logger.warning(
                            "Failed to persist corrected file path for deviation %s: %s",
                            deviation_id,
                            update_exc,
                        )
                else:
                    return jsonify({"error": "File not found on disk"}), 404

            ext = file_path.suffix[1:].lower()
            return send_file(
                str(file_path),
                mimetype=f"image/{ext}",
                as_attachment=False,
            )
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Get thumbnail failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
