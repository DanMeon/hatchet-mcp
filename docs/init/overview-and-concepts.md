# Hatchet Overview and Core Concepts

> Designing an MCP server requires a precise understanding of Hatchet's object model and exactly what an operator can query and control. This document provides that foundation.

## 1. What Is Hatchet

Hatchet is an **orchestration engine for background jobs, AI agents, and durable workflows**. Its defining characteristic is that it **uses PostgreSQL as its durability layer**: workflow state, execution history, and inputs/outputs are stored in Postgres rather than in a volatile broker such as Redis. This makes it easy to self-host and treats correctness, reliability, horizontal scalability, and observability as first-class goals.

SDKs are available in four languages: **Python, TypeScript, Go, and Ruby**.

Source: `README.md:31-49`

## 2. Core Object Model

The terminology is defined first.

| Term | Definition |
|---|---|
| **Task** | The smallest unit of work: a single function that receives an input and a context. Every Hatchet task is durable (state and results are preserved in Postgres even after completion). A task may run standalone (`FUNCTION`) or as a node in a DAG. |
| **Workflow (DAG)** | A dependency graph of tasks (directed acyclic graph). All dependencies are declared before execution; Hatchet schedules them in topological order, runs independent tasks in parallel, and passes each parent's output as its children's input. `WorkflowKind = DAG` |
| **Workflow Run** | A single execution instance of a workflow (or a standalone task). It has a unique external ID (UUID), a status, timestamps, an input, and an output. The canonical v1 object is `V1WorkflowRun`. |
| **Task Run / Step Run** | A single execution attempt of one task within a workflow run. In v1 it is called a **Task Run** (`V1TaskSummary`); in v0 (legacy) it was called a **Step Run** (`StepRun`). It has its own status, retry count, attempt number, and input/output/error. |
| **Worker** | A long-running process that registers and executes tasks. It connects to the Hatchet engine over **bidirectional gRPC** to receive task assignments and report results. It has a configurable concurrency limit defined by **slots** (default 100). The same task can be registered by multiple workers to scale horizontally. |
| **Event** | A message with a name (key) and a JSON payload. When an event key matches a task's `on_events` declaration, it triggers a workflow run. Wildcard matching (`subscription:*`) is supported. |
| **Cron** | A trigger that runs a task on a schedule using a POSIX cron expression (5 or 6 fields). Managed via code, the dashboard, or the API. |
| **Scheduled Run** | A one-shot trigger that runs once at a specific UTC time. Bulk deletion and rescheduling are supported. |
| **Tenant** | The unit of multi-tenant isolation. A single Hatchet instance hosts multiple fully isolated tenants. **Nearly every API path is scoped by `{tenant}` (a UUID)**, and a token is always bound to a specific tenant. |
| **Rate Limit** | A throttle on task execution. It can be static (a global limit declared at worker startup) or dynamic (a key extracted from the input/metadata via CEL and evaluated at runtime). |
| **Filter** | A declarative CEL expression attached to a workflow. It gates whether an incoming event actually creates a run. Its `scope` must match the event scope. |
| **Webhook Worker** | An inbound endpoint that converts external webhook HTTP POSTs (Stripe, GitHub, Slack, etc.) into Hatchet events. |
| **Durable Task / Durable Execution** | A task that uses durability primitives such as `wait` (sleeping or waiting for an event) and child-task spawning. Every wait writes a checkpoint to the durable event log, so after a retry or eviction the task replays from the last checkpoint rather than from the start, yielding effectively exactly-once execution. Logic between checkpoints must be deterministic. |
| **Task Eviction** | When a durable task blocks on a wait, the engine **evicts** the task from the worker to free its slot. Once the wait condition is satisfied, the task is requeued and reassigned, then replays from its checkpoint. Non-durable tasks occupy a slot for their entire lifetime. |

