"""Targeted regression tests for v0.4.0 fixes.

Each test pins one fix so a future refactor cannot quietly revert it. Grouped by the
finding ID from the verification report:
- C1: ApiClient pool reuse
- H1: read tools advertise readOnlyHint=True
- H3: tool title field is populated
- H5: resources go through the reliability wrapper
- H7: API errors carry a structured ``kind`` / ``status``
- H8: stderr tool.ok/tool.error records carry the MCP request_id when one is in scope
- H10: get_run_status returns camelCase ``workflowRunId``
"""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from hatchet_sdk.clients.rest.exceptions import ApiException

import hatchet_mcp._logging as logging_mod
import hatchet_mcp._shared as shared
import hatchet_mcp.client as client_mod
import hatchet_mcp.resources as resources_mod
import hatchet_mcp.tools.runs as runs_mod


# --- C1: ApiClient pool reuse ---------------------------------------------------------


def test_get_api_client_caches_single_instance(monkeypatch: pytest.MonkeyPatch):
    """get_api_client() must return the same ApiClient on every call (one PoolManager)."""
    fake_rest = MagicMock()
    fake_rest.api_config = MagicMock()
    monkeypatch.setattr(client_mod, "_api_client", None)
    monkeypatch.setattr(client_mod, "get_rest", lambda: fake_rest)
    created: list[Any] = []

    class FakeApiClient:
        def __init__(self, config: Any) -> None:
            created.append(config)

    monkeypatch.setattr(client_mod, "ApiClient", FakeApiClient)

    a = client_mod.get_api_client()
    b = client_mod.get_api_client()
    assert a is b
    assert len(created) == 1


# --- H1 + H3: read tool annotations and title ----------------------------------------


def test_read_tools_advertise_read_only_annotations(server_module):
    """Every read tool registered on app.mcp must have readOnlyHint=True, destructiveHint=False."""
    import hatchet_mcp.server as server

    registry = server_module.mcp._tool_manager._tools
    read_tool_names = {name for _fn, name, *_ in server.READ_TOOLS}
    for name in read_tool_names:
        tool = registry[name]
        ann = tool.annotations
        assert ann is not None, f"{name} missing annotations"
        assert ann.readOnlyHint is True, f"{name} not flagged readOnlyHint=True"
        assert ann.destructiveHint is False, f"{name} not flagged destructiveHint=False"
        # H3: title is populated (snake_case → Title Case).
        assert tool.title, f"{name} missing title"
        assert "_" not in tool.title, f"{name} title still snake_case: {tool.title}"


# --- H5: resources go through the reliability wrapper ---------------------------------


async def test_resource_run_retries_via_reliability_wrapper(
    monkeypatch: pytest.MonkeyPatch,
):
    """A resource read that hits a 5xx must retry, just like the equivalent tool call."""
    call_count = 0

    async def fake_aio_get(workflow_run_id: str):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ApiException(status=503, reason="Service Unavailable")
        sentinel = MagicMock()
        sentinel.model_dump.return_value = {"id": workflow_run_id, "status": "OK"}
        return sentinel

    fake_hatchet = MagicMock()
    fake_hatchet.runs.aio_get = AsyncMock(side_effect=fake_aio_get)
    monkeypatch.setattr(runs_mod, "get_hatchet", lambda: fake_hatchet)

    # Force a fresh wrap so monkeypatching get_hatchet inside runs_mod actually takes effect.
    wrapped = shared._reliability_wrap(runs_mod.get_run, retry=True)
    monkeypatch.setattr(resources_mod, "_wrapped_get_run", wrapped)

    raw = await resources_mod.resource_run("run-123")
    payload = json.loads(raw)
    assert payload == {"id": "run-123", "status": "OK"}
    assert call_count == 2  # one retry happened


# --- H7: HatchetAPIError carries status + kind ----------------------------------------


def test_api_error_classifies_known_statuses():
    err_404 = shared._api_error(ApiException(status=404, reason="Not Found"))
    assert isinstance(err_404, shared.HatchetAPIError)
    assert err_404.status == 404
    assert err_404.kind == "not_found"
    assert str(err_404).startswith("Hatchet API error: status 404")

    err_429 = shared._api_error(ApiException(status=429, reason="Too Many Requests"))
    assert err_429.kind == "rate_limited"

    err_503 = shared._api_error(ApiException(status=503, reason="Bad Gateway"))
    assert err_503.kind == "server_error"

    err_unknown = shared._api_error(ApiException(status=418, reason="I'm a teapot"))
    assert err_unknown.kind == "unknown"


# --- H8: stderr records carry request_id when available -------------------------------


async def test_tool_ok_record_includes_request_id_field(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """``tool.ok`` and ``tool.error`` payloads must include the request_id key (None outside a request)."""

    async def ok() -> dict[str, Any]:
        return {"ok": True}

    wrapped = shared._reliability_wrap(ok, retry=False)
    await wrapped()
    captured = capsys.readouterr().err.strip().splitlines()
    record = json.loads(captured[-1])
    assert record["event"] == "tool.ok"
    assert "request_id" in record  # present, even if value is None


async def test_tool_error_record_includes_status_and_kind(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    async def boom() -> dict[str, Any]:
        raise ApiException(status=429, reason="Too Many Requests")

    wrapped = shared._reliability_wrap(boom, retry=False)
    with pytest.raises(shared.HatchetAPIError):
        await wrapped()
    captured = capsys.readouterr().err.strip().splitlines()
    record = json.loads(captured[-1])
    assert record["event"] == "tool.error"
    assert record["error_status"] == 429
    assert record["error_kind"] == "rate_limited"
    assert "request_id" in record


# --- H10: get_run_status returns camelCase --------------------------------------------


async def test_get_run_status_returns_camelcase_key(monkeypatch: pytest.MonkeyPatch):
    fake_hatchet = MagicMock()
    fake_status = MagicMock()
    fake_status.value = "COMPLETED"
    fake_hatchet.runs.aio_get_status = AsyncMock(return_value=fake_status)
    monkeypatch.setattr(runs_mod, "get_hatchet", lambda: fake_hatchet)

    result = await runs_mod.get_run_status("run-abc")
    assert "workflowRunId" in result
    assert "workflow_run_id" not in result
    assert result == {"workflowRunId": "run-abc", "status": "COMPLETED"}


# --- _logging emitter passes request_id through redaction unchanged ------------------


def test_emit_preserves_none_request_id(capsys: pytest.CaptureFixture[str]):
    """``request_id=None`` should serialize to JSON null (consumers can distinguish absence)."""
    logging_mod.emit("tool.ok", tool="x", duration_ms=1, request_id=None)
    line = capsys.readouterr().err.strip()
    rec = json.loads(line)
    assert rec["request_id"] is None
