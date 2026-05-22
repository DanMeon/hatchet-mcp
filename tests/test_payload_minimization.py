"""Default-minimal projections on list_runs and list_events.

Both tools now default to `minimal_output=True` (GitHub MCP convention for list_*
tools), dropping the heavy fields the caller would normally not need on a broad
scan. Setting `minimal_output=False` returns the full SDK/REST shape. These tests
pin both directions plus the size-guard preservation.
"""

import copy
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import hatchet_mcp.tools.events as events
import hatchet_mcp.tools.runs as runs

_FULL_RUN_ROW = {
    "taskExternalId": "00000000-0000-0000-0000-000000000001",
    "workflowRunExternalId": "00000000-0000-0000-0000-000000000002",
    "status": "COMPLETED",
    "workflowName": "demo-workflow",
    "startedAt": "2026-05-22T08:00:00Z",
    "finishedAt": "2026-05-22T08:00:05Z",
    "errorMessage": None,
    "parentTaskExternalId": None,
    "numSpawnedChildren": 0,
    # ^ everything below is dropped by minimal_output=True
    "additionalMetadata": {"k": "v" * 100},
    "metadata": {"id": "x", "createdAt": "2026-05-22T08:00:00Z"},
    "displayName": "demo-workflow-display",
    "stepId": "00000000-0000-0000-0000-000000000003",
    "tenantId": "00000000-0000-0000-0000-000000000004",
    "workflowId": "00000000-0000-0000-0000-000000000005",
    "workflowVersionId": "00000000-0000-0000-0000-000000000006",
    "taskInsertedAt": "2026-05-22T08:00:00Z",
    "createdAt": "2026-05-22T08:00:00Z",
    "actionId": "demo:action",
    "input": {"big": "payload"},
    "output": {"big": "result"},
}

_RUN_MINIMAL_KEYS = {
    "taskExternalId",
    "workflowRunExternalId",
    "status",
    "workflowName",
    "startedAt",
    "finishedAt",
    "errorMessage",
    "parentTaskExternalId",
    "numSpawnedChildren",
}


def _mock_list_response(rows: list[dict[str, Any]]) -> MagicMock:
    """Stub an SDK model whose `.model_dump(mode='json', by_alias=True)` returns this shape.

    Uses deepcopy so that `row.pop(...)` in one tool invocation does not mutate the
    shared module-level fixture across tests.
    """
    result = MagicMock()
    result.model_dump.return_value = {
        "rows": [copy.deepcopy(r) for r in rows],
        "pagination": None,
    }
    return result


# * list_runs — minimal_output projection (default True)


async def test_list_runs_default_is_minimal(monkeypatch):
    """Default behavior dropped the heavy fields without any opt-in."""
    hatchet = MagicMock()
    hatchet.runs.aio_list = AsyncMock(return_value=_mock_list_response([_FULL_RUN_ROW]))
    monkeypatch.setattr(runs, "get_hatchet", lambda: hatchet)

    result = await runs.list_runs()

    row = result["rows"][0]
    assert set(row.keys()) == _RUN_MINIMAL_KEYS
    assert "additionalMetadata" not in row
    assert "metadata" not in row
    assert "input" not in row
    assert "output" not in row


async def test_list_runs_minimal_output_false_returns_full_rows(monkeypatch):
    """Explicit opt-out restores the full SDK row."""
    hatchet = MagicMock()
    hatchet.runs.aio_list = AsyncMock(return_value=_mock_list_response([_FULL_RUN_ROW]))
    monkeypatch.setattr(runs, "get_hatchet", lambda: hatchet)

    result = await runs.list_runs(minimal_output=False)

    row = result["rows"][0]
    assert "additionalMetadata" in row
    assert "metadata" in row
    assert "input" in row


