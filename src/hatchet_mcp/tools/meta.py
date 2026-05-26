"""Meta-tools: thin aggregation/composition over existing read tools.

These don't call any new Hatchet endpoint — they exist because LLMs ask the same
operational questions over and over ("what's failing the most?", "what's stuck?",
"why did this run fail?") and answering each in raw list_runs / get_run / get_task
calls eats round-trips and context. Each meta tool collapses a common 3-5-call
sequence into one structured response.
"""

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated, Any

from hatchet_sdk.clients.rest.api.task_api import TaskApi
from hatchet_sdk.clients.rest.api.workflow_runs_api import WorkflowRunsApi
from hatchet_sdk.clients.rest.exceptions import ApiException
from hatchet_sdk.clients.rest.models.v1_task_status import V1TaskStatus
from hatchet_sdk.clients.rest.models.v1_task_summary import V1TaskSummary
from hatchet_sdk.clients.rest.models.v1_workflow_run_details import V1WorkflowRunDetails
from mcp.types import ToolAnnotations
from pydantic import Field

from hatchet_mcp._shared import (
    HatchetAPIError,
    _clamp_limit,
    _guard_size,
    _parse_dt,
    _rest_call,
)
from hatchet_mcp.client import get_hatchet


async def top_failing_workflows(
    since: Annotated[
        str | None,
        Field(
            description="ISO 8601 start time, e.g. '2026-05-19T00:00:00Z'. Defaults to 24h ago."
        ),
    ] = None,
    until: Annotated[
        str | None, Field(description="ISO 8601 end time. Defaults to now.")
    ] = None,
    workflow_ids: Annotated[
        list[str] | None,
        Field(description="Optional restriction to these workflow IDs."),
    ] = None,
    limit: Annotated[
        int | None,
        Field(description="Max rows in the ranking (default 10, max 50)."),
    ] = None,
    scan_limit: Annotated[
        int | None,
        Field(
            description="Max FAILED runs to scan when building the ranking. Default 500, max 1000. "
            "If actual failures exceed this, the count is a lower bound (set ``truncated=true``)."
        ),
    ] = None,
) -> dict[str, Any]:
    """Rank workflows by failure count in a window, single call vs paginating list_runs manually.

    Internally calls list_runs(statuses=["FAILED"]) once with a large scan limit, groups by
    workflowName, and returns the top N. No new Hatchet endpoint — pure aggregation over
    runs.aio_list to save the LLM from doing the same in its context.
    """
    h = get_hatchet()
    top_n = _clamp_limit(limit, default=10, cap=50)
    scan = _clamp_limit(scan_limit, default=500, cap=1000)
    result = await h.runs.aio_list(
        since=_parse_dt(since, field="since"),
        until=_parse_dt(until, field="until"),
        statuses=[V1TaskStatus.FAILED],
        workflow_ids=workflow_ids,
        include_payloads=False,
        limit=scan,
        offset=0,
    )
    rows: list[V1TaskSummary] = list(result.rows or [])
    counts: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = row.workflow_name or "<unknown>"
        entry = counts.setdefault(
            name,
            {"workflowName": name, "failCount": 0, "lastFailureAt": None},
        )
        entry["failCount"] += 1
        finished = row.finished_at or row.started_at
        if finished is not None:
            iso_finished = finished.isoformat()
            if entry["lastFailureAt"] is None or iso_finished > entry["lastFailureAt"]:
                entry["lastFailureAt"] = iso_finished
    ranking = sorted(
        counts.values(), key=lambda r: (r["failCount"], r["workflowName"]), reverse=True
    )[:top_n]
    return _guard_size(
        {
            "rows": ranking,
            "scanned": len(rows),
            "truncated": len(rows) >= scan,
        }
    )


async def list_stuck_runs(
    stuck_after_minutes: Annotated[
        int,
        Field(
            description="Threshold in minutes. Runs in RUNNING state with started_at older "
            "than now - threshold are considered stuck. Default 30."
        ),
    ] = 30,
    workflow_ids: Annotated[
        list[str] | None,
        Field(description="Optional restriction to these workflow IDs."),
    ] = None,
    limit: Annotated[
        int | None,
        Field(description="Max stuck runs to return (default 50, max 100)."),
    ] = None,
    scan_limit: Annotated[
        int | None,
        Field(description="Max RUNNING runs to scan. Default 500, max 1000."),
    ] = None,
) -> dict[str, Any]:
    """Identify runs in RUNNING state longer than ``stuck_after_minutes``, single call.

    Hatchet has no native "stuck" predicate; this scans list_runs(RUNNING) and filters
    client-side by elapsed time. Returns the runs that exceeded the threshold along with
    each one's elapsed minutes, so the LLM doesn't have to do the time arithmetic per row.
    """
    if stuck_after_minutes < 0:
        raise ValueError(
            f"stuck_after_minutes must be >= 0; got {stuck_after_minutes!r}"
        )
    h = get_hatchet()
    out_limit = _clamp_limit(limit, default=50, cap=100)
    scan = _clamp_limit(scan_limit, default=500, cap=1000)
    result = await h.runs.aio_list(
        statuses=[V1TaskStatus.RUNNING],
        workflow_ids=workflow_ids,
        include_payloads=False,
        limit=scan,
        offset=0,
    )
    now = datetime.now(timezone.utc)
    stuck: list[dict[str, Any]] = []
    for row in result.rows or []:
        started = row.started_at
        if started is None:
            continue
        elapsed_min = (now - started).total_seconds() / 60.0
        if elapsed_min < stuck_after_minutes:
            continue
        stuck.append(
            {
                "taskExternalId": row.metadata.id if row.metadata else None,
                "workflowRunExternalId": row.workflow_run_external_id,
                "workflowName": row.workflow_name,
                "startedAt": started.isoformat(),
                "elapsedMinutes": round(elapsed_min, 1),
            }
        )
    stuck.sort(key=lambda r: r["elapsedMinutes"], reverse=True)
    return _guard_size(
        {
            "rows": stuck[:out_limit],
            "stuckAfterMinutes": stuck_after_minutes,
            "scanned": len(result.rows or []),
            "truncated": len(result.rows or []) >= scan,
        }
    )


