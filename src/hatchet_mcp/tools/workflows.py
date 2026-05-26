"""Workflow definitions: list/get/version/metrics (read), plus pause/resume (mutating)."""

from collections.abc import Callable
from typing import Annotated, Any

from hatchet_sdk.clients.rest.api.workflow_api import WorkflowApi
from hatchet_sdk.clients.rest.models.workflow_run_status import WorkflowRunStatus
from hatchet_sdk.clients.rest.models.workflow_update_request import (
    WorkflowUpdateRequest,
)
from mcp.types import ToolAnnotations
from pydantic import Field

from hatchet_mcp._shared import (
    _clamp_limit,
    _destructive,
    _dump,
    _parse_enum,
    _require_writable,
    _rest_call,
)
from hatchet_mcp.client import get_hatchet


async def list_workflows(
    workflow_name: Annotated[
        str | None, Field(description="Filter by workflow name (exact).")
    ] = None,
    limit: Annotated[
        int | None, Field(description="Max workflows to return (default 50, max 100).")
    ] = None,
    offset: Annotated[int | None, Field(description="Pagination offset.")] = None,
) -> dict[str, Any]:
    h = get_hatchet()
    result = await h.workflows.aio_list(
        workflow_name=workflow_name, limit=_clamp_limit(limit), offset=offset
    )
    return _dump(result)


async def get_workflow(
    workflow_id: Annotated[str, Field(description="The workflow ID (UUID).")],
) -> dict[str, Any]:
    h = get_hatchet()
    result = await h.workflows.aio_get(workflow_id)
    return _dump(result)


async def get_workflow_version(
    workflow_id: Annotated[str, Field(description="The workflow ID (UUID).")],
    version: Annotated[
        str | None,
        Field(
            description="Specific workflow version ID (UUID). Defaults to the latest version."
        ),
    ] = None,
) -> dict[str, Any]:
    h = get_hatchet()
    result = await h.workflows.aio_get_version(workflow_id, version=version)
    return _dump(result)


async def get_workflow_metrics(
    workflow_id: Annotated[str, Field(description="The workflow ID (UUID).")],
    status: Annotated[
        str | None,
        Field(
            description="Filter metrics to runs with this WorkflowRunStatus: PENDING, "
            "QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED, BACKOFF."
        ),
    ] = None,
    group_key: Annotated[
        str | None,
        Field(description="Filter metrics to runs grouped by this concurrency key."),
    ] = None,
) -> dict[str, Any]:
    status_enum = _parse_enum(status, WorkflowRunStatus, field="status")
    result = await _rest_call(
        lambda client, _tenant: WorkflowApi(client).workflow_get_metrics(
            workflow=workflow_id, status=status_enum, group_key=group_key
        )
    )
    return _dump(result)


async def pause_workflow(
    workflow_id: Annotated[
        str, Field(description="The workflow definition ID (UUID) to pause.")
    ],
) -> dict[str, Any]:
    _require_writable()
    # ^ No feature-client method for pausing a workflow; uses the low-level workflow:update (isPaused).
    result = await _rest_call(
        lambda client, _tenant: WorkflowApi(client).workflow_update(
            workflow=workflow_id,
            workflow_update_request=WorkflowUpdateRequest(isPaused=True),
        )
    )
    return _dump(result)


async def resume_workflow(
    workflow_id: Annotated[
        str, Field(description="The workflow definition ID (UUID) to resume.")
    ],
) -> dict[str, Any]:
    _require_writable()
    result = await _rest_call(
        lambda client, _tenant: WorkflowApi(client).workflow_update(
            workflow=workflow_id,
            workflow_update_request=WorkflowUpdateRequest(isPaused=False),
        )
    )
    return _dump(result)


READ_TOOLS: list[tuple[Callable[..., Any], str, str]] = [
    (
        list_workflows,
        "list_workflows",
        "List workflow definitions (not runs) in the tenant, with optional name filter and pagination.",
    ),
    (
        get_workflow,
        "get_workflow",
        "Get a single workflow definition by its ID (versions, tags, jobs).",
    ),
    (
        get_workflow_version,
        "get_workflow_version",
        "Get a specific version of a workflow definition (or the latest if version is "
        "omitted). Use to inspect the DAG, default priority, and tags of a deployed version.",
    ),
    (
        get_workflow_metrics,
        "get_workflow_metrics",
        "Get aggregate metrics for a workflow (success/failure/duration counts), optionally "
        "scoped to a specific run status or concurrency group key.",
    ),
]

MUTATING_TOOLS: list[tuple[Callable[..., Any], str, str, ToolAnnotations]] = [
    (
        pause_workflow,
        "pause_workflow",
        "Pause a workflow definition so it stops accepting new runs.",
        _destructive(idempotent=True),
    ),
    (
        resume_workflow,
        "resume_workflow",
        "Resume a paused workflow definition.",
        _destructive(idempotent=True),
    ),
]
