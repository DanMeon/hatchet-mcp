"""Serialization helpers: _dump is by-alias + json-mode; _api_error never carries the token."""

from datetime import datetime, timezone

from hatchet_sdk.clients.rest.exceptions import ApiException
from pydantic import BaseModel, Field

import hatchet_mcp._shared as shared


class _Sample(BaseModel):
    run_id: str = Field(alias="runId")
    created_at: datetime = Field(alias="createdAt")


def _sample() -> _Sample:
    # Pydantic synthesizes __init__ from the aliases, so construct via the aliases.
    return _Sample(runId="abc", createdAt=datetime(2026, 5, 20, tzinfo=timezone.utc))


def test_dump_uses_aliases():
    out = shared._dump(_sample())
    assert "runId" in out
    assert "createdAt" in out
    assert "run_id" not in out


def test_dump_is_json_native():
    out = shared._dump(_sample())
    # mode="json" → datetime is serialized to a string, not left as a datetime object.
    assert isinstance(out["createdAt"], str)


def test_api_error_redacts_token(monkeypatch):
    monkeypatch.setenv("HATCHET_CLIENT_TOKEN", "SECRET-JWT-123")
    exc = ApiException(
        status=500,
        reason="Internal Server Error",
        body="upstream rejected token SECRET-JWT-123 while calling",
    )
    err = shared._api_error(exc)
    text = str(err)
    assert isinstance(err, RuntimeError)
    assert "SECRET-JWT-123" not in text
    assert "***REDACTED***" in text


def test_api_error_includes_status_and_reason(monkeypatch):
    monkeypatch.delenv("HATCHET_CLIENT_TOKEN", raising=False)
    exc = ApiException(status=404, reason="Not Found")
    text = str(shared._api_error(exc))
    assert "status 404" in text
    assert "Not Found" in text


def test_api_error_truncates_long_body(monkeypatch):
    monkeypatch.delenv("HATCHET_CLIENT_TOKEN", raising=False)
    exc = ApiException(status=500, reason="boom", body="z" * 2000)
    text = str(shared._api_error(exc))
    assert text.count("z") <= 500
