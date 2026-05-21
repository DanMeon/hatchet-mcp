# Authentication and Connection

How the MCP server authenticates to Hatchet and which server it connects to. **Key point: a single token is all you need.**

## 1. At a Glance

```
HATCHET_CLIENT_TOKEN  (a single JWT)
   └─ embeds the tenant ID (sub) + REST server URL + gRPC address
   └─ the MCP server resolves the server address and tenant from this token alone, with no extra configuration
```

A Hatchet token is **a JWT, not an opaque string**. The payload carries the connection details, so the SDK decodes the token to discover the server URL and tenant automatically. As a result, switching between Cloud and self-hosted is just a matter of swapping the token.

## 2. Security Schemes (OpenAPI)

Three schemes are defined in `openapi.yaml:8-21`.

| Scheme | Type | Transport |
|---|---|---|
| `bearerAuth` | http / bearer | `Authorization: Bearer <token>` header |
| `cookieAuth` | apiKey (cookie) | `hatchet` cookie (for browser sessions) |
| `customAuth` | http / bearer | Same wire format as bearerAuth, used for per-operation overrides |

The MCP server uses **`bearerAuth` only** — every request carries `Authorization: Bearer <token>`.

## 3. JWT Token Structure ★

The Python SDK's `token.py` decodes the token directly from base64 (without verifying the signature — the goal is claim extraction, not validation). Source: `sdks/python/hatchet_sdk/token.py`

```python
class Claims(BaseModel):
    sub: str                     # tenant UUID
    server_url: str              # REST base URL (e.g. "https://app.dev.hatchet-tools.com")
    grpc_broadcast_address: str  # gRPC address (e.g. "app.dev.hatchet-tools.com:443")
```

Key functions:
- `get_tenant_id_from_jwt(token)` → extracts `sub` (the tenant UUID)
- `get_addresses_from_jwt(token)` → `(server_url, grpc_broadcast_address)`

The TypeScript SDK handles this identically in `config-loader/token.ts`.

**Implication for the MCP server**: the token is the only required input. There is no need to supply the REST base URL separately, since the token's `server_url` is used. However, in self-hosted setups the URL embedded in the token may be an internal address that is unreachable from outside, so an **override mechanism (an environment variable) is always provided as well** (see §6).

## 4. Token Issuance (API token endpoints)

File: `paths/api-tokens/api_tokens.yaml`

| Method | URL | operationId | Notes |
|---|---|---|---|
| POST | `/api/v1/tenants/{tenant}/api-tokens` | `api-token:create` | Body `{ name(✅, ≤255), expiresIn?(Go duration, e.g. "24h") }` → `{ token }`. **The full token value is returned only once, at creation time** |
| GET | `/api/v1/tenants/{tenant}/api-tokens` | `api-token:list` | `{ pagination, rows: APIToken[] }` (no secret value; `id/name/expiresAt`) |
| POST | `/api/v1/api-tokens/{api-token}` | `api-token:update:revoke` | 204 No Content |

In practice, tokens are usually **issued from the dashboard** and placed in `HATCHET_CLIENT_TOKEN`. The MCP server rarely needs to issue a token itself — calling the API already requires a token, which makes self-issuance a chicken-and-egg problem.

## 5. Tenant Model

- Almost every resource path is scoped by `{tenant}` (a UUID).
- The SDK resolves `tenant_id` automatically from the token's `sub` (`config.py:185-186`). Every feature client then passes `self.client_config.tenant_id` transparently, so **the MCP code never has to manage the tenant UUID directly**.
- **One token = one tenant.** Working with multiple tenants requires swapping the token. Multi-tenant support in the MCP server would require either accepting a per-tenant token map or taking the tenant as a tool argument and switching tokens accordingly (a single-tenant setup is recommended initially — see the [design doc](mcp-server-design.md)).

## 6. Environment Variables — Connection Settings

### Python SDK (`config.py`, prefix `HATCHET_CLIENT_`)

| Env Var | Field | Description |
|---|---|---|
| `HATCHET_CLIENT_TOKEN` | `token` | JWT API token (**required**) |
| `HATCHET_CLIENT_SERVER_URL` | `server_url` | REST base URL (default: from the token) |
| `HATCHET_CLIENT_HOST_PORT` | `host_port` | gRPC address (default: from the token) — usually unnecessary, since the MCP server uses REST only |
| `HATCHET_CLIENT_TENANT_ID` | `tenant_id` | tenant override (default: the token's `sub`) |
| `HATCHET_CLIENT_NAMESPACE` | `namespace` | resource name prefix |
| `HATCHET_CLIENT_TLS_STRATEGY` | `tls_config.strategy` | `tls` / `mtls` / `none` |
| `HATCHET_CLIENT_TLS_CERT_FILE` | | mTLS certificate |
| `HATCHET_CLIENT_TLS_KEY_FILE` | | mTLS key |
| `HATCHET_CLIENT_TLS_ROOT_CA_FILE` | | CA bundle |
| `HATCHET_CLIENT_DEBUG` | `debug` | debug logging |

`pydantic_settings` also loads `.env`, `.env.hatchet`, `.env.dev`, and `.env.local` (`config.py:21`).

> **Naming note**: the REST base URL is called `server_url` in Python but `api_url` in TypeScript. The TS env var is `HATCHET_CLIENT_API_URL`.

### TypeScript SDK (for reference)
`HATCHET_CLIENT_TOKEN`, `HATCHET_CLIENT_API_URL` (REST), `HATCHET_CLIENT_HOST_PORT` (gRPC), `HATCHET_CLIENT_TLS_STRATEGY`, `HATCHET_CLIENT_NAMESPACE`, `HATCHET_CLIENT_LOG_LEVEL`. Source: `config-loader.ts:11-24`

## 7. Cloud vs Self-hosted

| | Approach |
|---|---|
| **Hatchet Cloud** (`cloud.onhatchet.run`) | A token issued from the dashboard already embeds the correct `server_url` and gRPC address. No URL configuration needed — just provide the token |
| **Self-hosted** | Use a token that embeds the self-hosted server URL, or override it explicitly via `HATCHET_CLIENT_SERVER_URL` (Python) / `HATCHET_CLIENT_API_URL` (TS) |

The Python SDK's hardcoded default is `https://app.dev.hatchet-tools.com` (`config.py:148`), but when the token contains a `server_url`, that value takes precedence (`config.py:193-205`).

## 8. MCP Server Authentication Design (recommended)

1. The MCP server **takes `HATCHET_CLIENT_TOKEN` as an environment variable** (injected via the `env` block of the MCP client configuration).
2. It **supports a `HATCHET_CLIENT_SERVER_URL` override** for self-hosted deployments (for when the URL embedded in the token is unreachable).
3. If the token is missing, it **exits immediately with an error** (fail-fast). Attempting to operate with an empty token would only produce repeated 401s, so there is no point continuing.
4. The token is **never exposed in logs or tool responses.** Error messages are masked so the token cannot leak.

For an example MCP client (e.g. Claude Code) configuration, see the [deployment section of the design doc](mcp-server-design.md#4-packaging--distribution-uvx).

Next: [SDK and Communication](sdk-and-communication.md)
