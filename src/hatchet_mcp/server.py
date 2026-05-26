"""FastMCP stdio server exposing Hatchet over its REST API.

Thirty-five read-only tools are always registered; twenty-one mutating tools (run control,
event push, pause/resume, cron/scheduled/filter management, webhook intake) are registered
only when ``HATCHET_MCP_READ_ONLY=false`` and carry destructive annotations so clients can
prompt for approval. Tools live in ``tools/`` by domain, each exposing READ_TOOLS /
MUTATING_TOOLS catalogs; this module aggregates them, registers what the mode allows, and
serves. All operational tools map to verified ``hatchet-sdk`` calls and return the SDK's
Pydantic responses serialized to JSON (``by_alias=True``, matching the Hatchet
REST/dashboard shape); ``get_server_info`` is the one self-describing exception (see
``tools/server_info.py``).
"""

import logging

from mcp.server.fastmcp import FastMCP

from hatchet_mcp import _shared, app, prompts, resources
from hatchet_mcp._logging import emit
from hatchet_mcp.client import init_hatchet
from hatchet_mcp.config import ConfigError, load_config
from hatchet_mcp.tools import (
    events,
    filters,
    meta,
    observability,
    runs,
    schedules,
    server_info,
    tasks,
    webhooks,
    workers,
    workflows,
)

# SDK and transport loggers that would echo Authorization headers (full Bearer token) to
# stderr when a downstream process sets LOG_LEVEL=DEBUG. Forcing WARNING blocks that leak path.
_DEPENDENCY_LOGGERS = (
    "hatchet_sdk",
    "aiohttp",
    "aiohttp.client",
    "httpx",
    "httpcore",
    "grpc",
    "urllib3",
)

_TOOL_MODULES = (
    workflows,
    runs,
    tasks,
    workers,
    events,
    schedules,
    filters,
    webhooks,
    observability,
    meta,
    server_info,
)

READ_TOOLS = [tool for module in _TOOL_MODULES for tool in module.READ_TOOLS]
MUTATING_TOOLS = [tool for module in _TOOL_MODULES for tool in module.MUTATING_TOOLS]


def muzzle_dependency_loggers() -> None:
    """Force SDK/transport loggers to WARNING so Bearer tokens cannot leak via their debug output."""
    for logger_name in _DEPENDENCY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def register_read_tools(mcp: FastMCP) -> None:
    """Register every read-only tool, wrapped with retry+deadline (reads are inherently idempotent).

    Every read tool carries ``readOnlyHint=True, destructiveHint=False`` so clients that
    respect annotations (Cursor, Claude Code) can skip approval prompts. The ``title`` field
    (MCP 2025-06-18) is a display-name derived from the snake_case tool name.
    """
    for fn, name, description in READ_TOOLS:
        mcp.add_tool(
            _shared._reliability_wrap(fn, retry=True),
            name=name,
            title=_shared._humanize_tool_name(name),
            description=description,
            annotations=_shared._read_only_annotations(),
        )


def register_mutating_tools(mcp: FastMCP) -> None:
    """Register every mutating tool. Idempotent handlers get retry+deadline; non-idempotent get deadline only.

    Read-only mode skips this entirely so mutations are invisible to the protocol by default.
    """
    for fn, name, description, annotations in MUTATING_TOOLS:
        wrapped = _shared._reliability_wrap(fn, retry=bool(annotations.idempotentHint))
        mcp.add_tool(
            wrapped,
            name=name,
            title=_shared._humanize_tool_name(name),
            description=description,
            annotations=annotations,
        )


def main() -> None:
    """Entry point: validate config, fail fast, then serve over stdio.

    All diagnostics go to stderr — stdout is the MCP JSON-RPC channel.
    """
    muzzle_dependency_loggers()

    try:
        config = load_config()
        init_hatchet()
    except ConfigError as exc:
        emit("server.error", error=str(exc))
        raise SystemExit(1) from None

    _shared._read_only = config.read_only
    register_read_tools(app.mcp)
    resources.register(app.mcp)
    prompts.register(app.mcp)
    # The instructions are read at handshake time, so updating them here (no public setter
    # exists) makes the advertised mode match the tools that are actually registered.
    app.mcp._mcp_server.instructions = app._build_instructions(
        read_only=config.read_only
    )
    if not config.read_only:
        register_mutating_tools(app.mcp)

    tool_count = len(READ_TOOLS) + (0 if config.read_only else len(MUTATING_TOOLS))
    url_state = "override" if config.server_url_override else "token"
    emit(
        "server.start",
        read_only=config.read_only,
        server_url=url_state,
        tools=tool_count,
    )

    app.mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
