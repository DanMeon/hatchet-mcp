"""Structured stderr emitter: one JSON-line record per invocation, dual-channel token redaction."""

import asyncio
import json
from typing import Any

import pytest
from hatchet_sdk.clients.rest.exceptions import (
    NotFoundException,
    ServiceException,
)

import hatchet_mcp._shared as shared
import hatchet_mcp.server as server_mod
from hatchet_mcp._logging import emit

pytestmark = pytest.mark.spec("v0.2.0/reliability")


def _records(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    """Parse the captured stderr stream into a list of JSON records, in order."""
    captured = capsys.readouterr().err
    return [json.loads(line) for line in captured.splitlines() if line.strip()]


def _no_delay_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin jitter and replace asyncio.sleep so retry storms run instantly."""
    monkeypatch.setattr("random.uniform", lambda _a, _b: 1.0)

    async def _no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("asyncio.sleep", _no_sleep)


# * Emitter unit tests — schema and redaction depth
def test_emit_writes_single_jsonline(capsys: pytest.CaptureFixture[str]) -> None:
    emit("server.start", read_only=True, tools=24)
    assert _records(capsys) == [
        {"event": "server.start", "read_only": True, "tools": 24}
    ]


@pytest.mark.spec("v0.2.0/reliability#AC-6")
def test_emit_redacts_full_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HATCHET_CLIENT_TOKEN", "SECRET-JWT-123")
    emit("tool.error", tool="x", redacted_error="boom SECRET-JWT-123 oops")
    record = _records(capsys)[0]
    assert "SECRET-JWT-123" not in record["redacted_error"]
    assert "***REDACTED***" in record["redacted_error"]


@pytest.mark.spec("v0.2.0/reliability#AC-6")
def test_emit_redacts_token_prefix(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The first 16 chars of the token are also a redaction needle (config._TOKEN_PREFIX_LEN).
    monkeypatch.setenv("HATCHET_CLIENT_TOKEN", "eyJhbGciOiJSUzI1NiJ9.body.signature")
    emit("tool.error", tool="x", redacted_error="logs leak eyJhbGciOiJSUzI1 prefix")
    record = _records(capsys)[0]
    assert "eyJhbGciOiJSUzI1" not in record["redacted_error"]


@pytest.mark.spec("v0.2.0/reliability#AC-6")
def test_emit_redacts_nested_string(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A leak via a nested dict or list field would bypass a top-level-only redaction.
    monkeypatch.setenv("HATCHET_CLIENT_TOKEN", "SECRET-JWT-XYZ")
    emit(
        "custom",
        info={"inner": "leak SECRET-JWT-XYZ"},
        items=["leak SECRET-JWT-XYZ"],
    )
    record = _records(capsys)[0]
    assert "SECRET-JWT-XYZ" not in json.dumps(record)


# * AC-5 — every wrapper invocation emits exactly one record
@pytest.mark.spec("v0.2.0/reliability#AC-5")
async def test_wrapper_success_emits_tool_ok(
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def ok() -> dict[str, Any]:
        return {"v": 1}

    wrapped = shared._reliability_wrap(ok, retry=True)
    await wrapped()
    records = _records(capsys)
    assert len(records) == 1
    assert records[0]["event"] == "tool.ok"
    assert records[0]["tool"] == "ok"
    assert isinstance(records[0]["duration_ms"], int)
    assert records[0]["duration_ms"] >= 0


@pytest.mark.spec("v0.2.0/reliability#AC-5")
async def test_wrapper_api_error_emits_tool_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _no_delay_retries(monkeypatch)

    async def fails() -> None:
        raise ServiceException(status=503, reason="Service Unavailable")

    wrapped = shared._reliability_wrap(fails, retry=True)
    with pytest.raises(RuntimeError, match="Hatchet API error"):
        await wrapped()
    records = _records(capsys)
    assert len(records) == 1
    assert records[0]["event"] == "tool.error"
    assert records[0]["tool"] == "fails"
    assert "Hatchet API error" in records[0]["redacted_error"]


@pytest.mark.spec("v0.2.0/reliability#AC-5")
async def test_wrapper_validation_error_emits_tool_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # AC-5 explicitly covers raises *before* any Hatchet call — input validation helpers
    # like _parse_dt/_parse_statuses raise ValueError before the SDK is reached.
    async def validates() -> None:
        raise ValueError("since must be ISO 8601 datetime; got 'nonsense'")

    wrapped = shared._reliability_wrap(validates, retry=True)
    with pytest.raises(ValueError):
        await wrapped()
    records = _records(capsys)
    assert len(records) == 1
    assert records[0]["event"] == "tool.error"
    assert records[0]["tool"] == "validates"
    assert "ISO 8601" in records[0]["redacted_error"]
    assert records[0]["redacted_error"].startswith("ValueError:")


@pytest.mark.spec("v0.2.0/reliability#AC-5")
async def test_wrapper_404_emits_exactly_one_record(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # 404 is non-retryable — exactly one record, no extra emit during the retry probe.
    async def returns_404() -> None:
        raise NotFoundException(status=404, reason="Not Found")

    wrapped = shared._reliability_wrap(returns_404, retry=True)
    with pytest.raises(RuntimeError):
        await wrapped()
    records = _records(capsys)
    assert len(records) == 1
    assert records[0]["event"] == "tool.error"


@pytest.mark.spec("v0.2.0/reliability#AC-5")
async def test_wrapper_timeout_emits_tool_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(shared, "_PER_CALL_TIMEOUT_S", 0.05)

    async def hang() -> None:
        await asyncio.Event().wait()

    wrapped = shared._reliability_wrap(hang, retry=False)
    with pytest.raises(asyncio.TimeoutError):
        await wrapped()
    records = _records(capsys)
    assert len(records) == 1
    assert records[0]["event"] == "tool.error"
    assert records[0]["tool"] == "hang"
    assert "TimeoutError" in records[0]["redacted_error"]


@pytest.mark.spec("v0.2.0/reliability#AC-5")
async def test_wrapper_retry_storm_emits_only_one_record(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Even with three failed attempts, the wrapper must emit one record (not one per retry).
    _no_delay_retries(monkeypatch)

    counter = {"n": 0}

    async def fails() -> None:
        counter["n"] += 1
        raise ServiceException(status=503, reason="Service Unavailable")

    wrapped = shared._reliability_wrap(fails, retry=True)
    with pytest.raises(RuntimeError):
        await wrapped()
    assert counter["n"] == 3
    assert len(_records(capsys)) == 1


# * AC-6 — JSON-RPC channel preserves redact via `_api_error` (independent of the stderr surface)
@pytest.mark.spec("v0.2.0/reliability#AC-6")
async def test_jsonrpc_channel_strips_token_from_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HATCHET_CLIENT_TOKEN", "SECRET-JWT-VALUE")
    _no_delay_retries(monkeypatch)

    async def raises_with_token() -> None:
        exc = ServiceException(status=500, reason="Server Error")
        exc.body = "Authorization: Bearer SECRET-JWT-VALUE oops"
        raise exc

    wrapped = shared._reliability_wrap(raises_with_token, retry=True)
    with pytest.raises(RuntimeError) as excinfo:
        await wrapped()

    # MCP JSON-RPC channel — the raised RuntimeError must not carry the raw token.
    assert "SECRET-JWT-VALUE" not in str(excinfo.value)
    assert "***REDACTED***" in str(excinfo.value)

    # stderr channel — the emitted record must not carry the raw token either.
    captured_err = capsys.readouterr().err
    assert "SECRET-JWT-VALUE" not in captured_err
    assert "***REDACTED***" in captured_err


# * server lifecycle records
@pytest.mark.spec("v0.2.0/reliability#AC-5")
def test_server_error_record_on_missing_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("HATCHET_CLIENT_TOKEN", raising=False)
    with pytest.raises(SystemExit) as excinfo:
        server_mod.main()
    assert excinfo.value.code == 1
    records = _records(capsys)
    assert len(records) == 1
    assert records[0]["event"] == "server.error"
    assert "HATCHET_CLIENT_TOKEN" in records[0]["error"]


@pytest.mark.spec("v0.2.0/reliability#AC-5")
def test_server_start_record_on_normal_boot(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    server_module: Any,
) -> None:
    monkeypatch.setenv("HATCHET_CLIENT_TOKEN", "JWT-test-token-value")
    monkeypatch.setenv("HATCHET_MCP_READ_ONLY", "true")
    # Stub out the heavy side effects so main() returns after the startup emit.
    monkeypatch.setattr("hatchet_mcp.server.init_hatchet", lambda: None)
    monkeypatch.setattr("hatchet_mcp.server.register_read_tools", lambda _mcp: None)
    monkeypatch.setattr("hatchet_mcp.server.register_mutating_tools", lambda _mcp: None)
    monkeypatch.setattr("hatchet_mcp.resources.register", lambda _mcp: None)
    monkeypatch.setattr("hatchet_mcp.prompts.register", lambda _mcp: None)
    monkeypatch.setattr(server_mod.app.mcp, "run", lambda transport: None)

    server_mod.main()

    records = _records(capsys)
    starts = [r for r in records if r["event"] == "server.start"]
    assert len(starts) == 1
    assert starts[0]["read_only"] is True
    assert starts[0]["server_url"] in {"token", "override"}
    assert isinstance(starts[0]["tools"], int)
