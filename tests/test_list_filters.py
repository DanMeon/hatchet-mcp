"""Passthrough of SDK list-filter options on list_runs and list_scheduled.

The SDK exposes parent/event/order_by filters that the MCP tools forward verbatim.
These tests pin that the kwargs reach the SDK call with the right types (raw strings
for ID filters, parsed enum members for order_by).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from hatchet_sdk.clients.rest.models.scheduled_workflows_order_by_field import (
    ScheduledWorkflowsOrderByField,
)
from hatchet_sdk.clients.rest.models.workflow_run_order_by_direction import (
    WorkflowRunOrderByDirection,
)
from pydantic import BaseModel, Field

import hatchet_mcp.tools.runs as runs
import hatchet_mcp.tools.schedules as schedules


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


# * list_scheduled — new passthrough + ordering filters


async def test_list_scheduled_forwards_parent_workflow_run_id(monkeypatch):
    hatchet = MagicMock()
    hatchet.scheduled.aio_list = AsyncMock(return_value=_Rows())
    monkeypatch.setattr(schedules, "get_hatchet", lambda: hatchet)

    await schedules.list_scheduled(parent_workflow_run_id="parent-run-9")

    kwargs = hatchet.scheduled.aio_list.call_args.kwargs
    assert kwargs["parent_workflow_run_id"] == "parent-run-9"
    assert kwargs["order_by_field"] is None
    assert kwargs["order_by_direction"] is None


async def test_list_scheduled_parses_order_by_enums(monkeypatch):
    hatchet = MagicMock()
    hatchet.scheduled.aio_list = AsyncMock(return_value=_Rows())
    monkeypatch.setattr(schedules, "get_hatchet", lambda: hatchet)

    await schedules.list_scheduled(
        order_by_field="triggerAt", order_by_direction="DESC"
    )

    kwargs = hatchet.scheduled.aio_list.call_args.kwargs
    assert kwargs["order_by_field"] is ScheduledWorkflowsOrderByField.TRIGGERAT
    assert kwargs["order_by_direction"] is WorkflowRunOrderByDirection.DESC


async def test_list_scheduled_rejects_invalid_order_by_field(monkeypatch):
    hatchet = MagicMock()
    hatchet.scheduled.aio_list = AsyncMock(return_value=_Rows())
    monkeypatch.setattr(schedules, "get_hatchet", lambda: hatchet)

    with pytest.raises(ValueError, match="order_by_field"):
        await schedules.list_scheduled(order_by_field="bogus")


async def test_list_scheduled_rejects_invalid_order_by_direction(monkeypatch):
    hatchet = MagicMock()
    hatchet.scheduled.aio_list = AsyncMock(return_value=_Rows())
    monkeypatch.setattr(schedules, "get_hatchet", lambda: hatchet)

    with pytest.raises(ValueError, match="order_by_direction"):
        await schedules.list_scheduled(order_by_direction="sideways")


@pytest.mark.parametrize("wrong_case", ["triggerat", "TRIGGERAT", "TriggerAt"])
async def test_list_scheduled_order_by_field_is_case_sensitive(monkeypatch, wrong_case):
    """Pin the contract: order_by_field is exact-case 'triggerAt' / 'createdAt'.

    A future PR that lowercases or normalizes the input would silently change behavior
    for clients already passing the exact SDK enum value — break loudly instead.
    """
    hatchet = MagicMock()
    hatchet.scheduled.aio_list = AsyncMock(return_value=_Rows())
    monkeypatch.setattr(schedules, "get_hatchet", lambda: hatchet)

    with pytest.raises(ValueError, match="order_by_field"):
        await schedules.list_scheduled(order_by_field=wrong_case)
