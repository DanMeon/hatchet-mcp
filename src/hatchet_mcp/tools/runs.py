"""Workflow/task runs: list/get/status (read), plus trigger and bulk cancel/replay (mutating).

Bulk cancel/replay share ``_resolve_and_bulk``: it resolves the target run IDs (explicit or
by filter), enforces a 500-run cap, and returns a dry-run preview unless ``dry_run`` is false.
"""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from hatchet_sdk.clients.rest.api.workflow_runs_api import WorkflowRunsApi
from hatchet_sdk.clients.rest.exceptions import ApiException
from hatchet_sdk.clients.v1.api_client import maybe_additional_metadata_to_kv
from hatchet_sdk.features.runs import BulkCancelReplayOpts
from mcp.types import ToolAnnotations
from pydantic import Field

from hatchet_mcp._shared import (
    _api_error,
    _clamp_limit,
    _destructive,
    _dump,
    _dump_item,
    _parse_dt,
    _parse_statuses,
    _require_writable,
    _rest_call,
)
from hatchet_mcp.client import get_hatchet

_BULK_LIMIT = 500


async def list_runs(
    since: Annotated[
        str | None,
        Field(
            description="ISO 8601 start time, e.g. '2026-05-19T00:00:00Z'. Defaults to 24h ago."
        ),
    ] = None,
    until: Annotated[
        str | None, Field(description="ISO 8601 end time. Defaults to now.")
    ] = None,
    statuses: Annotated[
        list[str] | None,
        Field(
            description="Filter by v1 statuses: QUEUED, RUNNING, COMPLETED, CANCELLED, FAILED."
        ),
    ] = None,
    workflow_ids: Annotated[
        list[str] | None, Field(description="Filter by one or more workflow IDs.")
    ] = None,
    worker_id: Annotated[
        str | None, Field(description="Only runs handled by this worker ID.")
    ] = None,
    additional_metadata: Annotated[
        dict[str, str] | None,
        Field(description="Filter by run additional-metadata key/values."),
    ] = None,
    only_tasks: Annotated[
        bool,
        Field(
            description="Only individual task runs rather than top-level workflow runs."
        ),
    ] = False,
    include_payloads: Annotated[
        bool,
        Field(
            description="Include each run's input/output payloads. Default false to keep the "
            "response small — use get_run for one run's payloads, or set true with a small limit."
        ),
    ] = False,
    limit: Annotated[
        int | None, Field(description="Max runs to return (default 50, max 100).")
    ] = None,
    offset: Annotated[int | None, Field(description="Pagination offset.")] = None,
) -> dict[str, Any]:
    h = get_hatchet()
    try:
        result = await h.runs.aio_list(
            since=_parse_dt(since, field="since"),
            until=_parse_dt(until, field="until"),
            statuses=_parse_statuses(statuses),
            workflow_ids=workflow_ids,
            worker_id=worker_id,
            additional_metadata=additional_metadata,
            only_tasks=only_tasks,
            include_payloads=include_payloads,
            limit=_clamp_limit(limit),
            offset=offset,
        )
    except ApiException as exc:
        raise _api_error(exc) from None
    return _dump(result)


async def get_run(
    workflow_run_id: Annotated[
        str, Field(description="The workflow run external ID (UUID).")
    ],
) -> dict[str, Any]:
    h = get_hatchet()
    try:
        result = await h.runs.aio_get(workflow_run_id)
    except ApiException as exc:
        raise _api_error(exc) from None
    return _dump_item(result)


async def get_run_status(
    workflow_run_id: Annotated[
        str, Field(description="The workflow run external ID (UUID).")
    ],
) -> dict[str, Any]:
    h = get_hatchet()
    try:
        status = await h.runs.aio_get_status(workflow_run_id)
    except ApiException as exc:
        raise _api_error(exc) from None
    return {"workflow_run_id": workflow_run_id, "status": status.value}


