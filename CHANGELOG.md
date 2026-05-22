# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-05-22

### Changed (breaking)

- **`list_runs`** now defaults to a 9-field projection (`minimal_output=True`):
  `taskExternalId`, `workflowRunExternalId`, `status`, `workflowName`, `startedAt`,
  `finishedAt`, `errorMessage`, `parentTaskExternalId`, `numSpawnedChildren` —
  typically ~5-7x smaller per response (a 124 KB / 100-row scan drops to ~20 KB).
  Set `minimal_output=False` to get every field, or use `get_run` for one run's full
  record. Follows the GitHub MCP convention of defaulting list tools to a compact
  shape (`src/hatchet_mcp/tools/runs.py`).
- **`list_events`** now defaults to `minimal_output=True`, which drops each event's
  `payload`, `triggeredRuns`, and `additionalMetadata` fields. Set
  `minimal_output=False` for the full record, or use `get_event` for one event's full
  payload. Same convention as `list_runs` (`src/hatchet_mcp/tools/events.py`).

Callers that depended on the full row from either tool must now opt in by passing
`minimal_output=False`. The 500 KB size guard still wraps the minimal-projection
path so a runaway response cannot bypass it.

### Changed

- **`get_run_timings`** description now explicitly calls out that it is the cheapest way
  to expand a parent run's child task tree in a single call (use `depth=1` for direct
  children) — closes a discovery gap that previously forced callers to page through
  `list_runs` to find children of a known parent
  (`src/hatchet_mcp/tools/observability.py`).

## [0.2.1] - 2026-05-22

### Added

- **`list_runs`** now forwards two SDK filters that were previously hidden from MCP clients:
  `parent_task_external_id` (expand a sub-workflow tree from a parent run) and
  `triggering_event_external_id` (trace which runs an event caused)
  (`src/hatchet_mcp/tools/runs.py`).
- **`list_scheduled`** now forwards three SDK filters: `parent_workflow_run_id`,
  `order_by_field` (`triggerAt` / `createdAt`), and `order_by_direction` (`ASC` / `DESC`)
  (`src/hatchet_mcp/tools/schedules.py`). Invalid `order_by_*` values raise with the
  allowed-values list rather than reaching the SDK.
- **`list_crons`** now forwards `order_by_field` (`name` / `createdAt`) and
  `order_by_direction` (`ASC` / `DESC`) (`src/hatchet_mcp/tools/schedules.py`).
- **`list_events`** now forwards `event_ids` (specific events by UUID) and `scopes`
  (filter by event scope strings) (`src/hatchet_mcp/tools/events.py`).
- **`list_rate_limits`** now forwards `order_by_field` (`key` / `value` / `limitValue`)
  and `order_by_direction` (lowercase `asc` / `desc`, matching the SDK's
  `RateLimitOrderByDirection` enum — distinct from `WorkflowRunOrderByDirection`'s
  uppercase) (`src/hatchet_mcp/tools/observability.py`).
- New shared helper `_parse_enum` for validating a single (str) enum value, mirroring
  `_parse_enum_list` (`src/hatchet_mcp/_shared.py`).

## [0.2.0] - 2026-05-21

### Added

- New read tool **`get_server_info`** and matching resource **`hatchet://server/info`**, both
  delegating to a single `_build_server_info` helper and returning a byte-identical JSON
  payload (`read_only`, `read_tool_count`, `mutating_tool_count`, `server_url_source` —
  `"token"` or `"override"` —, `hatchet_sdk_version`, `python_version`). Neither surface
  carries the Hatchet token. Read tool count is now **25** (`src/hatchet_mcp/tools/server_info.py`,
  `src/hatchet_mcp/resources.py`).
- **Per-call 30s deadline** on every registered tool via `asyncio.wait_for`, so a hung Hatchet
  can no longer lock the stdio session (`src/hatchet_mcp/_shared.py`).
- **Idempotent-only retry** on transient `5xx`, `429`, and connection-class
  (`RestTransportError`) failures: 3 attempts, exponential backoff (1s / 2s / 4s with ±25%
  jitter), and `Retry-After` honored on `429` clamped to 10s. Non-idempotent mutations
  (`trigger_workflow`, `push_event`, `cancel_runs`, `replay_runs`, `restore_task`, every
  `create_*`) keep the deadline but skip the retry layer, gated at registration time by
  `ToolAnnotations.idempotentHint` (`src/hatchet_mcp/_shared.py`, `src/hatchet_mcp/server.py`).
