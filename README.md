# hatchet-mcp

[![PyPI version](https://img.shields.io/pypi/v/hatchet-mcp.svg)](https://pypi.org/project/hatchet-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/hatchet-mcp.svg)](https://pypi.org/project/hatchet-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/DanMeon/hatchet-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/DanMeon/hatchet-mcp/actions/workflows/ci.yml)

> **Unofficial, community project** — not affiliated with, sponsored by, or endorsed by Hatchet.
> It is an independent integration that talks to Hatchet only through the public REST API via the official `hatchet-sdk`.

An operational **MCP (Model Context Protocol) server** for [Hatchet](https://hatchet.run),
the durable orchestration engine. It exposes Hatchet's live state — and, optionally, its
control surface — to an LLM over the Hatchet **REST API** (via the official `hatchet-sdk`
feature clients) using the **stdio** transport.

It is a control tower for a Hatchet tenant: inspect workflow definitions, runs, tasks,
logs, workers, events, cron/scheduled triggers, rate limits, filters, queue/task metrics,
run timings, and OpenTelemetry traces — and, when explicitly enabled, trigger/cancel/replay
runs, push events, pause/resume workflows and workers, and manage cron/scheduled/filters.

**Read-only by default.** Out of the box it never triggers, cancels, replays, or mutates
anything, so it is safe to point at a production tenant. Mutating tools are unregistered
until you opt in with `HATCHET_MCP_READ_ONLY=false`.

> Design background lives in [`docs/init/`](docs/init/). See [`docs/init/mcp-server-design.md`](docs/init/mcp-server-design.md)
> for the full tool surface and security model.

## Quick start

1. **Get a token.** Visit your Hatchet dashboard → **Settings → API Tokens → Create**. The token is shown only once. (For self-hosted with an internal token URL, note the public REST URL — set it as `HATCHET_CLIENT_SERVER_URL`.)
2. **Run the server.** `uvx hatchet-mcp` (works with no prior install beyond `uv` itself).
3. **Set the token.** Either `export HATCHET_CLIENT_TOKEN=<your-token>` in your shell, or put it in your MCP client's `env:` block — see [Use it from an MCP client](#use-it-from-an-mcp-client) for a copy-pasteable `.mcp.json`.
4. **Ask the LLM.** Try "list my workflows" or "show runs from the last hour". The 24 read tools are available immediately; mutating tools stay hidden until you set `HATCHET_MCP_READ_ONLY=false`.

## Install & run

```bash
# From PyPI
uvx hatchet-mcp

# Directly from a git checkout, no install
uvx --from git+https://github.com/DanMeon/hatchet-mcp hatchet-mcp

# From a local clone
uvx --from . hatchet-mcp

# Local development
uv run hatchet-mcp
```

All launch the same stdio MCP server. Configuration is **environment-only** because `uvx`
makes passing CLI flags awkward. With no `HATCHET_CLIENT_TOKEN` the server **fails fast**
and exits non-zero — it never starts a half-configured server.

## Use it from an MCP client

The repo ships a [`.mcp.json.example`](.mcp.json.example) for project-scoped setup. Copy it to
`.mcp.json` (gitignored, so your token stays local) and fill in the token:

```bash
cp .mcp.json.example .mcp.json
# then edit .mcp.json → set HATCHET_CLIENT_TOKEN
```

Or register it directly with the CLI:

```bash
claude mcp add hatchet -e HATCHET_CLIENT_TOKEN=<your-token> -- uvx hatchet-mcp
```

Or the JSON config block (Claude Desktop / Claude Code). This example opts **into** the
mutating tools:

```json
{
  "mcpServers": {
    "hatchet": {
      "command": "uvx",
      "args": ["hatchet-mcp"],
      "env": {
        "HATCHET_CLIENT_TOKEN": "<your-token>",
        "HATCHET_CLIENT_SERVER_URL": "https://<self-host-url>",
        "HATCHET_MCP_READ_ONLY": "false"
      }
    }
  }
}
```

Omit `HATCHET_MCP_READ_ONLY` (or set it to `true`) to keep the safe, read-only posture.

### Multiple tenants

A Hatchet token is scoped to exactly one tenant, so to operate several tenants you run **one
server instance per tenant** — each with its own token — and register them as distinct MCP
servers. No special configuration is needed; the client picks the server by name.

```json
{
  "mcpServers": {
    "hatchet-prod": {
      "command": "uvx",
      "args": ["hatchet-mcp"],
      "env": { "HATCHET_CLIENT_TOKEN": "<prod-token>" }
    },
    "hatchet-staging": {
      "command": "uvx",
      "args": ["hatchet-mcp"],
      "env": { "HATCHET_CLIENT_TOKEN": "<staging-token>", "HATCHET_MCP_READ_ONLY": "false" }
    }
  }
}
```

This keeps tenant tokens in separate processes (no token mixing). See
[`docs/init/multitenancy-and-dependencies.md`](docs/init/multitenancy-and-dependencies.md) §1 for the rationale and the
alternative (a single server with a `tenant` argument), which was considered and not adopted.

## Configuration (environment only)

| Env var | Required | Default | Meaning |
|---|---|---|---|
| `HATCHET_CLIENT_TOKEN` | **yes** | — | Hatchet API token (a JWT). Server URL and tenant are decoded from it. |
| `HATCHET_CLIENT_SERVER_URL` | no | from token | REST base URL override (for a self-host whose token embeds an unreachable internal URL). |
| `HATCHET_MCP_READ_ONLY` | no | `true` | The mutation gate. `true` registers only the 24 read tools; `false` additionally registers the 17 mutating tools. Accepts `true/false/1/0/yes/no/on/off`; an unrecognized value fails fast. |

If `HATCHET_CLIENT_TOKEN` is missing the server **fails fast at startup** and exits — no
silent fallback. The token is never logged, echoed, or included in any error message
(even when the SDK rejects it, only the exception *type* is surfaced).

## Safety model

This server can drive a production orchestrator, so safety is layered:

- **Read-only by default.** `HATCHET_MCP_READ_ONLY` defaults to `true`. In that mode the 17
  mutating tools are **not registered at all** — an MCP client cannot see or call them.
- **Defense in depth.** Even if a mutating handler is somehow reached in read-only mode, it
  re-checks the gate and refuses.
- **Destructive annotations.** Every mutating tool is advertised with
  `destructiveHint=true` (and an accurate `idempotentHint`) so MCP clients can require
  human approval before each call.
- **Bulk guardrails.** `cancel_runs` / `replay_runs` default to a **dry run** — they return
  the matching run IDs *without acting*. You must re-call with `dry_run=false` to mutate.
  They also **refuse to act on more than 500 matching runs**, forcing a narrower filter.
- **Token confidentiality.** The token is never written to stdout (the JSON-RPC channel),
  stderr, tool responses, or error messages.
- **Single tenant.** One token scopes the whole server to one Hatchet tenant (its `sub`
  claim).

## Tools

41 tools total: **24 read-only** (always registered) + **17 mutating** (registered only
when `HATCHET_MCP_READ_ONLY=false`).

### Read-only (24) — always available

| Tool | Hatchet SDK / REST call | Purpose |
|---|---|---|
| `list_workflows` | `h.workflows.aio_list` | List workflow **definitions** (name, paused, versions) |
| `get_workflow` | `h.workflows.aio_get` | One workflow definition by ID |
| `list_runs` | `h.runs.aio_list` | List workflow/task runs (time, status, workflow, worker, metadata filters). **Excludes payloads by default** — use `get_run` for inputs/outputs |
| `get_run` | `h.runs.aio_get` | One run in detail (task tree / DAG shape, inputs, outputs) |
| `get_run_status` | `h.runs.aio_get_status` | Status only — lightweight polling |
| `get_task` | `h.runs.aio_get_task_run` | One task run by ID (status, attempt, worker, I/O) |
| `get_task_logs` | `h.logs.aio_list` | Log lines for a single task run |
| `list_task_events` | `TaskApi.v1_task_event_list` | Orchestration event timeline for a task run (state transitions) |
| `list_workers` | `h.workers.aio_list` | List workers (status, slots, registered actions) |
| `get_worker` | `h.workers.aio_get` | One worker by ID (slot state, recent runs, registered actions) |
| `list_events` | `EventApi.v1_event_list` | List ingested events (key, time, workflow, run-status, metadata) |
| `get_event` | `EventApi.v1_event_get` | One event with full payload + triggered-run summary |
| `list_event_keys` | `EventApi.v1_event_key_list` | Distinct event keys in the tenant |
| `list_crons` | `h.cron.aio_list` | List cron triggers |
| `get_cron` | `h.cron.aio_get` | One cron trigger by ID |
| `list_scheduled` | `h.scheduled.aio_list` | List scheduled (one-off, future) runs |
| `list_rate_limits` | `h.rate_limits.aio_list` | Rate limits with current consumption |
| `list_filters` | `h.filters.aio_list` | Event filters (CEL expressions) |
| `get_filter` | `h.filters.aio_get` | One event filter by ID |
| `cel_debug` | `h.cel.aio_debug` | Test a CEL expression against sample input (no filter created) |
| `get_queue_metrics` | `h.metrics.aio_get_queue_metrics` | Native per-queue depth |
| `get_task_metrics` | `h.metrics.aio_get_task_metrics` | Task counts grouped by status |
| `get_run_timings` | `WorkflowRunsApi.v1_workflow_run_get_timings` | Task waterfall timings for a run |
| `get_trace` | `ObservabilityApi.v1_observability_get_trace` | OpenTelemetry spans for a run |

### Mutating (17) — only when `HATCHET_MCP_READ_ONLY=false`

| Tool | Hatchet SDK / REST call | Idempotent | Purpose |
|---|---|---|---|
| `trigger_workflow` | `h.runs.aio_create` | no | Trigger a new workflow run by name |
| `cancel_runs` | `h.runs.aio_bulk_cancel` | no | Cancel runs by IDs or filter — **dry-run default, 500 cap** |
| `replay_runs` | `h.runs.aio_bulk_replay` | no | Replay runs by IDs or filter — **dry-run default, 500 cap** |
| `restore_task` | `TaskApi.v1_task_restore` | no | Restore an evicted durable task |
| `push_event` | `EventApi.event_create` | no | Push an event (may trigger event-driven workflows) |
| `pause_workflow` | `WorkflowApi.workflow_update` (`isPaused=true`) | yes | Pause a workflow definition |
| `resume_workflow` | `WorkflowApi.workflow_update` (`isPaused=false`) | yes | Resume a paused workflow definition |
| `pause_worker` | `h.workers.aio_pause` | yes | Pause a worker |
| `resume_worker` | `h.workers.aio_unpause` | yes | Resume a worker |
| `create_cron` | `h.cron.aio_create` | no | Create a cron trigger |
| `delete_cron` | `h.cron.aio_delete` | yes | Delete a cron trigger |
| `create_scheduled` | `h.scheduled.aio_create` | no | Schedule a one-off future run |
| `delete_scheduled` | `h.scheduled.aio_delete` | yes | Delete a scheduled run |
| `reschedule` | `h.scheduled.aio_update` | yes | Change a scheduled run's trigger time |
| `create_filter` | `h.filters.aio_create` | no | Create an event filter (CEL) |
| `update_filter` | `h.filters.aio_update` | yes | Update an event filter |
| `delete_filter` | `h.filters.aio_delete` | yes | Delete an event filter |

> **Status enums differ by engine generation** and are passed through unchanged (no lossy
> remapping). v1 runs/tasks use `QUEUED · RUNNING · COMPLETED · CANCELLED · FAILED`;
> legacy objects use `PENDING · RUNNING · SUCCEEDED · FAILED · CANCELLED · QUEUED · BACKOFF`.
> See [`docs/init/overview-and-concepts.md`](docs/init/overview-and-concepts.md) §5.

## Response size and limits

A live tenant can hold thousands of runs, each with large input/output payloads, so a naive
`list_runs` can return several megabytes and blow past an MCP client's context window. The
read tools follow the same "keep lists small, fetch detail on demand" pattern as the GitHub,
Sentry, and Grafana MCP servers:

- **Lists exclude heavy payloads by default.** `list_runs` returns run metadata — id, status,
  workflow, timings — but not each run's input/output. Pass `include_payloads=true` (ideally
  with a small `limit`) for the full rows, or fetch one run's payloads with `get_run`.
- **Every list tool defaults and caps its `limit`.** Unset resolves to **50**, the hard cap is
  **100**, and a value below 1 is rejected. `get_task_logs` is the exception — 1000 log lines,
  capped at 1000. Use `offset` to page where the tool exposes it.
- **Single-item `get_*` tools are never truncated.** `get_run` / `get_task` / `get_event`
  return the whole object — the one item is the point, so they bypass the size guard below.
- **A ~500 KB ceiling backstops every list result.** Anything larger is rejected with a
  message explaining how to narrow it (smaller `limit`, tighter time window or statuses)
  instead of silently overflowing your context. This also protects tools whose upstream call
  takes no `limit`, such as `list_workers`.

## Resources & prompts

In addition to tools, the server exposes **read-only MCP resources** (URI-addressable views
that reuse the read tools, so their JSON is identical) and **operator prompts**. Both are
always available and add no mutating surface.

Resources:

| URI | Backed by |
|---|---|
| `hatchet://workflows` | `list_workflows` |
| `hatchet://workflows/{workflow_id}` | `get_workflow` |
| `hatchet://workers` | `list_workers` |
| `hatchet://runs/{workflow_run_id}` | `get_run` |
| `hatchet://runs/{workflow_run_id}/status` | `get_run_status` |

Prompts:

| Prompt | Arguments | Orchestrates |
|---|---|---|
| `triage_failed_runs` | `hours` (default `24`) | `list_runs` → `get_run` → `get_task_logs` |
| `debug_run` | `workflow_run_id` | `get_run` → `get_run_timings` → `get_task_logs` → `get_trace` |
| `tenant_health` | `hours` (default `24`) | `get_queue_metrics` → `get_task_metrics` → `list_workers` |

## How it talks to Hatchet

```
MCP client (Claude Code, …)
   │  stdio (JSON-RPC)
   ▼
hatchet-mcp (Python, FastMCP)
   │  hatchet-sdk feature clients, async aio_* methods
   │  Authorization: Bearer <HATCHET_CLIENT_TOKEN>
   ▼
Hatchet REST API   (/api/v1/stable/… + /api/v1/…)
```

REST only — never the gRPC worker dispatcher protocol. A single token scopes the server to
a single tenant (resolved from the token's `sub` claim by the SDK).

## Development

```bash
uv sync                 # install runtime + dev deps on Python 3.10+
uv run pytest           # full test suite — needs no token, performs no real mutation
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyright
uv run hatchet-mcp      # needs HATCHET_CLIENT_TOKEN in the environment
```

## Contributing

Contributions are welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for development setup,
quality gates, project conventions, and the maintainer release process.

## Security

`hatchet-mcp` can drive a production orchestrator and handles an API token. Please report
vulnerabilities **privately** — see [`SECURITY.md`](SECURITY.md). Don't open a public issue
for security reports.

## License

MIT — see [`LICENSE`](LICENSE).

"Hatchet" and any related marks belong to their respective owners. This is an independent
project and is not affiliated with or endorsed by Hatchet.
