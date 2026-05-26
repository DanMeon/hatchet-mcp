# Documentation Conventions

Documentation policy for this project. We adopt a **spec-driven + immutable per-version** pattern. Read this document before writing a new document or editing an existing one.

> Flat documents written *before* the spec system was introduced live under [docs/init/](init/) — they are exempt from these conventions and from lint (kept as historical reference). New documents follow this policy.

## Document Lifecycle (4 Categories)

| Category | Meaning | Update policy | Examples |
|---|---|---|---|
| **Living** | Always current — location pointers + timeline + rules for other docs | Free to update, fine to touch on every change | `docs/CONVENTIONS.md` (itself), `docs/roadmap/README.md`, `docs/upstream/README.md`, `docs/traces/coverage.md`, `CHANGELOG.md`, `CLAUDE.md`, `AGENTS.md`, `README.md` |
| **Active** | Staging before flowing out to an external system | Major changes only, in-place update OK | `docs/upstream/<topic>.md` |
| **Draft** | Spec under construction — actively updated until its version reaches GA | Free to update until GA, then transitions to GA status | `docs/roadmap/v<X.Y.Z>/<topic>.md` (pre-release) |
| **GA** | Released spec / completed stage / completed verification | **No changes** — only typo/link fixes in place. Larger changes require a new spec + supersede | `docs/roadmap/v<X.Y.Z>/<topic>.md` (post-release), `docs/implementation/v<X.Y.Z>/stages/*.md` |

