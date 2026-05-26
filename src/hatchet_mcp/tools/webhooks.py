"""V1 inbound webhooks: list/get (read).

V1 webhooks are server-side endpoints that accept HTTP calls from external systems and
translate them into Hatchet events according to a CEL expression. Read-only surface for
now — create/update/delete carry credential material (BasicAuth, APIKeyAuth, HMACAuth)
that we leave to dashboard / CLI flows to avoid passing secrets through tool calls.
"""

from collections.abc import Callable
from typing import Annotated, Any

from hatchet_sdk.clients.rest.models.v1_webhook_source_name import V1WebhookSourceName
from mcp.types import ToolAnnotations
from pydantic import Field

from hatchet_mcp._shared import _clamp_limit, _dump, _parse_enum_list
from hatchet_mcp.client import get_hatchet


async def list_webhooks(
    webhook_names: Annotated[
        list[str] | None,
        Field(description="Filter by one or more webhook names."),
    ] = None,
    source_names: Annotated[
        list[str] | None,
        Field(
            description="Filter by webhook source name (V1WebhookSourceName values: "
            "GENERIC, GITHUB, LINEAR, SLACK, STRIPE)."
        ),
    ] = None,
    limit: Annotated[
        int | None,
        Field(description="Max webhooks to return (default 50, max 100)."),
    ] = None,
    offset: Annotated[int | None, Field(description="Pagination offset.")] = None,
) -> dict[str, Any]:
    h = get_hatchet()
    source_enums = _parse_enum_list(
        source_names, V1WebhookSourceName, field="source name"
    )
    result = await h.webhooks.aio_list(
        limit=_clamp_limit(limit),
        offset=offset,
        webhook_names=webhook_names,
        source_names=source_enums,
    )
    return _dump(result)


async def get_webhook(
    webhook_name: Annotated[
        str,
        Field(
            description="The webhook NAME (not ID — V1 webhooks are addressed by name)."
        ),
    ],
) -> dict[str, Any]:
    h = get_hatchet()
    result = await h.webhooks.aio_get(webhook_name)
    return _dump(result)


READ_TOOLS: list[tuple[Callable[..., Any], str, str]] = [
    (
        list_webhooks,
        "list_webhooks",
        "List V1 inbound webhooks configured in the tenant — endpoints that accept "
        "external HTTP calls and translate them into Hatchet events via CEL. Optional "
        "filters by webhook name(s) or source name(s).",
    ),
    (
        get_webhook,
        "get_webhook",
        "Get a single V1 inbound webhook by NAME (not ID) — auth mode, source, CEL "
        "expression for event-key derivation, static payload, and scope.",
    ),
]

MUTATING_TOOLS: list[tuple[Callable[..., Any], str, str, ToolAnnotations]] = []
