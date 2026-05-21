# MCP Server Design

The tool surface, architecture, **uvx distribution**, and security model of the Hatchet operations MCP server.

## 1. Scope

- **In scope**: reading and controlling Hatchet state over the REST API — workflow definitions, runs, tasks, workers, events, crons, schedules, logs, rate limits, and filters.
- **Out of scope**: running workers (the gRPC dispatcher) and defining/deploying workflow code. Those belong to the application via the Hatchet SDK. The MCP server is a control tower, not an executor.

## 2. MCP Tool Surface

The tools exposed to the LLM are split cleanly into **read-only** and **mutating** sets. Mutating tools are subject to the approval gate (§5).

### 2-A. Read-only tools

| Tool | SDK call / endpoint | Description |
|---|---|---|
| `list_workflows` | `h.workflows.list` / `workflow:list` | Workflow **definitions** (name, paused state, version) |
| `get_workflow` | `h.workflows.get` / `workflow:get` | A single workflow (versions, tags, jobs) |
| `list_runs` | `h.runs.list` / `v1-workflow-run:list` | Run list (filter by status, workflow, time range, metadata) |
| `get_run` | `h.runs.get` / `v1-workflow-run:get` | Run detail (task tree, events, DAG shape) |
| `get_run_status` | `h.runs.get_status` / `v1-workflow-run:get-status` | Status only (lightweight polling) |
| `get_run_result` | `h.runs.get_result` | Output of a completed run |
| `list_run_task_events` | `v1-workflow-run:task-events:list` | Task-event timeline for a run |
| `get_run_timings` | `v1-workflow-run:get:timings` | Task waterfall timings |
| `get_task` | `h.runs.get_task_run` / `v1-task:get` | A single task run (input/output/error) |
| `get_task_logs` | `h.logs.list` / `v1-log-line:list` | Task logs (filter by search, level, time range) |
| `get_tenant_logs` | `v1-tenant-log-line:list` | All logs across the tenant |
| `get_trace` | `v1-observability:get-trace` | OpenTelemetry spans for a run |
| `list_workers` | `h.workers.list` / `worker:list` | Worker list (status, slots, registered workflows) |
| `get_worker` | `h.workers.get` / `worker:get` | A single worker |
| `list_events` | `v1-event:list` | Event list (filter by key, time range, run status) |
| `get_event` | `v1-event:get` | A single event (payload) |
| `list_event_keys` | `v1:event-key:list` | Event keys |
| `list_crons` | `h.cron.list` / `cron-workflow:list` | Cron trigger list |
| `get_cron` | `h.cron.get` / `workflow-cron:get` | A single cron |
| `list_scheduled` | `h.scheduled.list` / `workflow-scheduled:list` | Scheduled-run list |
| `list_rate_limits` | `h.rate_limits.list` / `rate-limit:list` | Current rate limits |
| `list_filters` | `h.filters.list` / `v1-filter:list` | Event filter list |
| `get_task_metrics` | `h.metrics.get_task_metrics` | Task counts by status |
| `get_queue_metrics` | `h.metrics.get_queue_metrics` / `tenant:get:queue-metrics` | Queue depth per workflow (native server-side metric) |

### 2-B. Mutating tools

| Tool | SDK call / endpoint | Risk | Description |
|---|---|---|---|
| `trigger_workflow` | `h.runs.create` / `v1-workflow-run:create` | Medium | Trigger a new run (workflowName + input) |
| `cancel_runs` | `h.runs.bulk_cancel` / `v1-task:cancel` | High | Cancel runs/tasks (by ID or filter) |
| `replay_runs` | `h.runs.bulk_replay` / `v1-task:replay` | High | Replay failed/completed runs |
| `restore_task` | `v1-task:restore` | Medium | Restore an evicted durable task |
| `push_event` | `h.event.push` / `event:create` | Medium | Push an event (triggers event-driven workflows) |
| `pause_workflow` / `resume_workflow` | `workflow:update` (`isPaused`) | Medium | Pause/resume a workflow definition |
| `pause_worker` / `resume_worker` | `h.workers.pause/unpause` | Medium | Pause/resume a worker |
| `create_cron` / `delete_cron` | `h.cron.create/delete` | Medium | Create/delete a cron trigger |
| `create_scheduled` / `delete_scheduled` / `reschedule` | `h.scheduled.*` | Medium | Manage scheduled runs |
| `create_filter` / `update_filter` / `delete_filter` | `h.filters.*` | Low | Manage event filters |

