---
status: Draft
description: "v0.2.0 reliability ADR — 5 decisions: retry boundary, per-call deadline, log format, diagnostics surface, idempotency gate"
target: v0.2.0
last_updated: 2026-05-21
---

# v0.2.0 reliability — Design Decision Research

This records the **5** industry precedents, alternatives, and failure scenarios behind the decisions in [v0.2.0/reliability.md](../../roadmap/v0.2.0/reliability.md) §Decisions that an outside reader would question. The spec states the final decisions; this document captures their rationale.

## Decision Matrix

| # | Item | Options | Chosen | Primary basis |
|---|---|---|---|---|
| 1 | Retry boundary | A: no retry / B: blanket retry on all errors / C: idempotent-only retry with backoff + `Retry-After` | C | Non-idempotent retry replays mutations — a hard correctness rule |
| 2 | Per-call deadline | A: no deadline / B: 10s aggressive / C: 30s conservative | C | Read tools on a slow Hatchet can legitimately exceed 10s; 30s stays under typical MCP client kill thresholds |
| 3 | Log format | A: stdlib `logging.basicConfig` / B: `structlog` / C: small custom JSON-line emitter on stderr | C | A is unstructured; B adds a dependency on a `uvx`-distributed package; a ~20-line emitter aligns with the existing `redact()` helper |
| 4 | Diagnostics surface | A: tool only / B: resource only / C: tool + resource sharing one builder | C | Tool is discoverable to the LLM; resource is URI-addressable for clients that index resources — both cost almost nothing when they share one builder |
| 5 | Idempotency retry gate | A: reuse existing `_destructive(idempotent=...)` annotation via register-time wrap / B: new per-function decorator / C: separate retry config | A | The annotation is already the canonical "can this be safely retried?" answer and feeds the MCP `idempotentHint`; reading it at registration time avoids a parallel source of truth |

## 1. Retry boundary

### Facts

- `v0.1.0` has no retry layer: a single Hatchet 5xx becomes `RuntimeError("Hatchet API error: status 503...")` and surfaces to the MCP client unchanged (`_shared.py:72-82`)
- Every mutating tool carries an `idempotent` flag via `_destructive(idempotent=...)` (`_shared.py:177-181`), already used to set the MCP `idempotentHint` on the tool annotation
- RFC 7231 §6.6 classifies 5xx as the retryable family; RFC 6585 §4 defines 429 + `Retry-After`
- AWS SDKs and Stripe's official SDKs retry idempotent operations only, with exponential backoff and jitter

### Validator Counter-Arguments

- "Doesn't blanket retry waste time on permanent errors like 401?" → Only 5xx and 429 enter the retry path; 4xx (except 429) surfaces immediately on the first attempt
- "Can't the MCP client itself retry?" → It can, but it has no idempotency awareness and would replay non-idempotent mutations (`trigger_workflow`, `cancel_runs`) on a network blip — server-side gating is required
- "Why 3 attempts, not 5?" → 1s + 2s + 4s ≈ 7s retry budget fits inside the 30s per-call deadline (Decision 2) with headroom for the slowest individual attempt
- "What about 408 Request Timeout?" → Not currently retried — Hatchet does not document 408 as a transient state; if a real report comes in, add it to the retryable set in a patch
- "Can two consecutive 429s push the call past the 30s deadline?" → Worst case: 1s + 2s + 4s backoff + two 10s `Retry-After` waits ≈ 27s before the final attempt's network time. If the final attempt then runs near the deadline, the call hits the timeout (Decision 2) and surfaces as `TimeoutError`. This is the correct behavior — a sustained 429 stream means the tenant is genuinely rate-limited; surfacing it to the LLM (instead of holding forever) is the point of having a deadline

### Final Decision

C — idempotent-only retry. 3 attempts max with exponential backoff (1s / 2s / 4s, ±25% jitter). Retryable: 5xx + 429 + connection errors. 429 honors `Retry-After` clamped to 10s to stay within the per-call deadline. Read tools are always retryable (inherently idempotent); mutating tools retry only when `_destructive(idempotent=True)`.

### Primary Sources

- RFC 7231 §6.6 — Server Error 5xx: <https://datatracker.ietf.org/doc/html/rfc7231#section-6.6>
- RFC 6585 §4 — 429 Too Many Requests + `Retry-After`: <https://datatracker.ietf.org/doc/html/rfc6585#section-4>
- AWS SDK retry strategy: <https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html>
- Stripe API idempotent requests: <https://docs.stripe.com/api/idempotent_requests>

## 2. Per-call deadline

### Facts

