"""Tests for Profile Messages watchers prune API endpoint."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class _DummyConfig:
    """Minimal config stub for create_app in tests."""

    log_dir: Path
    log_level: str = "INFO"


class TestProfileMessagesWatchersPruneApi:
    """Validate /api/profile-messages/watchers/prune endpoint."""

    def test_prune_requires_username(self, tmp_path, monkeypatch) -> None:
        """Endpoint must validate input payload."""
        from src.api import stats_api as stats_api_module

        class _Auth:
            def ensure_authenticated(self) -> bool:
                return True

            def get_valid_token(self):
                return "token"

        monkeypatch.setattr(stats_api_module, "get_services", lambda: (_Auth(), None))

        class _Service:
            def prune_unfollowed_watchers(self, access_token: str, username: str, max_watchers: int):
                raise AssertionError("Should not be called when username missing")

        monkeypatch.setattr(stats_api_module, "get_profile_message_service", lambda: _Service())

        app = stats_api_module.create_app(config=_DummyConfig(log_dir=tmp_path))
        client = app.test_client()

        resp = client.post("/api/profile-messages/watchers/prune", json={"username": ""})
        assert resp.status_code == 400

        payload = resp.get_json()
        assert payload["success"] is False

    def test_prune_returns_service_result(self, tmp_path, monkeypatch) -> None:
        """Endpoint should return JSON with service result."""
        from src.api import stats_api as stats_api_module

        class _Auth:
            def ensure_authenticated(self) -> bool:
                return True

            def get_valid_token(self):
                return "token"

        monkeypatch.setattr(stats_api_module, "get_services", lambda: (_Auth(), None))

        class _Service:
            def prune_unfollowed_watchers(self, access_token: str, username: str, max_watchers: int):
                assert access_token == "token"
                assert username == "me"
                assert max_watchers == 50
                return {
                    "watchers_count": 2,
                    "has_more": False,
                    "pruned": True,
                    "deleted_count": 1,
                }

        monkeypatch.setattr(stats_api_module, "get_profile_message_service", lambda: _Service())

        app = stats_api_module.create_app(config=_DummyConfig(log_dir=tmp_path))
        client = app.test_client()

        resp = client.post(
            "/api/profile-messages/watchers/prune",
            json={"username": "me", "max_watchers": 50},
        )
        assert resp.status_code == 200

        payload = resp.get_json()
        assert payload["success"] is True
        assert payload["data"]["deleted_count"] == 1
