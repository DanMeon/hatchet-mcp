# SDK and Communication

How the MCP server calls the Hatchet REST API. Recommended approach: **use the Python SDK feature clients.**

## 1. Communication Options

| Approach | Pros | Cons |
|---|---|---|
| **A. Python SDK feature clients** (`h.runs.list(...)`, etc.) | The SDK handles authentication, tenant scoping, pagination, and generation (v1/legacy) routing. Pydantic response types. `aio_*` async variants. Stays current as the SDK is updated. | Requires the `hatchet-sdk` dependency (heavy — bundles gRPC and more). |
| **B. Python SDK low-level REST client** (`WorkflowRunsApi(client).v1_workflow_run_list(...)`) | Generated OpenAPI client gives 1:1 access to every endpoint. | More verbose than the feature clients. Tenant and similar parameters must be passed manually. |
| **C. Direct httpx calls** | Minimal dependencies (lightweight). Full control. | Authentication, URLs, pagination, and models must be implemented by hand. Burden of tracking spec changes. |

→ **Recommended: A (supplemented by B where needed).** Rationale in §4.

## 2. Python SDK Structure

### High-level `Hatchet` client
Location: `sdks/python/hatchet_sdk/hatchet.py`

```python
from hatchet_sdk import Hatchet
h = Hatchet()  # reads the token from the HATCHET_CLIENT_TOKEN environment variable
```

`Hatchet` properties delegate to the feature clients (all REST-based; only `h.event` is gRPC):

| Accessor | Class | Module |
|---|---|---|
| `h.runs` | `RunsClient` | `features/runs.py` |
| `h.workflows` | `WorkflowsClient` | `features/workflows.py` |
| `h.workers` | `WorkersClient` | `features/workers.py` |
| `h.cron` | `CronClient` | `features/cron.py` |
| `h.scheduled` | `ScheduledClient` | `features/scheduled.py` |
| `h.logs` | `LogsClient` | `features/logs.py` |
| `h.metrics` | `MetricsClient` | `features/metrics.py` |
| `h.filters` | `FiltersClient` | `features/filters.py` |
| `h.webhooks` | `WebhooksClient` | `features/webhooks.py` |
| `h.rate_limits` | `RateLimitsClient` | `features/rate_limits.py` |
| `h.cel` | `CELClient` | `features/cel.py` |
| `h.event` | `EventClient` | `clients/events.py` (gRPC-based push) |
| `h.tenant_id` | `str` | from config |

### Low-level REST client (generated)
Location: `sdks/python/hatchet_sdk/clients/rest/`
- `configuration.py` — `Configuration(host, access_token)` sets the `Authorization: Bearer` header
- `api_client.py` — `ApiClient(Configuration)` (context manager)
- `api/` — 24 generated per-resource API classes: `WorkflowApi`, `WorkflowRunApi`, `WorkflowRunsApi`, `TaskApi`, `EventApi`, `WorkerApi`, `TenantApi`, `LogApi`, `StepRunApi`, `FilterApi`, `WebhookApi`, `RateLimitsApi`, `CELApi` (uppercase), `MetadataApi`, `DurableTasksApi`, `ObservabilityApi`, `HealthcheckApi`, and others

`BaseRestClient` (`clients/v1/api_client.py`) is the foundation for every feature client:
```python
class BaseRestClient:
    def __init__(self, config: ClientConfig) -> None:
        self.tenant_id = config.tenant_id          # used throughout the feature clients
        self.client_config = config
        self.api_config = Configuration(host=config.server_url, access_token=config.token)
        self.api_config.datetime_format = "%Y-%m-%dT%H:%M:%S.%fZ"
    def client(self) -> ApiClient:
        return ApiClient(self.api_config)
```

## 3. Key feature-client methods (called by the MCP server)

Every method has an **`aio_*` async variant** (e.g. `h.runs.aio_list(...)`).

**`RunsClient`** (`features/runs.py`):
- `list(since, until, statuses, workflow_ids, ...) -> V1TaskSummaryList`
- `list_with_pagination(...)` — automatic pagination across date partitions
- `get(workflow_run_id) -> V1WorkflowRunDetails`
- `get_task_run(task_run_id) -> V1TaskSummary`
- `get_status(workflow_run_id) -> V1TaskStatus`
- `create(workflow_name, input, ...) -> V1WorkflowRunDetails` — trigger a new run
- `cancel(run_id)`, `bulk_cancel(opts)`
- `replay(run_id)`, `bulk_replay(opts)`
- `get_result(run_id) -> JSONSerializableMapping`

