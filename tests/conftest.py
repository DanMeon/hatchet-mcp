"""Shared fixtures.

Tools, resources, and prompts are registered once on the module-level ``app.mcp`` singleton.
Any test that registers mutating tools or flips the read-only gate must leave both as it found
them, so ``server_module`` snapshots and restores the tool registry and the ``_read_only`` flag.
"""

import pytest

import hatchet_mcp._shared as shared
import hatchet_mcp.app as app
import hatchet_mcp.server as server
from hatchet_mcp import prompts, resources

# Register the always-on surface (24 read tools + resources + prompts) once for the session.
server.register_read_tools(app.mcp)
resources.register(app.mcp)
prompts.register(app.mcp)


@pytest.fixture
def server_module():
    """Yield the shared app module, restoring its tool registry and read-only flag after."""
    registry = app.mcp._tool_manager._tools
    snapshot = dict(registry)
    read_only = shared._read_only
    try:
        yield app
    finally:
        registry.clear()
        registry.update(snapshot)
        shared._read_only = read_only