## 3. Architecture

```
MCP Client (e.g. Claude Code)
   │  stdio (JSON-RPC)
   ▼
hatchet-mcp server (Python, FastMCP)
   │  Python SDK feature client (async)
   │  Authorization: Bearer <HATCHET_CLIENT_TOKEN>
   ▼
Hatchet REST API  (/api/v1/stable/... + /api/v1/...)
```

- **Framework**: the official `mcp` SDK (FastMCP). Tools are grouped by domain under `tools/` and registered from per-module `READ_TOOLS` / `MUTATING_TOOLS` catalogs (mutating tools only in read-write mode).
- **Transport**: stdio (the MCP standard; the client launches the server as a subprocess).
- **Concurrency**: tool handlers are `async def` and call the SDK's `aio_*` methods.
- **Output**: Pydantic responses are returned as LLM-friendly JSON. Status enums are exposed as-is across the v0/v1 generation split ([concepts §5](overview-and-concepts.md)) and documented in each tool's description — no arbitrary remapping that would lose information (fail-fast philosophy).
- **Error handling**: API 4xx/5xx are returned as structured errors (status code + message). Unmet preconditions such as a missing token fail fast at startup.

## 4. Packaging & Distribution (uvx)

> Requirement: the server must be runnable via `uvx` with **no install step**.

`uvx` (= `uv tool run`) installs a Python package from PyPI or git into an isolated environment on the fly and runs its entry point. The package therefore just needs to be a distributable with a console-script entry point.

### pyproject.toml skeleton
```toml
[project]
name = "hatchet-mcp"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "mcp>=1.2.0",          # or fastmcp
    "hatchet-sdk>=1.33.5", # REST feature client
]

[project.scripts]
hatchet-mcp = "hatchet_mcp.server:main"   # ← entry point invoked by uvx

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

The key is the `[project.scripts]` entry `hatchet-mcp = "package.module:function"`. `main()` starts the stdio MCP server.

### Running it

```bash
# After publishing to PyPI
uvx hatchet-mcp

# Before PyPI — directly from git (works without publishing)
uvx --from git+https://github.com/<org>/hatchet-mcp hatchet-mcp

# Local development
uv run hatchet-mcp
```

### MCP client configuration (Claude Code example)
```json
{
  "mcpServers": {
    "hatchet": {
      "command": "uvx",
      "args": ["hatchet-mcp"],
      "env": {
        "HATCHET_CLIENT_TOKEN": "<your-token>",
        "HATCHET_CLIENT_SERVER_URL": "https://<self-host-url>"
      }
    }
  }
}
```
Or via the CLI: `claude mcp add hatchet -e HATCHET_CLIENT_TOKEN=... -- uvx hatchet-mcp`

### Requirements for uvx compatibility
- A single console-script entry point (`hatchet-mcp`).
- `requires-python` declared (the SDK needs 3.10+).
- Runtime dependencies pinned in `dependencies` (notably a lower bound on `hatchet-sdk`).
- `main()` starts the stdio server with no arguments (uvx invokes it without extra arguments).
- All configuration via **environment variables** (passing flags through a uvx invocation is awkward).
- A standard build backend (e.g. hatchling) and package layout so direct-from-git execution also works.

## 5. Security

- **Mutation gate**: tools like `trigger`/`cancel`/`replay`/`push_event` have large side effects. The server relies on the MCP client's tool approval (human-in-the-loop) and additionally provides a read-only mode flag (`HATCHET_MCP_READ_ONLY=true`) that disables mutating tools entirely.
- **Token never exposed**: the token is never written to logs, tool responses, or error messages ([auth §8](authentication-and-connection.md)).
- **Bulk limits**: broad cancel/replay filters can affect thousands of runs. Bulk operations are capped at 500 by the spec, and the tools surface the affected scope (e.g. the match count) up front to prompt confirmation.
- **Tenant isolation**: one token = one tenant. For multiple tenants, see [auth §5](authentication-and-connection.md).

---

← [README](README.md) | Related: [Concepts](overview-and-concepts.md) · [API](rest-api-reference.md) · [Auth](authentication-and-connection.md) · [SDK](sdk-and-communication.md)
