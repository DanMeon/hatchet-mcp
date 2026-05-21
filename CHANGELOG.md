# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/DanMeon/hatchet-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/DanMeon/hatchet-mcp/releases/tag/v0.1.0
