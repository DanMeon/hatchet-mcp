"""Events: list/get/keys (read, via the v1 event REST API), plus push (mutating, legacy event:create)."""

from collections.abc import Callable
from typing import Annotated, Any

from hatchet_sdk.clients.rest.api.event_api import EventApi
from hatchet_sdk.clients.rest.models.create_event_request import CreateEventRequest
from hatchet_sdk.clients.rest.models.v1_task_status import V1TaskStatus
from hatchet_sdk.clients.v1.api_client import maybe_additional_metadata_to_kv
from mcp.types import ToolAnnotations
from pydantic import Field

from hatchet_mcp._shared import (
    _clamp_limit,
    _destructive,
    _dump,
    _dump_item,
    _parse_dt,
    _parse_enum_list,
    _require_writable,
    _rest_call,
)


async def list_events(
    keys: Annotated[
        list[str] | None, Field(description="Filter by one or more event keys.")
    ] = None,
    since: Annotated[
        str | None,
        Field(
            description="ISO 8601 lower bound on event time, e.g. '2026-05-19T00:00:00Z'."
        ),
    ] = None,
    until: Annotated[
        str | None, Field(description="ISO 8601 upper bound on event time.")
    ] = None,
    workflow_ids: Annotated[
        list[str] | None,
        Field(description="Only events associated with these workflow IDs."),
    ] = None,
    statuses: Annotated[
        list[str] | None,
        Field(
            description="Only events whose triggered runs match these v1 statuses: "
            "QUEUED, RUNNING, COMPLETED, CANCELLED, FAILED."
        ),
    ] = None,
    event_ids: Annotated[
        list[str] | None,
        Field(description="Only these specific events by their UUIDs."),
    ] = None,
    scopes: Annotated[
        list[str] | None,
        Field(
            description="Filter by event scope strings — used to subset candidate filters "
            "at evaluation time. Mirrors the scope set on push_event."
        ),
    ] = None,
    additional_metadata: Annotated[
        dict[str, str] | None,
        Field(description="Filter by event additional-metadata key/values."),
    ] = None,
    limit: Annotated[
        int | None, Field(description="Max events to return (default 50, max 100).")
    ] = None,
    offset: Annotated[int | None, Field(description="Pagination offset.")] = None,
) -> dict[str, Any]:
    since_dt = _parse_dt(since, field="since")
    until_dt = _parse_dt(until, field="until")
    status_enums = _parse_enum_list(statuses, V1TaskStatus, field="status")
    metadata_kv = maybe_additional_metadata_to_kv(additional_metadata)
    result = await _rest_call(
        lambda client, tenant: EventApi(client).v1_event_list(
            tenant=tenant,
            offset=offset,
            limit=_clamp_limit(limit),
            keys=keys,
            since=since_dt,
            until=until_dt,
            workflow_ids=workflow_ids,
            workflow_run_statuses=status_enums,
            event_ids=event_ids,
            additional_metadata=metadata_kv,
            scopes=scopes,
        )
    )
    return _dump(result)


async def get_event(
    event_id: Annotated[str, Field(description="The event ID (UUID).")],
) -> dict[str, Any]:
    result = await _rest_call(
        lambda client, tenant: EventApi(client).v1_event_get(
            tenant=tenant, v1_event=event_id
        )
    )
    return _dump_item(result)


async def list_event_keys() -> dict[str, Any]:
    result = await _rest_call(
        lambda client, tenant: EventApi(client).v1_event_key_list(tenant=tenant)
    )
    return _dump(result)


async def push_event(
    key: Annotated[str, Field(description="The event key (e.g. 'user:created').")],
    data: Annotated[
        dict[str, Any] | None,
        Field(description="The event payload. Defaults to an empty object."),
    ] = None,
    additional_metadata: Annotated[
        dict[str, str] | None,
        Field(description="Additional metadata to attach to the event."),
    ] = None,
    priority: Annotated[
        int | None, Field(description="Event priority (1=low, 2=medium, 3=high).")
    ] = None,
    scope: Annotated[
        str | None,
        Field(description="Scope used to subset candidate filters at evaluation time."),
    ] = None,
) -> dict[str, Any]:
    _require_writable()
    # ^ Uses the legacy REST event:create (EventApi.event_create) to stay REST-only and avoid the gRPC h.event push client.
    result = await _rest_call(
        lambda client, tenant: EventApi(client).event_create(
            tenant=tenant,
            create_event_request=CreateEventRequest(
                key=key,
                data=data or {},
                additionalMetadata=additional_metadata,
                priority=priority,
                scope=scope,
            ),
        )
    )
    return _dump(result)


READ_TOOLS: list[tuple[Callable[..., Any], str, str]] = [
    (
        list_events,
        "list_events",
        "List events ingested by the tenant, filtered by key, time window, associated "
        "workflow, triggered-run status, specific event IDs, scope, or metadata. Each "
        "event carries its payload and a summary of the runs it triggered.",
    ),
    (
        get_event,
        "get_event",
        "Get a single event by ID, including its full payload and triggered-run summary.",
    ),
    (
        list_event_keys,
        "list_event_keys",
        "List the distinct event keys seen in the tenant — useful for discovering what to filter list_events by.",
    ),
]

MUTATING_TOOLS: list[tuple[Callable[..., Any], str, str, ToolAnnotations]] = [
    (
        push_event,
        "push_event",
        "Push an event (key + data) into the tenant, which may trigger event-driven workflows.",
        _destructive(idempotent=False),
    ),
]
