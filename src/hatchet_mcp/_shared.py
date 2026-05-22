"""Shared internal helpers for the tool/resource/prompt modules.

Serialization (with a result-size guard), input parsers, the low-level REST bridge, the
list-limit clamp, and the mutation gate. Tool modules import from here rather than from
``app`` so they stay independent of the ``FastMCP`` instance; this also keeps the import
graph acyclic (``server`` → tools → ``_shared``; ``app`` holds only the app instance).
"""

import asyncio
import functools
import json
import random
import time
from collections.abc import Callable
from datetime import datetime, timezone
from enum import Enum
from typing import Any, TypeVar

from hatchet_sdk.clients.rest.api_client import ApiClient
from hatchet_sdk.clients.rest.exceptions import ApiException, RestTransportError
from hatchet_sdk.clients.rest.models.v1_task_status import V1TaskStatus
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from hatchet_mcp._logging import emit
from hatchet_mcp.client import get_rest
from hatchet_mcp.config import redact

# * List limits and result-size guard
# List endpoints have no server-side cap, and a tool result that overflows the client's
# context is unrecoverable, so the server caps both: a default/max on each list tool's limit,
# and a byte ceiling on every serialized list result (defense-in-depth for tools like
# list_workers whose SDK call takes no limit). Single-item get_* use _dump_item (no guard).
_DEFAULT_LIST_LIMIT = 50
_MAX_LIST_LIMIT = 100
_MAX_RESULT_BYTES = 500_000


def _clamp_limit(
    limit: int | None, *, default: int = _DEFAULT_LIST_LIMIT, cap: int = _MAX_LIST_LIMIT
) -> int:
    """Resolve a list tool's limit: None becomes the default, anything above the cap is capped."""
    if limit is None:
        return default
    if limit < 1:
        raise ValueError(f"limit must be >= 1; got {limit!r}")
    return min(limit, cap)


