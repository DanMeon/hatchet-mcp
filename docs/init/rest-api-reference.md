# Hatchet REST API Reference

A complete inventory of the Hatchet REST API surface that the MCP server calls. All entries are sourced from `vendor/hatchet/api-contracts/openapi/`, where the master spec `openapi.yaml` maps each URL to an operation in a path file via `$ref`.

- **v1 stable API** (`/api/v1/stable/...`) — the new v1 engine. 37 endpoints (operations). → [§A](#a-v1-stable-api)
- **legacy API** (`/api/v1/...`) — the v0 era. Workflow definitions, workers, cron, schedules, and more. → [§B](#b-legacy-api)
- **Status / type enum index** → [§C](#c-enum-index)

## Common Conventions

### Authentication
Every endpoint requires either `bearerAuth` (HTTP Bearer token) or `cookieAuth` (the `hatchet` cookie). The only exceptions are the webhook-receive and SNS-receive endpoints, which use `security: []` (unauthenticated). The MCP server always uses `Authorization: Bearer <token>`. Source: `openapi.yaml:8-21`. For details on token structure, see the [authentication doc](authentication-and-connection.md).

### Pagination (offset-based)
List responses carry a `PaginationResponse` under `.pagination`.

| Field | Type | Meaning |
|---|---|---|
| `current_page` | int64 | Current page |
| `next_page` | int64 | Next page |
| `num_pages` | int64 | Total number of pages |

Requests accept `offset` (number of rows to skip) and `limit` (maximum number of rows). **The spec does not define default values** (only legacy workflows list defaults `limit` to 50). There is no cursor-based pagination. Source: `components/schemas/metadata.yaml:128-149`

### Common Metadata (`APIResourceMeta`)
The `metadata` field present on nearly every resource. Source: `metadata.yaml:105-127`

| Field | Type |
|---|---|
| `id` | string (UUID) |
| `createdAt` | date-time |
| `updatedAt` | date-time |

### `additionalMetadata` Filter Format — Note
When filtering runs, events, and similar resources by metadata, the value is an **array of `"key:value"` strings** (not a JSON object). Example: `["audit_id:123", "env:prod"]`.

---

# A. v1 stable API

Base files: `api-contracts/openapi/paths/v1/`, schemas under `components/schemas/v1/`. 37 operations total (30 URLs).

## A-1. Workflow Runs (10) — Most Important

File: `paths/v1/workflow-runs/workflow_run.yaml`

| Method | URL | operationId | Purpose |
|---|---|---|---|
| GET | `/api/v1/stable/tenants/{tenant}/workflow-runs` | `v1-workflow-run:list` | List runs (full filtering) |
| GET | `/api/v1/stable/tenants/{tenant}/workflow-runs/display-names` | `v1-workflow-run:display-names:list` | Resolve a list of IDs to display names in bulk |
| GET | `/api/v1/stable/tenants/{tenant}/workflow-runs/external-ids` | `v1-workflow-run:external-ids:list` | Return only filter-matching external IDs (no payload) |
| POST | `/api/v1/stable/tenants/{tenant}/workflow-runs/trigger` | `v1-workflow-run:create` | **Trigger a new run** |
| POST | `/api/v1/stable/tenants/{tenant}/durable-tasks/branch` | `v1-durable-task:branch` | Branch a durable task |
| GET | `/api/v1/stable/workflow-runs/{v1-workflow-run}` | `v1-workflow-run:get` | Run detail (run + tasks + events + DAG shape) |
| GET | `/api/v1/stable/workflow-runs/{v1-workflow-run}/status` | `v1-workflow-run:get-status` | Status only (lightweight) |
| GET | `/api/v1/stable/workflow-runs/{v1-workflow-run}/task-events` | `v1-workflow-run:task-events:list` | Task events for a run (paginated) |
| GET | `/api/v1/stable/workflow-runs/{v1-workflow-run}/task-timings` | `v1-workflow-run:get:timings` | Per-task waterfall timings |
| GET | `/api/v1/stable/durable-tasks/{durable-task}` | `v1-durable-task:event-log:list` | Durable event log |

### List Workflow Runs — Query Parameters (full)
`GET /api/v1/stable/tenants/{tenant}/workflow-runs` — Source: `paths/v1/workflow-runs/workflow_run.yaml:17-116`

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `tenant` (path) | UUID | Yes | |
| `since` | date-time | Yes | Lower time bound. **Must always be supplied** |
| `only_tasks` | boolean | Yes | `false` = include DAGs, `true` = tasks only |
| `offset` / `limit` | int64 | | Pagination |
| `statuses` | `V1TaskStatus[]` | | `QUEUED RUNNING COMPLETED CANCELLED FAILED` |
| `until` | date-time | | Upper time bound |
| `additional_metadata` | string[] | | `"key:value"` |
| `workflow_ids` | UUID[] | | Filter by workflow ID |
| `worker_id` | UUID | | Filter by executing worker |
| `parent_task_external_id` | UUID | | Child runs of a specific parent task |
| `triggering_event_external_id` | UUID | | Runs triggered by a specific event |
| `include_payloads` | boolean | | Whether to include input/output (defaults to true) |
| `running_filter` | `V1RunningFilter` | | `ALL` (default) `ON_WORKER` `EVICTED` |

Response: `V1TaskSummaryList = { pagination, rows: V1TaskSummary[] }`. Key `V1TaskSummary` fields (source `components/schemas/v1/task.yaml:7-140`): `metadata.id` (run UUID), `status`, `displayName`, `workflowId`, `workflowRunExternalId`, `type` (DAG/TASK), `input`, `output`, `createdAt`, `startedAt`, `finishedAt`, `duration` (ms), `errorMessage`, `retryCount`, `attempt`, `isDurable`, `isEvicted`, `workflowName`, `additionalMetadata`, `children` (recursive child tasks).

### Get Run Detail / Status / Timings
- `GET .../workflow-runs/{id}` → `V1WorkflowRunDetails = { run: V1WorkflowRun, taskEvents[], shape[], tasks: V1TaskSummary[], workflowConfig? }`. `shape` describes the DAG structure (`taskExternalId, stepId, childrenStepIds[], taskName`). Source: `workflow_run.yaml:349-391`, `components/schemas/v1/workflow_run.yaml:109-130` (`V1WorkflowRunDetails`), `:77-108` (shape item)
- `GET .../workflow-runs/{id}/status` → a single `V1TaskStatus` string. Source: `:393-441`
- `GET .../workflow-runs/{id}/task-timings?depth=N` → `V1TaskTimingList` (depth, queuedAt, startedAt, finishedAt, etc.). Source: `:534-583`

### Trigger Run
`POST .../workflow-runs/trigger`, body `V1TriggerWorkflowRunRequest` (source `components/schemas/v1/workflow_run.yaml:132-147`):

| Field | Type | Required |
|---|---|---|
| `workflowName` | string | Yes |
| `input` | object | Yes |
| `additionalMetadata` | object | |
| `priority` | integer | |

Response: `V1WorkflowRunDetails`.

## A-2. Tasks (9)

File: `paths/v1/tasks/tasks.yaml`

| Method | URL | operationId | Purpose |
|---|---|---|---|
| GET | `/api/v1/stable/tasks/{task}` | `v1-task:get` | Single task (input/output/error) |
| GET | `/api/v1/stable/tasks/{task}/task-events` | `v1-task-event:list` | Task lifecycle events |
| GET | `/api/v1/stable/tasks/{task}/logs` | `v1-log-line:list` | **Task log lines** |
| POST | `/api/v1/stable/tenants/{tenant}/tasks/cancel` | `v1-task:cancel` | Cancel tasks (by ID or filter) |
| POST | `/api/v1/stable/tenants/{tenant}/tasks/replay` | `v1-task:replay` | Replay tasks (by ID or filter) |
| POST | `/api/v1/stable/tasks/{task}/restore` | `v1-task:restore` | Restore an evicted durable task |
| GET | `/api/v1/stable/dags/tasks` | `v1-dag:list:tasks` | Fetch tasks by DAG IDs |
| GET | `/api/v1/stable/tenants/{tenant}/task-metrics` | `v1-task:list:status-metrics` | Per-status count metrics |
| GET | `/api/v1/stable/tenants/{tenant}/task-point-metrics` | `v1-task:get:point-metrics` | Per-minute throughput |

### Cancel / Replay (by ID or filter)
`POST .../tasks/cancel`, body `V1CancelTaskRequest`: either `externalIds: UUID[]` (task/run external IDs) **or** `filter: V1TaskFilter`. `V1TaskFilter` = `{ since (required), until, statuses[], workflowIds[], additionalMetadata[] }`. Response: `{ ids: UUID[] }` (the canceled IDs). Replay uses the same structure (`V1ReplayTaskRequest` → `{ ids }`). Source: `tasks.yaml:332-442`, `components/schemas/v1/task.yaml:372-409`

### Task Logs
`GET /api/v1/stable/tasks/{task}/logs`, query: `limit`, `since`, `until`, `search` (full-text search), `levels[]` (`DEBUG INFO WARN ERROR`), `order_by_direction` (`ASC DESC`), `attempt`. Response: `V1LogLineList`. Source: `tasks.yaml:488-571`

### Task Metrics
- `task-metrics?since(required)&until&workflow_ids[]&...` → `V1TaskRunMetrics` = `[{ status, count, runningDetailCount?{evicted,onWorker} }]`. Source: `tasks.yaml:178-270`
- `task-point-metrics?createdAfter&finishedBefore` → `{ results: [{ time, SUCCEEDED, FAILED }] }`. Source: `:272-330`

## A-3. Events (3)
File: `paths/v1/events/event.yaml`

| Method | URL | operationId | Purpose |
|---|---|---|---|
| GET | `/api/v1/stable/tenants/{tenant}/events` | `v1-event:list` | List events (with filters) |
| GET | `/api/v1/stable/tenants/{tenant}/events/{v1-event}` | `v1-event:get` | Single event |
| GET | `/api/v1/stable/tenants/{tenant}/events/keys` | `v1:event-key:list` | List of distinct event keys |

List query: `offset`, `limit`, `keys[]`, `since`, `until`, `workflowIds[]`, `workflowRunStatuses[]` (`V1TaskStatus`), `eventIds[]`, `additionalMetadata[]`, `scopes[]`. Response: `V1EventList`. `V1Event` fields: `metadata.id`, `key`, `workflowRunSummary{running,queued,succeeded,failed,cancelled}`, `payload`, `scope`, `seenAt`, `triggeredRuns[]`. Source: `event.yaml:48-163`, `components/schemas/v1/event.yaml:17-97`

## A-4. Logs — Tenant Level (2)
File: `paths/v1/logs/logs.yaml`

| Method | URL | operationId | Purpose |
|---|---|---|---|
| GET | `/api/v1/stable/tenants/{tenant}/logs` | `v1-tenant-log-line:list` | All logs for a tenant |
| GET | `/api/v1/stable/tenants/{tenant}/log-point-metrics` | `v1-tenant-log-line:get:point-metrics` | Per-minute log volume by level |

Tenant logs query: `limit`, `since`, `until`, `search`, `levels[]`, `order_by_direction`, `attempt`, `taskExternalIds[]`, `workflow_ids[]`, `step_ids[]`. `V1LogLine` = `{ createdAt, message, metadata, taskExternalId?, taskDisplayName?, retryCount?, attempt?, level? }`. Source: `logs.yaml:1-117`, `components/schemas/v1/logs.yaml:1-35`

> Logs for a single task are at A-2's `/api/v1/stable/tasks/{task}/logs`. Tenant-wide logs are here.

## A-5. Observability / Traces (1)
`GET /api/v1/stable/tenants/{tenant}/traces?run_external_id(required)&offset&limit` → `OtelSpanList`. OpenTelemetry spans (`traceId, spanId, spanName, spanKind, serviceName, statusCode, durationNs, parentSpanId, spanAttributes`). Source: `paths/v1/observability/traces.yaml:1-66`, `components/schemas/v1/otel.yaml`

## A-6. Filters (5) — CRUD
File: `paths/v1/filters/filter.yaml`

| Method | URL | operationId |
|---|---|---|
| GET | `/api/v1/stable/tenants/{tenant}/filters` | `v1-filter:list` |
| POST | `/api/v1/stable/tenants/{tenant}/filters` | `v1-filter:create` |
| GET | `/api/v1/stable/tenants/{tenant}/filters/{v1-filter}` | `v1-filter:get` |
| DELETE | `/api/v1/stable/tenants/{tenant}/filters/{v1-filter}` | `v1-filter:delete` |
| PATCH | `/api/v1/stable/tenants/{tenant}/filters/{v1-filter}` | `v1-filter:update` |

List query: `offset`, `limit`, `workflowIds[]`, `scopes[]`. Create body `V1CreateFilterRequest` = `{ workflowId (required), expression (required, CEL), scope (required), payload? }`. `V1Filter` = `{ metadata, tenantId, workflowId, scope, expression, payload, isDeclarative? }`. Source: `filter.yaml`, `components/schemas/v1/filter.yaml`

## A-7. Webhooks (6) — CRUD + Receive
File: `paths/v1/webhooks/webhook.yaml`. `{v1-webhook}` is the **name** (string).

| Method | URL | operationId | Notes |
|---|---|---|---|
| GET | `/api/v1/stable/tenants/{tenant}/webhooks` | `v1-webhook:list` | `sourceNames[]`, `webhookNames[]` filters |
| POST | `.../webhooks` | `v1-webhook:create` | oneOf per authType (BASIC/API_KEY/HMAC) |
| GET | `.../webhooks/{v1-webhook}` | `v1-webhook:get` | |
| DELETE | `.../webhooks/{v1-webhook}` | `v1-webhook:delete` | |
| PATCH | `.../webhooks/{v1-webhook}` | `v1-webhook:update` | |
| POST | `.../webhooks/{v1-webhook}` | `v1-webhook:receive` | **Unauthenticated** external receive |

`V1Webhook` = `{ metadata, tenantId, name, sourceName, eventKeyExpression, authType, scopeExpression?, staticPayload? }`. Source: `webhook.yaml`, `components/schemas/v1/webhook.yaml`

## A-8. CEL Debug (1)
`POST /api/v1/stable/tenants/{tenant}/cel/debug`, body `{ expression (required), input (required), filterPayload?, additionalMetadata? }` → `{ status: SUCCESS|ERROR, output?: bool, error? }`. Evaluates a CEL expression against test data. Source: `paths/v1/cel/cel.yaml`

---

# B. legacy API

Base files: `api-contracts/openapi/paths/` (top level, excluding `v1/`). Schemas under `components/schemas/`.

## B-1. Workflows (definitions) — Only Here, Not in stable
File: `paths/workflow/workflow.yaml`

| Method | URL | operationId | Purpose |
|---|---|---|---|
| GET | `/api/v1/tenants/{tenant}/workflows` | `workflow:list` | **List workflow definitions** |
| GET | `/api/v1/workflows/{workflow}` | `workflow:get` | Single workflow (with versions) |
| DELETE | `/api/v1/workflows/{workflow}` | `workflow:delete` | Delete |
| PATCH | `/api/v1/workflows/{workflow}` | `workflow:update` | **pause/resume** (`isPaused`) |
| GET | `/api/v1/workflows/{workflow}/versions` | `workflow-version:get` | Get version (defaults to latest) |
| GET | `/api/v1/workflows/{workflow}/metrics` | `workflow:get:metrics` | Concurrency / group-key metrics |
| GET | `/api/v1/tenants/{tenant}/workflows/{workflow}/worker-count` | `workflow:get:workers-count` | Available worker count |
| GET | `/api/v1/tenants/{tenant}/workflows/runs` | `workflow-run:list` | List runs (legacy) |
| GET | `/api/v1/tenants/{tenant}/workflows/runs/metrics` | `workflow-run:get:metrics` | Run counts by status |
| POST | `/api/v1/workflows/{workflow}/trigger` | `workflow-run:create` | Trigger run (legacy) |
| POST | `/api/v1/tenants/{tenant}/workflows/cancel` | `workflow-run:cancel` | Bulk-cancel runs |
| GET | `/api/v1/tenants/{tenant}/workflow-runs/{workflow-run}` | `workflow-run:get` | Single run (legacy) |
| GET | `/api/v1/tenants/{tenant}/workflow-runs/{workflow-run}/shape` | `workflow-run:get:shape` | Run + job/step shape |

`GET .../workflows` query: `offset` (default 0), `limit` (default 50), `name` (name search). Response: `WorkflowList = { rows: Workflow[], pagination }`.

**`Workflow` schema** (source `workflow.yaml:1`): `metadata`, `name`, `description?`, `isPaused?`, `versions: WorkflowVersionMeta[]`, `tags: [{name,color}]`, `jobs: Job[]`, `tenantId`. This is where you obtain whether a workflow is paused (`isPaused`), its version history, and its tags.

`GET .../workflows/runs` query (legacy run list): `offset`, `limit`, `eventId`, `workflowId`, `parentWorkflowRunId`, `parentStepRunId`, `statuses[]` (`WorkflowRunStatus`), `kinds[]` (`FUNCTION DURABLE DAG`), `additionalMetadata[]`, `createdAfter/Before`, `finishedAfter/Before`, `orderByField` (`createdAt startedAt finishedAt duration`), `orderByDirection` (`ASC DESC`).

## B-2. Cron Triggers (5) — legacy only
File: `paths/workflow/workflow.yaml`

| Method | URL | operationId | Purpose |
|---|---|---|---|
| GET | `/api/v1/tenants/{tenant}/workflows/crons` | `cron-workflow:list` | List crons |
| POST | `/api/v1/tenants/{tenant}/workflows/{workflow}/crons` | `cron-workflow-trigger:create` | Create cron (`{workflow}` = name) |
| GET | `/api/v1/tenants/{tenant}/workflows/crons/{cron-workflow}` | `workflow-cron:get` | Single cron |
| DELETE | `.../crons/{cron-workflow}` | `workflow-cron:delete` | Delete |
| PATCH | `.../crons/{cron-workflow}` | `workflow-cron:update` | enable/disable only |

List query: `offset`, `limit`, `workflowId`, `workflowName`, `cronName`, `additionalMetadata[]`, `orderByField` (`name createdAt`), `orderByDirection`. Create body `CreateCronWorkflowTriggerRequest` = `{ cronName (required), cronExpression (required), input (required), additionalMetadata (required), priority? (1-3) }`. `CronWorkflows` = `{ metadata, tenantId, workflowVersionId, workflowId, workflowName, cron, name?, input?, enabled, method(DEFAULT/API), priority? }` (`tenantId` and `workflowVersionId` are also required). Source: `workflow.yaml:1265-1490`, `components/schemas/workflow_run.yaml:374`

> The cron expression and input cannot be changed via PATCH (enable/disable only). To change them, delete and recreate.

## B-3. Scheduled Runs (7) — legacy only
File: `paths/workflow/workflow.yaml`

| Method | URL | operationId |
|---|---|---|
| GET | `/api/v1/tenants/{tenant}/workflows/scheduled` | `workflow-scheduled:list` |
| POST | `/api/v1/tenants/{tenant}/workflows/{workflow}/scheduled` | `scheduled-workflow-run:create` |
| GET | `.../scheduled/{scheduled-workflow-run}` | `workflow-scheduled:get` |
| DELETE | `.../scheduled/{scheduled-workflow-run}` | `workflow-scheduled:delete` |
| PATCH | `.../scheduled/{scheduled-workflow-run}` | `workflow-scheduled:update` (change triggerAt) |
| POST | `.../scheduled/bulk-delete` | `workflow-scheduled:bulk-delete` |
| POST | `.../scheduled/bulk-update` | `workflow-scheduled:bulk-update` |

List query: `offset`, `limit`, `orderByField` (`triggerAt createdAt`), `orderByDirection`, `workflowId`, `parentWorkflowRunId`, `parentStepRunId`, `additionalMetadata[]`, `statuses[]` (`ScheduledRunStatus`). Create body `ScheduleWorkflowRunRequest` = `{ triggerAt (required, date-time), input (required), additionalMetadata (required), priority? (1-3) }`. `ScheduledWorkflows` = `{ metadata, tenantId, workflowVersionId, workflowId, workflowName, triggerAt, input?, workflowRunStatus?, workflowRunId?, method, priority? }` (`tenantId` and `workflowVersionId` are also required). Bulk operations are limited to 1–500 items. Source: `workflow.yaml:852-1260`

## B-4. Workers (3) — legacy only
File: `paths/worker/worker.yaml`

| Method | URL | operationId | Purpose |
|---|---|---|---|
| GET | `/api/v1/tenants/{tenant}/worker` | `worker:list` | **List workers** |
| GET | `/api/v1/workers/{worker}` | `worker:get` | Single worker |
| PATCH | `/api/v1/workers/{worker}` | `worker:update` | **pause/resume** (`isPaused`) |

`Worker` schema (source `worker.yaml:106`): `metadata`, `name`, `type` (`SELFHOSTED MANAGED WEBHOOK`), `status` (`ACTIVE INACTIVE PAUSED`), `lastHeartbeatAt?`, `actions: string[]`, `registeredWorkflows: [{id,name}]`, `slots: SemaphoreSlots[]`, `slotConfig: map<type,{available,limit}>`, `dispatcherId?`, `labels?`, `webhookUrl?`, `runtimeInfo?{sdkVersion,language,os}`.

> Note: a worker does **not** expose flat `availableRuns`/`maxRuns` fields. Slot availability is represented by `slotConfig` (per-type `{available,limit}`) and the `slots[]` array.

## B-5. Step Run (7) — legacy (v0 step level)
File: `paths/step-run/step-run.yaml`

| Method | URL | operationId |
|---|---|---|
| GET | `/api/v1/tenants/{tenant}/step-runs/{step-run}` | `step-run:get` |
| POST | `.../step-runs/{step-run}/rerun` | `step-run:update:rerun` |
| POST | `.../step-runs/{step-run}/cancel` | `step-run:update:cancel` |
| GET | `.../step-runs/{step-run}/schema` | `step-run:get:schema` |
| GET | `/api/v1/step-runs/{step-run}/events` | `step-run:list:events` |
| GET | `.../workflow-runs/{workflow-run}/step-run-events` | `workflow-run:list:step-run-events` |
| GET | `/api/v1/step-runs/{step-run}/archives` | `step-run:list:archives` |

`StepRun` status is `StepRunStatus` (§C). `StepRunEvent` = `{ id, timeFirstSeen, timeLastSeen, reason: StepRunEventReason, severity(INFO/WARNING/CRITICAL), message, count, data? }`. Source: `components/schemas/workflow_run.yaml:611-740`

## B-6. Events (legacy, 9)
File: `paths/event/event.yaml`

| Method | URL | operationId | Purpose |
|---|---|---|---|
| GET | `/api/v1/tenants/{tenant}/events` | `event:list` | List |
| POST | `/api/v1/tenants/{tenant}/events` | `event:create` | **Push an event** |
| POST | `/api/v1/tenants/{tenant}/events/bulk` | `event:create:bulk` | Bulk push |
| GET | `/api/v1/events/{event}` | `event:get` | Single |
| GET | `/api/v1/events/{event}/data` | `event-data:get` | Payload |
| GET | `.../events/{event-with-tenant}/data` | `event-data:get-with-tenant` | Payload (tenant-scoped) |
| GET | `/api/v1/tenants/{tenant}/events/keys` | `event-key:list` | List keys |
| POST | `/api/v1/tenants/{tenant}/events/replay` | `event:update:replay` | Replay events |
| POST | `/api/v1/tenants/{tenant}/events/cancel` | `event:update:cancel` | Cancel event runs |

Create body `CreateEventRequest` = `{ key (required), data (required, object), additionalMetadata?, priority?, scope? }`. Source: `event.yaml`

## B-7. Rate Limits (2)
| Method | URL | operationId |
|---|---|---|
| GET | `/api/v1/tenants/{tenant}/rate-limits` | `rate-limit:list` |
| DELETE | `/api/v1/tenants/{tenant}/rate-limits?key=` | `rate-limit:delete` |

List query: `offset`, `limit`, `search`, `orderByField` (`key value limitValue`), `orderByDirection`. `RateLimit` = `{ key, tenantId, limitValue, value (current consumption), window (e.g. "1m"), lastRefill }`. Source: `paths/rate-limits/rate_limits.yaml`, `components/schemas/rate_limits.yaml`

## B-8. Other legacy
| Resource | Key endpoints | Notes |
|---|---|---|
| **Monitoring** | `POST /api/v1/monitoring/{tenant}/probe` | Run a health-probe workflow (no body) |
| **Tenant queue metrics** | `GET /api/v1/tenants/{tenant}/queue-metrics` | Queue depth per workflow — **a primary operational health signal** |
| | `GET /api/v1/tenants/{tenant}/step-run-queue-metrics` | Queue depth per action |
| **API tokens** | `POST/GET /api/v1/tenants/{tenant}/api-tokens`, `POST /api/v1/api-tokens/{api-token}` (revoke) | See the [authentication doc](authentication-and-connection.md) |
| **Webhook workers** | `GET/POST /api/v1/tenants/{tenant}/webhook-workers`, `DELETE /api/v1/webhook-workers/{webhook}` | Inbound webhook → event |
| **SNS (ingestors)** | `GET/POST /api/v1/tenants/{tenant}/sns`, `POST /api/v1/sns/{tenant}/{event}` (unauthenticated receive) | AWS SNS integration |
| **Slack** | `GET /api/v1/tenants/{tenant}/slack`, `DELETE /api/v1/slack/{slack}` | Slack notification integration |
| **Feature flags** | `GET /api/v1/tenants/{tenant}/feature-flags?featureFlagId=&isEnabledIfNoPosthog=` | Flag evaluation |

Source: `paths/monitoring/`, `paths/tenant/tenant.yaml`, `paths/api-tokens/`, `paths/webhook-worker/`, `paths/ingestors/`, `paths/slack/`, `paths/feature-flags/`

---

# C. enum index

| enum | Values | Source |
|---|---|---|
| `V1TaskStatus` (v1 runs/tasks) | `QUEUED RUNNING COMPLETED CANCELLED FAILED` | `v1/task.yaml:267` |
| `V1RunningFilter` | `ALL EVICTED ON_WORKER` | `v1/task.yaml:276` |
| `V1WorkflowType` | `DAG TASK` | `v1/task.yaml:1` |
| `V1TaskEventType` | `QUEUED ASSIGNED STARTED FINISHED FAILED RETRYING CANCELLED TIMED_OUT REASSIGNED SLOT_RELEASED RETRIED_BY_USER SENT_TO_WORKER RATE_LIMIT_ERROR ACKNOWLEDGED CREATED SKIPPED REQUEUED_NO_WORKER REQUEUED_RATE_LIMIT SCHEDULING_TIMED_OUT TIMEOUT_REFRESHED COULD_NOT_SEND_TO_WORKER DURABLE_EVICTED DURABLE_RESTORING` (23) | `v1/task.yaml:283` |
| `V1LogLineLevel` | `DEBUG INFO WARN ERROR` | `v1/logs.yaml:36` |
| `WorkflowRunStatus` (legacy) | `PENDING RUNNING SUCCEEDED FAILED CANCELLED QUEUED BACKOFF` | `workflow_run.yaml:495` |
| `ScheduledRunStatus` | `PENDING RUNNING SUCCEEDED FAILED CANCELLED QUEUED SCHEDULED` | `workflow_run.yaml:506` |
| `JobRunStatus` | `PENDING RUNNING SUCCEEDED FAILED CANCELLED BACKOFF` | `workflow_run.yaml:476` |
| `StepRunStatus` | `PENDING PENDING_ASSIGNMENT ASSIGNED RUNNING SUCCEEDED FAILED CANCELLED CANCELLING BACKOFF` | `workflow_run.yaml:463` |
| `WorkflowKind` | `FUNCTION DURABLE DAG` | `workflow_run.yaml:517` |
| `WorkerStatus` | `ACTIVE INACTIVE PAUSED` | `worker.yaml:146` |
| `WorkerType` | `SELFHOSTED MANAGED WEBHOOK` | `worker.yaml:73` |
| `WorkerRuntimeSDKs` | `GOLANG PYTHON TYPESCRIPT RUBY` | `worker.yaml:200` |
| `ConcurrencyLimitStrategy` | `CANCEL_IN_PROGRESS DROP_NEWEST QUEUE_NEWEST GROUP_ROUND_ROBIN` | `workflow.yaml:188` |
| `StepRunEventReason` | `REQUEUED_NO_WORKER REQUEUED_RATE_LIMIT SCHEDULING_TIMED_OUT ASSIGNED STARTED ACKNOWLEDGED FINISHED FAILED RETRYING CANCELLED TIMEOUT_REFRESHED REASSIGNED TIMED_OUT SLOT_RELEASED RETRIED_BY_USER WORKFLOW_RUN_GROUP_KEY_SUCCEEDED WORKFLOW_RUN_GROUP_KEY_FAILED` | `workflow_run.yaml:682` |

Next: [Authentication and Connection](authentication-and-connection.md)
