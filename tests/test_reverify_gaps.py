"""Tests for gaps found in the v0.4.0 re-verification pass.

Each test pins a bug or weak-assertion site flagged by the fresh-context review:
- C-1: describe_run_failure crashed on tasks with no timestamps (datetime.min was naive)
- C-1 sibling: timings failure must demote to None, not bubble (M2 fix)
- H4 wiring: FastMCP must detect ctx on the wrapped cancel_runs / replay_runs / bulk_delete_scheduled
- meta.py Python-attr contract: SDK rename of snake_case attributes would crash at runtime
- get_workflow_metrics: status / group_key must reach the SDK
- list_dag_tasks: SDK kwargs are actually exercised
- bulk_delete_scheduled filter-mode: kwarg-only wiring exercised end to end
- HatchetAPIError: 400/401/403/409/422 mapped (only 404/429/503/418 were tested)
- ReplayEventRequest: eventIds alias still mapped to event_ids
- get_api_client: returns the same instance under asyncio.gather concurrency
- _read_only_annotations: returns a fresh instance per call (no shared mutable singleton)
"""

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from hatchet_sdk.clients.rest.exceptions import ApiException
from hatchet_sdk.clients.rest.models.replay_event_request import ReplayEventRequest
from hatchet_sdk.clients.rest.models.v1_event import V1Event
from hatchet_sdk.clients.rest.models.v1_task_status import V1TaskStatus
from hatchet_sdk.clients.rest.models.v1_task_summary import V1TaskSummary
from hatchet_sdk.clients.rest.models.v1_workflow_run_details import V1WorkflowRunDetails

import hatchet_mcp._shared as shared
import hatchet_mcp.client as client_mod
import hatchet_mcp.tools.meta as meta_mod
import hatchet_mcp.tools.schedules as schedules_mod
import hatchet_mcp.tools.tasks as tasks_mod
import hatchet_mcp.tools.workflows as workflows_mod


def _pyd_with_dump(payload: dict[str, Any]) -> MagicMock:
    obj = MagicMock()
    obj.model_dump.return_value = payload
    return obj


# -------- C-1: describe_run_failure with no-timestamps failing task --------------------


async def test_describe_run_failure_no_timestamps_does_not_crash(
    monkeypatch: pytest.MonkeyPatch,
):
    """A FAILED task with finished_at=None and started_at=None must not raise TypeError."""
    failed_no_ts = MagicMock(
        status=V1TaskStatus.FAILED,
        metadata=MagicMock(id="task-failing"),
        started_at=None,
        finished_at=None,
    )
    failed_no_ts.model_dump.return_value = {"id": "task-failing", "status": "FAILED"}
    details = MagicMock(
        run=MagicMock(status=MagicMock(value="FAILED")), tasks=[failed_no_ts]
    )
    fake = MagicMock()
    fake.runs.aio_get = AsyncMock(return_value=details)
    fake.logs.aio_list = AsyncMock(return_value=_pyd_with_dump({"rows": []}))
    monkeypatch.setattr(meta_mod, "get_hatchet", lambda: fake)

    async def fake_rest_call(call):
        return _pyd_with_dump({})

    monkeypatch.setattr(meta_mod, "_rest_call", fake_rest_call)

    result = await meta_mod.describe_run_failure("run-z")
    assert result["failingTask"]["id"] == "task-failing"


async def test_describe_run_failure_timings_error_demotes_to_none(
    monkeypatch: pytest.MonkeyPatch,
):
    """If the timings REST call raises HatchetAPIError, timings is None and the call succeeds."""
    failed = MagicMock(
        status=V1TaskStatus.FAILED,
        metadata=MagicMock(id="task-failing"),
        started_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 5, 1, 0, 5, tzinfo=timezone.utc),
    )
    failed.model_dump.return_value = {"id": "task-failing", "status": "FAILED"}
    details = MagicMock(run=MagicMock(status=MagicMock(value="FAILED")), tasks=[failed])
    fake = MagicMock()
    fake.runs.aio_get = AsyncMock(return_value=details)
    fake.logs.aio_list = AsyncMock(return_value=_pyd_with_dump({"rows": ["log"]}))
    monkeypatch.setattr(meta_mod, "get_hatchet", lambda: fake)

    call_count = 0

    async def fake_rest_call(call):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _pyd_with_dump({"rows": ["evt"]})
        # ^ Second call is timings — make it fail with an API-flavored error.
        raise shared.HatchetAPIError(
            "Hatchet API error: status 503", status=503, kind="server_error"
        )

    monkeypatch.setattr(meta_mod, "_rest_call", fake_rest_call)

    result = await meta_mod.describe_run_failure("run-y")
    assert result["timings"] is None
    assert result["logs"] == {"rows": ["log"]}
    assert result["events"] == {"rows": ["evt"]}