async def trigger_workflow(
    workflow_name: Annotated[
        str, Field(description="The name of the workflow to trigger.")
    ],
    input: Annotated[
        dict[str, Any] | None,
        Field(description="Input payload for the run. Defaults to an empty object."),
    ] = None,
    additional_metadata: Annotated[
        dict[str, str] | None,
        Field(description="Additional metadata to attach to the run."),
    ] = None,
    priority: Annotated[
        int | None, Field(description="Run priority (1=low, 2=medium, 3=high).")
    ] = None,
) -> dict[str, Any]:
    _require_writable()
    h = get_hatchet()
    try:
        result = await h.runs.aio_create(
            workflow_name=workflow_name,
            input=input or {},
            additional_metadata=additional_metadata,
            priority=priority,
        )
    except ApiException as exc:
        raise _api_error(exc) from None
    return _dump(result)


async def _resolve_and_bulk(
    *,
    action: Literal["cancel", "replay"],
    run_ids: list[str] | None,
    since: str | None,
    until: str | None,
    statuses: list[str] | None,
    workflow_ids: list[str] | None,
    additional_metadata: dict[str, str] | None,
    dry_run: bool,
) -> dict[str, Any]:
    """Shared cancel/replay logic: resolve targets, enforce the 500 cap, preview unless dry_run is false."""
    _require_writable()

    has_filter = any(
        v is not None
        for v in (since, until, statuses, workflow_ids, additional_metadata)
    )
    if run_ids and has_filter:
        raise ValueError(
            "Provide either run_ids or filter parameters "
            "(since/until/statuses/workflow_ids/additional_metadata), not both."
        )
    if not run_ids and not has_filter:
        raise ValueError(
            "Provide run_ids, or at least one filter parameter "
            "(since/until/statuses/workflow_ids/additional_metadata)."
        )

    if run_ids:
        target_ids = list(run_ids)
    else:
        until_dt = _parse_dt(until, field="until") or datetime.now(timezone.utc)
        since_dt = _parse_dt(since, field="since") or (until_dt - timedelta(days=1))
        status_enums = _parse_statuses(statuses)
        metadata_kv = maybe_additional_metadata_to_kv(additional_metadata)
        try:
            target_ids = await _rest_call(
                lambda client, tenant: WorkflowRunsApi(
                    client
                ).v1_workflow_run_external_ids_list(
                    tenant=tenant,
                    since=since_dt,
                    until=until_dt,
                    statuses=status_enums,
                    workflow_ids=workflow_ids,
                    additional_metadata=metadata_kv,
                )
            )
        except ApiException as exc:
            raise _api_error(exc) from None

    matched = len(target_ids)
    if matched > _BULK_LIMIT:
        how_to_narrow = (
            "Pass fewer run_ids"
            if run_ids
            else "Narrow the filter (tighter time window, specific statuses or workflow_ids)"
        )
        raise ValueError(
            f"{matched} runs exceed the {_BULK_LIMIT}-run bulk cap. {how_to_narrow} and retry."
        )
    if matched == 0:
        return {
            "action": action,
            "dry_run": dry_run,
            "executed": False,
            "matched_count": 0,
            "run_ids": [],
            "note": "No runs matched; nothing to do.",
        }
    if dry_run:
        return {
            "action": action,
            "dry_run": True,
            "executed": False,
            "matched_count": matched,
            "run_ids": target_ids,
            "note": (
                f"Dry run — no runs were affected. "
                f"Re-call with dry_run=false to {action} these runs."
            ),
        }

    opts = BulkCancelReplayOpts(ids=target_ids)
    try:
        if action == "cancel":
            await get_hatchet().runs.aio_bulk_cancel(opts)
        else:
            await get_hatchet().runs.aio_bulk_replay(opts)
    except ApiException as exc:
        raise _api_error(exc) from None
    return {
        "action": action,
        "dry_run": False,
        "executed": True,
        "matched_count": matched,
        "run_ids": target_ids,
    }


