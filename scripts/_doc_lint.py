"""Shared docs-lint library — used by .claude/hooks/docs-lint.py (single file)
and scripts/lint_docs.py (whole-repo scan).

Enforces CONVENTIONS.md policy. Rules:

1. **Frontmatter (YAML)** — every spec except Living
   - status enum: Active / Draft / Frozen / Superseded
   - last_updated: YYYY-MM-DD (required)
   - description: required (non-empty string)
   - status:Active → forbids both ga / target
   - status:Draft → requires target, forbids ga
   - status:Frozen → requires ga (except: meta-level docs/implementation/<topic>.md /
     resolved docs/upstream/<topic>.md / pre-GA stage log)
   - status:Frozen + target allowed — only for a pre-GA stage log under
     `docs/implementation/vX.Y.Z/...` (CONVENTIONS § Implementation Log Structure). The
     body is immutable as written, but the release label is withheld until the parent
     version GAs — the editorial vs release dimension split of Rust RFC / PEP / ADR
   - status:Superseded → requires ga + superseded_by
   - ga ↔ target mutex (except the Frozen pre-GA stage case)
   - ga / target SemVer (vX.Y.Z)
2. **Supersede chain integrity** — the file pointed to by superseded_by exists +
   its supersedes back-references this file
3. **Filename kebab-case** — ALL-CAPS (README / CONVENTIONS, etc.) is exempt
4. **vX.Y.Z directory SemVer** — directories starting with v must be exact SemVer
5. **<topic>.md ↔ <topic>-research.md pair** — roadmap ↔ design coexist
6. **same-version spec ↔ spec direct link** — only the pair is exempt
7. **broken .md link** — relative path points to a real file

docs/init/ (flat docs from before the spec system) is exempt — skipped by lint.
"""

import re
import subprocess
from functools import cache
from pathlib import Path

# * Policy constants
LIVING_FILES = {
    "docs/CONVENTIONS.md",
    "docs/roadmap/README.md",
    "docs/traces/coverage.md",
    "docs/upstream/README.md",
}
STATUS_ENUM = {"Active", "Draft", "Frozen", "Superseded"}


# * frontmatter parser — flat key:value only (no multiline / nesting)
def parse_frontmatter(text: str) -> dict[str, str] | None:
    """Parse simple YAML frontmatter at the top of `text`.

    Returns ``None`` if no ``---``-delimited block is present at the start.
    Comments (``# ...``) and blank lines are skipped. Values are stripped of
    surrounding whitespace and unwrapped from matching single/double quotes.
    """
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    block = text[4:end]
    meta: dict[str, str] = {}
    for raw in block.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        v = v.strip()
        # ^ strip a trailing inline comment ('foo: bar  # note') — a '#' inside a quoted
        #   value is protected (safe after quote handling, given the flat key:value model)
        if not (v.startswith(("'", '"'))):
            v = v.split(" #", 1)[0].rstrip()
        # ^ unwrap only when the same quote is on both ends (mismatched left as-is)
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        meta[k.strip()] = v
    return meta


