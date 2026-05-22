"""Time-based triggers: cron triggers and one-off scheduled runs — list/get (read) + create/delete/reschedule."""

from collections.abc import Callable
from typing import Annotated, Any

from hatchet_sdk.clients.rest.models.cron_workflows_order_by_field import (
    CronWorkflowsOrderByField,
)
from hatchet_sdk.clients.rest.models.scheduled_run_status import ScheduledRunStatus
from hatchet_sdk.clients.rest.models.scheduled_workflows_order_by_field import (
    ScheduledWorkflowsOrderByField,
)
from hatchet_sdk.clients.rest.models.workflow_run_order_by_direction import (
    WorkflowRunOrderByDirection,
)
from mcp.types import ToolAnnotations
from pydantic import Field

from hatchet_mcp._shared import (
    _clamp_limit,
    _destructive,
    _dump,
    _parse_dt,
    _parse_enum,
    _parse_enum_list,
    _require_writable,
)
from hatchet_mcp.client import get_hatchet


async def list_crons(
    workflow_id: Annotated[
        str | None, Field(description="Filter by the target workflow ID.")
    ] = None,
    workflow_name: Annotated[
        str | None, Field(description="Filter by the target workflow name.")
    ] = None,
    cron_name: Annotated[
        str | None, Field(description="Filter by the cron trigger name.")
    ] = None,
    additional_metadata: Annotated[
        dict[str, str] | None,
        Field(description="Filter by cron additional-metadata key/values."),
    ] = None,
    order_by_field: Annotated[
        str | None,
        Field(description="Field to order by: name or createdAt."),
    ] = None,
    order_by_direction: Annotated[
        str | None,
        Field(description="Order direction: ASC or DESC."),
    ] = None,
    limit: Annotated[
        int | None,
        Field(description="Max cron triggers to return (default 50, max 100)."),
    ] = None,
    offset: Annotated[int | None, Field(description="Pagination offset.")] = None,
) -> dict[str, Any]:
    h = get_hatchet()
    order_field = _parse_enum(
        order_by_field, CronWorkflowsOrderByField, field="order_by_field"
    )
    order_direction = _parse_enum(
        order_by_direction, WorkflowRunOrderByDirection, field="order_by_direction"
    )
    result = await h.cron.aio_list(
        offset=offset,
        limit=_clamp_limit(limit),
        workflow_id=workflow_id,
        additional_metadata=additional_metadata,
        order_by_field=order_field,
        order_by_direction=order_direction,
        workflow_name=workflow_name,
        cron_name=cron_name,
    )
    return _dump(result)


async def get_cron(
    cron_id: Annotated[str, Field(description="The cron trigger ID (UUID).")],
) -> dict[str, Any]:
    h = get_hatchet()
    result = await h.cron.aio_get(cron_id)
    return _dump(result)


async def list_scheduled(
    workflow_id: Annotated[
        str | None, Field(description="Filter by the target workflow ID.")
    ] = None,
    parent_workflow_run_id: Annotated[
        str | None,
        Field(
            description="Only scheduled runs whose parent workflow run is this ID — use to "
            "find one-off runs spawned by a specific parent run."
        ),
    ] = None,
    statuses: Annotated[
        list[str] | None,
        Field(
            description="Filter by ScheduledRunStatus values: PENDING, RUNNING, SUCCEEDED, "
            "FAILED, CANCELLED, QUEUED, SCHEDULED."
        ),
    ] = None,
    additional_metadata: Annotated[
        dict[str, str] | None,
        Field(description="Filter by additional-metadata key/values."),
    ] = None,
    order_by_field: Annotated[
        str | None,
        Field(description="Field to order by: triggerAt or createdAt."),
    ] = None,
    order_by_direction: Annotated[
        str | None,
        Field(description="Order direction: ASC or DESC."),
    ] = None,
    limit: Annotated[
        int | None,
        Field(description="Max scheduled runs to return (default 50, max 100)."),
    ] = None,
    offset: Annotated[int | None, Field(description="Pagination offset.")] = None,
) -> dict[str, Any]:
    h = get_hatchet()
    status_enums = _parse_enum_list(
        statuses, ScheduledRunStatus, field="scheduled status"
    )
    order_field = _parse_enum(
        order_by_field, ScheduledWorkflowsOrderByField, field="order_by_field"
    )
    order_direction = _parse_enum(
        order_by_direction, WorkflowRunOrderByDirection, field="order_by_direction"
    )
    result = await h.scheduled.aio_list(
        offset=offset,
        limit=_clamp_limit(limit),
        workflow_id=workflow_id,
        parent_workflow_run_id=parent_workflow_run_id,
        statuses=status_enums,
        additional_metadata=additional_metadata,
        order_by_field=order_field,
        order_by_direction=order_direction,
    )
    return _dump(result)


