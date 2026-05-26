"""Tasks: single-task detail, log lines, and event timeline (read), plus restore of an evicted durable task (mutating)."""

from collections.abc import Callable
from typing import Annotated, Any

from hatchet_sdk.clients.rest.api.task_api import TaskApi
from mcp.types import ToolAnnotations
from pydantic import Field

from hatchet_mcp._shared import (
    _clamp_limit,
    _destructive,
    _dump,
    _dump_item,
    _guard_size,
    _parse_dt,
    _require_writable,
    _rest_call,
)
from hatchet_mcp.client import get_hatchet


async def get_task(
    task_run_id: Annotated[str, Field(description="The task run ID (UUID) to fetch.")],
) -> dict[str, Any]:
    h = get_hatchet()
    result = await h.runs.aio_get_task_run(task_run_id)
    return _dump_item(result)


async def get_task_logs(
    task_run_id: Annotated[
        str, Field(description="The task run ID to fetch logs for.")
    ],
    limit: Annotated[
        int, Field(description="Max log lines to return (max 1000).")
    ] = 1000,
    since: Annotated[
        str | None,
        Field(description="ISO 8601 start time, e.g. '2026-05-19T00:00:00Z'."),
    ] = None,
    until: Annotated[str | None, Field(description="ISO 8601 end time.")] = None,
) -> dict[str, Any]:
    h = get_hatchet()
    result = await h.logs.aio_list(
        task_run_id=task_run_id,
        limit=_clamp_limit(limit, default=1000, cap=1000),
        since=_parse_dt(since, field="since"),
        until=_parse_dt(until, field="until"),
    )
    return _dump(result)


async def list_task_events(
    task_run_id: Annotated[
        str, Field(description="The task run ID (UUID) to list events for.")
    ],
    limit: Annotated[
        int | None,
        Field(description="Max task events to return (default 50, max 100)."),
    ] = None,
    offset: Annotated[int | None, Field(description="Pagination offset.")] = None,
) -> dict[str, Any]:
    result = await _rest_call(
        lambda client, _tenant: TaskApi(client).v1_task_event_list(
            task=task_run_id, offset=offset, limit=_clamp_limit(limit)
        )
    )
    return _dump(result)


async def list_dag_tasks(
    dag_ids: Annotated[
        list[str],
        Field(
            description="One or more DAG (workflow-run) external IDs (UUIDs) to flatten "
            "into their constituent tasks."
        ),
    ],
) -> dict[str, Any]:
    result = await _rest_call(
        lambda client, tenant: TaskApi(client).v1_dag_list_tasks(
            dag_ids=dag_ids, tenant=tenant
        )
    )
    # ^ SDK returns List[V1DagChildren]; serialize each Pydantic model by hand because _dump
    # expects a single BaseModel, then wrap in a top-level key and guard the size.
    rows = [item.model_dump(mode="json", by_alias=True) for item in result]
    return _guard_size({"rows": rows})


async def restore_task(
    task_id: Annotated[
        str,
        Field(description="The task ID (UUID) of the evicted durable task to restore."),
    ],
) -> dict[str, Any]:
    _require_writable()
    result = await _rest_call(
        lambda client, _tenant: TaskApi(client).v1_task_restore(task=task_id)
    )
    return _dump(result)


READ_TOOLS: list[tuple[Callable[..., Any], str, str]] = [
    (
        get_task,
        "get_task",
        "Get a single task run by its ID (status, attempt, worker, inputs/outputs).",
    ),
    (
        get_task_logs,
        "get_task_logs",
        "List log lines emitted by a single task run, optionally bounded by time.",
    ),
    (
        list_task_events,
        "list_task_events",
        "List the orchestration event timeline for a single task run (state transitions "
        "like scheduled, started, retried, reassigned, completed/failed, with reasons).",
    ),
    (
        list_dag_tasks,
        "list_dag_tasks",
        "List the constituent tasks of one or more DAG (workflow-run) external IDs as a "
        "flat list. Complements get_run (which returns the nested task tree) when you want "
        "to iterate over every leaf task without traversing the tree.",
    ),
]

MUTATING_TOOLS: list[tuple[Callable[..., Any], str, str, ToolAnnotations]] = [
    (
        restore_task,
        "restore_task",
        "Restore an evicted durable task by its task ID.",
        _destructive(idempotent=False),
    ),
]
