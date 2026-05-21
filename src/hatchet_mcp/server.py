"""FastMCP stdio server exposing Hatchet over its REST API.

Twenty-four read-only tools are always registered; seventeen mutating tools (run control, event
push, pause/resume, cron/scheduled/filter management) are registered only when
``HATCHET_MCP_READ_ONLY=false`` and carry destructive annotations so clients can prompt for
approval. Tools live in ``tools/`` by domain, each exposing READ_TOOLS / MUTATING_TOOLS
catalogs; this module aggregates them, registers what the mode allows, and serves. All tools
map to verified ``hatchet-sdk`` calls and return the SDK's Pydantic responses serialized to
JSON (``by_alias=True``, matching the Hatchet REST/dashboard shape).
"""

import sys

from mcp.server.fastmcp import FastMCP

from hatchet_mcp import _shared, app, prompts, resources
from hatchet_mcp.client import init_hatchet
from hatchet_mcp.config import ConfigError, load_config
from hatchet_mcp.tools import (
    events,
    filters,
    observability,
    runs,
    schedules,
    tasks,
    workers,
    workflows,
)

_TOOL_MODULES = (
    workflows,
    runs,
    tasks,
    workers,
    events,
    schedules,
    filters,
    observability,
)

READ_TOOLS = [tool for module in _TOOL_MODULES for tool in module.READ_TOOLS]
MUTATING_TOOLS = [tool for module in _TOOL_MODULES for tool in module.MUTATING_TOOLS]


def register_read_tools(mcp: FastMCP) -> None:
    """Register every read-only tool. Always called — these are visible in both modes."""
    for fn, name, description in READ_TOOLS:
        mcp.add_tool(fn, name=name, description=description)


def register_mutating_tools(mcp: FastMCP) -> None:
    """Register every mutating tool. Called only when read-only mode is off, keeping them hidden by default."""
    for fn, name, description, annotations in MUTATING_TOOLS:
        mcp.add_tool(fn, name=name, description=description, annotations=annotations)


def main() -> None:
    """Entry point: validate config, fail fast, then serve over stdio.

    All diagnostics go to stderr — stdout is the MCP JSON-RPC channel.
    """
    try:
        config = load_config()
        init_hatchet()
    except ConfigError as exc:
        print(f"hatchet-mcp: {exc}", file=sys.stderr, flush=True)
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
    url_state = "override" if config.server_url_override else "from token"
    print(
        f"hatchet-mcp: starting stdio server "
        f"(read_only={config.read_only}, server_url={url_state}, tools={tool_count})",
        file=sys.stderr,
        flush=True,
    )

    app.mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
