# ADR writing rules — `docs/design/vX.Y.Z/<topic>-research.md`

Section-by-section rules for filling placeholders in `templates/adr.md`. Loaded by the `/new-spec` skill (step 2) alongside the template. The ADR is paired 1:1 with the spec body — asymmetry between this reference and `references/spec.md` weakens the pair-file discipline.

## Per-section rules

### Title — standard phrase

- Format: `# v<X.Y.Z> <topic> — Design Decision Research`
- No variants

### Intro — standard phrase

- Exact wording (one paragraph, verbatim):
  > This records the **N** industry precedents, alternatives, and failure scenarios behind the decisions in [<X.Y.Z>/<topic>.md](../../roadmap/vX.Y.Z/<topic>.md) §Decisions that an outside reader would question. The spec states the final decisions; this document captures their rationale.
- Substitute **N** with the actual decision count
- No comparative narrative or meta commentary in the intro — such comparisons belong inside the §N four-subsection blocks

### Decision Matrix — table (`# / Item / Options / Chosen / Primary basis`)

- `#` = 1, 2, 3 ... (1:1 with §N decision sections)
- Item: the decision label (must match the spec body Decisions cell label exactly)
- Options: terse phrasing `A: <label> / B: <label> / C: <label>` — detailed comparison goes in §N
- Chosen: a single letter `A` / `B` / `C`
- Primary basis: a one-phrase reason for adoption — the full reasoning chain goes in §N

### `## N. <decision item>` — fixed four-subsection order

For each decision, write all four subsections in this exact order:

#### `### Facts`

- Measurable / citable facts
- No opinions or decision statements
- Citations: `<file>:<line>` or external URLs — no one-line speculation

#### `### Validator Counter-Arguments`

- Questions a critical reader would ask + answers
- Self-expose the decision's weak points — be honest, not defensive
- Format: `- "Question?" → answer`

#### `### Final Decision`

- Which option (A/B/C) + 1–2 sentence core reasoning
- Must match the "Chosen" column of the decision matrix

#### `### Primary Sources`

- External citable sources — upstream PRs / commits / RFCs / W3C / IETF / official docs
- Avoid secondary sources (blogs / SEO posts)
- No personal-machine paths (`~/.claude/...`, etc.) — invisible to external readers

### References

- Pair (spec body), external PRs / issues / standards
- *spec ↔ spec direct links forbidden* — pair files are the only exception

## Cross-cutting policies (CONVENTIONS.md SSOT)

- § Section Role Separation — info routing between spec and ADR
- § Status Metadata — frontmatter schema
- § Cross-Link Direction Rules — spec ↔ spec direct link prohibition