- `v0.1.0` has no per-call timeout: `asyncio.to_thread(_invoke)` (`_shared.py:142-157`) and every `aio_*` SDK call can block indefinitely
- A stdio session lives as long as the MCP client; Claude Desktop sessions routinely run hours
- A 30s ceiling minus the retry budget (~7s) leaves > 20s for the slowest individual attempt — well above typical Hatchet read P99 latencies
- `asyncio.wait_for` (Python 3.10+) is the standard primitive; cancels the wrapped coroutine on timeout with a `TimeoutError`

### Validator Counter-Arguments

- "What if a legitimate `list_runs` takes more than 30s?" → The 500 KB result-size guard (`_shared.py:46-55`) and the `_clamp_limit` cap (100) already protect against multi-MB lists; a legitimate 30s+ read indicates the user should narrow the filter
- "Should the deadline be per-tool-kind (longer for bulk ops)?" → No — bulk ops are explicitly outside the retry layer (Decision 1) and already have their own guard rails (`runs.py:31, 205-214`); a single uniform deadline is simpler and predictable
- "Should the deadline be configurable?" → Not in 0.2. Env-only config keeps the surface tight; if real reports come in, add an env var in a patch

### Final Decision

C — 30 seconds, applied at the `_rest_call` and per-`aio_*` boundary via `asyncio.wait_for(coro, timeout=30)`. The retry layer (Decision 1) wraps inside the deadline, not outside: total wall-clock for a tool call is capped at 30s regardless of how many retries it took.

### Primary Sources

- MCP 2025-11-25 spec — no spec-mandated per-tool timeout: <https://modelcontextprotocol.io/specification/2025-11-25>
- Python `asyncio.wait_for`: <https://docs.python.org/3.10/library/asyncio-task.html#asyncio.wait_for>

## 3. Log format

### Facts

- `v0.1.0` emits one `print(...)` line on stderr at startup (`server.py:104-109`) and a second `print(...)` on `ConfigError` exit (`server.py:87`); no per-call records, no error correlation surface
- Stdout is the MCP JSON-RPC channel — any extra write there corrupts the protocol; stderr is the only safe diagnostic channel and already exclusive in `v0.1.0`
- `redact()` (`config.py`) strips the full token and its 16-char prefix; the MCP JSON-RPC error channel calls `redact()` inside `_api_error` (`_shared.py:82`) — this is the existing token-leak gate for tool errors
- `structlog` adds a ~30 KB transitive dependency; in a `uvx`-distributed package every cold start downloads it
- The Python stdlib has no built-in JSON formatter — a `JSONFormatter` is roughly the same line count as a custom emitter

### Validator Counter-Arguments

- "Why not stdlib `logging` with a custom `JSONFormatter`?" → That works, and is a valid future option. C is preferred because a tiny emitter colocates redaction with formatting (single point to audit) and avoids the stdlib's global root-logger entanglement that already drove the `muzzle_dependency_loggers` workaround (`server.py:33-41` for the muzzled set, `server.py:58-61` for the muzzle function)
- "Won't downstream tools rely on a stable schema?" → The schema is documented in the spec and stable across patches in this minor; a schema change gets a minor bump
- "What if a record's fields contain newlines?" → JSON-encode the whole record on one line; the emitter calls `json.dumps(..., ensure_ascii=False)` and writes a single `\n`-terminated line
- "Does this remove `redact()` from `_api_error`?" → No. The MCP JSON-RPC tool-error channel and the stderr structured-log channel are independent surfaces; each owns its redaction. `_api_error` keeps its existing call (`_shared.py:82`) — the emitter's redaction covers the stderr channel only

### Final Decision

C — a ~20-line custom emitter that writes one JSON-shaped record per event to stderr. Each tool invocation emits exactly one record (`event=tool.ok` or `event=tool.error`, not both). The startup banner becomes `event=server.start` with the same schema; the `ConfigError` exit-print becomes `event=server.error`. `redact()` is applied to every string field at format time *inside the emitter*, owning the stderr surface. The MCP JSON-RPC error channel (`_api_error` → `RuntimeError`) keeps its existing `redact()` call (`_shared.py:82`) unchanged — the two surfaces are independently redacted, neither acting as the other's gate.

### Primary Sources

- Python `logging` module (stdlib): <https://docs.python.org/3.10/library/logging.html>
- `structlog` (rejected dependency): <https://www.structlog.org/>

## 4. Diagnostics surface

### Facts

- `v0.1.0` exposes nothing about its own state; the LLM that sees a tool error must infer from the message whether the token is wrong, read-only is on, or the server URL override is missing
- MCP resources are URI-addressable and many clients (Claude Desktop) index them on connect; tools are discoverable but invoked on demand
- A shared `_build_server_info()` helper costs roughly 5 extra lines beyond a tool-only or resource-only implementation
- The payload schema is fixed (`read_only`, `read_tool_count`, `mutating_tool_count`, `server_url_source`, `hatchet_sdk_version`, `python_version`) and never contains the token

