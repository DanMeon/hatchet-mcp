"""Self-describing diagnostics: a single field bag of facts the LLM can pull to disambiguate tool errors.

Exposed both as a read tool (``get_server_info``) and as a resource
(``hatchet://server/info``, registered in ``resources.py``) — both delegate to
``_build_server_info`` so the two surfaces stay byte-identical (AC-8). The payload
never carries the Hatchet token: ``server_url_source`` is an *origin label*
(``"token"`` or ``"override"``), not the URL itself.
"""

import importlib.metadata
import os
import sys
from collections.abc import Callable
from typing import Any

from mcp.types import ToolAnnotations

from hatchet_mcp import _shared
from hatchet_mcp.config import SERVER_URL_ENV


def _build_server_info() -> dict[str, Any]:
    """Compute the diagnostics payload — read by both the tool and the resource handler."""
    # Late import to avoid a circular dependency: server.py imports this module to aggregate
    # its READ_TOOLS into the global catalog, so we resolve `server` only at call time.
    from hatchet_mcp import server as server_mod

    server_url_override = (os.environ.get(SERVER_URL_ENV) or "").strip()
    return {
        "read_only": _shared._read_only,
        "read_tool_count": len(server_mod.READ_TOOLS),
        "mutating_tool_count": len(server_mod.MUTATING_TOOLS),
        "server_url_source": "override" if server_url_override else "token",
        "hatchet_sdk_version": importlib.metadata.version("hatchet-sdk"),
        "python_version": (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        ),
    }


async def get_server_info() -> dict[str, Any]:
    """Return a self-describing snapshot of this server: mode, tool counts, SDK + Python versions."""
    return _build_server_info()


READ_TOOLS: list[tuple[Callable[..., Any], str, str]] = [
    (
        get_server_info,
        "get_server_info",
        "Return a snapshot of this hatchet-mcp instance — read_only mode, registered read/mutating "
        "tool counts, server_url_source (token vs override), hatchet-sdk version, Python version. "
        "Use when a tool error suggests the mode or config may be wrong. Never includes the token.",
    ),
]

MUTATING_TOOLS: list[tuple[Callable[..., Any], str, str, ToolAnnotations]] = []
