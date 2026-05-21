"""Event filters (CEL expressions that gate event-driven triggering): list/get + create/update/delete."""

from collections.abc import Callable
from typing import Annotated, Any

from hatchet_sdk.clients.rest.exceptions import ApiException
from hatchet_sdk.clients.rest.models.v1_update_filter_request import (
    V1UpdateFilterRequest,
)
from mcp.types import ToolAnnotations
from pydantic import Field

from hatchet_mcp._shared import (
    _api_error,
    _clamp_limit,
    _destructive,
    _dump,
    _require_writable,
)
from hatchet_mcp.client import get_hatchet


async def list_filters(
    workflow_ids: Annotated[
        list[str] | None, Field(description="Filter by one or more workflow IDs.")
    ] = None,
    scopes: Annotated[
        list[str] | None, Field(description="Filter by one or more filter scopes.")
    ] = None,
    limit: Annotated[
        int | None, Field(description="Max filters to return (default 50, max 100).")
    ] = None,
    offset: Annotated[int | None, Field(description="Pagination offset.")] = None,
) -> dict[str, Any]:
    h = get_hatchet()
    try:
        result = await h.filters.aio_list(
            limit=_clamp_limit(limit),
            offset=offset,
            workflow_ids=workflow_ids,
            scopes=scopes,
        )
    except ApiException as exc:
        raise _api_error(exc) from None
    return _dump(result)


async def get_filter(
    filter_id: Annotated[str, Field(description="The filter ID (UUID).")],
) -> dict[str, Any]:
    h = get_hatchet()
    try:
        result = await h.filters.aio_get(filter_id)
    except ApiException as exc:
        raise _api_error(exc) from None
    return _dump(result)


async def cel_debug(
    expression: Annotated[str, Field(description="The CEL expression to evaluate.")],
    input: Annotated[
        dict[str, Any] | None,
        Field(
            description="Input to evaluate against, simulating a workflow run input. Defaults to an empty object."
        ),
    ] = None,
    additional_metadata: Annotated[
        dict[str, Any] | None,
        Field(
            description="Additional metadata to evaluate against, simulating event/run metadata."
        ),
    ] = None,
    filter_payload: Annotated[
        dict[str, Any] | None,
        Field(
            description="Filter payload to evaluate against, simulating a payload set on a filter."
        ),
    ] = None,
) -> dict[str, Any]:
    h = get_hatchet()
    try:
        result = await h.cel.aio_debug(
            expression=expression,
            input=input or {},
            additional_metadata=additional_metadata,
            filter_payload=filter_payload,
        )
    except ApiException as exc:
        raise _api_error(exc) from None
    return _dump(result)


async def create_filter(
    workflow_id: Annotated[
        str, Field(description="The workflow ID (UUID) the filter gates.")
    ],
    expression: Annotated[
        str, Field(description="The CEL expression evaluated against incoming events.")
    ],
    scope: Annotated[
        str,
        Field(
            description="The scope used to subset candidate filters at evaluation time."
        ),
    ],
    payload: Annotated[
        dict[str, Any] | None,
        Field(description="Optional payload merged into matching event triggers."),
    ] = None,
) -> dict[str, Any]:
    _require_writable()
    h = get_hatchet()
    try:
        result = await h.filters.aio_create(
            workflow_id=workflow_id,
            expression=expression,
            scope=scope,
            payload=payload,
        )
    except ApiException as exc:
        raise _api_error(exc) from None
    return _dump(result)


async def update_filter(
    filter_id: Annotated[str, Field(description="The filter ID (UUID) to update.")],
    expression: Annotated[
        str | None,
        Field(description="New CEL expression. Omit to leave unchanged."),
    ] = None,
    scope: Annotated[
        str | None, Field(description="New scope. Omit to leave unchanged.")
    ] = None,
    payload: Annotated[
        dict[str, Any] | None,
        Field(description="New payload. Omit to leave unchanged."),
    ] = None,
) -> dict[str, Any]:
    _require_writable()
    h = get_hatchet()
    try:
        result = await h.filters.aio_update(
            filter_id,
            V1UpdateFilterRequest(expression=expression, scope=scope, payload=payload),
        )
    except ApiException as exc:
        raise _api_error(exc) from None
    return _dump(result)


async def delete_filter(
    filter_id: Annotated[str, Field(description="The filter ID (UUID) to delete.")],
) -> dict[str, Any]:
    _require_writable()
    h = get_hatchet()
    try:
        result = await h.filters.aio_delete(filter_id)
    except ApiException as exc:
        raise _api_error(exc) from None
    return _dump(result)


READ_TOOLS: list[tuple[Callable[..., Any], str, str]] = [
    (
        list_filters,
        "list_filters",
        "List event filters — CEL expressions that gate event-driven workflow triggering — "
        "with workflow/scope filters and pagination.",
    ),
    (
        get_filter,
        "get_filter",
        "Get a single event filter by ID (its CEL expression, scope, and payload).",
    ),
    (
        cel_debug,
        "cel_debug",
        "Test a CEL expression against sample input without creating a filter — returns the "
        "boolean result or a syntax/evaluation error. Useful before create_filter/update_filter.",
    ),
]

MUTATING_TOOLS: list[tuple[Callable[..., Any], str, str, ToolAnnotations]] = [
    (
        create_filter,
        "create_filter",
        "Create an event filter (CEL expression) that gates event-driven workflow triggering.",
        _destructive(idempotent=False),
    ),
    (
        update_filter,
        "update_filter",
        "Update an event filter's expression, scope, or payload by its ID.",
        _destructive(idempotent=True),
    ),
    (
        delete_filter,
        "delete_filter",
        "Delete an event filter by its ID.",
        _destructive(idempotent=True),
    ),
]
