# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/DanMeon/hatchet-mcp/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/DanMeon/hatchet-mcp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/DanMeon/hatchet-mcp/releases/tag/v0.1.0
