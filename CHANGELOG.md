# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
