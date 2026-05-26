---
status: Draft
description: "v0.3.0 operational-toolkit-expansion ADR — 7 decisions: tool surface, meta pattern, HTTP reuse, resource reliability, MCP annotations, error/log structure, 'get_run_status' camelCase"
target: v0.3.0
last_updated: 2026-05-26
---

# v0.3.0 operational-toolkit-expansion — Design Decision Research

This records the **7** industry precedents, alternatives, and failure scenarios behind the decisions in [v0.3.0/operational-toolkit-expansion.md](../../roadmap/v0.3.0/operational-toolkit-expansion.md) §Decisions that an outside reader would question. The spec states the final decisions; this document captures their rationale.

## Decision Matrix

| # | Item | Options | Chosen | Primary basis |
|---|---|---|---|---|
| 1 | Tool surface expansion | A: PR-per-tool (patch bumps) / B: single-spec bulk addition / C: domain-split specs (webhooks-spec, meta-spec, sdk-coverage-spec) | B | Operator narrative is unified ("the toolkit caught up with the SDK"); split specs would force cross-spec links that CONVENTIONS forbids and would fragment the changelog |
| 2 | Meta-tool pattern | A: LLM composes from existing reads / B: server-side aggregation tools / C: prompts that pre-embed common chains | B | Empirical: oncall queries ("what's failing?", "what's stuck?", "why did this run fail?") dominate observed usage; a 1-call answer beats a 4-call LLM chain by both latency and context budget |
| 3 | HTTP connection reuse | A: per-call `ApiClient` (status quo) / B: process-wide cached `ApiClient` + `threading.Lock` for init / C: `contextvars` per-task pool | B | The SDK ships PoolManager with `maxsize = cpu_count*5` already provisioned for concurrency, but rebuilds it per call; B reclaims that provisioning with one cache line. C is over-engineering for stdio's single-client model |
| 4 | Resources reliability wrap | A: keep raw fn calls (status quo, with the latent bug) / B: import-time `_wrap()` of each handler in `resources.py` / C: register-time wrap inside `server.py:resources.register` | B | Production bug fix. B is local (one file), preserves the existing wrapper contract, and survives a future `register_*_tools` refactor. C would centralize wrap policy but couples the resource module to server.py's import order |
| 5 | MCP annotation hygiene | A: leave annotations null / B: per-tool factory (`_read_only_annotations()`) + auto `title` from name / C: hand-curated annotations per tool | B | A leaves the spec default of "destructive, not read-only" — clients prompt on every read. C is per-call boilerplate that drifts. The factory pattern is one source of truth and is fresh-per-tool so a stray mutation can't flip the whole catalog |
| 6 | Error + observability structure | A: keep `RuntimeError` strings (status quo) / B: typed `HatchetAPIError` (status + kind) + lazy `request_id` in stderr / C: full MCP 2025-06-18 structured error channel | B | A forces LLMs to string-match `"status 429"` for branching. C requires client-side support of `structuredContent` in `CallToolResult.isError` — Claude Code reads `content` and ignores `structuredContent` as of MCP 2025-11-25. B is mechanically additive and works today |
| 7 | `get_run_status` return key | A: keep `workflow_run_id` snake_case (status quo, invariant violation) / B: switch to `workflowRunId` camelCase (breaking, minor bump) / C: dual-write both keys for one minor, then drop snake_case | B | C invents a deprecated key that nobody asked for and complicates the schema; the surface is one key in one tool, and the rest of the catalog has always returned camelCase — the inconsistency was actively misleading LLMs that learned the shape from `get_run` / `list_runs` |

## 1. Tool surface expansion

### Facts