- **Structured stderr logging**: one JSON-line record per tool invocation
  (`event=tool.ok` / `tool.error`, with `tool`, `duration_ms`, and a redacted `redacted_error`
  on failure) and per server lifecycle event (`event=server.start` / `server.error`). Records
  include input-validation failures that raise before any Hatchet call, because the timer
  starts at wrapper entry (`src/hatchet_mcp/_logging.py`).

### Changed

- Startup banner is now an `event=server.start` JSON record on stderr instead of the
  unstructured `hatchet-mcp: starting…` print; the `ConfigError` exit emits a matching
  `event=server.error` record (`src/hatchet_mcp/server.py`).
- `server.start` / `get_server_info` use the same origin label `"token"` / `"override"` for
  the server URL source so a single grep covers both channels.
- Tool handlers no longer wrap each Hatchet call in `try / except ApiException`; the
  reliability wrapper owns the SDK-exception-to-`RuntimeError` translation centrally, and the
  raw exception flows through the retry layer first.

### Security

- The stderr structured-log channel is independently redacted at format time — every string
  field, at any nesting depth, runs through `redact()` before emit. The existing MCP JSON-RPC
  error channel redaction via `_api_error` is unchanged; the two surfaces own independent
  redaction with neither acting as the other's gate (`src/hatchet_mcp/_logging.py`,
  `src/hatchet_mcp/_shared.py`).

### Docs

- Freeze the `v0.2.0/reliability` spec and its paired ADR (`Draft → Frozen`, `target → ga`),
  and bump `docs/roadmap/README.md`'s Status to v0.2.0.

## [0.1.1] - 2026-05-21

### Security

- `redact()` now strips both the full `HATCHET_CLIENT_TOKEN` and its 16-char prefix from
  external-facing strings, catching truncated log lines and partial header echoes that the
  exact-substring match in 0.1.0 missed (`src/hatchet_mcp/config.py`).
- `ConfigError` from `_parse_bool` runs the offending env value through `redact()` before
  echoing — a token mis-pasted into `HATCHET_MCP_READ_ONLY` no longer surfaces in the
  startup banner (`src/hatchet_mcp/config.py`).
- New `muzzle_dependency_loggers()` forces `hatchet_sdk`, `aiohttp`, `httpx`, `httpcore`,
  `grpc`, and `urllib3` loggers to `WARNING` at server boot, closing the only realistic
  path by which a downstream `LOG_LEVEL=DEBUG` could echo `Authorization: Bearer <token>`
  headers to stderr (`src/hatchet_mcp/server.py`).

### Docs

- README: add a 4-step Quick start (token → install → MCP-client wiring → first call) and
  remove the pre-publish placeholders (`(once published)`, `Before the package is published
  to PyPI…`) now that 0.1.0 is on PyPI.
- Scaffold the `v0.2.0/reliability` spec (idempotent retry + 30s deadline + structured
  stderr logs + `get_server_info` diagnostics) with its paired ADR and the first row in
  `docs/roadmap/README.md`'s active spec index.

## [0.1.0] - 2026-05-21

Initial release.

### Added

- FastMCP server exposing one Hatchet tenant over its REST API via stdio.
- **24 read-only tools** (always registered): workflows, runs, tasks, task logs and events,
  workers, events and event keys, crons, scheduled runs, rate limits, filters, CEL debug,
  queue/task metrics, run timings, and OpenTelemetry traces.
- **17 mutating tools** (opt-in via `HATCHET_MCP_READ_ONLY=false`): run trigger/cancel/replay,
  task restore, event push, workflow/worker pause-resume, and cron/scheduled/filter management.
- **5 MCP resources** and **3 operator prompts** (`triage_failed_runs`, `debug_run`,
  `tenant_health`).
- Layered safety: read-only by default, in-handler mutation gate, destructive tool hints,
  dry-run default and a 500-run cap on bulk cancel/replay, and full token redaction.
- Response-size controls: payload-free lists, default/max `limit` clamps, and a ~500 KB result
  ceiling.
- Environment-only configuration; fail-fast startup when `HATCHET_CLIENT_TOKEN` is missing.
- PyPI publishing via GitHub Actions Trusted Publishing (OIDC).

[Unreleased]: https://github.com/DanMeon/hatchet-mcp/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/DanMeon/hatchet-mcp/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/DanMeon/hatchet-mcp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/DanMeon/hatchet-mcp/releases/tag/v0.1.0
