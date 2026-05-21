# Spec body writing rules — `docs/roadmap/vX.Y.Z/<topic>.md`

Section-by-section rules for filling placeholders in `templates/spec.md`. Loaded by the `/new-spec` skill (step 2) alongside the template. The same rules apply to manual writes and Frozen-spec typo fixes.

## Per-section rules

### Title — single phrase

- Format: `# v<X.Y.Z> — <topic phrase>`
- Single phrase preferred. Avoid combinations (`+` / `and`) — if a combination feels needed, compress to a more abstract phrase
- A parenthetical subtitle is allowed. Example: `# v0.2.0 — Mutating-Tool Gate (read_only + dry_run)`

### Intro — core summary only, no scattered detail

The most-violated rule:

- **Include**: the spec's *core summary* (why + what + impact). Compatibility guarantees (schema / API / behavior unchanged)
- **OK to inline**:
  - *A single enabling-change reference* — one PR / issue / commit link that triggered the spec ("why now")
  - Version numbers (e.g. `v1.33.5`) — not raw commit hashes
  - Short method signatures / code refs when essential to "what changed"
- **Exclude**:
  - *Multiple* PR numbers / commit hashes scattered through the intro
  - Specific calendar dates (e.g. `2026-04-30`)
  - Inline policy quotes (a block quote of project policy text)
  - Work-breakdown enums `(1)(2)(3)...` — these belong in **Decisions table cells** or **ADR §N**
- Length scales with spec size:
  - PATCH: 1–2 paragraphs
  - MINOR: a separate `## Background` section is allowed
  - If the intro exceeds 3 paragraphs OR mixes distinct sub-topics, split into separate sections

### Pair link — standard phrase

- Exact wording (verbatim): `Rationale, alternatives, and failure scenarios for the key decisions live in the paired ADR: [<topic>-research.md](../../design/vX.Y.Z/<topic>-research.md).`
- Required when an ADR exists (PATCH / MINOR alike)
- No variant phrasings — standard phrase only

### Decisions — table (`Item / Value / Rationale`)

- Item format: `N — <label>` (e.g. `1 — API source`)
- Value: a single phrase or short sentence
- Rationale: 1–3 sentences
  - For longer comparison or option analysis, defer to ADR §N and add a one-line `See ADR §N for the full comparison` pointer in the cell
  - External citations (commit hash / PR # / date) inline OK — these are the details deferred from the intro

### Acceptance Criteria — AC-N IDs + behavior-driven

- Each item: `**AC-N** — <statement>` (CONVENTIONS § Acceptance Criteria Format — 1:1 with pytest markers)
- **Behavior-driven preferred** — input → output verification
- Avoid structural negatives (`<code/function/variable> does not exist`) — those are grep checks, not behavior
- Good: `AC-2 — when dry_run=true, the bulk-cancel tool returns the list of affected run IDs and performs no mutation` (verifies behavior)
- Bad: `AC-2 — the short-circuit branch is not left in the call site` (grep check)

### Non-Goals — preempt reader questions

- Items outside this spec's scope but *plausibly asked by external readers*
- Not just a "not doing" list — pair each item with **the reason** (why it's not in this spec)
- Must be consistent with Decisions — if a Decisions entry also appears in Non-Goals, that's a contradiction

### References

- Pair (ADR), upstream PRs / issues, precedent specs, policy citations
- *spec ↔ spec direct links forbidden* (CONVENTIONS § Cross-Link Direction Rules) — pair files are the only exception

## Cross-cutting policies (CONVENTIONS.md SSOT)

- § Section Role Separation — info routing across spec / ADR / CHANGELOG / implementation log
- § Status Metadata — frontmatter schema (status / target / ga / last_updated / description quoting)
- § Acceptance Criteria Format — AC-N IDs
- § Naming Rules — kebab-case, `vX.Y.Z` directories