- SDK feature-client coverage gap (verified by walking `.venv/lib/python3.13/site-packages/hatchet_sdk/features/*.py` and `clients/rest/api/*.py`): 10 read methods and 4 mutating methods had no MCP wrapper before this release
- Newly added domains: `tools/webhooks.py` (V1 inbound webhooks — list/get only; create/update/delete carry `BasicAuth` / `APIKeyAuth` / `HMACAuth` credential material excluded from MCP exposure by deliberate scope), `tools/meta.py` (composition over existing reads)
- The two excluded SDK methods are not bypasses: `Hatchet.rate_limits.aio_put` is implemented over gRPC inside the SDK (`hatchet_sdk/features/rate_limits.py:51` uses `new_conn(self.client_config, False)` + `WorkflowServiceStub.PutRateLimit`), violating this project's REST-only invariant (`tools/events.py:147` documents the same reason for `push_event` using the legacy REST `event:create`); `Hatchet.workflows.aio_delete`'s SDK docstring marks it "DANGEROUS — permanently deletes the workflow + all run history"
- v0.2.0 set the `_BULK_LIMIT = 500` precedent for `cancel_runs` / `replay_runs` (`tools/runs.py:31`); this release applies the same cap to `replay_events` and `bulk_delete_scheduled` (the latter only on the explicit-IDs path — filter mode delegates the cap to the server because `aio_bulk_delete` does not pre-resolve IDs client-side)

### Validator Counter-Arguments

- "Why not split into per-domain specs (webhooks-spec, meta-spec, sdk-coverage-spec)?" → CONVENTIONS § Cross-Link Direction Rules forbids spec ↔ spec direct links; three specs in one release would either need a meta-link page or share narrative through README, both of which add ceremony without aiding the reader. A single spec is the closer match to the operator-visible change ("the toolkit caught up with the SDK in one release")
- "Why include `replay_events` (mutating) but exclude `delete_workflow`?" → Asymmetry is intentional. `replay_events` is bounded by a 500-ID cap and idempotent at the event-store level (replaying the same event re-fires the same listeners); `delete_workflow` is irreversible and a single accidental call removes all historical run data. Symmetric inclusion would mistake the two for equivalent risks
- "Why is `bulk_delete_scheduled`'s 500-cap only on the explicit-IDs path?" → `Hatchet.scheduled.aio_bulk_delete` in filter mode does not return matched IDs; the SDK ships the deletion to the server which holds the authoritative count. Replicating the cap client-side would require a pre-resolve list call (no such SDK method exists today), adding latency for negligible safety
- "Should `list_webhooks` be excluded too if create/update/delete aren't supported?" → No. Read-only inspection of webhook configuration is the dominant operator query (incoming-event debugging), and the credential-exposure concern is mutate-side only

### Final Decision

B — single spec, bulk addition. 10 read + 4 mutating tools added; new domain modules `webhooks` (read-only) and `meta` (composition). `put_rate_limit` and `delete_workflow` deliberately excluded with the reasons recorded above. The 500-item cap pattern is applied to new bulk surfaces (`replay_events`; explicit-IDs path of `bulk_delete_scheduled`).

### Primary Sources

- hatchet-sdk REST API class index: `.venv/lib/python3.13/site-packages/hatchet_sdk/clients/rest/api/` (the SDK ships generated API classes for the 24 REST domains; the gap analysis walked each)
- MCP 2025-11-25 tools spec: <https://modelcontextprotocol.io/specification/2025-11-25/server/tools>
- Hatchet REST OpenAPI (canonical): <https://docs.hatchet.run/api>

## 2. Meta-tool pattern

### Facts

- Operator/oncall queries observed during v0.2.x usage cluster around three patterns: "what's failing the most?", "what's stuck right now?", "why did this specific run fail?"
- Each pattern previously required 3–5 LLM tool calls (paginate `list_runs(FAILED)` → in-context aggregate / `list_runs(RUNNING)` → per-row time arithmetic / `get_run` → `get_run_timings` → `get_task` → `get_task_logs` → `list_task_events`)
- LLM context budget grows linearly per tool call (each response adds JSON to context); a 4-call chain for one operator question can consume thousands of tokens that the meta-tool collapses into one structured payload
- `asyncio.gather(return_exceptions=True)` was chosen for `describe_run_failure`'s three independent reads — `logs`, `events`, `timings` are not causally dependent on each other; serializing them wastes wall-clock under the 30s per-call deadline

