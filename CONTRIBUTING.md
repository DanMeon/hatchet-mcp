# Contributing to hatchet-mcp

Thanks for contributing! This is an unofficial, community project. By contributing you agree
that your contributions are licensed under the project's [MIT License](LICENSE).

## Development setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.10+.

```bash
uv sync              # install runtime + dev dependencies
uv run hatchet-mcp   # run the server (needs HATCHET_CLIENT_TOKEN)
```

The full test suite needs **no token** and performs **no real mutation**.

## Quality gates

Run all of these before pushing — CI runs the same matrix and is the only enforced gate (the
`.claude/hooks` are not auto-wired):

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyright
uv run pytest -q
```

`pyright` type-checks `tests/` as well as `src/`, so keep test code type-clean.

## Conventions

- **Python 3.10+**; `ruff` and `pyright` are pinned to `py310` — no 3.11+-only syntax.
- **Read-only by default.** Mutating tools are registered only when `HATCHET_MCP_READ_ONLY=false`,
  and every mutating handler additionally calls `_require_writable()`. Never remove either layer.
- **Never leak the token.** It must never reach stdout, stderr, tool output, or an error string.
- **Tool output uses the Hatchet REST shape** (camelCase) — serialize SDK models through the
  shared `_dump` helper; tests pin this shape.
- **Configuration is environment-only** — add new knobs as env vars in `config.py`, not CLI flags.

### Adding a tool

1. Write the handler in the matching `src/hatchet_mcp/tools/<domain>.py`. Mutating handlers
   must call `_require_writable()` first.
2. Import shared helpers from `_shared`. Validate inputs with the `_parse_*` helpers; return SDK
   models via `_dump`. A list tool must clamp its `limit` with `_clamp_limit`.
3. Append to the module's `READ_TOOLS` or `MUTATING_TOOLS` catalog. A brand-new module must be
   added to `_TOOL_MODULES` in `server.py`.

## Documentation

`docs/` is spec-driven and immutable-per-version; read [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md)
before touching any doc. Start a new version spec with the `/new-spec` skill. Frozen specs are
superseded by a new version, never edited in place.

## Pull requests

1. Branch from `main`.
2. Make your change with tests; keep all quality gates green.
3. Open a PR against `main`. CI (lint, format, type-check, tests) must pass.