def _guard_size(data: dict[str, Any]) -> dict[str, Any]:
    """Reject a result large enough to overflow the client context, with guidance to narrow it."""
    size = len(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    if size > _MAX_RESULT_BYTES:
        raise RuntimeError(
            f"Result is {size:,} bytes, over the {_MAX_RESULT_BYTES:,}-byte cap that would "
            "overflow the client context. Narrow it with a smaller limit and tighter filters "
            "(time window / statuses); for list_runs keep include_payloads=false (the default)."
        )
    return data


def _dump_item(model: BaseModel) -> dict[str, Any]:
    """Serialize a single-item detail response in the Hatchet API shape, with no size guard.

    A get_* on one object should return it whole — there is no narrowing knob to recover from
    a hard cap. List tools use _dump, which guards, because they can be narrowed (see _clamp_limit).
    """
    return model.model_dump(mode="json", by_alias=True)


def _dump(model: BaseModel) -> dict[str, Any]:
    """Serialize a list/multi-item response in the Hatchet API shape and guard its size."""
    return _guard_size(_dump_item(model))


def _api_error(exc: ApiException) -> RuntimeError:
    """Turn an SDK REST exception into a concise, token-free error for the MCP client."""
    parts: list[str] = []
    if exc.status is not None:
        parts.append(f"status {exc.status}")
    if exc.reason:
        parts.append(str(exc.reason))
    header = "Hatchet API error" + (f": {', '.join(parts)}" if parts else "")
    body = exc.body or exc.data
    detail = f" — {str(body)[:500]}" if body else ""
    return RuntimeError(redact(header + detail))


def _parse_dt(value: str | None, *, field: str) -> datetime | None:
    """Parse an ISO 8601 string into a timezone-aware datetime (assumes UTC if naive)."""
    if value is None or not value.strip():
        return None

    raw = value.strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        raise ValueError(
            f"{field} must be an ISO 8601 datetime "
            f"(e.g. '2026-05-19T00:00:00Z'); got {value!r}"
        ) from None

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_statuses(values: list[str] | None) -> list[V1TaskStatus] | None:
    """Validate run-status strings against the v1 enum, raising on unknown values."""
    if not values:
        return None

    parsed: list[V1TaskStatus] = []
    for value in values:
        try:
            parsed.append(V1TaskStatus(value))
        except ValueError:
            allowed = [s.value for s in V1TaskStatus]
            raise ValueError(
                f"Invalid run status {value!r}. Allowed (v1): {allowed}"
            ) from None
    return parsed


_EnumT = TypeVar("_EnumT", bound=Enum)
_T = TypeVar("_T")


def _parse_enum_list(
    values: list[str] | None, enum_cls: type[_EnumT], *, field: str
) -> list[_EnumT] | None:
    """Validate string values against a (str) enum, raising on any unknown value."""
    if not values:
        return None

    parsed: list[_EnumT] = []
    for value in values:
        try:
            parsed.append(enum_cls(value))
        except ValueError:
            allowed = [getattr(member, "value", member) for member in enum_cls]
            raise ValueError(f"Invalid {field} {value!r}. Allowed: {allowed}") from None
    return parsed


def _parse_enum(
    value: str | None, enum_cls: type[_EnumT], *, field: str
) -> _EnumT | None:
    """Validate a single string against a (str) enum, raising on unknown."""
    if value is None or not value.strip():
        return None
    try:
        return enum_cls(value)
    except ValueError:
        allowed = [getattr(member, "value", member) for member in enum_cls]
        raise ValueError(f"Invalid {field} {value!r}. Allowed: {allowed}") from None


async def _rest_call(call: Callable[[ApiClient, str], _T]) -> _T:
    """Invoke a low-level (synchronous) REST API method off the event loop.

    A handful of reads — v1 events, OTel traces, run timings — have no
    ``aio_*`` feature method, so they call the generated API classes directly. The
    ``ApiClient`` context manager is entered inside the worker thread, mirroring how
    the SDK's own feature clients wrap their sync calls in ``asyncio.to_thread``. The
    callable receives the open client and the tenant ID.
    """
    base = get_rest()

    def _invoke() -> _T:
        with base.client() as client:
            return call(client, base.tenant_id)

    return await asyncio.to_thread(_invoke)


# * Mutation gate
# `_read_only` mirrors config.read_only and is set in main() before serving. Mutating tools
# are registered only when it is False (see server.register_mutating_tools), so they are
# invisible by default; the per-handler `_require_writable()` is defense-in-depth in case a
# handler is reached anyway.
_read_only = True


def _require_writable() -> None:
    """Raise if mutation is disabled. A redundant guard — these tools aren't registered in read-only mode."""
    if _read_only:
        raise RuntimeError(
            "This tool mutates Hatchet state and is disabled in read-only mode. "
            "Restart the server with HATCHET_MCP_READ_ONLY=false to enable mutating tools."
        )


def _destructive(*, idempotent: bool) -> ToolAnnotations:
    """Annotations marking a tool as a non-read-only, destructive mutation so clients can prompt for approval."""
    return ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=idempotent
    )


# * Reliability — retry + per-call deadline
# Every registered tool goes through `_reliability_wrap`. The 30s deadline is always on; the
# retry loop runs only when `retry=True` (set by `register_read_tools` always, by
# `register_mutating_tools` based on `annotations.idempotentHint`). Retryable errors:
# RestTransportError, 429, 5xx. Everything else surfaces on the first attempt. The retry
# budget (~7s with jitter) sits inside the deadline so wall-clock per call is capped at 30s.
_PER_CALL_TIMEOUT_S = 30.0
# ^ 4 attempts (1 initial + 3 retries); 3 sleeps total. Spec body says "3 attempts, 1s/2s/4s",
# which we treat as "3 retries after the first attempt" — matches ADR §1's 1s+2s+4s ≈ 7s budget.
_RETRY_BACKOFFS_S: tuple[float, ...] = (1.0, 2.0, 4.0)
_BACKOFF_JITTER = 0.25
_RETRY_AFTER_CAP_S = 10.0


def _is_retryable(exc: BaseException) -> bool:
    """5xx + 429 + transport-level errors retry; 4xx (auth/not-found/conflict) surface immediately."""
    if isinstance(exc, RestTransportError):
        return True
    if isinstance(exc, ApiException):
        status = exc.status
        if status is None:
            return False
        return status == 429 or 500 <= status <= 599
    return False