### Validator Counter-Arguments

- "Could prompts do this instead?" → Prompts can pre-embed parameters, but the response shape would still come back via independent tool calls (the prompt body cannot make Hatchet REST requests). The meta-tool moves the aggregation into the server, which is where it can use `asyncio.gather`, share auth/HTTP-pool, and apply the size guard once
- "What if `top_failing_workflows` undercounts because real failures exceed `scan_limit`?" → The `truncated` boolean is set when `scanned >= scan_limit`; an honest signal is better than silent undercount. Defaults (scan_limit=500, max=1000) are conservative; an operator with a 1000+ failure burst needs the full-narrative `list_runs` anyway
- "What if `describe_run_failure`'s timings call fails?" → The narrow `except (ApiException, HatchetAPIError, asyncio.TimeoutError)` demotes that branch to `timings=null` (logs + events are still returned). A broader catch (`except Exception`) would mask SDK rename / programming errors as `timings=null` and turn them into silent regressions — a real failure mode caught in this release's review pass
- "Why no meta-tool for `top_failing_tasks` (per-action) or `last_N_pushed_events`?" → YAGNI for v0.3.0; the three above were the dominant observed queries. The pattern can be repeated for new operator queries in a patch

### Final Decision

B — server-side aggregation. Three meta-tools, each thin (no new Hatchet endpoint, pure composition over existing read calls). `describe_run_failure` runs its three independent reads via `asyncio.gather` with narrow exception handling on the best-effort `timings` branch.

### Primary Sources

- Python `asyncio.gather`: <https://docs.python.org/3.10/library/asyncio-task.html#asyncio.gather>
- MCP 2025-11-25 tools — server-driven aggregation is the recommended pattern over chained client calls: <https://modelcontextprotocol.io/specification/2025-11-25/server/tools>

## 3. HTTP connection reuse

### Facts

