# Security Policy

## Reporting a vulnerability

**Please report security issues privately. Do not open a public GitHub issue.**

Use GitHub's private vulnerability reporting for this repository:
[**Security → Report a vulnerability**](https://github.com/DanMeon/hatchet-mcp/security/advisories/new).

Include enough detail to reproduce the issue (affected version, configuration, and a minimal
proof of concept where possible). You can expect an acknowledgement within a few days, and a
fix or mitigation plan once the report is confirmed.

## Supported versions

This project is pre-1.0; only the latest released `0.x` version receives security fixes.

| Version | Supported |
|---|---|
| latest `0.x` | ✅ |
| older | ❌ |

## Security model

`hatchet-mcp` can drive a production orchestrator and authenticates with a Hatchet API token,
so it is built to be safe by default:

- **Read-only by default.** `HATCHET_MCP_READ_ONLY` defaults to `true`; the mutating tools are
  not registered at all unless you explicitly opt in. A second in-handler gate refuses
  mutations even if a handler is somehow reached in read-only mode.
- **Token confidentiality.** The Hatchet token is read from the environment, never stored on a
  model, and never written to stdout, stderr, tool responses, or error messages — even SDK
  validation failures surface only the exception type, and all API error strings are redacted
  and length-capped.
- **Bulk guardrails.** `cancel_runs` / `replay_runs` default to a dry run and refuse to act on
  more than 500 matching runs.
- **Single tenant.** One token scopes the whole server to one Hatchet tenant.

See the **Safety model** section of the [README](README.md) for the full design.

## Handling tokens safely

- Keep your token in `.mcp.json` (gitignored) or an environment variable — never commit it.
- Prefer the default read-only mode for any token pointed at a production tenant.
- Scope tokens to the minimum tenant and permissions your use case needs.
