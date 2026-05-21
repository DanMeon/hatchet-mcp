#!/usr/bin/env python3
"""Collect ``@pytest.mark.spec(...)`` markers from tests/ and update
``docs/traces/coverage.md`` (Living).

Usage:
    uv run python scripts/generate_spec_trace.py [--check]

``--check`` flag: verify instead of update (for CI — exit 1 if coverage.md is stale).

Method: AST static analysis. Finds ``test_*`` functions decorated with
``@pytest.mark.spec("vX.Y.Z/topic#AC-N")`` and maps ``(spec_id → nodeid)``.

Tests with no marker pass as usual (CONVENTIONS § Trace Report).
"""

import ast
import re
from collections import defaultdict
from pathlib import Path

import typer

REPO = Path(__file__).resolve().parent.parent
TESTS_DIR = REPO / "tests"
COVERAGE_FILE = REPO / "docs" / "traces" / "coverage.md"

# ^ spec_id: vX.Y.Z/<topic>[#AC-N]
SPEC_ID_RE = re.compile(r"^v\d+\.\d+\.\d+/[a-z0-9-]+(?:#AC-\d+)?$")


def main(
    check: bool = typer.Option(
        False, "--check", help="verify staleness only (no write)"
    ),
) -> None:
    mapping = _collect_spec_markers(TESTS_DIR)
    body = _render(mapping)

    if check:
        existing = (
            COVERAGE_FILE.read_text(encoding="utf-8") if COVERAGE_FILE.exists() else ""
        )
        if existing != body:
            typer.echo(
                f"error: {COVERAGE_FILE.relative_to(REPO)} is stale — "
                "run scripts/generate_spec_trace.py to refresh.",
                err=True,
            )
            raise typer.Exit(1)
        typer.echo(f"{COVERAGE_FILE.relative_to(REPO)} up to date.")
        return

    COVERAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE_FILE.write_text(body, encoding="utf-8")
    n = sum(len(v) for v in mapping.values())
    typer.echo(
        f"updated {COVERAGE_FILE.relative_to(REPO)} — {len(mapping)} spec / {n} test mapping(s)"
    )


def _collect_spec_markers(tests_dir: Path) -> dict[str, list[str]]:
    """spec_id → list of pytest nodeids. Methods inside ``class TestFoo`` are emitted
    exactly as `tests/x.py::TestFoo::test_bar` (avoiding ast.walk flattening)."""
    mapping: dict[str, list[str]] = defaultdict(list)
    if not tests_dir.is_dir():
        return mapping

    for py_file in sorted(tests_dir.rglob("test_*.py")):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = py_file.relative_to(REPO)
        visitor = _SpecMarkerVisitor(rel)
        visitor.visit(tree)
        for spec_id, nodeids in visitor.mapping.items():
            mapping[spec_id].extend(nodeids)
    return mapping


class _SpecMarkerVisitor(ast.NodeVisitor):
    """Extracts @pytest.mark.spec(...) while keeping a class-context stack +
    module-level pytestmark.

    Also supports the file-level marker form
    pytestmark = pytest.mark.spec("vX.Y.Z/topic") (single or list) — auto-applied to
    every test_* function. Used for per-file (soft) mapping.
    """

    def __init__(self, file_rel: Path) -> None:
        self.file_rel = file_rel
        self.class_stack: list[str] = []
        self.module_specs: list[str] = []
        self.mapping: dict[str, list[str]] = defaultdict(list)

    def visit_Module(self, node: ast.Module) -> None:
        # ^ pre-pass: capture module-level 'pytestmark = ...'
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            if not (len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name)):
                continue
            if stmt.targets[0].id != "pytestmark":
                continue
            self.module_specs.extend(_extract_spec_ids_from_value(stmt.value))
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._maybe_add(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._maybe_add(node)
        self.generic_visit(node)

    def _maybe_add(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if not node.name.startswith("test_"):
            return
        spec_ids: list[str] = list(self.module_specs)
        for decorator in node.decorator_list:
            spec_id = _extract_spec_id(decorator)
            if spec_id:
                spec_ids.append(spec_id)
        parts = [*self.class_stack, node.name]
        nodeid = f"{self.file_rel}::{'::'.join(parts)}"
        for spec_id in spec_ids:
            if SPEC_ID_RE.match(spec_id):
                self.mapping[spec_id].append(nodeid)


def _extract_spec_ids_from_value(value: ast.AST) -> list[str]:
    """The RHS of pytestmark — a single marker call or a list of marker calls."""
    if isinstance(value, ast.List | ast.Tuple):
        return [s for elt in value.elts if (s := _extract_spec_id(elt)) is not None]
    spec_id = _extract_spec_id(value)
    return [spec_id] if spec_id else []


def _extract_spec_id(node: ast.AST) -> str | None:
    """Match ``@pytest.mark.spec("vX.Y.Z/...")`` or ``@mark.spec("...")``."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "spec"):
        return None
    if not (isinstance(func.value, ast.Attribute) and func.value.attr == "mark"):
        return None
    if not node.args or not isinstance(node.args[0], ast.Constant):
        return None
    val = node.args[0].value
    return val if isinstance(val, str) else None


def _render(mapping: dict[str, list[str]]) -> str:
    header = (
        "# Spec ↔ Test Trace\n\n"
        "Auto-generated — `scripts/generate_spec_trace.py`. Living.\n\n"
        "Maps spec acceptance criteria (AC-N) ↔ tests, collected from "
        '`@pytest.mark.spec("vX.Y.Z/topic#AC-N")` markers '
        "(CONVENTIONS § Trace Report).\n\n"
    )
    if not mapping:
        return header + "(No mappings yet.)\n"

    lines = ["| Spec | AC | Tests |", "|---|---|---|"]
    for spec_id in sorted(mapping):
        spec, _, ac = spec_id.partition("#")
        for nodeid in sorted(mapping[spec_id]):
            lines.append(f"| {spec} | {ac or '—'} | `{nodeid}` |")
    return header + "\n".join(lines) + "\n"


if __name__ == "__main__":
    typer.run(main)
