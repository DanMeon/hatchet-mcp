#!/usr/bin/env python3
"""tests/*.py PostToolUse hook — regenerate the spec trace report.

If the hook event's ``tool_input.file_path`` is a ``tests/**/*.py``, runs
``scripts/generate_spec_trace.py`` (write mode) to refresh ``docs/traces/coverage.md``.
Otherwise exits immediately.

Background: the trace is invalidated by ``@pytest.mark.spec(...)`` marker changes, but the
docs-lint hook only watches ``docs/*.md``. A marker added/renamed/removed in ``tests/*.py``
wouldn't trigger regeneration locally, so staleness would surface only at the CI ``--check``.

On failure (generator error): exit 2 + stderr — injected into the model context.
Normal regeneration or a non-applicable file: exit 0.
"""

import json
import subprocess
import sys
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
if not (rel_str.startswith("tests/") and rel.suffix == ".py"):
    sys.exit(0)

# * Regenerate the trace — same no-project + ad-hoc typer install pattern as CI.
#   Works regardless of the project venv's extras state.
result = subprocess.run(
    [
        "uv",
        "run",
        "--no-project",
        "--with",
        "typer>=0.12",
        "python",
        str(REPO / "scripts" / "generate_spec_trace.py"),
    ],
    cwd=str(REPO),
    capture_output=True,
    text=True,
)
if result.returncode != 0:
    sys.stderr.write("\nregen-spec-trace: generator failed\n")
    sys.stderr.write(result.stderr)
    sys.exit(2)