def _retry_after_seconds(exc: ApiException) -> float | None:
    """Pull integer-seconds `Retry-After` from a 429, clamped to 10s. HTTP-date format is ignored."""
    headers = getattr(exc, "headers", None)
    if not headers:
        return None
    raw: Any = None
    if hasattr(headers, "get"):
        raw = headers.get("Retry-After") or headers.get("retry-after")
    if raw is None:
        return None
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return None
    return min(max(seconds, 0.0), _RETRY_AFTER_CAP_S)


def _reliability_wrap(fn: Callable[..., Any], *, retry: bool) -> Callable[..., Any]:
    """Wrap `fn` with a 30s deadline, optional retry, and a single structured stderr record per invocation.

    Owns three concerns wrapped around every tool call: (1) `asyncio.wait_for` per-call
    deadline, (2) idempotent retry loop (when `retry=True`), (3) one ``tool.ok`` or
    ``tool.error`` JSON-line record emitted on stderr (AC-5 — including failures from
    input-validation helpers like `_parse_dt` / `_parse_statuses` that raise before any
    Hatchet call, because the timer starts at wrapper entry). Also owns the
    ApiException -> RuntimeError translation that handlers used to do inline, so the
    retry loop sees the raw SDK exception and only the final survivor is run through
    `_api_error` (which redacts + caps the message). `functools.wraps` propagates fn's
    `__wrapped__`, `__name__`, `__annotations__`, so FastMCP's
    `inspect.signature(fn, eval_str=True)` introspection sees the original parameters
    and the generated arg model is byte-identical to wrapping nothing.
    """
    tool_name = fn.__name__

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        async def _attempts() -> Any:
            if not retry:
                return await fn(*args, **kwargs)
            last: BaseException | None = None
            for attempt in range(len(_RETRY_BACKOFFS_S) + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    if not _is_retryable(exc):
                        raise
                    last = exc
                    if attempt == len(_RETRY_BACKOFFS_S):
                        break
                    base = _RETRY_BACKOFFS_S[attempt]
                    if isinstance(exc, ApiException) and exc.status == 429:
                        ra = _retry_after_seconds(exc)
                        if ra is not None:
                            base = max(base, ra)
                    delay = base * random.uniform(
                        1 - _BACKOFF_JITTER, 1 + _BACKOFF_JITTER
                    )
                    await asyncio.sleep(max(0.0, delay))
            assert last is not None
            raise last

        start = time.perf_counter()
        try:
            try:
                result = await asyncio.wait_for(
                    _attempts(), timeout=_PER_CALL_TIMEOUT_S
                )
            except ApiException as exc:
                raise _api_error(exc) from None
        except BaseException as exc:
            # asyncio.TimeoutError carries no message; build a meaningful one so the
            # tool.error record and the MCP JSON-RPC channel both name what timed out.
            if isinstance(exc, asyncio.TimeoutError) and not str(exc):
                msg = f"tool {tool_name!r} exceeded {_PER_CALL_TIMEOUT_S}s deadline"
            else:
                msg = f"{type(exc).__name__}: {exc}"
            redacted_msg = redact(msg)
            emit(
                "tool.error",
                tool=tool_name,
                duration_ms=int((time.perf_counter() - start) * 1000),
                redacted_error=redacted_msg,
            )
            # Defense-in-depth scrub for the MCP JSON-RPC channel. ApiException-derived already
            # passed through `_api_error` (redacted RuntimeError), so skip that path; for everything
            # else, write the redacted message into the exception's args so re-raise carries no raw
            # token. TimeoutError has empty args by default — fill it with our meaningful message.
            if not isinstance(exc, RuntimeError):
                try:
                    if isinstance(exc, asyncio.TimeoutError) and not exc.args:
                        exc.args = (redacted_msg,)
                    elif (
                        exc.args
                        and isinstance(exc.args[0], str)
                        and redact(exc.args[0]) != exc.args[0]
                    ):
                        exc.args = (redact(exc.args[0]), *exc.args[1:])
                except (AttributeError, TypeError):
                    pass  # ^ A few exception classes lock .args; leaving them alone is safe.
            raise
        emit(
            "tool.ok",
            tool=tool_name,
            duration_ms=int((time.perf_counter() - start) * 1000),
        )
        return result

    return wrapper