# -------- H4 wiring: FastMCP must see ctx on the wrapped handlers ----------------------


def test_h4_ctx_param_visible_on_wrapped_handlers():
    """FastMCP's find_context_parameter must see ctx on every handler that emits progress."""
    from mcp.server.fastmcp.utilities.context_injection import find_context_parameter

    from hatchet_mcp._shared import _reliability_wrap
    from hatchet_mcp.tools.runs import cancel_runs, replay_runs
    from hatchet_mcp.tools.schedules import bulk_delete_scheduled

    for fn in (cancel_runs, replay_runs, bulk_delete_scheduled):
        wrapped = _reliability_wrap(fn, retry=False)
        ctx_name = find_context_parameter(wrapped)
        assert ctx_name == "ctx", (
            f"{fn.__name__}: FastMCP cannot detect ctx — H4 auto-injection would be a no-op"
        )


# -------- meta.py Python-attribute contract --------------------------------------------


def test_meta_python_attrs_exist_on_v1_task_summary():
    """meta.py accesses these snake_case attributes directly — SDK rename → AttributeError."""
    fields = V1TaskSummary.model_fields
    for attr in [
        "workflow_name",
        "finished_at",
        "started_at",
        "metadata",
        "workflow_run_external_id",
        "status",
    ]:
        assert attr in fields, f"V1TaskSummary.{attr} no longer exists on the SDK model"


def test_meta_python_attrs_exist_on_v1_workflow_run_details():
    """describe_run_failure accesses details.run.status and details.tasks."""
    fields = V1WorkflowRunDetails.model_fields
    for attr in ["run", "tasks"]:
        assert attr in fields, (
            f"V1WorkflowRunDetails.{attr} no longer exists on the SDK model"
        )


def test_replay_event_request_alias_event_ids_maps_to_field():
    """events.replay_events passes ``eventIds=`` (alias). SDK must accept it."""
    fields = ReplayEventRequest.model_fields
    assert "event_ids" in fields, "ReplayEventRequest.event_ids field renamed"
    info = fields["event_ids"]
    assert info.alias == "eventIds", (
        "ReplayEventRequest.event_ids alias is not 'eventIds'"
    )


# -------- get_workflow_metrics: status / group_key kwargs reach the SDK ----------------


async def test_get_workflow_metrics_forwards_status_and_group_key(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, Any] = {}

    async def fake_rest_call(call):
        client = MagicMock()
        api_response = _pyd_with_dump({"totalRuns": 1})

        class CapturingWorkflowApi:
            def __init__(self, _c):
                pass

            def workflow_get_metrics(self, **kw):
                captured.update(kw)
                return api_response

        monkeypatch.setattr(workflows_mod, "WorkflowApi", CapturingWorkflowApi)
        return call(client, "tenant-x")

    monkeypatch.setattr(workflows_mod, "_rest_call", fake_rest_call)
    await workflows_mod.get_workflow_metrics("wf-1", status="FAILED", group_key="key-1")
    assert captured["workflow"] == "wf-1"
    assert captured["group_key"] == "key-1"
    assert captured["status"] is not None
    assert getattr(captured["status"], "value", captured["status"]) == "FAILED"


# -------- list_dag_tasks: SDK kwargs actually exercised --------------------------------


async def test_list_dag_tasks_forwards_dag_ids_and_tenant(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, Any] = {}

    async def fake_rest_call(call):
        client = MagicMock()

        class CapturingTaskApi:
            def __init__(self, _c):
                pass

            def v1_dag_list_tasks(self, **kw):
                captured.update(kw)
                return [_pyd_with_dump({"taskId": "t1"})]

        monkeypatch.setattr(tasks_mod, "TaskApi", CapturingTaskApi)
        return call(client, "tenant-x")

    monkeypatch.setattr(tasks_mod, "_rest_call", fake_rest_call)
    await tasks_mod.list_dag_tasks(dag_ids=["dag-1", "dag-2"])
    assert captured["dag_ids"] == ["dag-1", "dag-2"]
    assert captured["tenant"] == "tenant-x"


# -------- bulk_delete_scheduled filter-mode end-to-end --------------------------------


