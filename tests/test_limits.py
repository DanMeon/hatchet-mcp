"""List-limit clamping, the result-size guard, and the payload-off default for list_runs."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

import hatchet_mcp.tools.runs as runs
from hatchet_mcp._shared import (
    _DEFAULT_LIST_LIMIT,
    _MAX_LIST_LIMIT,
    _MAX_RESULT_BYTES,
    _clamp_limit,
    _dump,
    _dump_item,
    _guard_size,
)


class _Rows(BaseModel):
    rows: list[str] = []


class _Blob(BaseModel):
    blob: str = ""


def test_clamp_limit_none_uses_default():
    assert _clamp_limit(None) == _DEFAULT_LIST_LIMIT


def test_clamp_limit_passes_through_in_range():
    assert _clamp_limit(25) == 25


def test_clamp_limit_caps_above_max():
    assert _clamp_limit(10_000) == _MAX_LIST_LIMIT


def test_clamp_limit_rejects_below_one():
    with pytest.raises(ValueError, match="limit must be"):
        _clamp_limit(0)


def test_clamp_limit_custom_default_and_cap():
    assert _clamp_limit(None, default=1000, cap=1000) == 1000
    assert _clamp_limit(5000, default=1000, cap=1000) == 1000


def test_guard_size_allows_small_result():
    data = {"rows": [{"id": "x"}]}
    assert _guard_size(data) is data


def test_guard_size_rejects_oversized_result():
    rows = [{"v": "x" * 1024} for _ in range(_MAX_RESULT_BYTES // 1024 + 50)]
    with pytest.raises(RuntimeError, match="overflow the client context"):
        _guard_size({"rows": rows})


def test_dump_item_skips_size_guard_for_single_item():
    big = _Blob(blob="x" * (_MAX_RESULT_BYTES + 1000))
    out = _dump_item(big)
    assert len(out["blob"]) > _MAX_RESULT_BYTES


def test_dump_applies_size_guard_for_lists():
    big = _Blob(blob="x" * (_MAX_RESULT_BYTES + 1000))
    with pytest.raises(RuntimeError, match="overflow the client context"):
        _dump(big)


async def test_list_runs_excludes_payloads_and_clamps_limit_by_default(monkeypatch):
    hatchet = MagicMock()
    hatchet.runs.aio_list = AsyncMock(return_value=_Rows())
    monkeypatch.setattr(runs, "get_hatchet", lambda: hatchet)

    await runs.list_runs()

    kwargs = hatchet.runs.aio_list.call_args.kwargs
    assert kwargs["include_payloads"] is False
    assert kwargs["limit"] == _DEFAULT_LIST_LIMIT


async def test_list_runs_caps_oversized_limit_and_honors_explicit_payloads(monkeypatch):
    hatchet = MagicMock()
    hatchet.runs.aio_list = AsyncMock(return_value=_Rows())
    monkeypatch.setattr(runs, "get_hatchet", lambda: hatchet)

    await runs.list_runs(limit=10_000, include_payloads=True)

    kwargs = hatchet.runs.aio_list.call_args.kwargs
    assert kwargs["limit"] == _MAX_LIST_LIMIT
    assert kwargs["include_payloads"] is True