Source: `frontend/docs/pages/v1/tasks.mdx`, `directed-acyclic-graphs.mdx`, `workers.mdx`, `events.mdx`, `cron-runs.mdx`, `scheduled-runs.mdx`, `rate-limits.mdx`, `durable-tasks.mdx`, `task-eviction.mdx`, and `api-contracts/openapi/components/schemas/v1/*.yaml`

### Object Relationships (at a glance)

```
Tenant
 ├─ Workflow (definition, DAG or standalone task)
 │    ├─ WorkflowVersion (version)
 │    ├─ Cron trigger / Scheduled run / Filter
 │    └─ WorkflowRun (single execution)
 │         └─ TaskRun(=StepRun) ... (per DAG node)
 │              └─ TaskEvent (lifecycle event), LogLine, OtelSpan(trace)
 ├─ Worker (task execution process, gRPC connection)
 ├─ Event (workflow trigger message)
 ├─ RateLimit
 └─ WebhookWorker
```

## 3. Architecture — gRPC (workers) vs REST (management/MCP)

This is the most important distinction for MCP design.

- **Workers connect to the Hatchet engine over bidirectional gRPC.** The gRPC dispatcher protocol handles task assignment, status updates, heartbeats, and result reporting. Because it is a long-lived streaming connection, it is unsuitable for *querying* state.
- **Clients, management tools, and monitoring read and control state through the REST API (the Hatchet API server).** Triggering runs, listing them, checking status, cancelling, replaying, managing cron/schedules, and reading logs all go through this path.

Consequently, an operations/monitoring MCP server uses the REST API exclusively and does not touch the gRPC worker protocol.

Source: `frontend/docs/pages/v1/architecture-and-guarantees.mdx:9-51` (the diagram distinguishes `ENG <-.->|gRPC| W` from `APP <--> API`)

## 4. v0 vs v1 — Why There Are Two REST Paths

Hatchet's execution engine was **rewritten as v1** — not merely a new SDK, but a change to the engine architecture itself. As a result, the REST API splits into two families.

1. **Engine architecture change**: the v1 engine queues and dispatches tasks in a fundamentally different way from v0. Existing runs are not migrated on upgrade; they remain under "View Legacy V0 Data" in the dashboard. A tenant opts in via the dashboard button or by setting `SERVER_DEFAULT_ENGINE_VERSION=V1`.

2. **REST API split**:
   - **Legacy path** `/api/v1/...` — endpoints from the v0 era (e.g. `/api/v1/tenants/{tenant}/workflow-runs`)
   - **Stable path** `/api/v1/stable/...` — new endpoints compatible with the v1 engine (e.g. `/api/v1/stable/tenants/{tenant}/workflow-runs`)
   - The migration guide states explicitly: "The current (legacy) APIs for listing, cancelling, and replaying runs **do not work** on the v1 engine. New endpoints are provided as the upgrade path."

3. **Caveat — not every capability has moved to stable**: workflow **definition** queries (`workflow:list/get`), **worker** queries, **cron/scheduled** management, and **rate-limit** queries still live only under legacy `/api/v1/...`. Run/task queries, triggering, cancellation, replay, logs, traces, and events, by contrast, live under stable `/api/v1/stable/...`. As a result, the MCP server must call **both generations**.

Source: `frontend/docs/pages/v1/migrating/migration-guide-engine.mdx`, `v1-sdk-improvements.mdx`

> The Python SDK handles this split internally through its feature clients (for example, `h.runs` targets stable while `h.workflows` targets legacy), so using the SDK rarely requires choosing a path by hand. See the [SDK documentation](sdk-and-communication.md).

## 5. Run Lifecycle and Status

### Status enums differ by generation

The same "status" can have different enum values in v1 versus legacy. These must not be conflated when displaying or filtering status in the MCP server.

**v1 — `V1TaskStatus`** (shared by runs and tasks, 5 values):
```
QUEUED | RUNNING | COMPLETED | CANCELLED | FAILED
```
Source: `api-contracts/openapi/components/schemas/v1/task.yaml:267-275`

