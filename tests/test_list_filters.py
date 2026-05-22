"""Passthrough of SDK list-filter options on list_runs.

These tests pin that filter kwargs reach the SDK call with the right names.
"""

from unittest.mock import AsyncMock, MagicMock

from pydantic import BaseModel, Field

import hatchet_mcp.tools.runs as runs


class _Rows(BaseModel):
    rows: list[str] = Field(default_factory=list)


# * list_runs — new passthrough filters


async def test_list_runs_forwards_parent_task_external_id(monkeypatch):
    hatchet = MagicMock()
    hatchet.runs.aio_list = AsyncMock(return_value=_Rows())
    monkeypatch.setattr(runs, "get_hatchet", lambda: hatchet)

    await runs.list_runs(parent_task_external_id="parent-task-1")

    kwargs = hatchet.runs.aio_list.call_args.kwargs
    assert kwargs["parent_task_external_id"] == "parent-task-1"
    assert kwargs["triggering_event_external_id"] is None


async def test_list_runs_forwards_triggering_event_external_id(monkeypatch):
    hatchet = MagicMock()
    hatchet.runs.aio_list = AsyncMock(return_value=_Rows())
    monkeypatch.setattr(runs, "get_hatchet", lambda: hatchet)

    await runs.list_runs(triggering_event_external_id="event-42")

    kwargs = hatchet.runs.aio_list.call_args.kwargs
    assert kwargs["triggering_event_external_id"] == "event-42"
    assert kwargs["parent_task_external_id"] is None


async def test_list_runs_omits_passthrough_filters_by_default(monkeypatch):
    hatchet = MagicMock()
    hatchet.runs.aio_list = AsyncMock(return_value=_Rows())
    monkeypatch.setattr(runs, "get_hatchet", lambda: hatchet)

    await runs.list_runs()

    kwargs = hatchet.runs.aio_list.call_args.kwargs
    assert kwargs["parent_task_external_id"] is None
    assert kwargs["triggering_event_external_id"] is None
