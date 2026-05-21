---
status: Frozen
description: "v0.2.0 — idempotent retry + 30s deadline + structured stderr logs + 'get_server_info' diagnostics tool"
ga: v0.2.0
last_updated: 2026-05-21
---

# v0.2.0 — Reliability

This version makes `hatchet-mcp` resilient to upstream blips and observable from the outside. `v0.1.0` returns a hard error on the first transient Hatchet 5xx and emits a single `print` to stderr at startup — useful for the maintainer, opaque for downstream MCP clients trying to attribute a failure. This spec adds resilience at the REST boundary, observability of every tool invocation, and a self-describing surface, while keeping every existing tool's input shape, output shape, and read/write semantics unchanged. Per-decision specifics live in the Decisions table.

Existing invariants are preserved: read-only by default, the two-layer mutation gate, the 500-run bulk cap, the `redact()` boundary, and the camelCase REST shape. No tool is removed; one read tool is added.

Rationale, alternatives, and failure scenarios for the key decisions live in the paired ADR: [reliability-research.md](../../design/v0.2.0/reliability-research.md).

## Decisions

| Item | Value | Rationale |
|---|---|---|
| 1 — Retry boundary | Exponential backoff (3 attempts, 1s/2s/4s with ±25% jitter); 5xx and 429 only; idempotent ops only; `Retry-After` honored on 429 (clamped to 10s) | Transient 5xx and rate-limit responses are the dominant failure modes for a long-lived stdio server; non-idempotent mutations (`trigger_workflow`, `push_event`, `cancel_runs`, `replay_runs`, `restore_task`, `create_*`) must never retry because replay risks duplicate side effects. See ADR §1 for the full comparison. |
| 2 — Per-call deadline | 30 seconds, applied at the `_rest_call` and per-`aio_*` call site via `asyncio.wait_for`. The deadline wraps **every** read and mutating tool (so AC-4 holds for non-idempotent mutations too); the retry layer (Decision 1 + 5) wraps only idempotent ones and lives *inside* the deadline. Retry budget (~7s) sits inside the deadline, not outside | A stdio session can run for hours per Claude Desktop session; a hung Hatchet would otherwise lock the entire conversation. 30s leaves > 20s for the slowest individual attempt while staying under typical MCP client kill thresholds. See ADR §2. |
| 3 — Log format | One JSON-shaped record per tool invocation on stderr: `{event, tool, duration_ms, redacted_error?}`. `event` is `tool.ok` or `tool.error`; startup banner becomes `event=server.start` with the same shape. **Two independently-redacted surfaces**: (a) the stderr structured records are redacted *inside the log emitter* at format time; (b) the MCP JSON-RPC tool-error channel keeps its existing `redact()` call inside `_api_error` (`_shared.py:82`), unchanged. Each surface owns its own redaction — neither acts as the other's gate | A single `print` at startup is opaque — users debugging "did the tool fail or did Claude not call it?" have no audit trail. A structured record per invocation makes the answer one `grep` away without leaking tokens. See ADR §3. |
| 4 — Diagnostics surface | New read tool `get_server_info` + resource `hatchet://server/info`, both backed by one `_build_server_info()` helper. Payload: `{read_only, read_tool_count, mutating_tool_count, server_url_source, hatchet_sdk_version, python_version}`. Read tool count becomes 25 after this spec | The LLM hitting a tool error cannot distinguish "wrong token" from "read-only is on" from "server URL override missing" without a self-describing endpoint. Tool form is discoverable by the LLM; resource form is URI-addressable for clients that index resources on connect. See ADR §4. |
| 5 — Idempotency retry gate | Implementation lives at registration time, not as a Python decorator on the handler. `register_mutating_tools` already iterates `(fn, name, description, annotations)` tuples (`server.py:70-72`); it reads `annotations.idempotentHint` and selects the wrap variant before calling `mcp.add_tool` — idempotent handlers get the full retry+deadline wrap, non-idempotent ones get a deadline-only wrap (since Decision 2 covers every tool). `register_read_tools` (`server.py:64-66`) wraps unconditionally with retry+deadline because reads are inherently retryable. No new per-function marker, no `mcp._tool_manager` lookup, no catalog-tuple-shape change | The MCP `ToolAnnotations.idempotentHint` is already the canonical "can this be safely retried?" answer and feeds the per-tool MCP annotation; reading it where it already lives (the catalog tuple at registration time) avoids a parallel source of truth. See ADR §5. |

