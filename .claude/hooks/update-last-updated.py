#!/usr/bin/env python3
"""Auto-update the frontmatter last_updated of docs/*.md on edit.

Runs as a PostToolUse hook after Edit / Write / MultiEdit. If the hook event's
``tool_input.file_path`` is a ``docs/*.md`` with frontmatter, replaces the
``last_updated:`` line in place with today's date.

Skip conditions:
- files outside ``docs/``
- files without frontmatter (Living: CONVENTIONS / roadmap/README / traces/coverage)
- last_updated already today
- frontmatter status is Frozen or Superseded — the body-meaning-immutable principle.
  Editing such a file is either (a) a bulk migration using the Frozen exemption (handled
  per-PR by hand) or (b) a typo/link fix (where updating last_updated is appropriate);
  both are possible, so auto-handling is risky — the hook skips and the user decides.

This hook is silent (exit 0) — check the result via git diff.
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

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

target = REPO / rel
if not target.is_file():
    sys.exit(0)

text = target.read_text(encoding="utf-8")
if not text.startswith("---\n"):
    sys.exit(0)
end = text.find("\n---\n", 4)
if end < 0:
    sys.exit(0)

block = text[4:end]
status_match = re.search(r"^status:\s*(\S+)", block, re.MULTILINE)
if status_match and status_match.group(1) in ("Frozen", "Superseded"):
    # ^ no auto-update for Frozen / Superseded — requires an explicit user decision
    sys.exit(0)

today = date.today().isoformat()
new_block, n = re.subn(
    r"^last_updated:\s*\S+",
    f"last_updated: {today}",
    block,
    count=1,
    flags=re.MULTILINE,
)
if n == 0 or new_block == block:
    sys.exit(0)

new_text = "---\n" + new_block + text[end:]
target.write_text(new_text, encoding="utf-8")
sys.exit(0)
