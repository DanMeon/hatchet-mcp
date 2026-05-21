"""Bulk cancel/replay safety: dry-run default, 500-run cap, single SDK call on execute."""

from unittest.mock import AsyncMock, MagicMock

import pytest

import hatchet_mcp._shared as shared
import hatchet_mcp.tools.runs as runs


@pytest.fixture
def writable(server_module, monkeypatch):
    """Read-write mode with a fully mocked Hatchet client — no network, no real mutation."""
    shared._read_only = False
    hatchet = MagicMock()
    hatchet.runs.aio_bulk_cancel = AsyncMock()
    hatchet.runs.aio_bulk_replay = AsyncMock()
    monkeypatch.setattr(runs, "get_hatchet", lambda: hatchet)
    return hatchet


@pytest.mark.parametrize("action", ["cancel", "replay"])
async def test_dry_run_is_default_and_skips_mutation(writable, action):
    hatchet = writable
    handler = runs.cancel_runs if action == "cancel" else runs.replay_runs

    result = await handler(run_ids=["r1", "r2"])

    assert result["dry_run"] is True
    assert result["executed"] is False
    assert result["matched_count"] == 2
    assert result["run_ids"] == ["r1", "r2"]
    hatchet.runs.aio_bulk_cancel.assert_not_called()
    hatchet.runs.aio_bulk_replay.assert_not_called()


@pytest.mark.parametrize("action", ["cancel", "replay"])
async def test_over_500_cap_is_refused(writable, action):
    hatchet = writable
    handler = runs.cancel_runs if action == "cancel" else runs.replay_runs
    run_ids = [f"r{i}" for i in range(501)]

    with pytest.raises(ValueError, match="500"):
        await handler(run_ids=run_ids, dry_run=False)

    hatchet.runs.aio_bulk_cancel.assert_not_called()
    hatchet.runs.aio_bulk_replay.assert_not_called()


async def test_exactly_500_is_allowed(writable):
    hatchet = writable
    run_ids = [f"r{i}" for i in range(500)]

    result = await runs.cancel_runs(run_ids=run_ids, dry_run=False)

    assert result["executed"] is True
    assert result["matched_count"] == 500
    hatchet.runs.aio_bulk_cancel.assert_called_once()


@pytest.mark.parametrize("action", ["cancel", "replay"])
async def test_execute_calls_sdk_exactly_once(writable, action):
    hatchet = writable
    handler = runs.cancel_runs if action == "cancel" else runs.replay_runs
    sdk = (
        hatchet.runs.aio_bulk_cancel
        if action == "cancel"
        else hatchet.runs.aio_bulk_replay
    )
    other = (
        hatchet.runs.aio_bulk_replay
        if action == "cancel"
        else hatchet.runs.aio_bulk_cancel
    )

    result = await handler(run_ids=["r1"], dry_run=False)

    assert result["executed"] is True
    assert result["dry_run"] is False
    sdk.assert_called_once()
    other.assert_not_called()
    opts = sdk.call_args.args[0]
    assert list(opts.ids) == ["r1"]


async def test_filter_mode_dry_run_returns_matched_ids(writable, monkeypatch):
    hatchet = writable
    resolve = AsyncMock(return_value=["a", "b", "c"])
    monkeypatch.setattr(runs, "_rest_call", resolve)

    result = await runs.cancel_runs(statuses=["FAILED"])

    assert result["dry_run"] is True
    assert result["executed"] is False
    assert result["matched_count"] == 3
    assert result["run_ids"] == ["a", "b", "c"]
    resolve.assert_awaited_once()
    hatchet.runs.aio_bulk_cancel.assert_not_called()


async def test_filter_mode_no_matches(writable, monkeypatch):
    hatchet = writable
    monkeypatch.setattr(runs, "_rest_call", AsyncMock(return_value=[]))

    result = await runs.cancel_runs(statuses=["FAILED"], dry_run=False)

    assert result["executed"] is False
    assert result["matched_count"] == 0
    assert "nothing to do" in result["note"].lower()
    hatchet.runs.aio_bulk_cancel.assert_not_called()


async def test_run_ids_and_filter_are_mutually_exclusive(writable):
    with pytest.raises(ValueError, match="not both"):
        await runs.cancel_runs(run_ids=["r1"], statuses=["FAILED"])


async def test_requires_run_ids_or_filter(writable):
    with pytest.raises(ValueError):
        await runs.cancel_runs()
