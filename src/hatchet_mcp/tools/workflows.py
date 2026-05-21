"""Workflow definitions: list/get, plus pause/resume (mutating, via the low-level workflow:update)."""

from collections.abc import Callable
from typing import Annotated, Any

from hatchet_sdk.clients.rest.api.workflow_api import WorkflowApi
from hatchet_sdk.clients.rest.exceptions import ApiException
from hatchet_sdk.clients.rest.models.workflow_update_request import (
    WorkflowUpdateRequest,
)
from mcp.types import ToolAnnotations
from pydantic import Field

from hatchet_mcp._shared import (
    _api_error,
    _clamp_limit,
    _destructive,
    _dump,
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
    try:
        result = await h.workflows.aio_list(
            workflow_name=workflow_name, limit=_clamp_limit(limit), offset=offset
        )
    except ApiException as exc:
        raise _api_error(exc) from None
    return _dump(result)


async def get_workflow(
    workflow_id: Annotated[str, Field(description="The workflow ID (UUID).")],
) -> dict[str, Any]:
    h = get_hatchet()
    try:
        result = await h.workflows.aio_get(workflow_id)
    except ApiException as exc:
        raise _api_error(exc) from None
    return _dump(result)


async def pause_workflow(
    workflow_id: Annotated[
        str, Field(description="The workflow definition ID (UUID) to pause.")
    ],
) -> dict[str, Any]:
    _require_writable()
    # ^ No feature-client method for pausing a workflow; uses the low-level workflow:update (isPaused).
    try:
        result = await _rest_call(
            lambda client, _tenant: WorkflowApi(client).workflow_update(
                workflow=workflow_id,
                workflow_update_request=WorkflowUpdateRequest(isPaused=True),
            )
        )
    except ApiException as exc:
        raise _api_error(exc) from None
    return _dump(result)


async def resume_workflow(
    workflow_id: Annotated[
        str, Field(description="The workflow definition ID (UUID) to resume.")
    ],
) -> dict[str, Any]:
    _require_writable()
    try:
        result = await _rest_call(
            lambda client, _tenant: WorkflowApi(client).workflow_update(
                workflow=workflow_id,
                workflow_update_request=WorkflowUpdateRequest(isPaused=False),
            )
        )
    except ApiException as exc:
        raise _api_error(exc) from None
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