_EPOCH_UTC = datetime.min.replace(tzinfo=timezone.utc)


def _find_failing_task(details: V1WorkflowRunDetails) -> V1TaskSummary | None:
    """Pick the most informative failed leaf task from a workflow run's task tree, if any.

    Sort key falls back to ``_EPOCH_UTC`` (tz-aware) when both ``finished_at`` and
    ``started_at`` are None — mixing naive ``datetime.min`` with the SDK's tz-aware
    UTC timestamps raises ``TypeError`` in ``sorted``.
    """
    candidates = [t for t in (details.tasks or []) if t.status == V1TaskStatus.FAILED]
    if not candidates:
        return None
    candidates.sort(
        key=lambda t: t.finished_at or t.started_at or _EPOCH_UTC,
        reverse=True,
    )
    return candidates[0]


async def describe_run_failure(
    workflow_run_id: Annotated[
        str,
        Field(description="The workflow run external ID (UUID) to diagnose."),
    ],
    log_tail: Annotated[
        int,
        Field(
            description="Number of recent log lines from the failing task to include. "
            "Default 200, max 1000."
        ),
    ] = 200,
) -> dict[str, Any]:
    """One-call failure diagnostic: run summary + failing task + last log lines + event timeline.

    Replaces the common 4-call sequence (get_run → get_run_timings → get_task → get_task_logs
    → list_task_events). The LLM saves round-trips and gets a single structured payload.
    """
    log_lines = _clamp_limit(log_tail, default=200, cap=1000)
    h = get_hatchet()
    details: V1WorkflowRunDetails = await h.runs.aio_get(workflow_run_id)

    failing = _find_failing_task(details)
    if failing is None:
        return {
            "workflowRunId": workflow_run_id,
            "workflowRunStatus": (details.run.status.value if details.run else None),
            "failingTask": None,
            "note": "No FAILED task found in this run.",
        }

    failing_task_id = failing.metadata.id if failing.metadata else None
    if failing_task_id is None:
        return {
            "workflowRunId": workflow_run_id,
            "workflowRunStatus": (details.run.status.value if details.run else None),
            "failingTask": failing.model_dump(mode="json", by_alias=True),
            "note": "Failing task has no external ID; cannot fetch logs/events.",
        }

    # Three independent reads → run in parallel; timings is best-effort and may fail
    # transiently (HatchetAPIError) or hit the per-call deadline (asyncio.TimeoutError).
    # Logs and events are required for the diagnostic, so their exceptions propagate.
    logs, events, timings_result = await asyncio.gather(
        h.logs.aio_list(task_run_id=failing_task_id, limit=log_lines),
        _rest_call(
            lambda client, _tenant: TaskApi(client).v1_task_event_list(
                task=failing_task_id, limit=50
            )
        ),
        _rest_call(
            lambda client, _tenant: WorkflowRunsApi(client).v1_workflow_run_get_timings(
                v1_workflow_run=workflow_run_id
            )
        ),
        return_exceptions=True,
    )
    if isinstance(logs, BaseException):
        raise logs
    if isinstance(events, BaseException):
        raise events
    timings: dict[str, Any] | None
    if isinstance(
        timings_result, (ApiException, HatchetAPIError, asyncio.TimeoutError)
    ):
        timings = None
    elif isinstance(timings_result, BaseException):
        raise timings_result
    else:
        timings = timings_result.model_dump(mode="json", by_alias=True)

    return _guard_size(
        {
            "workflowRunId": workflow_run_id,
            "workflowRunStatus": (details.run.status.value if details.run else None),
            "failingTask": failing.model_dump(mode="json", by_alias=True),
            "logs": logs.model_dump(mode="json", by_alias=True),
            "events": events.model_dump(mode="json", by_alias=True),
            "timings": timings,
        }
    )


READ_TOOLS: list[tuple[Callable[..., Any], str, str]] = [
    (
        top_failing_workflows,
        "top_failing_workflows",
        "Rank workflows by failure count in a time window. Single call vs paginating "
        "list_runs(FAILED) manually. Defaults to the last 24h, top 10. "
        "Returns rows of {workflowName, failCount, lastFailureAt}, plus scanned/truncated flags.",
    ),
    (
        list_stuck_runs,
        "list_stuck_runs",
        "List runs in RUNNING state for longer than ``stuck_after_minutes`` (default 30). "
        "Computes elapsed minutes client-side from list_runs(RUNNING) — Hatchet has no native "
        "stuck predicate. Useful for oncall triage of hung jobs.",
    ),
    (
        describe_run_failure,
        "describe_run_failure",
        "One-call failure diagnostic for a workflow run: returns the run summary, the most "
        "recently-failed leaf task, its last log lines (default 200), its event timeline, and "
        "the run-timings waterfall. Replaces the get_run→get_task→get_task_logs→list_task_events "
        "chain for the most common 'why did this run fail?' question.",
    ),
]


MUTATING_TOOLS: list[tuple[Callable[..., Any], str, str, ToolAnnotations]] = []
