"""Tests for StatsService rate-limit handling.

These tests focus on `_fetch_deviation_details`, ensuring that the
service reacts gracefully to DeviantArt rate limits and does not keep
issuing requests once a user-level threshold has been reached.
"""

from __future__ import annotations

from typing import Any

import logging

import pytest

from src.service.stats_service import StatsService


class _DummyDeviationStatsRepository:
    """Minimal stub for DeviationStatsRepository used in tests.

    The rate-limit behavior under test does not touch the repository, so
    this object intentionally has no methods. It merely satisfies the
    constructor signature of ``StatsService``.
    """


class _DummyStatsSnapshotRepository:
    """Minimal stub for StatsSnapshotRepository used in tests."""


class _DummyUserStatsSnapshotRepository:
    """Minimal stub for UserStatsSnapshotRepository used in tests."""


class _DummyDeviationMetadataRepository:
    """Minimal stub for DeviationMetadataRepository used in tests."""


class _DummyDeviationRepository:
    """Minimal stub for DeviationRepository used in tests."""


def _build_service() -> StatsService:
    """Create a StatsService instance with dummy dependencies for tests."""

    logger = logging.getLogger("stats_service_test")
    return StatsService(
        _DummyDeviationStatsRepository(),
        _DummyStatsSnapshotRepository(),
        _DummyUserStatsSnapshotRepository(),
        _DummyDeviationMetadataRepository(),
        _DummyDeviationRepository(),
        logger
    )


class _FakeResponse:
    """Simple stand-in for ``requests.Response`` for testing purposes."""

    def __init__(
        self,
        status_code: int,
        payload: Any,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        # ``text`` is used only for logging in our code under test.
        self.text = str(payload)
        self.reason = ""
        self.headers = headers or {}

    def json(self) -> Any:  # noqa: D401
        """Return prepared JSON-like payload."""

        return self._payload

    def raise_for_status(self) -> None:
        """Mimic ``requests`` behaviour for 4xx/5xx codes."""

        from requests import HTTPError

        if 400 <= self.status_code:
            raise HTTPError(f"HTTP {self.status_code}")


def test_fetch_deviation_details_stops_on_429_after_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure that a 429 rate-limit response triggers backoff and then stops.

    When DeviantArt signals an adaptive rate limit with HTTP 429, the
    client should retry a few times with exponential backoff and then stop
    making further /deviation/{id} calls during the current sync run.
    """

    service = _build_service()

    calls: list[str] = []

    def fake_get(url: str, params: dict[str, str]) -> _FakeResponse:  # type: ignore[override]
        calls.append(url)
        # Always return rate limit.
        return _FakeResponse(
            429,
            {
                "error": "user_api_threshold",
                "error_description": "User request limit reached.",
                "status": "error",
            },
        )

    # Avoid real sleeping in tests by patching time.sleep to a no-op.
    monkeypatch.setattr("src.service.stats_service.requests.get", fake_get)
    monkeypatch.setattr("src.service.stats_service.time.sleep", lambda _seconds: None)

    result = service._fetch_deviation_details("token", ["A", "B", "C"])  # type: ignore[attr-defined]

    # No details can be collected once we consistently hit the limit.
    assert result == {}
    # We expect 1 + RATE_LIMIT_MAX_RETRIES calls for the first deviation only.
    assert len(calls) == 1 + service.RATE_LIMIT_MAX_RETRIES


def test_fetch_deviation_details_keeps_partial_data_before_429_with_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure details fetched before the first unrecoverable 429 are preserved.

    If some deviation details are fetched successfully and then the
    client hits a rate limit which remains after backoff retries, the
    previously obtained details should be returned while further
    deviations are skipped.
    """

    service = _build_service()

    # For deviation A: succeed immediately.
    # For deviation B: always return a 429 rate-limit response. The service
    # under test will apply exponential backoff and eventually stop after
    # RATE_LIMIT_MAX_RETRIES attempts without ever requesting deviation C.

    def fake_get(url: str, params: dict[str, str]) -> _FakeResponse:  # type: ignore[override]
        if url.endswith("/A"):
            return _FakeResponse(
                200,
                {"deviationid": "A", "published_time": "2024-01-01T00:00:00Z"},
            )

        if url.endswith("/B"):
            return _FakeResponse(
                429,
                {
                    "error": "user_api_threshold",
                    "error_description": "User request limit reached.",
                    "status": "error",
                },
            )

        # Deviation C should never be requested once rate limiting for B is
        # detected and retries are exhausted. If it is, the test should fail.
        raise AssertionError(f"Unexpected request URL in fake_get: {url}")

    monkeypatch.setattr("src.service.stats_service.requests.get", fake_get)
    monkeypatch.setattr("src.service.stats_service.time.sleep", lambda _seconds: None)

    result = service._fetch_deviation_details("token", ["A", "B", "C"])  # type: ignore[attr-defined]

    # Details for A were fetched before the rate limit occurred.
    assert "A" in result
    assert result["A"]["published_time"] == "2024-01-01T00:00:00Z"

    # After exhausting retries for B, we should not proceed to C.
    assert "C" not in result
