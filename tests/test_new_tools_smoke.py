"""Smoke tests for v0.4.0 new tools.

One happy-path test per new handler so a typo, import error, or wrong SDK arg surfaces
in CI. Deeper behavior tests (edge cases, error paths) are intentionally left to
follow-up files per domain.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import hatchet_mcp.tools.events as events_mod
import hatchet_mcp.tools.meta as meta_mod
import hatchet_mcp.tools.observability as observability_mod
import hatchet_mcp.tools.runs as runs_mod
import hatchet_mcp.tools.schedules as schedules_mod
import hatchet_mcp.tools.tasks as tasks_mod
import hatchet_mcp.tools.webhooks as webhooks_mod
import hatchet_mcp.tools.workflows as workflows_mod


def _pyd_with_dump(payload: dict[str, Any]) -> MagicMock:
    """Helper: a MagicMock that pretends to be a Pydantic model with ``model_dump``."""
    obj = MagicMock()
    obj.model_dump.return_value = payload
    return obj


# --- workflows.get_workflow_version / get_workflow_metrics ----------------------------


async def test_get_workflow_version(monkeypatch: pytest.MonkeyPatch):
    fake = MagicMock()
    fake.workflows.aio_get_version = AsyncMock(
        return_value=_pyd_with_dump({"versionId": "v-1", "version": "1.0.0"})
    )
    monkeypatch.setattr(workflows_mod, "get_hatchet", lambda: fake)
    result = await workflows_mod.get_workflow_version("wf-1", version=None)
    assert result == {"versionId": "v-1", "version": "1.0.0"}
    fake.workflows.aio_get_version.assert_awaited_once_with("wf-1", version=None)


async def test_get_workflow_metrics(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    async def fake_rest_call(call):
        client = MagicMock()
        api_response = _pyd_with_dump({"totalRuns": 10, "totalSuccesses": 8})

        # Capture the WorkflowApi kwargs the lambda passes through.
        class CapturingWorkflowApi:
            def __init__(self, _c):
                pass

            def workflow_get_metrics(self, **kw):
                captured.update(kw)
                return api_response

        monkeypatch.setattr(workflows_mod, "WorkflowApi", CapturingWorkflowApi)
        return call(client, "tenant-x")

    monkeypatch.setattr(workflows_mod, "_rest_call", fake_rest_call)
    result = await workflows_mod.get_workflow_metrics(
        "wf-1", status=None, group_key=None
    )
    assert result == {"totalRuns": 10, "totalSuccesses": 8}
    assert captured["workflow"] == "wf-1"


# --- observability.get_task_stats -----------------------------------------------------


async def test_get_task_stats(monkeypatch: pytest.MonkeyPatch):
    fake = MagicMock()
    fake.metrics.aio_get_task_stats = AsyncMock(
        return_value={
            "action.a": _pyd_with_dump({"count": 5, "p95": 100}),
            "action.b": _pyd_with_dump({"count": 7, "p95": 200}),
        }
    )
    monkeypatch.setattr(observability_mod, "get_hatchet", lambda: fake)
    result = await observability_mod.get_task_stats()
    assert "stats" in result
    assert result["stats"]["action.a"] == {"count": 5, "p95": 100}
    assert result["stats"]["action.b"] == {"count": 7, "p95": 200}


# --- schedules.get_scheduled / bulk_delete_scheduled ----------------------------------


async def test_get_scheduled(monkeypatch: pytest.MonkeyPatch):
    fake = MagicMock()
    fake.scheduled.aio_get = AsyncMock(
        return_value=_pyd_with_dump({"scheduledId": "sch-1"})
    )
    monkeypatch.setattr(schedules_mod, "get_hatchet", lambda: fake)
    result = await schedules_mod.get_scheduled("sch-1")
    assert result == {"scheduledId": "sch-1"}


async def test_bulk_delete_scheduled_dry_run_with_explicit_ids(
    monkeypatch: pytest.MonkeyPatch,
):
    import hatchet_mcp._shared as shared

    monkeypatch.setattr(shared, "_read_only", False)
    fake = MagicMock()
    fake.scheduled.aio_bulk_delete = AsyncMock()
    monkeypatch.setattr(schedules_mod, "get_hatchet", lambda: fake)

    result = await schedules_mod.bulk_delete_scheduled(
        scheduled_ids=["a", "b", "c"], dry_run=True
    )
    assert result["dry_run"] is True
    assert result["executed"] is False
    assert result["matched_count"] == 3
    fake.scheduled.aio_bulk_delete.assert_not_awaited()


async def test_bulk_delete_scheduled_rejects_mixed_inputs(
    monkeypatch: pytest.MonkeyPatch,
):
    import hatchet_mcp._shared as shared

    monkeypatch.setattr(shared, "_read_only", False)
    with pytest.raises(ValueError, match="either scheduled_ids or filter"):
        await schedules_mod.bulk_delete_scheduled(
            scheduled_ids=["a"], workflow_id="wf-1"
        )


# --- tasks.list_dag_tasks -------------------------------------------------------------


async def test_list_dag_tasks(monkeypatch: pytest.MonkeyPatch):
    async def fake_rest_call(call):
        return [
            _pyd_with_dump({"taskId": "t1"}),
            _pyd_with_dump({"taskId": "t2"}),
        ]

    monkeypatch.setattr(tasks_mod, "_rest_call", fake_rest_call)
    result = await tasks_mod.list_dag_tasks(dag_ids=["dag-1"])
    assert result == {"rows": [{"taskId": "t1"}, {"taskId": "t2"}]}


# --- runs.cancel_run / replay_run -----------------------------------------------------


async def test_cancel_run(monkeypatch: pytest.MonkeyPatch):
    import hatchet_mcp._shared as shared

    monkeypatch.setattr(shared, "_read_only", False)
    fake = MagicMock()
    fake.runs.aio_cancel = AsyncMock()
    monkeypatch.setattr(runs_mod, "get_hatchet", lambda: fake)
    result = await runs_mod.cancel_run("run-1")
    assert result == {"action": "cancel", "executed": True, "run_id": "run-1"}
    fake.runs.aio_cancel.assert_awaited_once_with("run-1")


async def test_replay_run(monkeypatch: pytest.MonkeyPatch):
    import hatchet_mcp._shared as shared

    monkeypatch.setattr(shared, "_read_only", False)
    fake = MagicMock()
    fake.runs.aio_replay = AsyncMock()
    monkeypatch.setattr(runs_mod, "get_hatchet", lambda: fake)
    result = await runs_mod.replay_run("run-1")
    assert result == {"action": "replay", "executed": True, "run_id": "run-1"}
    fake.runs.aio_replay.assert_awaited_once_with("run-1")


# --- events.replay_events -------------------------------------------------------------


async def test_replay_events(monkeypatch: pytest.MonkeyPatch):
    import hatchet_mcp._shared as shared

    monkeypatch.setattr(shared, "_read_only", False)
    captured: dict[str, Any] = {}

    async def fake_rest_call(call):
        client = MagicMock()
        response = _pyd_with_dump({"rows": [], "pagination": {}})

        class CapturingEventApi:
            def __init__(self, _c):
                pass

            def event_update_replay(self, **kw):
                captured.update(kw)
                return response

        monkeypatch.setattr(events_mod, "EventApi", CapturingEventApi)
        return call(client, "tenant-x")

    monkeypatch.setattr(events_mod, "_rest_call", fake_rest_call)
    uuid_a = "00000000-0000-0000-0000-000000000001"
    uuid_b = "00000000-0000-0000-0000-000000000002"
    result = await events_mod.replay_events(event_ids=[uuid_a, uuid_b])
    assert result == {"rows": [], "pagination": {}}
    assert captured["tenant"] == "tenant-x"
    assert captured["replay_event_request"].event_ids == [uuid_a, uuid_b]


async def test_replay_events_rejects_empty(server_module):
    """Uses the server_module fixture so _read_only is restored on failure."""
    import hatchet_mcp._shared as shared

    shared._read_only = False
    with pytest.raises(ValueError, match="at least one event ID"):
        await events_mod.replay_events(event_ids=[])


async def test_replay_events_caps_at_500(server_module):
    import hatchet_mcp._shared as shared

    shared._read_only = False
    with pytest.raises(ValueError, match="500-event replay cap"):
        await events_mod.replay_events(event_ids=["e"] * 501)


# --- webhooks.list_webhooks / get_webhook ---------------------------------------------


async def test_list_webhooks(monkeypatch: pytest.MonkeyPatch):
    fake = MagicMock()
    fake.webhooks.aio_list = AsyncMock(
        return_value=_pyd_with_dump({"rows": [], "pagination": {}})
    )
    monkeypatch.setattr(webhooks_mod, "get_hatchet", lambda: fake)
    result = await webhooks_mod.list_webhooks(
        webhook_names=None, source_names=None, limit=None, offset=None
    )
    assert result == {"rows": [], "pagination": {}}


async def test_get_webhook(monkeypatch: pytest.MonkeyPatch):
    fake = MagicMock()
    fake.webhooks.aio_get = AsyncMock(
        return_value=_pyd_with_dump({"name": "webhook-1"})
    )
    monkeypatch.setattr(webhooks_mod, "get_hatchet", lambda: fake)
    result = await webhooks_mod.get_webhook("webhook-1")
    assert result == {"name": "webhook-1"}
    fake.webhooks.aio_get.assert_awaited_once_with("webhook-1")


# --- meta.top_failing_workflows / list_stuck_runs / describe_run_failure --------------


async def test_top_failing_workflows(monkeypatch: pytest.MonkeyPatch):
    rows = [
        MagicMock(
            workflow_name="wf-a",
            started_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            finished_at=datetime(2026, 5, 1, 0, 1, tzinfo=timezone.utc),
        ),
        MagicMock(
            workflow_name="wf-a",
            started_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            finished_at=datetime(2026, 5, 1, 0, 2, tzinfo=timezone.utc),
        ),
        MagicMock(
            workflow_name="wf-b",
            started_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            finished_at=datetime(2026, 5, 1, 0, 3, tzinfo=timezone.utc),
        ),
    ]
    sdk_result = MagicMock(rows=rows)
    fake = MagicMock()
    fake.runs.aio_list = AsyncMock(return_value=sdk_result)
    monkeypatch.setattr(meta_mod, "get_hatchet", lambda: fake)

    result = await meta_mod.top_failing_workflows(limit=5)
    assert result["scanned"] == 3
    assert result["rows"][0]["workflowName"] == "wf-a"
    assert result["rows"][0]["failCount"] == 2
    assert result["rows"][1]["workflowName"] == "wf-b"
    assert result["rows"][1]["failCount"] == 1


async def test_list_stuck_runs(monkeypatch: pytest.MonkeyPatch):
    now = datetime.now(timezone.utc)
    old_started = now - timedelta(minutes=45)
    fresh_started = now - timedelta(minutes=5)
    rows = [
        MagicMock(
            workflow_name="wf-stuck",
            workflow_run_external_id="wre-1",
            metadata=MagicMock(id="task-1"),
            started_at=old_started,
        ),
        MagicMock(
            workflow_name="wf-fresh",
            workflow_run_external_id="wre-2",
            metadata=MagicMock(id="task-2"),
            started_at=fresh_started,
        ),
    ]
    fake = MagicMock()
    fake.runs.aio_list = AsyncMock(return_value=MagicMock(rows=rows))
    monkeypatch.setattr(meta_mod, "get_hatchet", lambda: fake)

    result = await meta_mod.list_stuck_runs(stuck_after_minutes=30)
    assert len(result["rows"]) == 1
    assert result["rows"][0]["workflowName"] == "wf-stuck"
    assert result["rows"][0]["elapsedMinutes"] >= 30


async def test_describe_run_failure_no_failed_tasks(monkeypatch: pytest.MonkeyPatch):
    fake = MagicMock()
    details = MagicMock(run=MagicMock(status=MagicMock(value="COMPLETED")), tasks=[])
    fake.runs.aio_get = AsyncMock(return_value=details)
    monkeypatch.setattr(meta_mod, "get_hatchet", lambda: fake)
    result = await meta_mod.describe_run_failure("run-x")
    assert result["failingTask"] is None
    assert result["workflowRunStatus"] == "COMPLETED"


async def test_describe_run_failure_happy_path(monkeypatch: pytest.MonkeyPatch):
    """Failing task → fetch logs + events + timings in parallel → assemble result."""
    from hatchet_sdk.clients.rest.models.v1_task_status import V1TaskStatus

    failed_task = MagicMock(
        status=V1TaskStatus.FAILED,
        metadata=MagicMock(id="task-failing"),
        started_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 5, 1, 0, 5, tzinfo=timezone.utc),
    )
    failed_task.model_dump.return_value = {
        "id": "task-failing",
        "status": "FAILED",
        "errorMessage": "boom",
    }
    details = MagicMock(
        run=MagicMock(status=MagicMock(value="FAILED")), tasks=[failed_task]
    )
    fake = MagicMock()
    fake.runs.aio_get = AsyncMock(return_value=details)
    fake.logs.aio_list = AsyncMock(return_value=_pyd_with_dump({"rows": ["line"]}))
    monkeypatch.setattr(meta_mod, "get_hatchet", lambda: fake)

    call_seq: list[str] = []

    async def fake_rest_call(call):
        # Both REST calls return success; tag them by ordering since both lambdas
        # are structurally similar. asyncio.gather schedules them in source order:
        # events first, timings second.
        idx = len(call_seq)
        call_seq.append("call")
        if idx == 0:
            return _pyd_with_dump({"rows": ["evt"]})
        return _pyd_with_dump({"waterfall": []})

    monkeypatch.setattr(meta_mod, "_rest_call", fake_rest_call)

    result = await meta_mod.describe_run_failure("run-y")
    assert result["workflowRunId"] == "run-y"
    assert result["workflowRunStatus"] == "FAILED"
    assert result["failingTask"]["id"] == "task-failing"
    assert result["logs"] == {"rows": ["line"]}
    assert result["events"] == {"rows": ["evt"]}
    assert result["timings"] == {"waterfall": []}
    assert len(call_seq) == 2