async def test_list_runs_minimal_preserves_pagination(monkeypatch):
    hatchet = MagicMock()
    response = MagicMock()
    response.model_dump.return_value = {
        "rows": [_FULL_RUN_ROW],
        "pagination": {"currentPage": 1, "numPages": 5},
    }
    hatchet.runs.aio_list = AsyncMock(return_value=response)
    monkeypatch.setattr(runs, "get_hatchet", lambda: hatchet)

    result = await runs.list_runs()

    assert result["pagination"] == {"currentPage": 1, "numPages": 5}


async def test_list_runs_minimal_path_still_size_guarded(monkeypatch):
    """The minimal-projection bypass must keep `_guard_size` in front of the response.

    A future refactor that returned the filtered dict directly (skipping the guard)
    would silently re-open the 500KB overflow risk this whole change is about.
    """
    hatchet = MagicMock()
    hatchet.runs.aio_list = AsyncMock(return_value=_mock_list_response([_FULL_RUN_ROW]))
    monkeypatch.setattr(runs, "get_hatchet", lambda: hatchet)

    calls: list[dict[str, Any]] = []
    orig = runs._guard_size

    def spy(data: dict[str, Any]) -> dict[str, Any]:
        calls.append(data)
        return orig(data)

    monkeypatch.setattr(runs, "_guard_size", spy)

    await runs.list_runs()

    assert len(calls) == 1


# * list_events — minimal_output projection (default True)


_FULL_EVENT_ROW = {
    "metadata": {"id": "evt-1", "createdAt": "2026-05-22T08:00:00Z"},
    "key": "demo:event",
    "tenantId": "00000000-0000-0000-0000-000000000001",
    "workflowRunSummary": {"queuedCount": 0, "runningCount": 0},
    "additionalMetadata": {"k": "v"},
    "payload": {"big": "payload"},
    "scope": "default",
    "seenAt": "2026-05-22T08:00:00Z",
    "triggeredRuns": [
        {"workflowRunId": "00000000-0000-0000-0000-000000000002", "status": "QUEUED"}
    ],
}


def _patch_rest_call_with_event_api(monkeypatch, api):
    monkeypatch.setattr(events, "EventApi", lambda _client: api)

    async def fake_rest_call(call: Any) -> Any:
        return call(object(), "tenant-id")

    monkeypatch.setattr(events, "_rest_call", fake_rest_call)


async def test_list_events_default_drops_heavy_fields(monkeypatch):
    api = MagicMock()
    api.v1_event_list = MagicMock(return_value=_mock_list_response([_FULL_EVENT_ROW]))
    _patch_rest_call_with_event_api(monkeypatch, api)

    result = await events.list_events()

    row = result["rows"][0]
    assert "payload" not in row
    assert "triggeredRuns" not in row
    assert "additionalMetadata" not in row
    # ^ orientation fields preserved
    assert row["key"] == "demo:event"
    assert row["scope"] == "default"
    assert row["seenAt"] == "2026-05-22T08:00:00Z"


async def test_list_events_minimal_output_false_returns_full_row(monkeypatch):
    api = MagicMock()
    api.v1_event_list = MagicMock(return_value=_mock_list_response([_FULL_EVENT_ROW]))
    _patch_rest_call_with_event_api(monkeypatch, api)

    result = await events.list_events(minimal_output=False)

    row = result["rows"][0]
    assert "payload" in row
    assert "triggeredRuns" in row
    assert "additionalMetadata" in row


async def test_list_events_minimal_path_still_size_guarded(monkeypatch):
    api = MagicMock()
    api.v1_event_list = MagicMock(return_value=_mock_list_response([_FULL_EVENT_ROW]))
    _patch_rest_call_with_event_api(monkeypatch, api)

    calls: list[dict[str, Any]] = []
    orig = events._guard_size

    def spy(data: dict[str, Any]) -> dict[str, Any]:
        calls.append(data)
        return orig(data)

    monkeypatch.setattr(events, "_guard_size", spy)

    await events.list_events()

    assert len(calls) == 1
