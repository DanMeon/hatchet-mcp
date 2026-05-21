"""The FastMCP app instance and its mode-dependent server instructions.

Holds only the ``FastMCP`` singleton and the instructions text. Tool/resource/prompt
modules get their shared helpers from ``_shared``; ``server`` wires everything together
and serves. Keeping the app instance separate from the helpers keeps the import graph
acyclic (``server`` → tools → ``_shared``).
"""

from mcp.server.fastmcp import FastMCP

_INSTRUCTIONS_BASE = """\
Operational view of a Hatchet orchestration tenant over its REST API.

Use these tools to inspect workflow definitions, workflow/task runs, run status, task
logs, workers, events, cron and scheduled triggers, rate limits, and event filters, plus
queue/task metrics, run timings, and OpenTelemetry traces.

Run/task status values come straight from Hatchet and differ by engine generation:
v1 runs and tasks use QUEUED / RUNNING / COMPLETED / CANCELLED / FAILED, while legacy
objects may use PENDING / SUCCEEDED / BACKOFF and similar. They are reported verbatim.
A single token scopes every call to one tenant."""

_INSTRUCTIONS_READ_ONLY = """\

This server is in READ-ONLY mode: it never triggers, cancels, replays, or otherwise
mutates anything, and no mutating tools are exposed. Start it with
HATCHET_MCP_READ_ONLY=false to additionally enable mutating tools (run control, event
push, pause/resume, and cron/scheduled/filter management)."""

_INSTRUCTIONS_READ_WRITE = """\

This server is in READ-WRITE mode (HATCHET_MCP_READ_ONLY=false): besides the read-only
tools above it exposes MUTATING tools — trigger/cancel/replay runs, restore tasks, push
events, pause/resume workflows and workers, and manage cron triggers, scheduled runs,
and event filters. Every mutating tool is annotated as destructive so clients can
require approval. Bulk cancel/replay default to a dry-run preview and refuse to act on
more than 500 matching runs."""


def _build_instructions(*, read_only: bool) -> str:
    """Compose the server instructions, telling clients which mode (and tools) are active."""
    suffix = _INSTRUCTIONS_READ_ONLY if read_only else _INSTRUCTIONS_READ_WRITE
    return _INSTRUCTIONS_BASE + suffix


# Default to the read-only posture at import time; main() overrides it from config before serving.
mcp = FastMCP("hatchet-mcp", instructions=_build_instructions(read_only=True))
