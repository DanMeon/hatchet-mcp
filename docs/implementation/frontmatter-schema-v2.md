---
status: GA
description: "Migrate spec frontmatter from 'target/ga + Frozen' (v1) to 'version + released + GA' (v2). 4 GA specs + lint + skill templates updated in one PR"
released: 2026-05-26
last_updated: 2026-05-26
---

# Frontmatter Schema v2 Migration

A meta-level docs-system change with no `version:` field — applies across all releases, not tied to a single one.

## Motivation

Schema v1 used two version keys that rename mid-lifecycle: `target: vX.Y.Z` while Draft, then renamed to `ga: vX.Y.Z` on GA. The rename had three costs:

1. **Drift surface**: each GA transition is two coupled edits (`status: Draft → Frozen` + `target → ga` rename). An exemption rule (Frozen body immutability) had to be carved out to legitimize the rename, and the [lint validator](../../scripts/_doc_lint.py) carried a `pre-GA stage log` case that treated `status: Frozen + target` as legal — extra complexity to express what is fundamentally "this stage was written before GA."
2. **Search asymmetry**: "find every doc for v0.3.0" needed `grep -E "^(target|ga): v0\.3\.0"` (OR query). A single permanent identifier reduces it to a single-key grep.
3. **Semantic conflation**: `Frozen` encoded two facts simultaneously — "released" + "immutable body". A reader couldn't tell which axis was load-bearing without reading the body-policy section.

Cost of the migration: 4 GA spec/ADR files + the lint validator + the `/new-spec` skill templates + CONVENTIONS itself. Bounded; lower the longer it's deferred (5 GA docs today vs. 30+ later).

## Decision

| # | Before (v1) | After (v2) | Rationale |
|---|---|---|---|
| 1 | `target: vX.Y.Z` (Draft) ↔ `ga: vX.Y.Z` (Frozen) | Single `version: vX.Y.Z` carried unchanged from Draft through Superseded | One identifier per spec — no rename, no mid-lifecycle key drift, single-key grep |
| 2 | `status: Frozen` | `status: GA` | `GA` is the actual fact (released). Immutability is a policy of § Document Lifecycle, named separately, not folded into the status word |
| 3 | (no GA-date field) | `released: YYYY-MM-DD` (required for `GA` / `Superseded`) | `last_updated` is editorial activity; `released` is a fact about the parent version. Two axes deserve two fields |
| 4 | "pre-GA stage log" used `status: Frozen + target` as a schema-level affordance | `status: Draft + version: vX.Y.Z`; body immutability is the implementation-log policy alone | Schema enforces facts; policy enforces behavior. Splitting them removed the lint exception |

## Decision Matrix (alternatives considered)

| Option | Identifier | Status enum | GA date | Verdict |
|---|---|---|---|---|
| A: keep v1 (`target` / `ga` mutex, `Frozen`) | two keys, renamed | Active/Draft/Frozen/Superseded | none — implicit in `ga` field | Status quo; preserves the costs above. Rejected |
| **B: chosen** — `version` permanent, `status: GA`, `released` date | one key, permanent | Active/Draft/GA/Superseded | `released: YYYY-MM-DD` | Splits "released" (fact) from "immutable" (policy); single identifier survives lifecycle |
| C: `state: Final` (Rust RFC style), no separate date | one key, permanent | Draft/Active/Final/Superseded | none | Loses the released-date semantic; "Final" is less concrete than "GA" for a versioned project |
| D: `lifecycle: ga` (separate key from status) | one key | (no status enum) | `released: YYYY-MM-DD` | Adds a parallel enum; doubles the field count without clear payoff |

B chosen. Option C's loss of `released` was decisive — a versioned project needs the GA date as a first-class fact for archive policy + correlating spec to PyPI / git tag.

## Migration trail

Single PR. Affected files:

- `docs/CONVENTIONS.md` — § Status Metadata / § Document Lifecycle / § Adding a New Spec / § Implementation Log Structure / § Updating This Document all rewritten for the new schema. CONVENTIONS is the SSOT; the migration trail itself is recorded here, not there
- `scripts/_doc_lint.py` — `STATUS_ENUM`, `validate_frontmatter`, and the module docstring rewritten for `version` / `released` / `GA` / `Superseded`. The `pre-GA stage log` exemption was removed (no longer needed once `version` survives lifecycle)
- `.claude/skills/new-spec/templates/spec.md`, `templates/adr.md`, `references/spec.md`, `SKILL.md` — emit `version:` instead of `target:`; reference schema field list updated
- `docs/roadmap/v0.2.0/reliability.md`, `docs/design/v0.2.0/reliability-research.md`, `docs/roadmap/v0.3.0/operational-toolkit-expansion.md`, `docs/design/v0.3.0/operational-toolkit-expansion-research.md` — 4 GA specs / ADRs migrated in bulk per the `GA exemption — non-semantic schema migration` rule. Bodies untouched (decisions, citations, line numbers preserved). `released` dates back-filled from `git log -1 --format=%ai vX.Y.Z`
- `CHANGELOG.md` — `[Unreleased]` entry under `### Docs`

Bodies of GA specs (v0.2.0 + v0.3.0) are unchanged — the `GA exemption` allows pure-frontmatter format migration in place, no decision / citation / line-number drift.

## Consequences

- **Lint cost**: lower. One exemption removed; validator branches collapsed
- **New-spec workflow**: lower friction. GA transition is `status: Draft → GA` + add `released:`, no key rename
- **Search**: `grep "^version: v0.3.0" docs/` is the full v0.3.0 inventory
- **Reader load**: `status: GA` is closer to plain English than `status: Frozen` was. The immutability policy stays cited (CONVENTIONS § Document Lifecycle)
- **Tooling**: any external script that read `ga:` or `target:` directly needs `version:` instead. None known in this repo as of this writing; the CI `docs.yml` workflow runs through the lint script which was migrated in the same PR

## Non-goals

- **Renaming `Active` or `Superseded`** — kept as-is; both names are already accurate
- **Removing `last_updated`** — distinct from `released` (editorial activity vs. release fact), both retained
- **Archive policy migration** — separate concern (CONVENTIONS § Archive Policy v1.0+), deferred until needed