## Acceptance Criteria

- **AC-1** — when Hatchet returns a 503 on a read tool, the server retries up to 3 times with exponential backoff and surfaces the final error only if every attempt still fails
- **AC-2** — when Hatchet returns 429 with a `Retry-After` header on a retryable call, the server waits at least that long (clamped to 10s) before the next attempt
- **AC-3** — when a non-idempotent mutating tool (`trigger_workflow`, `push_event`, `restore_task`, `cancel_runs`, `replay_runs`, every `create_*`) sees a transient 5xx, the tool surfaces the error on the first attempt and performs no retry
- **AC-4** — when a single Hatchet request exceeds the 30s per-call deadline, the tool surfaces a timeout error instead of hanging indefinitely
- **AC-5** — every tool invocation — including failures from input validation helpers (`_parse_dt`, `_parse_statuses`, `_clamp_limit`, `_parse_enum_list`) that raise *before* any Hatchet call — emits exactly one structured JSON record to stderr containing `event` (`tool.ok` or `tool.error`), `tool`, and `duration_ms` (measured from invocation entry to record emit)
- **AC-6** — a `tool.error` record contains a `redacted_error` field that never includes the raw `HATCHET_CLIENT_TOKEN` (full value or 16-char prefix); the MCP JSON-RPC tool-error channel also never carries the raw token, preserved by `_api_error` continuing to call `redact()`
- **AC-7** — calling `get_server_info` returns a JSON object with the exact keys `read_only`, `read_tool_count`, `mutating_tool_count`, `server_url_source` (`"token"` or `"override"`), `hatchet_sdk_version`, `python_version`; the response never contains the token
- **AC-8** — reading the `hatchet://server/info` resource returns a payload byte-identical to `get_server_info`'s response

## Non-Goals

- **HTTP / SSE transport** — out of scope here. A transport change introduces an auth story (OAuth or header tokens) that is its own design decision, deferred to a later minor
- **Read-tool result caching** — read tools must reflect live tenant state; a cache layer would risk staleness with negligible payoff for a stdio server
- **FastMCP `task=True` background tasks** — tied to a FastMCP 3.x migration that carries its own breaking-change inventory; not in scope for 0.2
- **Bulk-op partial-failure recovery** — `cancel_runs` / `replay_runs` are non-idempotent and intentionally outside the retry layer; partial-failure semantics stay as-is in 0.2
- **Configurable deadline / retry knobs** — env-only config keeps the surface tight; a single env var per knob is YAGNI until a real report justifies it

## References

- Paired ADR: [reliability-research.md](../../design/v0.2.0/reliability-research.md)
- `_shared.py:72-82` — current `_api_error` shape (no retry; existing `redact()` call retained by Decision 3)
- `_shared.py:142-157` — current `_rest_call` (no per-call timeout)
- `_shared.py:177-181` — `_destructive(idempotent=...)` annotation whose `idempotentHint` field Decision 5 reads at registration time
- `server.py:33-41` — `_DEPENDENCY_LOGGERS` tuple muzzled in `v0.1` to block dependency-logger token leaks
- `server.py:70-72` — `register_mutating_tools` loop where Decision 5's wrap happens
- `server.py:104-109` — current single-`print` startup banner replaced by an `event=server.start` structured record (the `ConfigError` exit-`print` at `server.py:87` transitions to an `event=server.error` record on the same channel)
- [SECURITY.md](../../../SECURITY.md) — token confidentiality boundary that Decision 3's dual-surface redaction preserves
