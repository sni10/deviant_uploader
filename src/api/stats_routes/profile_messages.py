"""Profile message broadcasting API routes."""

from __future__ import annotations

from collections.abc import Callable

from flask import Flask, g, jsonify, request


def register_profile_message_routes(
    app: Flask,
    *,
    get_services: Callable[[], tuple[object, object]],
    get_profile_message_service: Callable[[], object],
) -> None:
    """Register profile message broadcasting endpoints."""

    @app.route("/api/profile-messages", methods=["GET"])
    def get_profile_messages():
        """Get all profile message templates."""
        try:
            service = get_profile_message_service()
            messages = service.message_repo.get_all_messages()

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
                                else m.created_at.isoformat() if m.created_at else None
                            ),
                        }
                        for m in messages
                    ],
                }
            )
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Get messages failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages", methods=["POST"])
    def create_profile_message():
        """Create new profile message template."""
        try:
            data = request.get_json() or {}
            title = data.get("title", "").strip()
            body = data.get("body", "").strip()

            if not title or not body:
                return (
                    jsonify({"success": False, "error": "Title and body are required"}),
                    400,
                )

            service = get_profile_message_service()
            message_id = service.message_repo.create_message(title, body)

            return jsonify({"success": True, "message_id": message_id})
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Create message failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/<int:message_id>", methods=["PUT"])
    def update_profile_message(message_id):
        """Update profile message template."""
        try:
            data = request.get_json() or {}
            title = data.get("title")
            body = data.get("body")
            is_active = data.get("is_active")

            service = get_profile_message_service()
            service.message_repo.update_message(
                message_id,
                title=title.strip() if title else None,
                body=body.strip() if body else None,
                is_active=is_active,
            )

            return jsonify({"success": True})
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Update message failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/<int:message_id>", methods=["DELETE"])
    def delete_profile_message(message_id):
        """Delete profile message template."""
        try:
            service = get_profile_message_service()
            service.message_repo.delete_message(message_id)

            return jsonify({"success": True})
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Delete message failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/fetch-watchers", methods=["POST"])
    def fetch_watchers():
        """Fetch watchers and add to queue."""
        try:
            data = request.get_json() or {}
            username = data.get("username", "").strip()
            max_watchers = int(data.get("max_watchers", 50))

            if not username:
                return jsonify({"success": False, "error": "Username is required"}), 400

            if max_watchers < 1 or max_watchers > 500:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "max_watchers must be between 1 and 500",
                        }
                    ),
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

            service = get_profile_message_service()
            result = service.fetch_watchers(access_token, username, max_watchers)

            return jsonify({"success": True, "data": result})
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Fetch watchers failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/watchers/prune", methods=["POST"])
    def prune_unfollowed_watchers():
        """Remove unfollowed watchers from database based on current DA list."""
        try:
            data = request.get_json() or {}
            username = data.get("username", "").strip()
            max_watchers = int(data.get("max_watchers", 500))

            if not username:
                return jsonify({"success": False, "error": "Username is required"}), 400

            if max_watchers < 1 or max_watchers > 5000:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "max_watchers must be between 1 and 5000",
                        }
                    ),
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

            service = get_profile_message_service()
            result = service.prune_unfollowed_watchers(access_token, username, max_watchers)

            return jsonify({"success": True, "data": result})
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Prune watchers failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/worker/start", methods=["POST"])
    def start_broadcast_worker():
        """Start worker to broadcast message to watchers queue.
        
        Worker will randomly select from active message templates for each send.
        """
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

            service = get_profile_message_service()
            result = service.start_worker(access_token, auth_service=auth_service)

            return jsonify(result)
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Start broadcast worker failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/worker/stop", methods=["POST"])
    def stop_broadcast_worker():
        """Stop broadcast worker."""
        try:
            service = get_profile_message_service()
            result = service.stop_worker()

            return jsonify(result)
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Stop broadcast worker failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/worker/status", methods=["GET"])
    def get_broadcast_worker_status():
        """Get broadcast worker and queue status."""
        try:
            service = get_profile_message_service()
            status = service.get_worker_status()

            return jsonify({"success": True, "data": status})
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Get broadcast status failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/queue/clear", methods=["POST"])
    def clear_watchers_queue():
        """Clear watchers queue."""
        try:
            service = get_profile_message_service()
            result = service.clear_queue()

            return jsonify(result)
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Clear queue failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/queue/list", methods=["GET"])
    def get_watchers_list():
        """Get watchers queue with selection status."""
        try:
            service = get_profile_message_service()
            watchers = service.get_watchers_list()

            return jsonify({"success": True, "data": watchers})
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Get watchers list failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/queue/toggle", methods=["POST"])
    def toggle_watcher_selection():
        """Toggle selection for specific watcher."""
        try:
            data = request.get_json() or {}
            username = data.get("username", "").strip()
            selected = data.get("selected", False)

            if not username:
                return jsonify({"success": False, "error": "Username is required"}), 400

            service = get_profile_message_service()
            result = service.update_watcher_selection(username, selected)

            return jsonify(result)
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Toggle watcher selection failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/queue/select-all", methods=["POST"])
    def select_all_watchers():
        """Select all watchers in queue."""
        try:
            service = get_profile_message_service()
            result = service.select_all_watchers()

            return jsonify(result)
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Select all watchers failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/queue/deselect-all", methods=["POST"])
    def deselect_all_watchers():
        """Deselect all watchers in queue."""
        try:
            service = get_profile_message_service()
            result = service.deselect_all_watchers()

            return jsonify(result)
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Deselect all watchers failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/queue/remove-selected", methods=["POST"])
    def remove_selected_watchers_from_queue():
        """Remove selected watchers from in-memory queue."""
        try:
            service = get_profile_message_service()
            result = service.remove_selected_from_queue()

            return jsonify(result)
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Remove selected watchers failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/queue/retry-failed", methods=["POST"])
    def retry_failed_messages():
        """Retry failed messages by adding them back to queue."""
        try:
            data = request.get_json() or {}
            limit = int(data.get("limit", 100))

            service = get_profile_message_service()
            result = service.retry_failed_messages(limit=limit)

            return jsonify(result)
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Retry failed messages failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/logs", methods=["GET"])
    def get_broadcast_logs():
        """Get broadcast logs."""
        try:
            message_id = request.args.get("message_id")
            limit = int(request.args.get("limit", 100))
            offset = int(request.args.get("offset", 0))

            service = get_profile_message_service()

            if message_id:
                logs = service.log_repo.get_logs_by_message_id(
                    int(message_id), limit, offset
                )
            else:
                logs = service.log_repo.get_all_logs(limit, offset)

            return jsonify(
                {
                    "success": True,
                    "data": [
                        {
                            "log_id": log.log_id,
                            "message_id": log.message_id,
                            "recipient_username": log.recipient_username,
                            "recipient_userid": log.recipient_userid,
                            "commentid": log.commentid,
                            "status": log.status.value,
                            "error_message": log.error_message,
                            "sent_at": (
                                log.sent_at
                                if isinstance(log.sent_at, str)
                                else log.sent_at.isoformat() if log.sent_at else None
                            ),
                            "profile_url": (
                                f"https://www.deviantart.com/{log.recipient_username}"
                            ),
                        }
                        for log in logs
                    ],
                }
            )
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Get logs failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/watchers/saved", methods=["GET"])
    def get_saved_watchers():
        """Get watchers from database."""
        try:
            limit = int(request.args.get("limit", 1000))

            service = get_profile_message_service()
            watchers = service.watcher_repo.get_all_watchers(limit)

            return jsonify(
                {
                    "success": True,
                    "data": [
                        {
                            "username": w.username,
                            "userid": w.userid,
                            "fetched_at": (
                                w.fetched_at
                                if isinstance(w.fetched_at, str)
                                else w.fetched_at.isoformat() if w.fetched_at else None
                            ),
                        }
                        for w in watchers
                    ],
                }
            )
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Get saved watchers failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/watchers/save", methods=["POST"])
    def save_watcher_to_db():
        """Save single watcher to database."""
        try:
            data = request.get_json() or {}
            username = data.get("username", "").strip()
            userid = data.get("userid", "").strip()

            if not username or not userid:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "username and userid are required",
                        }
                    ),
                    400,
                )

            service = get_profile_message_service()
            result = service.save_watcher_to_db(username, userid)

            return jsonify(result)
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Save watcher failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/watchers/save-selected", methods=["POST"])
    def save_selected_watchers_to_db():
        """Save only selected watchers from queue to database."""
        try:
            service = get_profile_message_service()
            result = service.save_selected_to_db()

            return jsonify(result)
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Save selected watchers failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/watchers/add-to-queue", methods=["POST"])
    def add_saved_watcher_to_queue():
        """Add saved watcher to sending queue."""
        try:
            data = request.get_json() or {}
            username = data.get("username", "").strip()
            userid = data.get("userid", "").strip()

            if not username or not userid:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "username and userid are required",
                        }
                    ),
                    400,
                )

            service = get_profile_message_service()
            result = service.add_saved_watcher_to_queue(username, userid)

            return jsonify(result)
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Add watcher to queue failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/watchers/add-selected-to-queue", methods=["POST"])
    def add_selected_saved_watchers_to_queue():
        """Add selected saved watchers to sending queue."""
        try:
            data = request.get_json() or {}
            watchers = data.get("watchers", [])

            if not isinstance(watchers, list):
                return jsonify({"success": False, "error": "watchers must be a list"}), 400

            if len(watchers) > 5000:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "watchers list is too large (max 5000)",
                        }
                    ),
                    400,
                )

            service = get_profile_message_service()
            result = service.add_selected_saved_to_queue(watchers)

            return jsonify(result)
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Add selected saved watchers to queue failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/profile-messages/watchers/add-all-to-queue", methods=["POST"])
    def add_all_saved_to_queue():
        """Add all saved watchers to sending queue."""
        try:
            data = request.get_json() or {}
            limit = int(data.get("limit", 1000))

            service = get_profile_message_service()
            result = service.add_all_saved_to_queue(limit)

            return jsonify(result)
        except Exception as e:  # noqa: BLE001
            g.logger.error(f"Add all saved to queue failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500
