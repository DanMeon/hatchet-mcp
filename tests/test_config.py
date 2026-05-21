"""config.py: fail-fast on a missing token, HATCHET_MCP_READ_ONLY parsing, token redaction."""

import pytest

from hatchet_mcp.config import (
    READ_ONLY_ENV,
    SERVER_URL_ENV,
    TOKEN_ENV,
    ConfigError,
    load_config,
    redact,
)


def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    with pytest.raises(ConfigError):
        load_config()


def test_blank_token_raises(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "   ")
    with pytest.raises(ConfigError):
        load_config()


@pytest.mark.parametrize(
    "raw",
    ["true", "True", "TRUE", "1", "yes", "on"],
)
def test_read_only_truthy(monkeypatch, raw):
    monkeypatch.setenv(TOKEN_ENV, "tok")
    monkeypatch.setenv(READ_ONLY_ENV, raw)
    assert load_config().read_only is True


@pytest.mark.parametrize(
    "raw",
    ["false", "False", "FALSE", "0", "no", "off"],
)
def test_read_only_falsy(monkeypatch, raw):
    monkeypatch.setenv(TOKEN_ENV, "tok")
    monkeypatch.setenv(READ_ONLY_ENV, raw)
    assert load_config().read_only is False


def test_read_only_defaults_true(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "tok")
    monkeypatch.delenv(READ_ONLY_ENV, raising=False)
    assert load_config().read_only is True


def test_read_only_blank_defaults_true(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "tok")
    monkeypatch.setenv(READ_ONLY_ENV, "   ")
    assert load_config().read_only is True


def test_read_only_invalid_raises(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "tok")
    monkeypatch.setenv(READ_ONLY_ENV, "maybe")
    with pytest.raises(ConfigError):
        load_config()


def test_invalid_read_only_message_is_token_free(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "supersecret-jwt")
    monkeypatch.setenv(READ_ONLY_ENV, "maybe")
    with pytest.raises(ConfigError) as excinfo:
        load_config()
    assert "supersecret-jwt" not in str(excinfo.value)


def test_server_url_override(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "tok")
    monkeypatch.setenv(SERVER_URL_ENV, "https://hatchet.internal")
    assert load_config().server_url_override == "https://hatchet.internal"


def test_server_url_override_absent(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "tok")
    monkeypatch.delenv(SERVER_URL_ENV, raising=False)
    assert load_config().server_url_override is None


def test_redact_strips_token(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "supersecret")
    out = redact("connection failed for supersecret at host")
    assert "supersecret" not in out
    assert "***REDACTED***" in out


def test_redact_strips_token_prefix(monkeypatch):
    # Truncated/wrapped log lines often surface only the JWT header prefix; the full-substring
    # check would miss them, so redact also strips the first 16 chars of the token.
    monkeypatch.setenv(TOKEN_ENV, "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.body.signature")
    out = redact("Authorization: Bearer eyJhbGciOiJIUzI1 (truncated)")
    assert "eyJhbGciOiJIUzI1" not in out
    assert "***REDACTED***" in out


def test_redact_noop_without_token(monkeypatch):
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    assert redact("nothing to hide here") == "nothing to hide here"


def test_invalid_read_only_message_redacts_long_token(monkeypatch):
    # A 16+ char token mis-pasted into HATCHET_MCP_READ_ONLY must not leak via the
    # ConfigError message that echoes the offending value.
    monkeypatch.setenv(TOKEN_ENV, "eyJhbGciOiJIUzI1NiJ9.body.signature")
    monkeypatch.setenv(READ_ONLY_ENV, "eyJhbGciOiJIUzI1NiJ9.body.signature")
    with pytest.raises(ConfigError) as excinfo:
        load_config()
    assert "eyJhbGciOiJIUzI1NiJ9" not in str(excinfo.value)
