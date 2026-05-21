"""Environment-only configuration and fail-fast startup checks.

The Hatchet SDK reads ``HATCHET_CLIENT_TOKEN`` (and ``HATCHET_CLIENT_SERVER_URL``)
directly from the environment, so this module only validates that the required token is
present and exposes the MCP-specific knobs. The token value itself is never stored on a
model, logged, or echoed.
"""

import os

from pydantic import BaseModel

TOKEN_ENV = "HATCHET_CLIENT_TOKEN"
SERVER_URL_ENV = "HATCHET_CLIENT_SERVER_URL"
READ_ONLY_ENV = "HATCHET_MCP_READ_ONLY"

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})

# 16 chars covers the JWT header + the first byte of the payload. False positives are
# acceptable here — any unrelated match in an error string is still safe to redact.
_TOKEN_PREFIX_LEN = 16


class ConfigError(RuntimeError):
    """Raised at startup when required configuration is missing or invalid."""


class ServerConfig(BaseModel):
    """MCP-server-level settings. Deliberately does not hold the token."""

    read_only: bool
    server_url_override: str | None


def redact(message: str) -> str:
    """Strip the Hatchet token and its 16-char prefix so neither can leak."""
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        return message

    needles = {token}
    if len(token) >= _TOKEN_PREFIX_LEN:
        needles.add(token[:_TOKEN_PREFIX_LEN])

    for needle in needles:
        if needle in message:
            message = message.replace(needle, "***REDACTED***")
    return message


def _parse_bool(raw: str | None, *, default: bool) -> bool:
    if raw is None or not raw.strip():
        return default

    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False

    allowed = sorted(_TRUE | _FALSE)
    raise ConfigError(
        f"{READ_ONLY_ENV} must be a boolean ({allowed}); got {redact(raw)!r}"
    )


def load_config() -> ServerConfig:
    """Validate the environment and return server settings, failing fast if the token is absent."""
    if not os.environ.get(TOKEN_ENV, "").strip():
        raise ConfigError(
            f"{TOKEN_ENV} is required but not set. "
            "Provide a Hatchet API token (a JWT) via the environment to start the server."
        )

    return ServerConfig(
        read_only=_parse_bool(os.environ.get(READ_ONLY_ENV), default=True),
        server_url_override=(os.environ.get(SERVER_URL_ENV) or "").strip() or None,
    )
