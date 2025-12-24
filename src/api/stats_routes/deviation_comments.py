"""Deviation auto-comment API routes."""

from __future__ import annotations

from collections.abc import Callable

from flask import Flask, g, jsonify, request

from ...domain.models import (
    DeviationCommentLogStatus,
    DeviationCommentQueueStatus,
)


def _parse_queue_status(value: str | None) -> DeviationCommentQueueStatus | None:
    """Parse queue status from request parameters."""
    if not value:
        return None

    normalized = value.strip().lower()
    for status in DeviationCommentQueueStatus:
        if status.value == normalized:
            return status
    return None


def _parse_log_status(value: str | None) -> DeviationCommentLogStatus | None:
    """Parse log status from request parameters."""
    if not value:
        return None

    normalized = value.strip().lower()
    for status in DeviationCommentLogStatus:
        if status.value == normalized:
            return status
    return None


def register_deviation_comment_routes(
    app: Flask,
    *,
    get_services: Callable[[], tuple[object, object]],
    get_deviation_comment_service: Callable[[], tuple[object, object]],
) -> None:
    """Register deviation auto-comment endpoints."""

    @app.route("/api/deviation-comments/messages", methods=["GET"])
    def get_comment_messages():
        """Get all comment templates."""
        try:
            _collector, poster = get_deviation_comment_service()
            messages = poster.message_repo.get_all_messages()

            return jsonify(
                {
                    "success": True,
                    "data": [
                        {
                            "message_id": m.message_id,
                            "title": m.title,
                            "body": m.body,
                            "is_active": m.is_active,
                            "created_at": (
                                m.created_at
                                if isinstance(m.created_at, str)
                                else m.created_at.isoformat()
                                if m.created_at
                                else None
                            ),
                        }
                        for m in messages
                    ],
                }
            )
        except Exception as e:  # noqa: BLE001
            g.logger.error("Get comment messages failed: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/deviation-comments/messages", methods=["POST"])
    def create_comment_message():
        """Create new comment template."""
        try:
            data = request.get_json() or {}
            title = (data.get("title") or "").strip()
            body = (data.get("body") or "").strip()

            if not title or not body:
                return (
                    jsonify({"success": False, "error": "Title and body are required"}),
                    400,
                )

            _collector, poster = get_deviation_comment_service()
            message_id = poster.message_repo.create_message(title, body)

            return jsonify({"success": True, "message_id": message_id})
        except Exception as e:  # noqa: BLE001
            g.logger.error("Create comment message failed: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/deviation-comments/messages/<int:message_id>", methods=["PUT"])
    def update_comment_message(message_id: int):
        """Update comment template."""
        try:
            data = request.get_json() or {}
            title = data.get("title")
            body = data.get("body")
            is_active = data.get("is_active")

            _collector, poster = get_deviation_comment_service()
            poster.message_repo.update_message(
                message_id,
                title=title.strip() if isinstance(title, str) else None,
                body=body.strip() if isinstance(body, str) else None,
                is_active=is_active,
            )

            return jsonify({"success": True})
        except Exception as e:  # noqa: BLE001
            g.logger.error("Update comment message failed: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/deviation-comments/messages/<int:message_id>", methods=["DELETE"])
    def delete_comment_message(message_id: int):
        """Delete comment template."""
        try:
            _collector, poster = get_deviation_comment_service()
            poster.message_repo.delete_message(message_id)

            return jsonify({"success": True})
        except Exception as e:  # noqa: BLE001
            g.logger.error("Delete comment message failed: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route(
        "/api/deviation-comments/messages/<int:message_id>/toggle",
        methods=["POST"],
    )
    def toggle_comment_message(message_id: int):
        """Toggle comment template active flag."""
        try:
            _collector, poster = get_deviation_comment_service()
            message = poster.message_repo.get_message_by_id(message_id)

            if message is None:
                return jsonify({"success": False, "error": "Template not found"}), 404

            new_status = not message.is_active
            poster.message_repo.update_message(message_id, is_active=new_status)

            return jsonify({"success": True, "is_active": new_status})
        except Exception as e:  # noqa: BLE001
            g.logger.error("Toggle comment message failed: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/deviation-comments/collect/watch-feed", methods=["POST"])
    def collect_watch_feed():
        """Collect deviations from watch feed."""
        try:
            data = request.get_json() or {}
            pages = int(data.get("pages", 5))

            if pages < 1 or pages > 20:
                return (
                    jsonify({"success": False, "error": "Pages must be between 1 and 20"}),
                    400,
                )

            auth_service, _stats_service = get_services()

            if not auth_service.ensure_authenticated():
                return jsonify({"success": False, "error": "Not authenticated"}), 401

            access_token = auth_service.get_valid_token()
            if not access_token:
                return (
                    jsonify({"success": False, "error": "Failed to obtain access token"}),
                    401,
                )

            collector, _poster = get_deviation_comment_service()
            result = collector.collect_from_watch_feed(access_token, pages)

            return jsonify({"success": True, "data": result})
        except Exception as e:  # noqa: BLE001
            g.logger.error("Collect watch feed failed: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/deviation-comments/collect/global-feed", methods=["POST"])
    def collect_global_feed():
        """Collect deviations from global feed."""
        try:
            data = request.get_json() or {}
            pages = int(data.get("pages", 5))

            if pages < 1 or pages > 20:
                return (
                    jsonify({"success": False, "error": "Pages must be between 1 and 20"}),
                    400,
                )

            auth_service, _stats_service = get_services()

            if not auth_service.ensure_authenticated():
                return jsonify({"success": False, "error": "Not authenticated"}), 401

            access_token = auth_service.get_valid_token()
            if not access_token:
                return (
                    jsonify({"success": False, "error": "Failed to obtain access token"}),
                    401,
                )

            collector, _poster = get_deviation_comment_service()
            result = collector.collect_from_global_feed(access_token, pages)

            return jsonify({"success": True, "data": result})
        except Exception as e:  # noqa: BLE001
            g.logger.error("Collect global feed failed: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/deviation-comments/worker/start", methods=["POST"])
    def start_comment_worker():
        """Start background worker."""
        try:
            auth_service, _stats_service = get_services()

            if not auth_service.ensure_authenticated():
                return jsonify({"success": False, "error": "Not authenticated"}), 401

            access_token = auth_service.get_valid_token()
            if not access_token:
                return (
                    jsonify({"success": False, "error": "Failed to obtain access token"}),
                    401,
                )

            data = request.get_json() or {}
            template_id = data.get("template_id")
            template_id = int(template_id) if template_id is not None else None

            _collector, poster = get_deviation_comment_service()
            result = poster.start_worker(access_token, auth_service=auth_service, template_id=template_id)

            return jsonify(result)
        except Exception as e:  # noqa: BLE001
            g.logger.error("Start comment worker failed: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/deviation-comments/worker/stop", methods=["POST"])
    def stop_comment_worker():
        """Stop background worker."""
        try:
            _collector, poster = get_deviation_comment_service()
            result = poster.stop_worker()

            return jsonify(result)
        except Exception as e:  # noqa: BLE001
            g.logger.error("Stop comment worker failed: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/deviation-comments/worker/status", methods=["GET"])
    def get_comment_worker_status():
        """Get worker and queue status."""
        try:
            _collector, poster = get_deviation_comment_service()
            status = poster.get_worker_status()

            return jsonify({"success": True, "data": status})
        except Exception as e:  # noqa: BLE001
            g.logger.error("Get comment worker status failed: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/deviation-comments/queue", methods=["GET"])
    def get_comment_queue():
        """Get queue entries by status."""
        try:
            status = _parse_queue_status(request.args.get("status"))
            limit = int(request.args.get("limit", 100))

            _collector, poster = get_deviation_comment_service()
            queue_items = poster.queue_repo.get_queue(status=status, limit=limit)

            return jsonify(
                {
                    "success": True,
                    "data": [
                        {
                            "deviationid": item.deviationid,
                            "deviation_url": item.deviation_url,
                            "title": item.title,
                            "author_username": item.author_username,
                            "author_userid": item.author_userid,
                            "source": item.source,
                            "ts": item.ts,
                            "status": item.status.value,
                            "attempts": item.attempts,
                            "last_error": item.last_error,
                            "created_at": (
                                item.created_at
                                if isinstance(item.created_at, str)
                                else item.created_at.isoformat()
                                if item.created_at
                                else None
                            ),
                            "updated_at": (
                                item.updated_at
                                if isinstance(item.updated_at, str)
                                else item.updated_at.isoformat()
                                if item.updated_at
                                else None
                            ),
                        }
                        for item in queue_items
                    ],
                }
            )
        except Exception as e:  # noqa: BLE001
            g.logger.error("Get comment queue failed: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/deviation-comments/queue/clear", methods=["POST"])
    def clear_comment_queue():
        """Clear queue entries."""
        try:
            data = request.get_json() or {}
            status_value = data.get("status")
            status = _parse_queue_status(status_value)

            _collector, poster = get_deviation_comment_service()
            cleared = poster.queue_repo.clear_queue(status=status)

            return jsonify({"success": True, "cleared_count": cleared})
        except Exception as e:  # noqa: BLE001
            g.logger.error("Clear comment queue failed: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/deviation-comments/queue/reset-failed", methods=["POST"])
    def reset_failed_comment_queue():
        """Reset failed queue entries to pending."""
        try:
            _collector, poster = get_deviation_comment_service()
            reset_count = poster.queue_repo.reset_failed_to_pending()

            return jsonify({"success": True, "reset_count": reset_count})
        except Exception as e:  # noqa: BLE001
            g.logger.error("Reset failed comment queue failed: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/deviation-comments/queue/remove-selected", methods=["POST"])
    def remove_selected_from_queue():
        """Remove selected queue entries."""
        try:
            data = request.get_json() or {}
            deviationids = data.get("deviationids", [])

            if not isinstance(deviationids, list):
                return jsonify({"success": False, "error": "deviationids must be a list"}), 400

            _collector, poster = get_deviation_comment_service()
            removed = poster.queue_repo.remove_by_ids([str(i) for i in deviationids])

            return jsonify({"success": True, "removed_count": removed})
        except Exception as e:  # noqa: BLE001
            g.logger.error("Remove selected from queue failed: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/deviation-comments/logs", methods=["GET"])
    def get_comment_logs():
        """Get comment logs."""
        try:
            status = _parse_log_status(request.args.get("status"))
            limit = int(request.args.get("limit", 100))
            offset = int(request.args.get("offset", 0))

            _collector, poster = get_deviation_comment_service()
            logs = poster.log_repo.get_logs(limit=limit, status=status, offset=offset)

            return jsonify(
                {
                    "success": True,
                    "data": [
                        {
                            "log_id": log.log_id,
                            "message_id": log.message_id,
                            "deviationid": log.deviationid,
                            "deviation_url": log.deviation_url,
                            "author_username": log.author_username,
                            "commentid": log.commentid,
                            "comment_text": log.comment_text,
                            "status": log.status.value,
                            "error_message": log.error_message,
                            "sent_at": (
                                log.sent_at
                                if isinstance(log.sent_at, str)
                                else log.sent_at.isoformat()
                                if log.sent_at
                                else None
                            ),
                        }
                        for log in logs
                    ],
                }
            )
        except Exception as e:  # noqa: BLE001
            g.logger.error("Get comment logs failed: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/deviation-comments/logs/stats", methods=["GET"])
    def get_comment_log_stats():
        """Get comment log stats grouped by template."""
        try:
            _collector, poster = get_deviation_comment_service()
            stats = poster.log_repo.get_stats_by_template()

            return jsonify({"success": True, "data": stats})
        except Exception as e:  # noqa: BLE001
            g.logger.error("Get comment log stats failed: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500
