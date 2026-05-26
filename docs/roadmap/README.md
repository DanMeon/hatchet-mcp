# Roadmap

Per-version roadmap + the **SSOT for the active spec index**. Every spec's Status / Version / Released is tracked on this page. See [docs/CONVENTIONS.md](../CONVENTIONS.md) for the documentation policy.

This document is Living — update freely.

## Status

The spec-driven documentation system was introduced for new work. Design documents written before it live under [../init/](../init/) (exempt from the conventions). New work is captured as per-version specs via `/new-spec`.

`hatchet-mcp` is at **v0.3.0** (Beta).

## Active spec index

Each row is one spec + its paired design research (if any). Status follows [CONVENTIONS.md § Document Lifecycle](../CONVENTIONS.md).

| Version | Status | Roadmap spec | Design research (ADR) |
|---|---|---|---|
| v0.2.0 (reliability) | GA | [v0.2.0/reliability.md](v0.2.0/reliability.md) | [design/v0.2.0/reliability-research.md](../design/v0.2.0/reliability-research.md) |
| v0.3.0 (operational-toolkit-expansion) | GA | [v0.3.0/operational-toolkit-expansion.md](v0.3.0/operational-toolkit-expansion.md) | [design/v0.3.0/operational-toolkit-expansion-research.md](../design/v0.3.0/operational-toolkit-expansion-research.md) |

## Unstarted work

An undecided narrative — the intent/scope of minors that don't yet have a `vX.Y.Z` directory. As work approaches, promote it to a formal spec with `/new-spec <version> <topic>`.

Candidate directions (original design notes under [../init/](../init/)):

- **Multi-tenancy** — serving more than one Hatchet tenant from a single server. See [../init/multitenancy-and-dependencies.md](../init/multitenancy-and-dependencies.md).
- **Dependency footprint** — a lighter dependency set for `uvx` distribution. See [../init/multitenancy-and-dependencies.md](../init/multitenancy-and-dependencies.md).

## Implementation / verification logs (GA)

Logs written after work completes. Immutable — no body changes.

| Version | Implementation log | Verification report |
|---|---|---|
| — | — | — |

## Principles

- **MINOR-grained increments** — one feature chunk at a time, accumulated without breaking changes
- **No breaking changes across phase boundaries** — moving to the next phase keeps existing APIs and tool contracts
- **Versions match the git tag's `v` prefix** — consistent directory and document names
- **Spec lifecycle**: Draft → GA → (if needed) → Superseded by …. Details: [CONVENTIONS.md § Adding a New Spec](../CONVENTIONS.md)