- The SDK's `RESTClientObject.__init__` (`.venv/lib/python3.13/site-packages/hatchet_sdk/clients/rest/rest.py:67-118`) builds a fresh `urllib3.PoolManager` with `connection_pool_maxsize = cpu_count * 5` on every construction
- `ApiClient.__exit__` is a no-op (`hatchet_sdk/clients/rest/api_client.py:93-97`) — entering and exiting `with base.client() as client:` releases nothing. The prior code also never released the pool on `with`-exit (the `urllib3.PoolManager.clear()` path is never reached via the SDK's `with` block), so this decision changes construction cost only, not cleanup semantics
- `urllib3.PoolManager.pools` is an instance attribute (`urllib3/poolmanager.py:222-223`); there is no class-level / module-level pool sharing
- The PoolManager has internal locking (`urllib3/poolmanager.py:354`) and is documented thread-safe; sharing one across `asyncio.to_thread` workers is supported
- This problem also exists in the SDK's own feature clients (49+ `with self.client() as client:` sites in `hatchet_sdk/features/*.py`) — patching `_rest_call` covers our 11 REST-direct sites but leaves the SDK's `aio_*` paths upstream

### Validator Counter-Arguments

- "Why a `threading.Lock` if asyncio is single-threaded?" → `_rest_call` dispatches via `asyncio.to_thread`, so the inner `if _api_client is None` check runs in different worker threads. Two concurrent first calls can both observe `None` before either assigns; the lock + double-check closes that race
- "Could we use an `asyncio.Lock` instead?" → No — the lock guards thread-pool workers, not coroutines on the same event loop. `threading.Lock` is the correct primitive here
- "Why not also monkey-patch `BaseRestClient.client()` to fix the SDK-side problem?" → That would violate the "one client, one tenant" invariant philosophy (CLAUDE.md invariant 3) and create maintenance debt for an upstream issue. File an SDK PR instead; local patch covers our REST-direct sites
- "What if the cached `ApiClient` carries per-request mutable state?" → Verified by reading `ApiClient` source. Mutable attributes (`default_headers`, `cookie`, `user_agent`) are only written in `__init__` or via setters we never call; `param_serialize` reads `default_headers` but never writes. No per-request state on the shared instance

### Final Decision

B — process-wide cache + `threading.Lock`. `client.get_api_client()` returns the single `ApiClient` instance (lazy-initialized), and `_rest_call` invokes the cached client directly instead of entering the no-op `with` context. Per-call TCP+TLS handshakes drop to amortized zero on the 11 REST-direct sites.

### Primary Sources

- `urllib3.PoolManager` thread-safety: <https://urllib3.readthedocs.io/en/stable/advanced-usage.html#using-poolmanager>
- Python `threading.Lock` (used for the double-checked init): <https://docs.python.org/3.10/library/threading.html#threading.Lock>
- Python `asyncio.to_thread` (the worker boundary that creates the race): <https://docs.python.org/3.10/library/asyncio-task.html#asyncio.to_thread>

## 4. Resources reliability wrap

### Facts

- v0.2.0 added the 30s deadline + retry on 5xx/429/transport + structured `tool.ok` / `tool.error` log records via `_shared._reliability_wrap`; the wrap is applied at `server.py:register_read_tools` for each tool catalog entry
- `resources.py` imports six tool handler functions directly (`get_run`, `list_workflows`, `list_workers`, `get_workflow`, `get_run_status`, `get_server_info`) and awaits them in the resource handler bodies — bypassing the wrapper entirely
- The pre-fix test `test_resource_delegates_with_by_alias` (`tests/test_resources_prompts.py`) only verified serialization shape, not reliability semantics — the gap was invisible in CI
- A resource read against a hung Hatchet hangs the entire MCP session until the client times out (Claude Desktop kill thresholds vary by version; the spec deadline guarantees a 30s ceiling that the resource path skipped)

### Validator Counter-Arguments

- "Could we wrap once at `register_read_tools` time and look up the wrapped version from the tool registry?" → That works but creates an ordering dependency: `resources.register` must run after `register_read_tools`. The current `_wrap()` at module import time has no such dependency and produces a function object resources can reference directly
- "Does the import-time wrap interact badly with test monkeypatches?" → The wrap captures the function reference, not the result of `get_hatchet()`; the body of the wrapped function still calls `get_hatchet` at runtime, and tests that monkey-patch `runs.get_hatchet` see the patch. Verified empirically in `tests/test_regressions.py::test_resource_run_retries_via_reliability_wrapper` (one retry observed under a 503 → 200 sequence)
- "Why does the test file re-wrap inside the test?" → Honest answer: not strictly needed; the production wrap would suffice. The test re-wrap is defensive (independent of import-time state) and was kept because removing it doesn't make the test stronger. A code-quality nit, not a correctness issue

### Final Decision

B — import-time `_wrap()` per resource handler. `resources.py` creates six `_wrapped_*` constants at module import (`_wrapped_get_run = _wrap(get_run)`, etc.) and the resource handlers await those instead of the raw imports. Six handlers, six wrappers, no ordering dependency.

### Primary Sources

- Decision lineage: [`v0.2.0/reliability.md`](../../roadmap/v0.2.0/reliability.md) — the wrapper this fix retrofits onto the resources path
- MCP 2025-11-25 resources: <https://modelcontextprotocol.io/specification/2025-11-25/server/resources>

## 5. MCP annotation hygiene

### Facts

- MCP `ToolAnnotations` defaults (per spec): `readOnlyHint=false, destructiveHint=true, idempotentHint=false, openWorldHint=true`. Without an explicit annotation, every read is presented to the client as a destructive operation requiring user confirmation
- The `title` field was added in MCP 2025-06-18 to give clients a human-readable display name distinct from `name` (which serves protocol identity)
- `mcp.types.ToolAnnotations` is a Pydantic V2 `BaseModel`; `model_config` does **not** set `frozen=True`, so instances are mutable
- Empirical: a shared singleton `_READ_ONLY_ANNOTATIONS` mutated in one place would propagate to every registered read tool (verified — FastMCP's `list_tools` copies the reference into `MCPTool.annotations` without deep-copying)
- `_humanize_tool_name` is a one-line implementation: `return name.replace("_", " ").title()`. Output is correct for 33 of 35 tool names; `cel_debug` → "Cel Debug" and `list_dag_tasks` → "List Dag Tasks" mishandle the acronyms (deferred as cosmetic — `name` is the protocol identity, `title` is display only)

### Validator Counter-Arguments

- "Is `idempotentHint=true` meaningful on a read tool?" → Per spec, `idempotentHint` is meaningful only when `readOnlyHint=false`. Setting it to true on a read is spec-vacuous (not wrong, not load-bearing). Leaving it true is harmless and avoids a special case in the factory
- "Why a factory instead of a frozen dataclass?" → `ToolAnnotations` is upstream from the SDK; subclassing or freezing it requires patching upstream code. A factory function is the cheapest mitigation
- "Does the title-acronym issue matter for `cel_debug` / `list_dag_tasks`?" → Display-only. Clients invoke tools by `name`, not `title`. Cosmetic deferral acknowledged; an acronym map can be added in a patch if a real report comes in

### Final Decision

B — per-tool factory. `_read_only_annotations()` returns a fresh `ToolAnnotations` instance per registration; `register_read_tools` calls it inside the catalog loop. `title=_humanize_tool_name(name)` is passed to `add_tool` for every tool (read + mutating).

### Primary Sources

- MCP 2025-11-25 tool annotations: <https://modelcontextprotocol.io/specification/2025-11-25/server/tools>
- MCP 2025-06-18 changelog — `title` field added: <https://modelcontextprotocol.io/specification/2025-06-18>

## 6. Error + observability structure

### Facts

- `_api_error()` in v0.2.x returned `RuntimeError("Hatchet API error: status N, reason — body")` — single string, no machine-readable structure. The wrapper at `_shared.py:_reliability_wrap` re-raises it without touching the status
- `pytest.raises(RuntimeError, match="Hatchet API error")` is used 7+ times across the v0.2.x test suite; preserving the message prefix preserves those assertions
- MCP 2025-06-18 spec added `structuredContent` to `CallToolResult` for typed payloads, but Claude Code (the dominant client at this MCP's deployment site) reads only `content` and ignores `structuredContent` — verified via GitHub issue tracker; structured error channel uptake is uneven
- FastMCP exposes `request_id` via `mcp.get_context().request_id` only inside an active request; outside it raises `ValueError("Context is not available outside of a request")`
- Hatchet returns HTTP status codes for known semantics: 400 (bad request / validation), 401/403 (auth), 404 (not found), 409 (conflict), 422 (validation), 429 (rate limit), 5xx (server error). The `_STATUS_KIND` map covers all of these; status outside the map maps to `"unknown"` for ambiguous 4xx and `"server_error"` for 5xx

### Validator Counter-Arguments

- "Does the typed exception break existing test asserts?" → No — `HatchetAPIError` is a `RuntimeError` subclass and the message prefix is preserved. Existing `pytest.raises(RuntimeError, match="Hatchet API error")` still match
- "Why not adopt MCP `structuredContent` for errors now?" → Client uptake too uneven (Claude Code reads `content`, Gemini CLI validates `structuredContent` against `outputSchema`, VS Code prefers `structuredContent`). A typed `kind` in stderr + RuntimeError gives downstream tooling a structured channel today; the protocol path is a future addition once major clients converge
- "Could the lazy `app.mcp` import create a circular dependency?" → The import graph is `_shared → app` and `server → app`, `server → _shared` — verified linear (no `app → _shared` or `app → server` edge). The lazy import inside `_current_request_id()` is defensive against future changes, not load-bearing today
- "What if `request_id` retrieval raises?" → Handled. The tuple `(LookupError, ValueError, RuntimeError, AttributeError)` catches every documented FastMCP failure mode; the function returns `None` and emit proceeds. A noisy regression would surface as `request_id=null` records rather than a crash

### Final Decision

B — typed `HatchetAPIError` + lazy `request_id` in stderr. `_STATUS_KIND` maps known HTTP codes to enumerated `kind` strings; the wrapper propagates `error_status` and `error_kind` into both `tool.ok` and `tool.error` records (the OK record carries `request_id` only). Backward-compatible message prefix preserved.

### Primary Sources

- MCP 2025-06-18 structured content / outputSchema: <https://modelcontextprotocol.io/specification/2025-06-18>
- Claude Code MCP client behavior — reads `content` not `structuredContent`: <https://github.com/anthropics/claude-code/issues>
- FastMCP `Context.request_id` API: `.venv/lib/python3.13/site-packages/mcp/server/fastmcp/server.py:332-341`
- HTTP status code semantics (RFC 9110): <https://datatracker.ietf.org/doc/html/rfc9110>

## 7. `get_run_status` return key

### Facts

- CLAUDE.md invariant 4: "Tool output uses the Hatchet REST shape — serialize SDK models through `_dump`, which forces `by_alias=True` → camelCase keys (`runId`, `createdAt`); tests pin this shape"
- `get_run_status` was the single tool that hand-built a snake_case dict instead of going through `_dump_item` — predates the invariant's enforcement
- Every other tool returning IDs uses camelCase (`workflowRunId`, `taskExternalId`, `runId`); the snake_case key in `get_run_status` was an outlier
- The resource `hatchet://runs/{workflow_run_id}/status` follows by pass-through (the resource handler just `json.dumps` the tool's return value)
- Parameter names are unchanged — `workflow_run_id` is still the kwarg name for the tool input; only the return-dict key flips

### Validator Counter-Arguments

- "Why not dual-write both keys for one minor?" → Invents a deprecated key nobody asked for. The downstream impact is bounded: one key in one tool; the LLMs already learned camelCase from every other tool's response
- "Should the parameter name flip too?" → No — Python kwargs and URI template variables stay snake_case by convention. Only the *output* shape needed alignment
- "What if a downstream tool pattern-matches `workflow_run_id` from `get_run_status` output?" → Surfaces immediately as a `KeyError`, not a silent regression. The breaking change is loud by design
- "Why is this a separate decision from #1?" → Decision #1 is additive (new tools); #7 is a contract change to an existing tool. Mixing them in one decision row would conflate "what's new" with "what changed shape"

### Final Decision

B — switch to `workflowRunId` camelCase. Single-line change in `tools/runs.py:get_run_status`; resource pass-through propagates automatically. Documented as the release's single breaking change in CHANGELOG.

### Primary Sources

- Hatchet REST OpenAPI uses `runId` / `workflowRunId` throughout: <https://docs.hatchet.run/api>

## References

- Paired spec: [v0.3.0/operational-toolkit-expansion.md](../../roadmap/v0.3.0/operational-toolkit-expansion.md)
- MCP 2025-11-25 specification: <https://modelcontextprotocol.io/specification/2025-11-25>
- MCP 2025-06-18 changelog: <https://modelcontextprotocol.io/specification/2025-06-18>
- hatchet-sdk Python source (verified during the gap analysis): <https://github.com/hatchet-dev/hatchet-python-sdk>
- urllib3 PoolManager documentation: <https://urllib3.readthedocs.io/en/stable/advanced-usage.html>
- RFC 9110 (HTTP Semantics): <https://datatracker.ietf.org/doc/html/rfc9110>
