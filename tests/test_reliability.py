"""Reliability wrapper: retry + 30s deadline + Retry-After + idempotency-gated retry at registration time."""

import asyncio
import inspect
from typing import Annotated, Any

import pytest
from hatchet_sdk.clients.rest.exceptions import (
    NotFoundException,
    RestConnectionError,
    ServiceException,
    TooManyRequestsException,
)
from pydantic import Field

import hatchet_mcp._shared as shared
import hatchet_mcp.app as app
import hatchet_mcp.server as server

pytestmark = pytest.mark.spec("v0.2.0/reliability")


def _no_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin random.uniform to 1.0 so jitter contributes nothing and sleep args equal backoff base."""
    monkeypatch.setattr("random.uniform", lambda _a, _b: 1.0)


def _capture_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace asyncio.sleep with a recorder that returns instantly so tests stay fast and deterministic."""
    calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        calls.append(delay)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    return calls


# * AC-1 — exponential-backoff retry on 5xx / 429 / transport errors; 4xx surfaces immediately
@pytest.mark.spec("v0.2.0/reliability#AC-1")
async def test_503_exhausts_retries_then_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_jitter(monkeypatch)
    sleep_calls = _capture_sleep(monkeypatch)

    counter = {"n": 0}

    async def always_503() -> dict[str, Any]:
        counter["n"] += 1
        raise ServiceException(status=503, reason="Service Unavailable")

    wrapped = shared._reliability_wrap(always_503, retry=True)
    with pytest.raises(RuntimeError, match="Hatchet API error"):
        await wrapped()
    # Spec: 4 attempts (initial + 3 retries), 3 sleeps with backoff series 1s/2s/4s.
    assert counter["n"] == 4
    assert sleep_calls == [1.0, 2.0, 4.0]


@pytest.mark.spec("v0.2.0/reliability#AC-1")
async def test_503_recovers_on_third_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_jitter(monkeypatch)
    _capture_sleep(monkeypatch)

    counter = {"n": 0}

    async def two_503s_then_ok() -> dict[str, Any]:
        counter["n"] += 1
        if counter["n"] < 3:
            raise ServiceException(status=503, reason="Service Unavailable")
        return {"ok": True}

    wrapped = shared._reliability_wrap(two_503s_then_ok, retry=True)
    assert await wrapped() == {"ok": True}
    assert counter["n"] == 3


@pytest.mark.spec("v0.2.0/reliability#AC-1")
async def test_404_surfaces_on_first_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_jitter(monkeypatch)
    sleep_calls = _capture_sleep(monkeypatch)

    counter = {"n": 0}

    async def returns_404() -> None:
        counter["n"] += 1
        raise NotFoundException(status=404, reason="Not Found")

    wrapped = shared._reliability_wrap(returns_404, retry=True)
    with pytest.raises(RuntimeError, match="Hatchet API error"):
        await wrapped()
    assert counter["n"] == 1
    assert sleep_calls == []


@pytest.mark.spec("v0.2.0/reliability#AC-1")
async def test_connection_error_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_jitter(monkeypatch)
    sleep_calls = _capture_sleep(monkeypatch)

    counter = {"n": 0}

    async def conn_err() -> None:
        counter["n"] += 1
        raise RestConnectionError(reason="connect refused")

    wrapped = shared._reliability_wrap(conn_err, retry=True)
    with pytest.raises(RuntimeError, match="Hatchet API error"):
        await wrapped()
    assert counter["n"] == 4
    assert sleep_calls == [1.0, 2.0, 4.0]


# * AC-2 — 429 honors Retry-After clamped to 10s; falls back to backoff when missing
@pytest.mark.spec("v0.2.0/reliability#AC-2")
async def test_429_retry_after_above_cap_clamps_to_10s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_jitter(monkeypatch)
    sleep_calls = _capture_sleep(monkeypatch)

    counter = {"n": 0}

    async def returns_429() -> None:
        counter["n"] += 1
        exc = TooManyRequestsException(status=429, reason="Too Many Requests")
        exc.headers = {"Retry-After": "30"}
        raise exc

    wrapped = shared._reliability_wrap(returns_429, retry=True)
    with pytest.raises(RuntimeError, match="Hatchet API error"):
        await wrapped()
    assert counter["n"] == 4
    # Three sleeps: each Retry-After=30 clamps to the 10s cap, dominating the 1s/2s/4s backoff.
    assert sleep_calls == [10.0, 10.0, 10.0]


@pytest.mark.spec("v0.2.0/reliability#AC-2")
async def test_429_uses_backoff_when_no_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_jitter(monkeypatch)
    sleep_calls = _capture_sleep(monkeypatch)

    async def returns_429_no_header() -> None:
        raise TooManyRequestsException(status=429, reason="Too Many Requests")

    wrapped = shared._reliability_wrap(returns_429_no_header, retry=True)
    with pytest.raises(RuntimeError, match="Hatchet API error"):
        await wrapped()
    assert sleep_calls == [1.0, 2.0, 4.0]


@pytest.mark.spec("v0.2.0/reliability#AC-2")
async def test_429_retry_after_below_backoff_keeps_backoff_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_jitter(monkeypatch)
    sleep_calls = _capture_sleep(monkeypatch)

    async def returns_429_short_header() -> None:
        exc = TooManyRequestsException(status=429, reason="Too Many Requests")
        exc.headers = {"Retry-After": "0"}
        raise exc

    wrapped = shared._reliability_wrap(returns_429_short_header, retry=True)
    with pytest.raises(RuntimeError, match="Hatchet API error"):
        await wrapped()
    # max(backoff, retry_after=0) keeps the backoff floor; 429 still races to the deadline.
    assert sleep_calls == [1.0, 2.0, 4.0]


