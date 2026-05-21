#!/usr/bin/env python3
"""docs/*.md PostToolUse lint — single-file mode.

If the hook event's ``tool_input.file_path`` is a ``docs/*.md``, applies the shared lib
(``scripts/_doc_lint.py``) rules. Otherwise exits immediately.

On violation: exit 2 + stderr — Claude Code injects stderr into the LLM context so the
model becomes aware of the violations. exit 1 is non-blocking, so do not use it.

Rules / policy SSOT: ``scripts/_doc_lint.py`` docstring + ``docs/CONVENTIONS.md``.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from _doc_lint import lint_file  # noqa: E402

try:
    event = json.loads(sys.stdin.read() or "{}")
except json.JSONDecodeError:
    sys.exit(0)

tool_input = event.get("tool_input") or {}
file_path = tool_input.get("file_path") or ""
if not file_path:
    sys.exit(0)

try:
    rel = Path(file_path).resolve().relative_to(REPO)
except ValueError:
    sys.exit(0)

rel_str = str(rel).replace("\\", "/")
if not (rel_str.startswith("docs/") and rel.suffix == ".md"):
    sys.exit(0)

errors = lint_file(rel_str, REPO)
if errors:
    sys.stderr.write(f"\ndocs-lint: {len(errors)} violation(s)\n")
    for i, e in enumerate(errors, 1):
        sys.stderr.write(f"  {i}. {e}\n")
    sys.stderr.write("policy: docs/CONVENTIONS.md\n")
    sys.exit(2)
