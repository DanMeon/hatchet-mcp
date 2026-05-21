"""Structured stderr emitter — one JSON-line record per event.

Every tool invocation and every server lifecycle event emits exactly one record on
stderr (stdout is reserved for the MCP JSON-RPC protocol). Every string field — at any
depth — is run through ``redact()`` at format time, so this surface owns its own
token-leak boundary independent of ``_api_error``'s redaction on the MCP JSON-RPC
channel (the two surfaces are independently redacted by design — see
docs/roadmap/v0.2.0/reliability.md Decision 3).

Event names are stable across patches in a minor:
  - ``tool.ok`` / ``tool.error`` — one record per tool invocation, emitted by the
    reliability wrapper (see ``_shared._reliability_wrap``).
  - ``server.start`` / ``server.error`` — emitted from ``server.main`` at startup
    and on ``ConfigError``.
"""

import json
import sys
from typing import Any

from hatchet_mcp.config import redact


def _redact_in_value(value: Any) -> Any:
    """Recursively redact every string inside a field value (covers nested dicts / lists)."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [_redact_in_value(item) for item in value]
    if isinstance(value, dict):
        return {k: _redact_in_value(v) for k, v in value.items()}
    return value


def emit(event: str, **fields: Any) -> None:
    """Write one JSON-line record to stderr with the ``event`` discriminator and supplied fields."""
    record: dict[str, Any] = {"event": event}
    record.update({k: _redact_in_value(v) for k, v in fields.items()})
    sys.stderr.write(json.dumps(record, ensure_ascii=False) + "\n")
    sys.stderr.flush()