async def create_cron(
    workflow_name: Annotated[
        str, Field(description="The name of the workflow the cron triggers.")
    ],
    cron_name: Annotated[str, Field(description="A name for this cron trigger.")],
    expression: Annotated[
        str,
        Field(
            description="The cron expression (5 or 6 fields, or an alias like @daily)."
        ),
    ],
    input: Annotated[
        dict[str, Any] | None,
        Field(
            description="Input payload for each triggered run. Defaults to an empty object."
        ),
    ] = None,
    additional_metadata: Annotated[
        dict[str, str] | None,
        Field(
            description="Additional metadata for each triggered run. Defaults to an empty object."
        ),
    ] = None,
    priority: Annotated[
        int | None, Field(description="Run priority (1=low, 2=medium, 3=high).")
    ] = None,
) -> dict[str, Any]:
    _require_writable()
    h = get_hatchet()
    result = await h.cron.aio_create(
        workflow_name=workflow_name,
        cron_name=cron_name,
        expression=expression,
        input=input or {},
        additional_metadata=additional_metadata or {},
        priority=priority,
    )
    return _dump(result)


async def delete_cron(
    cron_id: Annotated[str, Field(description="The cron trigger ID (UUID) to delete.")],
) -> dict[str, Any]:
    _require_writable()
    h = get_hatchet()
    await h.cron.aio_delete(cron_id)
    return {"deleted": True, "cron_id": cron_id}


async def create_scheduled(
    workflow_name: Annotated[
        str, Field(description="The name of the workflow to schedule.")
    ],
    trigger_at: Annotated[
        str,
        Field(
            description="ISO 8601 datetime when the run should fire, e.g. '2026-05-21T09:00:00Z'."
        ),
    ],
    input: Annotated[
        dict[str, Any] | None,
        Field(description="Input payload for the run. Defaults to an empty object."),
    ] = None,
    additional_metadata: Annotated[
        dict[str, str] | None,
        Field(
            description="Additional metadata for the run. Defaults to an empty object."
        ),
    ] = None,
) -> dict[str, Any]:
    _require_writable()
    trigger_dt = _parse_dt(trigger_at, field="trigger_at")
    if trigger_dt is None:
        raise ValueError("trigger_at is required (ISO 8601 datetime).")
    h = get_hatchet()
    result = await h.scheduled.aio_create(
        workflow_name=workflow_name,
        trigger_at=trigger_dt,
        input=input or {},
        additional_metadata=additional_metadata or {},
    )
    return _dump(result)


async def delete_scheduled(
    scheduled_id: Annotated[
        str, Field(description="The scheduled run ID (UUID) to delete.")
    ],
) -> dict[str, Any]:
    _require_writable()
    h = get_hatchet()
    await h.scheduled.aio_delete(scheduled_id)
    return {"deleted": True, "scheduled_id": scheduled_id}


async def reschedule(
    scheduled_id: Annotated[
        str, Field(description="The scheduled run ID (UUID) to reschedule.")
    ],
    trigger_at: Annotated[
        str,
        Field(
            description="New ISO 8601 datetime for the run, e.g. '2026-05-21T09:00:00Z'."
        ),
    ],
) -> dict[str, Any]:
    _require_writable()
    trigger_dt = _parse_dt(trigger_at, field="trigger_at")
    if trigger_dt is None:
        raise ValueError("trigger_at is required (ISO 8601 datetime).")
    h = get_hatchet()
    result = await h.scheduled.aio_update(scheduled_id, trigger_dt)
    return _dump(result)


READ_TOOLS: list[tuple[Callable[..., Any], str, str]] = [
    (
        list_crons,
        "list_crons",
        "List cron triggers in the tenant (schedule expression, target workflow, enabled "
        "state), with optional filters, ordering (name/createdAt ASC/DESC), and pagination.",
    ),
    (
        get_cron,
        "get_cron",
        "Get a single cron trigger by ID (expression, target workflow, input, enabled state).",
    ),
    (
        list_scheduled,
        "list_scheduled",
        "List scheduled (one-off, future-dated) workflow runs, with status/workflow/parent "
        "filters, optional ordering (triggerAt/createdAt ASC/DESC), and pagination. "
        "Status values are ScheduledRunStatus: PENDING, RUNNING, SUCCEEDED, FAILED, "
        "CANCELLED, QUEUED, SCHEDULED.",
    ),
]

MUTATING_TOOLS: list[tuple[Callable[..., Any], str, str, ToolAnnotations]] = [
    (
        create_cron,
        "create_cron",
        "Create a cron trigger that runs a workflow on a schedule.",
        _destructive(idempotent=False),
    ),
    (
        delete_cron,
        "delete_cron",
        "Delete a cron trigger by its ID.",
        _destructive(idempotent=True),
    ),
    (
        create_scheduled,
        "create_scheduled",
        "Schedule a one-off future workflow run at a given time.",
        _destructive(idempotent=False),
    ),
    (
        delete_scheduled,
        "delete_scheduled",
        "Delete a scheduled (future) workflow run by its ID.",
        _destructive(idempotent=True),
    ),
    (
        reschedule,
        "reschedule",
        "Change the trigger time of an existing scheduled workflow run.",
        _destructive(idempotent=True),
    ),
]
