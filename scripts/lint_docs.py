#!/usr/bin/env python3
"""docs/ lint — full repo scan. Used by CI.

Usage:
    uv run python scripts/lint_docs.py [TARGET_DIR]
    uv run python scripts/lint_docs.py docs/  # default

Applies the same rules as .claude/hooks/docs-lint.py (shared lib
scripts/_doc_lint.py) to each markdown file. See the _doc_lint.py docstring for the rules.

exit 0: no violations / exit 1: one or more violations.
"""

import sys
from pathlib import Path

import typer

# ^ add scripts/ to the import path to load the sibling _doc_lint module
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _doc_lint import lint_file  # noqa: E402


def main(
    target: str = typer.Argument("docs", help="directory relative to the repo root"),
) -> None:
    repo = Path(__file__).resolve().parent.parent
    target_dir = (repo / target).resolve()
    if not target_dir.is_dir():
        typer.echo(f"error: {target_dir} is not a directory", err=True)
        raise typer.Exit(1)

    all_errors: list[str] = []
    for path in sorted(target_dir.rglob("*.md")):
        rel = path.relative_to(repo)
        rel_str = str(rel).replace("\\", "/")
        all_errors.extend(lint_file(rel_str, repo))

    if all_errors:
        for e in all_errors:
            typer.echo(e, err=True)
        typer.echo(
            f"\n{len(all_errors)} violation(s) under {target}/ — policy: docs/CONVENTIONS.md",
            err=True,
        )
        raise typer.Exit(1)


if __name__ == "__main__":
    typer.run(main)
