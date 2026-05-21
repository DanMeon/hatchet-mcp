"""Workers: list, plus pause/resume (mutating)."""

from collections.abc import Callable
from typing import Annotated, Any

from hatchet_sdk.clients.rest.exceptions import ApiException
from mcp.types import ToolAnnotations
from pydantic import Field

from hatchet_mcp._shared import _api_error, _destructive, _dump, _require_writable
from hatchet_mcp.client import get_hatchet


async def list_workers() -> dict[str, Any]:
    h = get_hatchet()
    try:
        result = await h.workers.aio_list()
    except ApiException as exc:
        raise _api_error(exc) from None
    return _dump(result)


async def get_worker(
    worker_id: Annotated[str, Field(description="The worker ID (UUID) to fetch.")],
) -> dict[str, Any]:
    h = get_hatchet()
    try:
        result = await h.workers.aio_get(worker_id)
    except ApiException as exc:
        raise _api_error(exc) from None
    return _dump(result)


async def pause_worker(
    worker_id: Annotated[str, Field(description="The worker ID (UUID) to pause.")],
) -> dict[str, Any]:
    _require_writable()
    h = get_hatchet()
    try:
        result = await h.workers.aio_pause(worker_id)
    except ApiException as exc:
        raise _api_error(exc) from None
    return _dump(result)


async def resume_worker(
    worker_id: Annotated[str, Field(description="The worker ID (UUID) to resume.")],
) -> dict[str, Any]:
    _require_writable()
    h = get_hatchet()
    try:
        result = await h.workers.aio_unpause(worker_id)
    except ApiException as exc:
        raise _api_error(exc) from None
    return _dump(result)


READ_TOOLS: list[tuple[Callable[..., Any], str, str]] = [
    (
        list_workers,
        "list_workers",
        "List workers in the tenant with their status, slots, and registered actions.",
    ),
    (
        get_worker,
        "get_worker",
        "Get a single worker by its ID, with its slot state, recent runs, and registered actions.",
    ),
]

MUTATING_TOOLS: list[tuple[Callable[..., Any], str, str, ToolAnnotations]] = [
    (
        pause_worker,
        "pause_worker",
        "Pause a worker so it stops picking up new work.",
        _destructive(idempotent=True),
    ),
    (
        resume_worker,
        "resume_worker",
        "Resume a paused worker.",
        _destructive(idempotent=True),
    ),
]