**legacy — `WorkflowRunStatus`** (7 values):
```
PENDING | RUNNING | SUCCEEDED | FAILED | CANCELLED | QUEUED | BACKOFF
```
Source: `components/schemas/workflow_run.yaml:495`

**legacy — `StepRunStatus`** (9 values, more granular):
```
PENDING | PENDING_ASSIGNMENT | ASSIGNED | RUNNING | SUCCEEDED | FAILED | CANCELLED | CANCELLING | BACKOFF
```
Source: `components/schemas/workflow_run.yaml:463`

**legacy — `ScheduledRunStatus`** (schedule-specific, adds `SCHEDULED`):
```
PENDING | RUNNING | SUCCEEDED | FAILED | CANCELLED | QUEUED | SCHEDULED
```
Source: `components/schemas/workflow_run.yaml:506`

> Key difference: v1 marks success as `COMPLETED`, whereas legacy uses `SUCCEEDED`. v1 simplifies status to 5 values, collapsing legacy's intermediate states such as `PENDING`, `BACKOFF`, and `ASSIGNED`.

### Simplified flow

```
QUEUED ──> RUNNING ──> COMPLETED        (v1)
                  └──> FAILED
                  └──> CANCELLED
(legacy starts at PENDING, marks success as SUCCEEDED, and uses BACKOFF for retry waits)
```

For a DAG: if any non-skipped task fails, the entire run fails. A task skipped via `skip_if` does not fail the run. Source: `directed-acyclic-graphs.mdx:100-113`

### replay vs rerun vs restore vs cancel (central to designing MCP mutation tools)

These four are distinctly different.

| Operation | v1 endpoint | Meaning |
|---|---|---|
| **Replay** | `POST /api/v1/stable/tenants/{tenant}/tasks/replay` (`v1-task:replay`) | Re-runs a completed/failed task **from the start** with its original input. Can be applied in bulk by ID list or by filter (status, workflow, time range, metadata). The primary means of retrying failed runs. |
| **Restore** | `POST /api/v1/stable/tasks/{task}/restore` (`v1-task:restore`) | **Durable tasks only.** Resumes an evicted durable task from its last checkpoint. Unlike replay, it does not start from the beginning. |
| **Rerun** | `POST /api/v1/tenants/{tenant}/step-runs/{step-run}/rerun` (legacy) | Re-runs a single step within a v0 workflow run. Superseded by task-level replay in v1; does not work on the v1 engine. |
| **Cancel** | `POST /api/v1/stable/tenants/{tenant}/tasks/cancel` (`v1-task:cancel`) | Cancels one or more queued/running tasks. Can be applied in bulk by ID or by filter. |

Source: `api-contracts/openapi/paths/v1/tasks/tasks.yaml:335-486`, `frontend/docs/pages/v1/bulk-retries-and-cancellations.mdx`

### Durable task eviction cycle

```
RUNNING (occupies a slot)
  → reaches a wait
  → if the eviction policy fires: EVICTED (isEvicted=true, still displayed as RUNNING)
  → wait condition satisfied
  → requeued → RUNNING (worker replays the event log from the checkpoint)
```

Source: `frontend/docs/pages/v1/task-eviction.mdx`

## 6. MCP Perspective

- The MCP server is a **REST API client** (not gRPC).
- A single token operates on **one tenant** (handling multiple tenants requires switching tokens — see [Authentication](authentication-and-connection.md)).
- Run/task queries and control use **v1 stable**, while workflow definitions, workers, cron, schedules, and rate limits use the **legacy** path.
- Because status enums differ by generation, a decision is required on whether to normalize them consistently in tool responses or expose the raw values as-is (see the [design](mcp-server-design.md) discussion).

Next: [REST API Reference](rest-api-reference.md)
