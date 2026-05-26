"""URI-addressable read-only views of the same objects the read tools return.

Each handler delegates to a read tool through the same reliability wrapper used at tool
registration, so resources inherit the 30s deadline, retry on 5xx/429/transport errors,
and structured ``tool.ok``/``tool.error`` stderr records. The payload is byte-for-byte
the tool's _dump output serialized to a JSON string. Resources are always available and
independent of the mutation gate. ``register`` is called from server/main (and from the
test harness).
"""

import json
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.fastmcp import FastMCP

from hatchet_mcp._shared import _reliability_wrap
from hatchet_mcp.tools.runs import get_run, get_run_status
from hatchet_mcp.tools.server_info import get_server_info
from hatchet_mcp.tools.workers import list_workers
from hatchet_mcp.tools.workflows import get_workflow, list_workflows


def _wrap(
    fn: Callable[..., Awaitable[dict[str, Any]]],
) -> Callable[..., Awaitable[Any]]:
    """Reuse the tool reliability wrapper so resources retry, deadline, and emit telemetry."""
    return _reliability_wrap(fn, retry=True)


_wrapped_list_workflows = _wrap(list_workflows)
_wrapped_get_workflow = _wrap(get_workflow)
_wrapped_list_workers = _wrap(list_workers)
_wrapped_get_run = _wrap(get_run)
_wrapped_get_run_status = _wrap(get_run_status)
_wrapped_get_server_info = _wrap(get_server_info)


async def resource_workflows() -> str:
    return json.dumps(await _wrapped_list_workflows(), ensure_ascii=False)


async def resource_workflow(workflow_id: str) -> str:
    return json.dumps(await _wrapped_get_workflow(workflow_id), ensure_ascii=False)


async def resource_workers() -> str:
    return json.dumps(await _wrapped_list_workers(), ensure_ascii=False)


async def resource_run(workflow_run_id: str) -> str:
    return json.dumps(await _wrapped_get_run(workflow_run_id), ensure_ascii=False)


async def resource_run_status(workflow_run_id: str) -> str:
    return json.dumps(
        await _wrapped_get_run_status(workflow_run_id), ensure_ascii=False
    )


async def resource_server_info() -> str:
    return json.dumps(await _wrapped_get_server_info(), ensure_ascii=False)


def register(mcp: FastMCP) -> None:
    """Register every read-only resource on the given server."""
    mcp.resource(
        "hatchet://workflows",
        name="workflows",
        description="All workflow definitions in the tenant (JSON).",
        mime_type="application/json",
    )(resource_workflows)
    mcp.resource(
        "hatchet://workflows/{workflow_id}",
        name="workflow",
        description="One workflow definition by ID — versions, tags, jobs (JSON).",
        mime_type="application/json",
    )(resource_workflow)
    mcp.resource(
        "hatchet://workers",
        name="workers",
        description="All workers in the tenant with status, slots, and registered actions (JSON).",
        mime_type="application/json",
    )(resource_workers)
    mcp.resource(
        "hatchet://runs/{workflow_run_id}",
        name="run",
        description="One workflow run in detail — task tree / DAG shape, inputs, outputs (JSON).",
        mime_type="application/json",
    )(resource_run)
    mcp.resource(
        "hatchet://runs/{workflow_run_id}/status",
        name="run-status",
        description="Status only of one workflow run — lightweight polling (JSON).",
        mime_type="application/json",
    )(resource_run_status)
    mcp.resource(
        "hatchet://server/info",
        name="server-info",
        description="Self-describing snapshot of this hatchet-mcp instance — mode, tool counts, "
        "server_url_source, SDK and Python versions (JSON). Byte-identical to get_server_info.",
        mime_type="application/json",
    )(resource_server_info)