# * code-fence stripper — exclude example links inside fences / inline-backtick links
def _strip_code(text: str) -> str:
    """Remove ```...``` blocks + inline `...` backticks. The lint regexes run on this
    output rather than raw text — preventing false positives where an example link
    inside a fence is flagged as a broken/cross-link violation."""
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]+`", "", text)
    return text


# * Rule 1+2: frontmatter schema + supersede chain
def validate_frontmatter(rel_str: str, meta: dict[str, str], repo: Path) -> list[str]:
    errors: list[str] = []

    status = meta.get("status")
    if not status:
        return ["frontmatter: missing 'status' field"]
    if status not in STATUS_ENUM:
        return [
            f"frontmatter: invalid 'status' {status!r} — must be one of {sorted(STATUS_ENUM)}"
        ]

    last_updated = meta.get("last_updated", "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", last_updated):
        errors.append(
            f"frontmatter: 'last_updated' must be YYYY-MM-DD (got {last_updated!r})"
        )

    if not meta.get("description", "").strip():
        errors.append("frontmatter: 'description' is required (non-empty string)")

    has_ga = "ga" in meta
    has_target = "target" in meta

    if status == "Active":
        if has_ga or has_target:
            errors.append("frontmatter: status:Active forbids 'ga' and 'target'")
    elif status == "Draft":
        if not has_target:
            errors.append("frontmatter: status:Draft requires 'target'")
        if has_ga:
            errors.append("frontmatter: status:Draft forbids 'ga' (use 'target')")
    elif status == "Frozen":
        # ^ exempt: meta-level (outside vX.Y.Z) implementation, resolved upstream
        is_meta_level = rel_str.startswith("docs/implementation/") and not re.match(
            r"docs/implementation/v\d+\.\d+\.\d+/", rel_str
        )
        is_upstream_resolved = rel_str.startswith("docs/upstream/")
        # ^ exempt: pre-GA stage log — CONVENTIONS § Implementation Log Structure. Same
        #   editorial vs release dimension split as Rust RFC / PEP / ADR. The stage body
        #   is immutable as written (= Frozen) but the ga label is withheld until the
        #   parent version GAs — expressed as target in that window. Bulk target → ga at GA.
        is_pre_ga_stage = (
            re.match(r"docs/implementation/v\d+\.\d+\.\d+/", rel_str) is not None
            and has_target
            and not has_ga
        )
        if not has_ga:
            if not (is_meta_level or is_upstream_resolved or is_pre_ga_stage):
                errors.append(
                    "frontmatter: status:Frozen requires 'ga' "
                    "(except meta-level docs/implementation/<topic>.md, "
                    "docs/upstream/<topic>.md, and pre-GA stage log)"
                )
        if has_target and not is_pre_ga_stage:
            errors.append("frontmatter: status:Frozen forbids 'target'")
    elif status == "Superseded":
        if not has_ga:
            errors.append("frontmatter: status:Superseded requires 'ga' (preserved)")
        if has_target:
            errors.append("frontmatter: status:Superseded forbids 'target'")
        if "superseded_by" not in meta:
            errors.append("frontmatter: status:Superseded requires 'superseded_by'")

    if has_ga and has_target:
        errors.append("frontmatter: 'ga' and 'target' are mutually exclusive")

    for field in ("ga", "target"):
        val = meta.get(field, "")
        if val and not re.fullmatch(r"v\d+\.\d+\.\d+", val):
            errors.append(
                f"frontmatter: {field!r} must be SemVer 'vX.Y.Z' (got {val!r})"
            )

    errors.extend(_validate_supersede_chain(rel_str, meta, repo))
    return errors


def _validate_supersede_chain(
    rel_str: str, meta: dict[str, str], repo: Path
) -> list[str]:
    errors: list[str] = []
    rel = Path(rel_str)

    superseded_by = meta.get("superseded_by")
    # ^ supersede path base: under vX.Y.Z → docs/<kind>/, meta-level flat → docs/<kind>/.
    #   format: a vX.Y.Z file is '<vX.Y.Z>/<topic>.md', meta-level is '<topic>.md'.
    base, expected = _supersede_base(rel)

    if superseded_by:
        target_rel = base / superseded_by
        target = repo / target_rel
        if not target.exists():
            errors.append(
                f"frontmatter: superseded_by {superseded_by!r} not found (resolved: {target_rel})"
            )
        else:
            target_meta = parse_frontmatter(target.read_text(encoding="utf-8"))
            if target_meta is None:
                errors.append(
                    f"frontmatter: superseded_by target {superseded_by!r} lacks frontmatter"
                )
            elif target_meta.get("supersedes") != expected:
                errors.append(
                    f"frontmatter: supersede chain broken — target's "
                    f"'supersedes' is {target_meta.get('supersedes')!r}, "
                    f"expected {expected!r}"
                )

    supersedes = meta.get("supersedes")
    if supersedes:
        target_rel = base / supersedes
        if not (repo / target_rel).exists():
            errors.append(
                f"frontmatter: supersedes {supersedes!r} not found (resolved: {target_rel})"
            )

    return errors


def _supersede_base(rel: Path) -> tuple[Path, str]:
    """The base directory of the supersede chain + this file's expected back-reference ID.

    A vX.Y.Z file (`docs/<kind>/<vX.Y.Z>/<file>.md`) → base=`docs/<kind>/`,
    expected=`<vX.Y.Z>/<file>.md`.
    A meta-level flat file (`docs/<kind>/<file>.md`) → base=`docs/<kind>/`,
    expected=`<file>.md`.
    """
    if re.fullmatch(r"v\d+\.\d+\.\d+", rel.parent.name):
        return rel.parent.parent, str(rel.relative_to(rel.parent.parent))
    return rel.parent, rel.name


# * Rule 3+4: filename kebab-case + vX.Y.Z directory SemVer
def validate_filename(rel_str: str) -> list[str]:
    errors: list[str] = []
    parts = rel_str.split("/")

    stem = parts[-1].removesuffix(".md")
    if not (
        re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", stem) or re.fullmatch(r"[A-Z]+", stem)
    ):
        errors.append(
            f"filename {parts[-1]!r} must be kebab-case (or ALL-CAPS for "
            "README / CONVENTIONS / CHANGELOG)"
        )

    for part in parts[:-1]:
        if re.match(r"^v\d", part) and not re.fullmatch(r"v\d+\.\d+\.\d+", part):
            errors.append(f"version directory {part!r} must be 'vX.Y.Z' (SemVer)")

    return errors


# * Rule 5: <topic>.md ↔ <topic>-research.md pair existence
PAIR_EXEMPT_VERSIONS: set[str] = set()


def validate_pair(rel_str: str, repo: Path) -> list[str]:
    m = re.match(r"docs/(roadmap|design)/(v\d+\.\d+\.\d+)/(.+)\.md$", rel_str)
    if not m:
        return []
    side, ver, base = m.group(1), m.group(2), m.group(3)
    if ver in PAIR_EXEMPT_VERSIONS:
        return []

    if side == "roadmap":
        pair = repo / "docs" / "design" / ver / f"{base}-research.md"
        if not pair.exists():
            return [
                f"pair file missing — expected docs/design/{ver}/{base}-research.md"
            ]
    else:
        if not base.endswith("-research"):
            return [f"design file {base!r} must end with '-research'"]
        topic = base.removesuffix("-research")
        pair = repo / "docs" / "roadmap" / ver / f"{topic}.md"
        if not pair.exists():
            return [f"pair file missing — expected docs/roadmap/{ver}/{topic}.md"]
    return []


# * Rule 6: same-version spec ↔ spec direct link (pair only)
def validate_cross_link(rel_str: str, text: str) -> list[str]:
    m = re.match(r"docs/(roadmap|design)/(v\d+\.\d+\.\d+)/(.+)\.md$", rel_str)
    if not m:
        return []
    base = m.group(3)
    if base.endswith("-research"):
        allowed_link = f"{base.removesuffix('-research')}.md"
    else:
        allowed_link = f"{base}-research.md"
    self_link = f"{base}.md"

    errors: list[str] = []
    for link in re.findall(r"\]\(([^)]+\.md)[^)]*\)", _strip_code(text)):
        link_target = link.split("#")[0]
        if "/" in link_target:
            continue
        if link_target in (allowed_link, self_link):
            continue
        errors.append(
            f"same-version spec direct link {link!r} — route through roadmap/README.md"
        )
    return errors


@cache
def _git_visible_paths(repo: Path) -> frozenset[Path]:
    """Resolved absolute paths git would surface on a fresh CI checkout.

    ``git ls-files --cached --others --exclude-standard`` lists tracked files plus
    untracked-but-not-gitignored files — the exact set a CI runner sees after
    ``actions/checkout``. ``.gitignored`` files like CLAUDE.md / AGENTS.md are excluded,
    so a markdown link to a local-only file is caught here instead of going green
    locally and red on CI. Returns an empty set outside a git repo.
    """
    try:
        out = subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=repo,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return frozenset()
    return frozenset((repo / line).resolve() for line in out.splitlines() if line)


# * Rule 7: broken .md link
def validate_broken_link(rel_str: str, text: str, repo: Path) -> list[str]:
    target_dir = (repo / rel_str).parent
    visible = _git_visible_paths(repo)
    errors: list[str] = []
    for link in re.findall(r"\]\(([^)]+\.md)[^)]*\)", _strip_code(text)):
        link_target = link.split("#")[0].split("?")[0]
        if not link_target or link_target.startswith("http"):
            continue
        resolved = (target_dir / link_target).resolve()
        try:
            resolved.relative_to(repo)
        except ValueError:
            # ^ absolute path outside the repo — skip
            continue
        if not resolved.exists():
            errors.append(f"broken .md link {link!r} (resolved: {resolved})")
        elif visible and resolved not in visible:
            # ^ file exists locally but is .gitignored — CI checkout would not see it
            errors.append(
                f"broken .md link {link!r} (resolved: {resolved} is gitignored — "
                f"would not exist on CI checkout)"
            )
    return errors


def lint_file(rel_str: str, repo: Path) -> list[str]:
    """Run all rules on a single docs/*.md path. Returns error strings prefixed
    with the file path. Empty list = clean."""
    # ^ docs/init/ is flat docs from before the spec system — conventions don't apply
    if rel_str.startswith("docs/init/"):
        return []
    target = repo / rel_str
    if not target.is_file():
        return []
    text = target.read_text(encoding="utf-8")
    errors: list[str] = []

    if rel_str not in LIVING_FILES:
        meta = parse_frontmatter(text)
        if meta is None:
            errors.append(
                "missing YAML frontmatter — add "
                "'---\\nstatus: <Active|Draft|Frozen|Superseded>\\n"
                "[ga|target]: vX.Y.Z\\nlast_updated: YYYY-MM-DD\\n---' "
                "(CONVENTIONS § Status Metadata)"
            )
        else:
            errors.extend(validate_frontmatter(rel_str, meta, repo))

    errors.extend(validate_filename(rel_str))
    errors.extend(validate_pair(rel_str, repo))
    errors.extend(validate_cross_link(rel_str, text))
    errors.extend(validate_broken_link(rel_str, text, repo))

    return [f"{rel_str}: {e}" for e in errors]
