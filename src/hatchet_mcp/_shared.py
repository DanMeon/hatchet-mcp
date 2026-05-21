"""Shared internal helpers for the tool/resource/prompt modules.

Serialization (with a result-size guard), input parsers, the low-level REST bridge, the
list-limit clamp, and the mutation gate. Tool modules import from here rather than from
``app`` so they stay independent of the ``FastMCP`` instance; this also keeps the import
graph acyclic (``server`` → tools → ``_shared``; ``app`` holds only the app instance).
"""

import asyncio
import json
from collections.abc import Callable
from datetime import datetime, timezone
from enum import Enum
from typing import Any, TypeVar

from hatchet_sdk.clients.rest.api_client import ApiClient
from hatchet_sdk.clients.rest.exceptions import ApiException
from hatchet_sdk.clients.rest.models.v1_task_status import V1TaskStatus
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from hatchet_mcp.client import get_rest
from hatchet_mcp.config import redact

# * List limits and result-size guard
# List endpoints have no server-side cap, and a tool result that overflows the client's
# context is unrecoverable, so the server caps both: a default/max on each list tool's limit,
# and a byte ceiling on every serialized list result (defense-in-depth for tools like
# list_workers whose SDK call takes no limit). Single-item get_* use _dump_item (no guard).
_DEFAULT_LIST_LIMIT = 50
_MAX_LIST_LIMIT = 100
_MAX_RESULT_BYTES = 500_000


def _clamp_limit(
    limit: int | None, *, default: int = _DEFAULT_LIST_LIMIT, cap: int = _MAX_LIST_LIMIT
) -> int:
    """Resolve a list tool's limit: None becomes the default, anything above the cap is capped."""
    if limit is None:
        return default
    if limit < 1:
        raise ValueError(f"limit must be >= 1; got {limit!r}")
    return min(limit, cap)


def _guard_size(data: dict[str, Any]) -> dict[str, Any]:
    """Reject a result large enough to overflow the client context, with guidance to narrow it."""
    size = len(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    if size > _MAX_RESULT_BYTES:
        raise RuntimeError(
            f"Result is {size:,} bytes, over the {_MAX_RESULT_BYTES:,}-byte cap that would "
            "overflow the client context. Narrow it with a smaller limit and tighter filters "
            "(time window / statuses); for list_runs keep include_payloads=false (the default)."
        )
    return data


def _dump_item(model: BaseModel) -> dict[str, Any]:
    """Serialize a single-item detail response in the Hatchet API shape, with no size guard.

    A get_* on one object should return it whole — there is no narrowing knob to recover from
    a hard cap. List tools use _dump, which guards, because they can be narrowed (see _clamp_limit).
    """
    return model.model_dump(mode="json", by_alias=True)


def _dump(model: BaseModel) -> dict[str, Any]:
    """Serialize a list/multi-item response in the Hatchet API shape and guard its size."""
    return _guard_size(_dump_item(model))


def _api_error(exc: ApiException) -> RuntimeError:
    """Turn an SDK REST exception into a concise, token-free error for the MCP client."""
    parts: list[str] = []
    if exc.status is not None:
        parts.append(f"status {exc.status}")
    if exc.reason:
        parts.append(str(exc.reason))
    header = "Hatchet API error" + (f": {', '.join(parts)}" if parts else "")
    body = exc.body or exc.data
    detail = f" — {str(body)[:500]}" if body else ""
    return RuntimeError(redact(header + detail))


def _parse_dt(value: str | None, *, field: str) -> datetime | None:
    """Parse an ISO 8601 string into a timezone-aware datetime (assumes UTC if naive)."""
    if value is None or not value.strip():
        return None

    raw = value.strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        raise ValueError(
            f"{field} must be an ISO 8601 datetime "
            f"(e.g. '2026-05-19T00:00:00Z'); got {value!r}"
        ) from None

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_statuses(values: list[str] | None) -> list[V1TaskStatus] | None:
    """Validate run-status strings against the v1 enum, raising on unknown values."""
    if not values:
        return None

    parsed: list[V1TaskStatus] = []
    for value in values:
        try:
            parsed.append(V1TaskStatus(value))
        except ValueError:
            allowed = [s.value for s in V1TaskStatus]
            raise ValueError(
                f"Invalid run status {value!r}. Allowed (v1): {allowed}"
            ) from None
    return parsed


_EnumT = TypeVar("_EnumT", bound=Enum)
_T = TypeVar("_T")


def _parse_enum_list(
    values: list[str] | None, enum_cls: type[_EnumT], *, field: str
) -> list[_EnumT] | None:
    """Validate string values against a (str) enum, raising on any unknown value."""
    if not values:
        return None

    parsed: list[_EnumT] = []
    for value in values:
        try:
            parsed.append(enum_cls(value))
        except ValueError:
            allowed = [getattr(member, "value", member) for member in enum_cls]
            raise ValueError(f"Invalid {field} {value!r}. Allowed: {allowed}") from None
    return parsed


async def _rest_call(call: Callable[[ApiClient, str], _T]) -> _T:
    """Invoke a low-level (synchronous) REST API method off the event loop.

    A handful of reads — v1 events, OTel traces, run timings — have no
    ``aio_*`` feature method, so they call the generated API classes directly. The
    ``ApiClient`` context manager is entered inside the worker thread, mirroring how
    the SDK's own feature clients wrap their sync calls in ``asyncio.to_thread``. The
    callable receives the open client and the tenant ID.
    """
    base = get_rest()

    def _invoke() -> _T:
        with base.client() as client:
            return call(client, base.tenant_id)

    return await asyncio.to_thread(_invoke)


# * Mutation gate
# `_read_only` mirrors config.read_only and is set in main() before serving. Mutating tools
# are registered only when it is False (see server.register_mutating_tools), so they are
# invisible by default; the per-handler `_require_writable()` is defense-in-depth in case a
# handler is reached anyway.
_read_only = True


def _require_writable() -> None:
    """Raise if mutation is disabled. A redundant guard — these tools aren't registered in read-only mode."""
    if _read_only:
        raise RuntimeError(
            "This tool mutates Hatchet state and is disabled in read-only mode. "
            "Restart the server with HATCHET_MCP_READ_ONLY=false to enable mutating tools."
        )


def _destructive(*, idempotent: bool) -> ToolAnnotations:
    """Annotations marking a tool as a non-read-only, destructive mutation so clients can prompt for approval."""
    return ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=idempotent
    )
