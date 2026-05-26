---
name: new-spec
description: Scaffold a new version spec and paired ADR following docs/CONVENTIONS.md. Invoke when the user wants to start a new version spec (e.g. "start v0.2.0 mutating-tool gate", "first spec for phase 3"). Idempotent — aborts if the spec already exists. State the version + topic before invoking and wait for user confirmation.
argument-hint: <version> <topic>
arguments:
  - version
  - topic
---

# /new-spec — scaffold a new version spec

Given `<version>` (e.g. `v0.2.0`) and `<topic>` (e.g. `mutating-tool-gate`), create a new per-version spec, its paired ADR (design research), and the index entry in one shot.

## Outputs

1. `docs/roadmap/<version>/<topic>.md` — the spec body (frontmatter `status: Draft`, `version: <version>`)
2. `docs/design/<version>/<topic>-research.md` — the paired ADR (same frontmatter)
3. `docs/roadmap/README.md` — append a row to the active spec index table

## Procedure

When this skill is invoked, execute the following steps in order:

1. **Validate arguments**
   - `version` must match the SemVer pattern `vX.Y.Z`
   - `topic` must be kebab-case (`[a-z0-9]+(-[a-z0-9]+)*`)
   - Abort if `docs/roadmap/<version>/<topic>.md` already exists — never overwrite an existing spec

2. **Read the four files** which are the SSOT for body structure:
   - [`templates/spec.md`](templates/spec.md) — spec body skeleton (placeholders only, copied directly)
   - [`templates/adr.md`](templates/adr.md) — ADR skeleton (placeholders only, copied directly)
   - [`references/spec.md`](references/spec.md) — per-section rules for the spec body (single-phrase title, intro = core summary without scattered detail, behavior-driven AC-N, etc.)
   - [`references/adr.md`](references/adr.md) — per-section rules for the ADR (standard intro phrase, four subsections (`### Facts` / `### Validator Counter-Arguments` / `### Final Decision` / `### Primary Sources`))

   Also re-read `docs/CONVENTIONS.md` for cross-cutting policy: § Status Metadata (frontmatter schema), § Section Role Separation (info routing lookup), § Cross-Link Direction Rules, § Naming Rules, § Acceptance Criteria Format. Conventions are Living and may have evolved since the last skill invocation.

3. **Create directories** if missing:
   - `docs/roadmap/<version>/`
   - `docs/design/<version>/`

4. **Write `docs/roadmap/<version>/<topic>.md`** by copying [`templates/spec.md`](templates/spec.md) verbatim and substituting placeholders (`<version>` / `<topic>` / `<topic phrase>` / intro prose / Decisions table entries / AC bullets / Non-Goals bullets). Apply the [`references/spec.md`](references/spec.md) per-section rules — *especially* the intro rule (no detail, defer to Decisions table cells), which is the most-violated rule.

5. **Write `docs/design/<version>/<topic>-research.md`** by copying [`templates/adr.md`](templates/adr.md) verbatim and substituting placeholders. Apply the [`references/adr.md`](references/adr.md) per-section rules — *especially* the standard intro phrase (exact wording + no meta narrative) and the fixed four-subsection order.

6. **Append a row to `docs/roadmap/README.md`** in the active spec index table (find the `## Active spec index` section, add at the end of the table):

   ```markdown
   | <version> (<topic>) | Draft | [<version>/<topic>.md](<version>/<topic>.md) | [design/<version>/<topic>-research.md](../design/<version>/<topic>-research.md) |
   ```

7. **Run the integrity check**: `uv run --no-project --with "typer>=0.12" python scripts/lint_docs.py docs/`. If violations are reported, surface them to the user and propose corrections — do not silently fix.

8. **Spawn a fresh-context architect-reviewer subagent** for independent review (author ≠ reviewer principle). Use the `Agent` tool with `subagent_type: "architect-reviewer"` and a self-contained prompt that includes:
   - Project context (hatchet-mcp, spec-driven release model, `docs/CONVENTIONS.md` SSOT)
   - The exact paths of the new spec body, paired ADR, and the README index row
   - Cross-check sources to read (`docs/CONVENTIONS.md` for convention compliance, primary code/files relevant to the spec's technical claims)
   - Explicit ask: P0/P1/P2 findings with file:line citations covering — (a) internal consistency (decisions ↔ ACs ↔ ADR matrix), (b) convention compliance, (c) technical accuracy of upstream/code claims, (d) logical gaps / unstated assumptions, (e) scope discipline (anything in the spec that's actually a future version's work, anything in non-goals that's actually in scope)
   - Output verdict: `APPROVE` / `REQUEST CHANGES` / `REJECT`
   - Length cap (~600 words)

   Surface findings verbatim to the user. **Do not silently apply fixes** — the user reviews the findings and decides which to address. The false-positive rate is non-zero (~30% in practice); the user is the final arbiter. After fixes, re-run lint (step 7) and re-run review (step 8) only if the user requests a second pass — don't auto-loop.

## Rules (must comply with `docs/CONVENTIONS.md`)

This section is a quick reference only — the authoritative SSOT is `docs/CONVENTIONS.md`. If a re-quoted rule here drifts from the SSOT, the SSOT wins.

- **Frontmatter schema** (§ Status Metadata): `status` enum / `version` SemVer (required for Draft/GA/Superseded) / `released` `YYYY-MM-DD` (required for GA/Superseded) / `last_updated` `YYYY-MM-DD` / description quoting (double quotes + single quotes for inline identifiers)
- **Body structure SSOT** (§ Spec / ADR Body Structure): the step 4 / 5 skeletons are *structure* only; the *content rules* are owned by the CONVENTIONS §
- **Info routing** (§ Section Role Separation): details go in Decisions table cells not the intro, option comparison goes in ADR §N four subsections
- **Cross-link direction** (§ Cross-Link Direction Rules): only the pair may link spec ↔ spec directly. Other spec ↔ spec direct links are forbidden — route through README
- **Naming** (§ Naming Rules): kebab-case filenames, `vX.Y.Z` directories, no `./` prefix, fully-qualified URLs for external resources only

## Limits

- The step 4 / 5 skeletons are *structural* — actual decisions / acceptance criteria / non-goals / decision matrix entries must be filled per CONVENTIONS § Spec / ADR Body Structure (not by mimicking recent specs)
- This skill automates **structural consistency** (frontmatter / pair / index / skeleton, steps 1–7) and **delegates independent review** (step 8) — but content judgment, accept/reject of reviewer findings, and any fix application remain the user's call. The reviewer's false-positive rate is non-zero; never blindly accept.
- The auto-spawned review (step 8) is intentional for *new spec* creation (high-stakes, low-frequency, immutable-after-GA). Other skills (commit-message / docstring-edit / etc.) should NOT copy this pattern by default — the verifier-spawn cost is justified only when the miss-cost outweighs the invocation overhead.
