"""Tests for Profile Messages API datetime serialization.

Some drivers can return datetime columns as strings. The API should not assume
datetime objects and call .isoformat() unconditionally.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class _DummyConfig:
    """Minimal config stub for create_app in tests."""

    log_dir: Path
    log_level: str = "INFO"


class TestProfileMessagesApiSerialization:
    """Validate that profile message endpoints serialize string timestamps."""

    def test_get_profile_messages_accepts_string_created_at(self, tmp_path, monkeypatch):
        """GET /api/profile-messages should not crash on string created_at."""
        from src.api import stats_api as stats_api_module

        class _Msg:
            def __init__(self):
                self.message_id = 1
                self.title = "t"
                self.body = "b"
                self.is_active = True
                self.created_at = "2025-12-17 08:30:30"

        class _MessageRepo:
            def get_all_messages(self):
                return [_Msg()]

        class _Service:
            def __init__(self):
                self.message_repo = _MessageRepo()

        monkeypatch.setattr(stats_api_module, "get_profile_message_service", lambda: _Service())

        app = stats_api_module.create_app(config=_DummyConfig(log_dir=tmp_path))
        client = app.test_client()

        resp = client.get("/api/profile-messages")
        assert resp.status_code == 200

        payload = resp.get_json()
        assert payload["success"] is True
        assert payload["data"][0]["created_at"] == "2025-12-17 08:30:30"

    def test_get_profile_message_logs_accepts_string_sent_at(self, tmp_path, monkeypatch):
        """GET /api/profile-messages/logs should not crash on string sent_at."""
        from src.api import stats_api as stats_api_module

        class _Log:
            def __init__(self):
                self.log_id = 1
                self.message_id = 1
                self.recipient_username = "u"
                self.recipient_userid = "123"
                self.commentid = None

                class _Status:
                    value = "sent"

                self.status = _Status()
                self.error_message = None
                self.sent_at = "2025-12-17 08:30:30"

        class _LogRepo:
            def get_all_logs(self, limit, offset):
                return [_Log()]

        class _Service:
            def __init__(self):
                self.log_repo = _LogRepo()

        monkeypatch.setattr(stats_api_module, "get_profile_message_service", lambda: _Service())

        app = stats_api_module.create_app(config=_DummyConfig(log_dir=tmp_path))
        client = app.test_client()

        resp = client.get("/api/profile-messages/logs?limit=50")
        assert resp.status_code == 200

        payload = resp.get_json()
        assert payload["success"] is True
        assert payload["data"][0]["sent_at"] == "2025-12-17 08:30:30"