**`WorkflowsClient`**: `list(workflow_name, limit, offset) -> WorkflowList`, `get(workflow_id) -> Workflow`, `get_version(...)`, `delete(...)`

**`WorkersClient`**: `list() -> WorkerList`, `get(worker_id) -> Worker`, `update(worker_id, opts)`, `pause(worker_id)`, `unpause(worker_id)`

**`CronClient`**: `create(workflow_name, cron_name, expression, input, additional_metadata, priority)`, `delete(cron_id)`, `list(...)`, `get(cron_id)`

**`ScheduledClient`**: `create(workflow_name, trigger_at, input, additional_metadata)`, `list(...)`, `get(id)`, `delete(id)`, `bulk_delete(filter)`, `bulk_update(updates)`

**`LogsClient`**: `list(task_run_id, limit, since, until) -> V1LogLineList`

**`MetricsClient`** (`features/metrics.py`): `get_queue_metrics()`, `get_task_metrics(since, until, ...)`, `get_task_stats()`, `scrape_tenant_prometheus_metrics()` (note: `get_task_status_metrics` / `get_task_point_metrics` are not on the feature client — those are method names on the low-level `TaskApi`)

**`FiltersClient`** / **`WebhooksClient`** / **`RateLimitsClient`** / **`CELClient`**: CRUD/list/get for each resource

> The feature clients cover nearly every endpoint in the [API reference](rest-api-reference.md). Endpoints that are not covered (e.g. legacy step-run, SNS/Slack, trace) can be called through the low-level API classes from §1-B.

## 4. Recommended: Python SDK (A) — rationale

1. **Automatic generation routing**: `h.runs` calls the v1 stable API, while `h.workflows` / `h.workers` / `h.cron` / `h.scheduled` call legacy automatically. This reduces the need for the MCP server to handle the v0/v1 path split described in [Overview and Concepts](overview-and-concepts.md).
2. **Automatic auth and tenant resolution**: only the token needs to be provided ([Authentication](authentication-and-connection.md)).
3. **Async-friendly**: the `aio_*` methods plug directly into the async handlers of the Python MCP frameworks (`mcp` / FastMCP).
4. **Type-safe**: responses are Pydantic models, which makes serializing MCP tool output straightforward.
5. **The TypeScript SDK is equivalent**, but Python's `ClientConfig` is a plain `BaseSettings`, making standalone instantiation simpler (the TS SDK relies on an `init()` factory plus `.hatchet.yaml`). Python is also a natural fit for distributing the MCP server via uvx ([Design](mcp-server-design.md)).

### Minimal usage example

```python
import asyncio
from datetime import datetime, timedelta, timezone
from hatchet_sdk import Hatchet

h = Hatchet()  # uses HATCHET_CLIENT_TOKEN

async def list_recent_runs():
    res = await h.runs.aio_list(
        since=datetime.now(tz=timezone.utc) - timedelta(days=1),
        limit=50,
    )
    for run in res.rows:
        print(run.metadata.id, run.display_name, run.status)

asyncio.run(list_recent_runs())
```

When a direct low-level client call is needed:
```python
from hatchet_sdk.config import ClientConfig
from hatchet_sdk.clients.v1.api_client import BaseRestClient
from hatchet_sdk.clients.rest.api.workflow_runs_api import WorkflowRunsApi

config = ClientConfig()
base = BaseRestClient(config)
with base.client() as client:
    api = WorkflowRunsApi(client)
    result = api.v1_workflow_run_list(tenant=config.tenant_id, since=...)
```

## 5. Note on dependency weight

`hatchet-sdk` bundles heavy dependencies required for worker execution, such as gRPC. The MCP server uses only REST, so ideally it would need only the REST portion. However:
- The current SDK ships REST and gRPC as a single package, so a partial install is not possible.
- uvx installs into an isolated environment, so the dependency weight does not pollute the user's system.
- → The full `hatchet-sdk` dependency is accepted. If the weight becomes a problem, splitting out just the REST layer via option C (httpx plus a subset of the generated models) can be revisited later ([dependency analysis](multitenancy-and-dependencies.md)).

Next: [MCP Server Design](mcp-server-design.md)