### Validator Counter-Arguments

- "Doesn't exposing server state risk leaking config?" → `server_url_source` is the *origin label* (`"token"` or `"override"`) not the URL itself; the payload is run through `redact()` as defense-in-depth even though no field should contain the token
- "Should this be a prompt instead?" → A prompt orchestrates multi-tool flows; a single field bag of facts is the wrong abstraction for a prompt — a tool/resource pair is correct
- "Why include `hatchet_sdk_version`?" → A common support question is "are you on a current SDK?"; exposing the version short-circuits that loop without the user inspecting their lock file
- "Does diagnostics belong in a reliability spec at all?" → The primary use case is "the LLM hits a tool error and needs to self-diagnose"; that is a resilience-as-debuggability concern, not a separate feature. The spec lives together because diagnostics-without-resilience leaves errors uncorrelated, and resilience-without-diagnostics leaves the user unable to verify mode

### Final Decision

C — both. A read tool `get_server_info()` (becoming the 25th read tool after this spec) and a resource `hatchet://server/info`, both calling `_build_server_info()` and returning byte-identical JSON.

### Primary Sources

- MCP 2025-11-25 — resources: <https://modelcontextprotocol.io/specification/2025-11-25/server/resources>
- MCP 2025-11-25 — tools: <https://modelcontextprotocol.io/specification/2025-11-25/server/tools>

## 5. Idempotency retry gate

### Facts

- `_destructive(idempotent: bool)` is set on every mutating tool (per-module `MUTATING_TOOLS` tuples in `tools/*.py`)
- The annotation already feeds MCP `ToolAnnotations.idempotentHint` so MCP clients can prompt differently for retryable vs non-retryable mutations
- The MCP tool annotation lives on the registered `Tool` object via `mcp.add_tool(..., annotations=...)`, not on the Python function — a function-level decorator cannot read it back from the function
- `register_mutating_tools` (`server.py:70-72`) and `register_read_tools` (`server.py:64-66`) already iterate the catalog tuples and have direct access to the annotation at registration time
- `CLAUDE.md` records the project commitment that "idempotency annotations are honest" — every mutating handler's flag was hand-verified against the SDK call shape

### Validator Counter-Arguments

- "Where does the retry decorator read the `idempotent` flag from?" → Not from the function. From the catalog tuple at registration time. `register_mutating_tools` reads `annotations.idempotentHint` from its local loop variable and either wraps or skip-wraps `fn` before calling `mcp.add_tool`. The annotation stays the single source of truth — no per-function marker, no `mcp._tool_manager` lookup, no catalog-tuple shape change
- "What about read tools — they have no `MUTATING_TOOLS`-style annotation?" → Reads are idempotent by definition; `register_read_tools` always wraps. The retry wrapper itself is annotation-agnostic — only the *decision to wrap* depends on registration-time flag inspection
- "What if the SDK quietly changes a call's idempotency semantics?" → The annotation is the single point of truth; if a divergence is discovered, fix the annotation, not the retry layer. This is no worse than today, where the MCP `idempotentHint` would also be stale
- "What about `pause_workflow` (idempotent=True) — if the second attempt arrives after a resume, it could re-pause?" → That is an acceptable replay surface for an idempotent op; the alternative is to not retry it, which sacrifices the resilience benefit on a tool that is by construction safe to repeat

### Final Decision

A — reuse `_destructive(idempotent=...)` via register-time inspection. `register_mutating_tools` reads `annotations.idempotentHint` from each catalog tuple and wraps `fn` in the retry-and-deadline wrapper only when True. `register_read_tools` wraps unconditionally. No new config knob, no function-level marker, no catalog-tuple-shape change — the annotation is read where it already lives.

### Primary Sources

- MCP 2025-11-25 — `ToolAnnotations.idempotentHint`: <https://modelcontextprotocol.io/specification/2025-11-25/server/tools>

## References

- Paired spec: [v0.2.0/reliability.md](../../roadmap/v0.2.0/reliability.md)
- RFC 7231 — HTTP/1.1 Semantics: <https://datatracker.ietf.org/doc/html/rfc7231>
- RFC 6585 — Additional HTTP Status Codes: <https://datatracker.ietf.org/doc/html/rfc6585>
- AWS SDK retry behavior: <https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html>
- Stripe API idempotency: <https://docs.stripe.com/api/idempotent_requests>
- MCP 2025-11-25 specification: <https://modelcontextprotocol.io/specification/2025-11-25>