@pytest.mark.spec("v0.2.0/reliability#AC-2")
async def test_429_malformed_retry_after_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_jitter(monkeypatch)
    sleep_calls = _capture_sleep(monkeypatch)

    async def returns_429_http_date() -> None:
        exc = TooManyRequestsException(status=429, reason="Too Many Requests")
        exc.headers = {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}
        raise exc

    wrapped = shared._reliability_wrap(returns_429_http_date, retry=True)
    with pytest.raises(RuntimeError, match="Hatchet API error"):
        await wrapped()
    assert sleep_calls == [1.0, 2.0, 4.0]


# * AC-3 — non-idempotent mutating tools (idempotent=False) skip the retry layer
@pytest.mark.spec("v0.2.0/reliability#AC-3")
async def test_non_idempotent_503_surfaces_without_retry(
    server_module: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_jitter(monkeypatch)
    sleep_calls = _capture_sleep(monkeypatch)
    shared._read_only = False
    server.register_mutating_tools(app.mcp)

    counter = {"n": 0}

    async def fake_aio_create(**_kwargs: Any) -> None:
        counter["n"] += 1
        raise ServiceException(status=503, reason="Service Unavailable")

    class _FakeHatchet:
        class runs:
            aio_create = staticmethod(fake_aio_create)

    monkeypatch.setattr("hatchet_mcp.tools.runs.get_hatchet", lambda: _FakeHatchet)

    tool = app.mcp._tool_manager._tools["trigger_workflow"]
    with pytest.raises(RuntimeError, match="Hatchet API error"):
        await tool.fn(workflow_name="x")
    assert counter["n"] == 1
    assert sleep_calls == []


@pytest.mark.spec("v0.2.0/reliability#AC-3")
async def test_idempotent_mutation_503_retries(
    server_module: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_jitter(monkeypatch)
    sleep_calls = _capture_sleep(monkeypatch)
    shared._read_only = False
    server.register_mutating_tools(app.mcp)

    counter = {"n": 0}

    async def fake_rest_call(_call: Any) -> None:
        counter["n"] += 1
        raise ServiceException(status=503, reason="Service Unavailable")

    monkeypatch.setattr("hatchet_mcp.tools.workflows._rest_call", fake_rest_call)

    tool = app.mcp._tool_manager._tools["pause_workflow"]
    with pytest.raises(RuntimeError, match="Hatchet API error"):
        await tool.fn(workflow_id="wf1")
    assert counter["n"] == 4
    assert sleep_calls == [1.0, 2.0, 4.0]


@pytest.mark.spec("v0.2.0/reliability#AC-3")
def test_mutating_idempotency_split_matches_catalog() -> None:
    # Pin the non-idempotent set so a future catalog edit cannot silently flip a tool into the
    # retry layer. These five are the destructive operations the ADR §1 explicitly excludes.
    non_idempotent = {
        name for _, name, _, ann in server.MUTATING_TOOLS if not ann.idempotentHint
    }
    create_or_trigger = {
        "trigger_workflow",
        "push_event",
        "restore_task",
        "cancel_runs",
        "replay_runs",
        "create_cron",
        "create_scheduled",
        "create_filter",
    }
    assert create_or_trigger.issubset(non_idempotent)


# * AC-4 — 30s deadline cancels a hung Hatchet call
@pytest.mark.spec("v0.2.0/reliability#AC-4")
async def test_deadline_surfaces_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shared, "_PER_CALL_TIMEOUT_S", 0.05)

    async def hang() -> None:
        await asyncio.Event().wait()

    wrapped = shared._reliability_wrap(hang, retry=False)
    with pytest.raises(asyncio.TimeoutError) as excinfo:
        await wrapped()
    # The wrapper rewrites the TimeoutError args with a meaningful message naming the tool
    # and the deadline, so the MCP JSON-RPC error channel doesn't surface an empty string.
    assert "hang" in str(excinfo.value)
    assert "0.05" in str(excinfo.value)


@pytest.mark.spec("v0.2.0/reliability#AC-4")
async def test_deadline_applies_to_non_idempotent_tools_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Decision 2 covers every tool — non-idempotent mutations get the deadline, just not retry.
    monkeypatch.setattr(shared, "_PER_CALL_TIMEOUT_S", 0.05)

    async def hang() -> None:
        await asyncio.Event().wait()

    wrapped = shared._reliability_wrap(hang, retry=False)
    with pytest.raises(asyncio.TimeoutError):
        await wrapped()


# * Regression — functools.wraps must keep fn's signature visible through inspect.signature
# so FastMCP's func_metadata can build the same arg model as if there were no wrap (otherwise
# every tool's input schema collapses to **kwargs — a silent disaster at register time).
def test_wrapper_preserves_signature_for_fastmcp_introspection() -> None:
    async def my_handler(
        workflow_id: Annotated[str, Field(description="The workflow ID.")],
        limit: Annotated[int | None, Field(description="Max items.")] = None,
        until: Annotated[str | None, Field(description="Upper bound.")] = None,
    ) -> dict[str, Any]:
        return {"workflow_id": workflow_id}

    wrapped = shared._reliability_wrap(my_handler, retry=True)

    sig = inspect.signature(wrapped, eval_str=True)
    assert list(sig.parameters) == ["workflow_id", "limit", "until"]
    # Defaults are preserved (FastMCP reads these to mark params as optional in the schema).
    assert sig.parameters["limit"].default is None
    assert sig.parameters["until"].default is None
    # Type hints survive — pydantic's create_model in FastMCP relies on them for the arg model.
    assert wrapped.__wrapped__ is my_handler  # type: ignore[attr-defined]
    hints = my_handler.__annotations__
    assert wrapped.__annotations__ == hints