async def test_bulk_delete_scheduled_filter_mode_dry_run(
    server_module, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(shared, "_read_only", False)
    fake = MagicMock()
    fake.scheduled.aio_bulk_delete = AsyncMock()
    monkeypatch.setattr(schedules_mod, "get_hatchet", lambda: fake)

    result = await schedules_mod.bulk_delete_scheduled(workflow_id="wf-1", dry_run=True)
    assert result["dry_run"] is True
    assert result["matched_count"] is None
    fake.scheduled.aio_bulk_delete.assert_not_awaited()


async def test_bulk_delete_scheduled_filter_mode_executes(
    server_module, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(shared, "_read_only", False)
    fake = MagicMock()
    fake.scheduled.aio_bulk_delete = AsyncMock(
        return_value=_pyd_with_dump({"deleted": 7})
    )
    monkeypatch.setattr(schedules_mod, "get_hatchet", lambda: fake)

    result = await schedules_mod.bulk_delete_scheduled(
        workflow_id="wf-1",
        parent_workflow_run_id="pwr-1",
        dry_run=False,
    )
    assert result == {"deleted": 7}
    fake.scheduled.aio_bulk_delete.assert_awaited_once_with(
        scheduled_ids=None,
        workflow_id="wf-1",
        parent_workflow_run_id="pwr-1",
        parent_step_run_id=None,
        statuses=None,
        additional_metadata=None,
    )


# -------- HatchetAPIError: 400/401/403/409/422 mapping --------------------------------


@pytest.mark.parametrize(
    ("status", "expected_kind"),
    [
        (400, "validation_error"),
        (401, "unauthorized"),
        (403, "unauthorized"),
        (409, "conflict"),
        (422, "validation_error"),
    ],
)
def test_api_error_classifies_remaining_known_statuses(status: int, expected_kind: str):
    err = shared._api_error(ApiException(status=status, reason="r"))
    assert isinstance(err, shared.HatchetAPIError)
    assert err.status == status
    assert err.kind == expected_kind


# -------- C1 concurrency: get_api_client returns the same instance under gather -------


async def test_get_api_client_is_concurrency_safe(monkeypatch: pytest.MonkeyPatch):
    """Multiple asyncio.to_thread workers racing past `if _api_client is None` must build one."""
    monkeypatch.setattr(client_mod, "_api_client", None)
    fake_rest = MagicMock()
    fake_rest.api_config = MagicMock()
    monkeypatch.setattr(client_mod, "get_rest", lambda: fake_rest)
    created: list[Any] = []

    class FakeApiClient:
        def __init__(self, config: Any) -> None:
            created.append(config)

    monkeypatch.setattr(client_mod, "ApiClient", FakeApiClient)

    instances = await asyncio.gather(
        *(asyncio.to_thread(client_mod.get_api_client) for _ in range(10))
    )
    assert len({id(i) for i in instances}) == 1
    assert len(created) == 1


# -------- _read_only_annotations: fresh instance per call -----------------------------


def test_read_only_annotations_returns_fresh_instance():
    """Each call must return a new ToolAnnotations so a stray mutation can't flip every read tool."""
    a = shared._read_only_annotations()
    b = shared._read_only_annotations()
    assert a is not b
    assert a.readOnlyHint is True
    assert b.readOnlyHint is True


# -------- list_stuck_runs negative validation -----------------------------------------


async def test_list_stuck_runs_rejects_negative_threshold():
    with pytest.raises(ValueError, match="stuck_after_minutes must be >= 0"):
        await meta_mod.list_stuck_runs(stuck_after_minutes=-1)


# -------- top_failing_workflows: truncated flag ---------------------------------------


async def test_top_failing_workflows_sets_truncated_flag(
    monkeypatch: pytest.MonkeyPatch,
):
    """When scanned rows == scan_limit, truncated=True (data may be incomplete)."""
    rows = [
        MagicMock(
            workflow_name=f"wf-{i}",
            started_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            finished_at=datetime(2026, 5, 1, 0, i + 1, tzinfo=timezone.utc),
        )
        for i in range(3)
    ]
    sdk_result = MagicMock(rows=rows)
    fake = MagicMock()
    fake.runs.aio_list = AsyncMock(return_value=sdk_result)
    monkeypatch.setattr(meta_mod, "get_hatchet", lambda: fake)

    result = await meta_mod.top_failing_workflows(limit=10, scan_limit=3)
    assert result["truncated"] is True
    assert result["scanned"] == 3


# -------- V1Event field check for replay context --------------------------------------


def test_v1_event_has_expected_top_level_fields():
    """list_events drops three fields by alias; this also pins the V1Event id field path."""
    fields = V1Event.model_fields
    # Just confirm presence of `metadata` (needed for any event-id lookups).
    assert "metadata" in fields
