# Multitenancy and Dependencies

Two operational topics: how to work with more than one tenant, and the shape of the dependency tree (notably the gRPC stack).

## 1. Multitenancy

### 1-1. Background — one token = one tenant

A Hatchet API token is a JWT, and **the tenant ID (the `sub` claim) and the server URL are embedded in the token.** The SDK (`Hatchet()`) resolves the tenant and URL from that token, so a single token can **never access more than one tenant.** Real multitenancy means handling *multiple tokens*.

This server is single-tenant by design: one `HATCHET_CLIENT_TOKEN` → one client → one tenant.

### 1-2. Options

| Option | How | Code change | Security | Notes |
|---|---|---|---|---|
| **A. Multiple server instances** | One hatchet-mcp process per tenant (one token each). Register several servers in the MCP client config, e.g. `hatchet-prod`, `hatchet-staging` | **None** | **Best** — process isolation, no token mixing | Recommended default. More processes; the client picks which server to use |
| **B. Token map + `tenant` argument** | Inject N tokens via an env such as `HATCHET_MCP_TENANTS` (JSON: alias→token); the server caches a client per alias. Add a `tenant` argument to every tool, with a configurable default | **Large** — propagate a `tenant` parameter across 41 tools + resources, and handle multi-token caching and redaction | Medium — all tenant tokens live in one process env (larger blast radius) | Only when a single server must switch tenants. Also requires a policy for whether the `read_only` gate applies per-tenant or globally |
| **C. Per-call token argument** | Pass the token as an argument on every tool call | Large | **Rejected** — the token would pass through the LLM and transport layers (violates the token-never-exposed principle, [design §5]) | Not adopted |

### 1-3. Recommended pattern

- **Multiple instances (A) is the recommended pattern.** Zero code, best security, and sufficient for most operational scenarios: run one hatchet-mcp process per tenant and register each in the MCP client (see the README "Multiple tenants" section).
- If a single server must switch tenants, option B is possible, but it is a broad change that adds a `tenant` parameter to 41 tool signatures and would first require deciding:
  1. the token-injection format (`HATCHET_MCP_TENANTS` JSON env vs multiple `HATCHET_CLIENT_TOKEN_<ALIAS>` envs);
  2. how the default tenant is chosen (the behavior of calls that omit it);
  3. whether the `read_only` gate is global or per-tenant;
  4. extending `redact()` to mask every tenant token.

## 2. Dependencies (the gRPC stack)

### 2-1. Measurements (this repo's .venv, Python 3.13, macOS arm64)

Every tool is **REST-only**, so the gRPC dispatcher is never used at runtime. This raises the question: can the gRPC stack be dropped?

| Item | Size | Notes |
|---|---|---|
| `grpc` (includes the native `_cython/cygrpc*.so`, a single 37M file) | **38M** | the bulk of the gRPC stack |
| `grpc_tools` | **22M** | usually a build-time tool, but the SDK imports it at runtime |
| `google` (protobuf runtime) | 2.2M | |
| `setuptools` | 4.2M | pulled in by `grpcio-tools` |
| `aiohttp` | 3.0M | the SDK's async REST transport |
| **Total removable by dropping gRPC** | **~66M (+3M aiohttp)** | only possible by removing hatchet-sdk |
| `cryptography` | 23M | **unrelated to gRPC** — arrives via `mcp[crypto]→pyjwt[crypto]`. Separate item (§2-4) |
| `pydantic`+`pydantic_core` | ~8M | used directly, kept |
| `mcp` | 1.9M | kept |

**Runtime import profile** (`import hatchet_mcp.server`):

- import time **~736 ms**
- at import time, `grpc`, `grpc_tools`, `aiohttp`, and `google.protobuf` are **all loaded into memory**
- importing only `hatchet_sdk.clients.rest.api.*` (the REST path) still runs the parent `hatchet_sdk/__init__.py`, which **loads gRPC along with it.** Cleanly isolating REST-only usage is therefore not possible with the current SDK layout.

### 2-2. Key facts

1. `grpcio` / `grpcio-tools` / `protobuf` are **hard dependencies** of hatchet-sdk (not optional extras). As long as hatchet-sdk is a dependency, this ~66M is installed **and loaded at runtime.**
2. The only way to drop gRPC is therefore to **drop the hatchet-sdk dependency and implement REST directly (with httpx).** (`httpx` already ships as a dependency of `mcp`, so it is not a new dependency.)

### 2-3. httpx-direct vs keeping the SDK — trade-offs

| Criterion | httpx-direct REST | Keep hatchet-sdk (current) |
|---|---|---|
| Install size | ~66M smaller | heavy |
| import/startup time | faster (~736ms → much lower) | 736ms |
| Maintenance | **entirely on us** — endpoint URLs, resolving tenant/URL from the JWT, pagination, error mapping, retries (replacing tenacity), rewriting every response Pydantic model | absorbed by the SDK (endpoints, models, auth, retries) |
| Regression risk | high (41 tools depend on the SDK feature client, generated REST classes, models, and helpers) | low (our code is a thin wrapper) |
| Correctness | we must track Hatchet API changes ourselves | follows via SDK upgrades |

For uvx distribution: the first run downloads about 47 packages, but **uvx caches them**, so later runs are fast. Size and startup are a once-per-process cost, not a per-request cost.

### 2-4. A bigger item found along the way — `cryptography` (23M)

`cryptography` (23M) comes not from gRPC but via **`mcp[crypto]` → `pyjwt[crypto]`**. If the server does not use MCP authentication (OAuth/JWT verification), depending on `mcp` without the crypto extra could cut 23M independently of any gRPC work. Note that some `mcp` versions may force crypto, so this **needs verification** (including how the current `mcp>=1.2.0` resolves the crypto extra).

### 2-5. Recommendation

- **Keep hatchet-sdk for now.** Re-implementing the entire REST surface to save ~66M and a few hundred ms in a single-tenant operations tool is a poor cost/benefit trade with high regression risk; the thinness of the code and the SDK's maintenance absorption are worth more.
- Alternatives, in priority order:
  1. **Upstream improvement** — propose that Hatchet split the gRPC dependency into an optional extra (cleanest; keeps our code as-is).
  2. **Investigate avoiding `mcp[crypto]`** — a potential 23M saving independent of gRPC; a low-risk thing to scope first.
  3. **httpx-only re-implementation** — only if size becomes a real constraint (e.g. extreme cold-start environments), and as a separate opt-in.

---

← [README](../../README.md) | Related: [MCP Design](mcp-server-design.md) · [SDK](sdk-and-communication.md)