`GA` follows the operating model of [Rust RFCs](https://rust-lang.github.io/rfcs/) / [Python PEPs](https://peps.python.org/): the historical record of a decision is preserved, so "why was it designed this way" stays clear. The `GA` label folds two ideas — *released* (a fact about the parent version) and *immutable* (a policy on the body) — into one status the reader can pattern-match without looking up two rules.

### GA exemption — non-semantic schema migration

An exception to the no-edit rule for GA bodies. A **non-semantic** change that preserves the decision, citations, and meaning while updating only the *representation* of metadata is allowed in place — e.g. a bulk frontmatter schema migration.

Conditions:

- **non-semantic** — no changed decision, no new citation, no added meaning. Metadata format only
- **whole-spec bulk** — applied to all affected files in a single PR. No one-off per-file updates
- a commit using this exemption must state *which schema migration* in the PR description

Semantic changes (decision / citation / meaning) follow the normal supersede procedure.

### GA external-dependency rot

A GA body is a historical record. As time passes and external dependencies (library versions / API signatures / external URLs) get deprecated, the body is not changed — preserving the accuracy *as of the decision* is the point of immutability. Current truth lives in the *code* and the *latest spec*.

## Status Metadata — YAML frontmatter

Every spec except `Living` starts with a YAML frontmatter block:

```markdown
---
status: GA
description: <one-line summary, 50-150 chars recommended>
version: v0.2.0
released: 2026-05-21
last_updated: 2026-05-21
---

# <Document Title>

<body begins>
```

### Field schema

| Field | Type | Rule |
|---|---|---|
| `status` | enum: `Active` / `Draft` / `GA` / `Superseded` | required |
| `description` | non-empty string (50-150 chars recommended) | required. One-line summary — for index/search/tooltip |
| `version` | `vX.Y.Z` SemVer | required for `Draft` / `GA` / `Superseded`. Forbidden for `Active`. Permanent identifier — a Draft's `version` is its target release; on GA the same key carries the same value |
| `released` | `YYYY-MM-DD` | required for `GA` / `Superseded`. The date the parent version reached GA. Forbidden for `Active` / `Draft` |
| `supersedes` | `<vX.Y.Z>/<topic>.md` or omitted | what the new spec replaces |
| `superseded_by` | `<vX.Y.Z>/<topic>.md` | required when `status: Superseded` |
| `last_updated` | `YYYY-MM-DD` | required. Auto-updated on meaningful-change commits ([hook](#auto-updated-last_updated)). Distinct from `released`: `released` is a fact about the parent version, `last_updated` is editorial activity on this file |

`description` guidance:

- One-line summary — a compression of the first paragraph or title+core decision. 50-150 chars recommended
- No added meaning — must be a compression of what's already in the body. No new decision / citation / fact (the GA body immutability principle especially)
- A non-semantic format change, so the GA exemption [non-semantic schema migration](#ga-exemption--non-semantic-schema-migration) applies — even GA specs may add or refine it in place
- Meaningful for all document kinds (roadmap / design / implementation / upstream / verification), so there is no schema branch
- **Quoting** — wrap the whole value in double quotes `"..."` and use single quotes for inline code/identifiers `'hatchet-mcp'` (YAML-safe + flat-parser compatible). E.g. `description: "v0.2.0 — 'read_only' gate..."`

`Active` (e.g. `upstream/<topic>.md`) omits both `version` and `released` — by definition not tied to a release.

`Living` has no frontmatter — by definition always current. Instead an index like a README exposes the Status of other documents.

### Lifecycle exceptions (GA without a version)

Two GA documents omit `version` because they're not tied to a single release:

1. **Meta-level implementation log** — `docs/implementation/<topic>.md` (flat, not under a `vX.Y.Z/`) — cross-version meta work like this schema migration itself
2. **Resolved upstream doc** — `docs/upstream/<topic>.md` after the in-place transition described in § upstream/

Both still carry `status: GA` + `released`; only `version` is omitted.

### Pre-GA stage log

A stage file under `docs/implementation/vX.Y.Z/stages/stage-N.md` is **immutable on write** even before its parent version reaches GA. The frontmatter is `status: Draft` + `version: vX.Y.Z`; immutability is a policy of § Implementation Log Structure, not enforced by the schema. On parent GA, bulk-flip `status: Draft → GA` and add `released: <parent GA date>`; `version` stays as-is.

### Example

One representative form (GA). The others (`Draft` / `Active` / `Superseded`) apply the field combinations from the schema table.

```markdown
---
status: GA
description: "v0.2.0 — 'read_only' gate + 'dry_run' preview for mutating tools. Blocked by default, mutations only on explicit opt-in"
version: v0.2.0
released: 2026-05-21
last_updated: 2026-05-21
---

# v0.2.0 — Mutating-Tool Gate

The default is read-only...
```

### Auto-updated last_updated

A Claude Code PostToolUse hook (`.claude/hooks/update-last-updated.py`) sets the frontmatter `last_updated` of `docs/*.md` to today's date on edit. **The manual-update procedure is retired** — do not touch the frontmatter directly.

A commit using the exemption for a bulk migration skips the hook (non-semantic — no meaning change). In that case `last_updated` is carried over unchanged.

## Per-Directory Policy

```
docs/
├── CONVENTIONS.md                    Living  — this document. Policy SSOT
├── init/                             (legacy) flat docs from before the spec system — exempt from conventions/lint
├── roadmap/
│   ├── README.md                     Living  — active spec index + unstarted narrative
│   └── v<X.Y.Z>/<topic>.md           Draft → GA on release — per-version spec
├── design/
│   └── v<X.Y.Z>/<topic>-research.md  Draft → GA on release — ADR-style decision evidence
├── implementation/
│   ├── v<X.Y.Z>/...                  GA      — completed stage work logs
│   └── <topic>.md                    GA      — meta-level / cross-version work
├── traces/
│   └── coverage.md                   Living  — spec ↔ test auto mapping
├── upstream/
│   ├── README.md                     Living  — active / resolved issue index + archive policy
│   └── <topic>.md                    Active  — drafts of issues for external deps (Hatchet core / hatchet-sdk). Archived once merged upstream
└── verification/
    └── v<X.Y.Z>/...                  GA      — verification reports for large units of work (limited)
```

### init/

- Flat documents written *before* the spec system. No frontmatter / pair / naming conventions apply, excluded from lint (`scripts/_doc_lint.py` skips `docs/init/`)
- New work may reference their content, but anything worth promoting to a real spec is rewritten into roadmap/design via `/new-spec`

### roadmap/

- `README.md` (Living) — active spec index + unstarted-work narrative. The SSOT for which spec targets which version; also holds the intent/scope of unstarted minors
- `vX.Y.Z/<topic>.md` (Draft → GA) — per-version spec. One major topic of a release = one file

### design/

- `vX.Y.Z/<topic>-research.md` (Draft → GA) — ADR-style decision evidence. Decision matrix + per-item (facts / validator counter-arguments / final decision / sources). 1:1 paired with its roadmap spec

### implementation/

- `vX.Y.Z/migration.md` or `vX.Y.Z/stages/stage-N.md` — work log. Immutable on completion. Records deliverables / verification results / carried-over items
- Small work (single session / a few days) goes in a single `migration.md`. Large work (multiple weeks, dependency tracking needed) is split into `stages/stage-N.md`
- **If a stage is authored before its parent version reaches GA**, the frontmatter is `status: Draft` + `version: vX.Y.Z` (body immutable as written — policy of this section, not the schema). On parent GA, bulk-flip `status: Draft → GA` and add `released: <parent GA date>` — `version` stays the same

### upstream/

- `README.md` (Living) — active / resolved issue index + archive policy SSOT. Holds self-tracking meta (whether registered upstream / RESOLVED date / related spec references)
- `<topic>.md` (Active) — drafts of issues/proposals being considered for submission to external dependencies (Hatchet core `hatchet-dev/hatchet`, `hatchet-sdk`, etc.). No per-version mapping. **The body should be in a form that can be posted as-is into a GitHub issue** — self-tracking sentences stay out of the body and are managed by the README index above
- This directory is staging before flowing out to an external system (GitHub Issues) — not part of a formal spec
- **On resolution** — two options:
  - **delete** — when no other spec references this file. The info is preserved by the GitHub permalink + this PR's commit history
  - **in-place GA transition** — when a GA spec references this file. Set frontmatter `status: GA` + `released: <resolution date>` (omit `version` — not tied to a specific release), add a one-line block quote `> **RESOLVED** — see upstream PR/commit …` above the first header. Preserve the existing body (historical record)

### verification/

- `vX.Y.Z/<scope>-review.md` (GA) — output of a verifier subagent (code-reviewer / test-automator). Limited to **large units of work** (multi-stage / suspicious areas / cross-cutting refactors)
- Small work (single-session PR / typo / dep bump) skips this — git log + PR description is the SSOT

## Spec / ADR Body Structure

The SSOT for body structure rules lives in the `/new-spec` skill's template files:

- **Spec body skeleton**: [`.claude/skills/new-spec/templates/spec.md`](../.claude/skills/new-spec/templates/spec.md) — placeholders only, copied directly
- **Spec body rules**: [`.claude/skills/new-spec/references/spec.md`](../.claude/skills/new-spec/references/spec.md) — per-section prose (single-phrase title, intro = core summary without scattered detail, Decisions table format, behavior-driven AC-N, etc.)
- **ADR skeleton**: [`.claude/skills/new-spec/templates/adr.md`](../.claude/skills/new-spec/templates/adr.md) — placeholders only
- **ADR rules**: [`.claude/skills/new-spec/references/adr.md`](../.claude/skills/new-spec/references/adr.md) — per-section prose (standard intro phrase, decision matrix format, four subsections (Facts / Validator Counter-Arguments / Final Decision / Primary Sources))

Manual writes, post-GA typo fixes, and new specs all use these two templates as the single SSOT. The `/new-spec` skill scaffolds by copying these templates — automation and manual writing stay aligned with no drift risk.

If this section and a template file disagree, **the template file wins**.

## Section Role Separation — info routing lookup

A single SSOT lookup table for "where does this information go?". It makes the role asymmetry across spec ↔ ADR ↔ CHANGELOG ↔ implementation log explicit, preventing *the same info duplicated in several places* or *missing everywhere and lost*.

| Information | Location |
|---|---|
| The spec's core intent / impact / no-change guarantees | spec intro |
| Raw decision details (commit hash / PR # / date / policy phrase) | spec Decisions table cell |
| Option comparison / validator counter-arguments / primary sources | ADR §N four subsections |
| User-visible changes (*what* — added / changed / removed tools, APIs, compatibility) | CHANGELOG `[X.Y.Z]` section |
| Per-stage workflow / trial-and-error / a/b/c option decisions (*why·how*) | implementation log (`docs/implementation/...`) |
| spec ↔ test mapping (auto-generated) | `docs/traces/coverage.md` (Living) |
| Staging before flowing to an external system | `docs/upstream/<topic>.md` (Active) |

Core separation rules:
- *No duplicate recording of the same fact* — CHANGELOG is *what*, implementation log is *why·how*. A change with no a/b/c comparison value (simple dep bump, typo) is just a CHANGELOG line — no implementation log
- *No detail leaking into the spec intro* — details go in Decisions table cells
- *No option comparison leaking into the spec Decisions table* — options / alternatives go in ADR four subsections

## Cross-Link Direction Rules

Make inter-document dependencies one-directional to break the chain where "changing one document forces updating another".

```
Living  ───→  Active  ───→  Draft  ───→  GA
  ↑              ↑             ↑          ↑
  └──────────────┴─────────────┴──────────┘
           (links pointing back up are OK)
```

- **Living → anywhere** OK (index role)
- **Active → Draft / GA** OK (a phase points to a spec)
- **Draft → Active / Living / GA** OK
- **GA → elsewhere** avoid where possible (adding a new cross-link after GA is a body edit)

### No direct spec ↔ spec links (one exception)

- **Forbidden**: direct links between specs in the same directory. Adding a new spec would force touching existing specs — a chain reaction
- **Instead**: `roadmap/README.md` exposes them together
- **Exception**: **the pair** — `roadmap/vX.Y.Z/<topic>.md` and `design/vX.Y.Z/<topic>-research.md` are a 1:1 pair (spec ↔ ADR). Direct links between the pair are kept (the two are effectively two faces of one decision)

## Adding a New Spec

The `/new-spec <version> <topic>` Claude Code skill automates this procedure (`.claude/skills/new-spec/SKILL.md`).

### When creating a new v<X.Y.Z>

1. Create directories: `docs/roadmap/v<X.Y.Z>/`, `docs/design/v<X.Y.Z>/`
2. Write the spec file — frontmatter `status: Draft`, `version: vX.Y.Z`
3. Write the paired design research file — same frontmatter
4. Add a row to the index table in `docs/roadmap/README.md` (promote from the unstarted narrative if it was there)

### After a version reaches GA

1. Transition specs in that vX.Y.Z directory: frontmatter `status: Draft → GA`, add `released: <GA date>`. `version` stays as-is
2. Update the `docs/roadmap/README.md` index (Status column)
3. Finalize that version's section in `CHANGELOG.md`
4. Write the implementation log — `docs/implementation/v<X.Y.Z>/...` (immutable on write)

### When a decision needs changing after GA

1. **Write a new spec** — never edit the existing file. A new file (e.g. `docs/roadmap/v0.4.0/<topic>-correction.md`)
2. Update **only the frontmatter** of the existing GA spec: `status: Superseded`, `superseded_by: v0.4.0/<topic>-correction.md`. Preserve `version` + `released`
3. Back-reference in the new spec's `supersedes` — forming a two-way chain
4. Add a § Supersedes section to the new spec body stating what changed and how
5. Record the reason in CHANGELOG

Non-semantic changes like typos / broken links / external URL changes can be done in place (last_updated auto-updates).

## Implementation Log Structure

Three kinds under `docs/implementation/`:

- `vX.Y.Z/stages/stage-N.md` — work named in that release's spec § implementation-stage split (large, multi-stage). 1:1 mapping with the spec's stage table
- `vX.Y.Z/<topic>.md` (flat under vX.Y.Z) — small specless work (refactor / chore / perf / dep bump). Written only when the a/b/c option comparison has value beyond a single CHANGELOG line. 1:1 with the branch prefix `<type>/<topic>`
- `<topic>.md` (flat outside any vX.Y.Z) — meta-level / cross-version work (e.g. a docs-system overhaul). Immutable on write; frontmatter `version` is omitted (N/A — not tied to a single release); `status: GA` + `released: <write date>` still required

Changes that fit in one CHANGELOG line (typo cleanup, simple dep bump, small docstring update) get no file — git log + CHANGELOG is the SSOT.

If five or more ad-hoc notes accumulate, consider a `chores/` directory then (YAGNI).

## Acceptance Criteria Format

A spec's § Acceptance Criteria section assigns each item an `AC-N` ID (for 1:1 mapping with test markers). Format is free — plain prose is fine as long as it's testable and clear. If ambiguity is a concern, a structured pattern like [EARS notation](https://alistairmavin.com/ears/) (`THE ... SHALL`, `WHEN ..., THE ... SHALL`) may be referenced (not mandatory).

```markdown
## Acceptance Criteria

- **AC-1** — when `read_only=true`, a mutating-tool call is blocked before execution + a guidance message
- **AC-2** — when `dry_run=true`, returns a preview of affected targets with no actual mutation
- **AC-3** — bulk operations are rejected above 500 items (cap)
- **AC-4** — an invalid tenant token yields an auth error + the tool does not run
```

## Trace Report — pytest spec markers

Tests map to specs via the `pytest.mark.spec(spec_id)` marker. The `spec_id` format is `"vX.Y.Z/topic#AC-N"` — AC-level mapping.

File-level application (all tests verify the same spec): one line `pytestmark = pytest.mark.spec("vX.Y.Z/topic")` at module top. A test verifying an additional spec adds a `@pytest.mark.spec(...)` decorator (both accumulate). Tests with no marker pass as usual (they just don't appear in the mapping).

In CI, `scripts/generate_spec_trace.py` extracts markers via AST static analysis → auto-updates `docs/traces/coverage.md` (Living). Locally, a PostToolUse hook (`.claude/hooks/regen-spec-trace.py`) regenerates it on `tests/*.py` edit.

## Archive Policy (v1.0+)

At each major release GA, move the previous major's GA specs to `docs/archive/v<N>/` (same structure, no body change). The README index exposes only the active major; the archive is a one-line link to a separate page. The goal is index / search readability — unrelated to git size. **A pre-v1.0-GA task**, so deferred until then.

## Naming Rules

- Filenames: kebab-case (`mcp-tools.md`, not `mcp_tools.md`)
- Directories: `v` prefix + SemVer (`v0.2.0/`, not `0.2.0/`)
- ADR files: `<topic>-research.md` (stem matches the roadmap spec `<topic>.md`)
- Stage files: `stage-<N>.md` (1-indexed)
- **Relative paths**: same / child directory is implicit (`foo.md`, `subdir/foo.md`). Parent is `../foo.md`. No `./` prefix (redundant). Only external resources use a fully-qualified URL

## Updating This Document

CONVENTIONS.md itself is Living. Update in place on policy change. **But** because changes here affect all spec writing:

- Large changes (e.g. adding/removing a Status category, frontmatter schema change) include a bulk migration of affected existing documents in the PR (the [GA exemption](#ga-exemption--non-semantic-schema-migration) may apply)
- Small changes (e.g. a naming rule addition) are in-place + apply to new documents first, with existing ones cleaned up gradually

## References

- Rust RFC process: <https://rust-lang.github.io/rfcs/>
- Python PEP process: <https://peps.python.org/pep-0001/>
- ADR (Architecture Decision Records): <https://adr.github.io/>
- Diátaxis 4-axis: <https://diataxis.fr/>
- GitHub Spec Kit: <https://github.com/github/spec-kit>
- EARS notation: <https://alistairmavin.com/ears/>