async def cancel_runs(
    run_ids: Annotated[
        list[str] | None,
        Field(
            description="Explicit run/task external IDs to cancel. Mutually exclusive with the filter parameters."
        ),
    ] = None,
    since: Annotated[
        str | None,
        Field(
            description="Filter mode: ISO 8601 lower bound on run time. Defaults to 24h before `until`."
        ),
    ] = None,
    until: Annotated[
        str | None,
        Field(
            description="Filter mode: ISO 8601 upper bound on run time. Defaults to now."
        ),
    ] = None,
    statuses: Annotated[
        list[str] | None,
        Field(
            description="Filter mode: v1 statuses (QUEUED, RUNNING, COMPLETED, CANCELLED, FAILED)."
        ),
    ] = None,
    workflow_ids: Annotated[
        list[str] | None,
        Field(description="Filter mode: restrict to these workflow IDs."),
    ] = None,
    additional_metadata: Annotated[
        dict[str, str] | None,
        Field(description="Filter mode: match run additional-metadata key/values."),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(
            description="When true (default), return the matching run IDs WITHOUT cancelling. Set false to actually cancel."
        ),
    ] = True,
) -> dict[str, Any]:
    return await _resolve_and_bulk(
        action="cancel",
        run_ids=run_ids,
        since=since,
        until=until,
        statuses=statuses,
        workflow_ids=workflow_ids,
        additional_metadata=additional_metadata,
        dry_run=dry_run,
    )


async def replay_runs(
    run_ids: Annotated[
        list[str] | None,
        Field(
            description="Explicit run/task external IDs to replay. Mutually exclusive with the filter parameters."
        ),
    ] = None,
    since: Annotated[
        str | None,
        Field(
            description="Filter mode: ISO 8601 lower bound on run time. Defaults to 24h before `until`."
        ),
    ] = None,
    until: Annotated[
        str | None,
        Field(
            description="Filter mode: ISO 8601 upper bound on run time. Defaults to now."
        ),
    ] = None,
    statuses: Annotated[
        list[str] | None,
        Field(
            description="Filter mode: v1 statuses (QUEUED, RUNNING, COMPLETED, CANCELLED, FAILED)."
        ),
    ] = None,
    workflow_ids: Annotated[
        list[str] | None,
        Field(description="Filter mode: restrict to these workflow IDs."),
    ] = None,
    additional_metadata: Annotated[
        dict[str, str] | None,
        Field(description="Filter mode: match run additional-metadata key/values."),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(
            description="When true (default), return the matching run IDs WITHOUT replaying. Set false to actually replay."
        ),
    ] = True,
) -> dict[str, Any]:
    return await _resolve_and_bulk(
        action="replay",
        run_ids=run_ids,
        since=since,
        until=until,
        statuses=statuses,
        workflow_ids=workflow_ids,
        additional_metadata=additional_metadata,
        dry_run=dry_run,
    )


READ_TOOLS: list[tuple[Callable[..., Any], str, str]] = [
    (
        list_runs,
        "list_runs",
        "List workflow/task runs filtered by time, status, workflow, worker, or metadata. "
        "Defaults to the last 24h. Status values are v1: QUEUED/RUNNING/COMPLETED/CANCELLED/FAILED.",
    ),
    (
        get_run,
        "get_run",
        "Get full details of a workflow run by ID: task tree / DAG shape, inputs, outputs.",
    ),
    (
        get_run_status,
        "get_run_status",
        "Get only the status of a workflow run (lightweight polling). "
        "Returns a v1 value: QUEUED, RUNNING, COMPLETED, CANCELLED, or FAILED.",
    ),
]

MUTATING_TOOLS: list[tuple[Callable[..., Any], str, str, ToolAnnotations]] = [
    (
        trigger_workflow,
        "trigger_workflow",
        "Trigger a new workflow run by workflow name with an input payload. Returns the run details.",
        _destructive(idempotent=False),
    ),
    (
        cancel_runs,
        "cancel_runs",
        "Cancel runs/tasks by explicit IDs or by filter. Defaults to a dry-run preview (returns matching "
        "IDs without cancelling); set dry_run=false to cancel. Refuses to act on more than 500 matching runs.",
        _destructive(idempotent=False),
    ),
    (
        replay_runs,
        "replay_runs",
        "Replay (re-run) runs/tasks by explicit IDs or by filter. Defaults to a dry-run preview (returns "
        "matching IDs without replaying); set dry_run=false to replay. Refuses to act on more than 500 matching runs.",
        _destructive(idempotent=False),
    ),
]
