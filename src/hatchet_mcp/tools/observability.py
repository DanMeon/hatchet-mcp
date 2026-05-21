"""Read-only observability: queue/task metrics, run timings, OTel traces, and rate limits."""

from collections.abc import Callable
from typing import Annotated, Any

from hatchet_sdk.clients.rest.api.observability_api import ObservabilityApi
from hatchet_sdk.clients.rest.api.workflow_runs_api import WorkflowRunsApi
from mcp.types import ToolAnnotations
from pydantic import Field

from hatchet_mcp._shared import _clamp_limit, _dump, _parse_dt, _rest_call
from hatchet_mcp.client import get_hatchet


async def get_queue_metrics() -> dict[str, Any]:
    h = get_hatchet()
    queues = await h.metrics.aio_get_queue_metrics()
    return {"queues": queues}


async def get_task_metrics(
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
        list[str] | None, Field(description="Filter metrics to these workflow IDs.")
    ] = None,
) -> dict[str, Any]:
    h = get_hatchet()
    result = await h.metrics.aio_get_task_metrics(
        since=_parse_dt(since, field="since"),
        until=_parse_dt(until, field="until"),
        workflow_ids=workflow_ids,
    )
    return _dump(result)


async def get_run_timings(
    workflow_run_id: Annotated[
        str, Field(description="The workflow run external ID (UUID).")
    ],
    depth: Annotated[
        int | None, Field(description="Max child depth to retrieve in the task tree.")
    ] = None,
) -> dict[str, Any]:
    result = await _rest_call(
        lambda client, _tenant: WorkflowRunsApi(client).v1_workflow_run_get_timings(
            v1_workflow_run=workflow_run_id, depth=depth
        )
    )
    return _dump(result)


async def get_trace(
    workflow_run_id: Annotated[
        str, Field(description="The workflow run external ID (UUID).")
    ],
    limit: Annotated[
        int | None, Field(description="Max spans to return (default 50, max 100).")
    ] = None,
    offset: Annotated[int | None, Field(description="Span pagination offset.")] = None,
) -> dict[str, Any]:
    result = await _rest_call(
        lambda client, tenant: ObservabilityApi(client).v1_observability_get_trace(
            tenant=tenant,
            run_external_id=workflow_run_id,
            offset=offset,
            limit=_clamp_limit(limit),
        )
    )
    return _dump(result)


async def list_rate_limits(
    search: Annotated[
        str | None, Field(description="Filter rate limits by key (substring search).")
    ] = None,
    limit: Annotated[
        int | None,
        Field(description="Max rate limits to return (default 50, max 100)."),
    ] = None,
    offset: Annotated[int | None, Field(description="Pagination offset.")] = None,
) -> dict[str, Any]:
    h = get_hatchet()
    result = await h.rate_limits.aio_list(
        offset=offset, limit=_clamp_limit(limit), search=search
    )
    return _dump(result)


READ_TOOLS: list[tuple[Callable[..., Any], str, str]] = [
    (
        get_queue_metrics,
        "get_queue_metrics",
        "Get native per-queue depth metrics for the tenant (pending work grouped by queue). "
        "More accurate than client-side run counting.",
    ),
    (
        get_task_metrics,
        "get_task_metrics",
        "Get task counts grouped by status (queued, running, completed, failed, cancelled) "
        "over a time window. Defaults to the last 24h.",
    ),
    (
        get_run_timings,
        "get_run_timings",
        "Get the task waterfall timings for a workflow run (queued/started/finished per "
        "task), optionally limited by tree depth.",
    ),
    (
        get_trace,
        "get_trace",
        "Get the OpenTelemetry spans (distributed trace) for a workflow run, paginated over "
        "spans.",
    ),
    (
        list_rate_limits,
        "list_rate_limits",
        "List rate limits configured in the tenant with current consumption, limit value, "
        "window, and last refill time.",
    ),
]

MUTATING_TOOLS: list[tuple[Callable[..., Any], str, str, ToolAnnotations]] = []
