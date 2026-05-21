# Hatchet MCP — Design & Reference Docs

Research and design notes for an operations-focused **MCP (Model Context Protocol) server** that controls and monitors **Hatchet**, an orchestration engine.

The server exposes a broad slice of Hatchet's surface to an LLM — workflow listing, run status, trigger/cancel/replay, logs, workers, cron/schedules, events, and rate limits — over the REST API.

## Documents

| Document | Contents |
|---|---|
| [overview-and-concepts.md](overview-and-concepts.md) | What Hatchet is, its core object model (Task/Workflow/Run/Worker/Event/Cron/...), architecture (gRPC vs REST), the v0/v1 split, and the run lifecycle |
| [rest-api-reference.md](rest-api-reference.md) | Full REST API reference — v1 stable (37 endpoints) + legacy. Endpoints, parameters, responses, and status enums |
| [authentication-and-connection.md](authentication-and-connection.md) | JWT token structure, the tenant model, environment variables, Cloud vs self-hosted, TLS, and token issuance |
| [sdk-and-communication.md](sdk-and-communication.md) | How the MCP server talks to Hatchet — the Python SDK feature-client structure, a comparison with direct REST calls, and the recommended approach |
| [mcp-server-design.md](mcp-server-design.md) | The MCP tool surface (read/mutating), tool→API mapping, server architecture, **uvx packaging & distribution**, and security |
| [multitenancy-and-dependencies.md](multitenancy-and-dependencies.md) | Multitenancy and dependency analysis — the multiple-instance pattern and the ~66M gRPC stack measurement |

## Key design decisions

1. **Language: Python** — the Hatchet Python SDK (`hatchet-sdk`) has the cleanest feature client, and its `aio_*` async methods fit the MCP async model well. (See [SDK](sdk-and-communication.md).)
2. **Communication: REST API** — the MCP server queries and controls state, so it uses the REST API. It does not use the gRPC dispatcher protocol that workers rely on. (See [Concepts](overview-and-concepts.md).)
3. **Transport: stdio** — the MCP standard. Clients such as Claude Code launch the server as a subprocess.
4. **Distribution: `uvx`** — built as a Python package with a `[project.scripts]` entry point so it runs without installation via `uvx hatchet-mcp` (or `uvx --from git+...`). (See [Design](mcp-server-design.md).)
5. **Authentication: a single JWT token** — `HATCHET_CLIENT_TOKEN` embeds the server URL and tenant, so almost no extra configuration is needed. (See [Auth](authentication-and-connection.md).)
6. **API generation: v1 stable first** — the new v1 engine uses `/api/v1/stable/...`, while some management features (workflow definitions, workers, crons, schedules) use the legacy `/api/v1/...`. Both are covered. (See [API](rest-api-reference.md).)

## Sources

These docs were written by analyzing the Hatchet source directly.

- **Repository**: `hatchet-dev/hatchet` (GitHub)
- **Python SDK version**: `1.33.5`
- **OpenAPI spec**: `api-contracts/openapi/openapi.yaml` (`info.version: 1.0.0`)

Factual claims cite `file:line` references into that source where possible (e.g. `api-contracts/openapi/paths/v1/tasks/tasks.yaml:391`).

> Note: Hatchet is under active development, so the spec may change after the analyzed revision. Re-check against the current Hatchet source before relying on a specific detail.
