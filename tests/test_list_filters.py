"""Passthrough of SDK list-filter options on list_runs, list_crons, list_scheduled,
list_events, and list_rate_limits.

The SDK exposes parent/event/order_by/scope filters that the MCP tools forward verbatim.
These tests pin that the kwargs reach the SDK (or REST) call with the right types (raw
strings/lists for ID/scope filters, parsed enum members for order_by).
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from hatchet_sdk.clients.rest.models.cron_workflows_order_by_field import (
    CronWorkflowsOrderByField,
)
from hatchet_sdk.clients.rest.models.rate_limit_order_by_direction import (
    RateLimitOrderByDirection,
)
from hatchet_sdk.clients.rest.models.rate_limit_order_by_field import (
    RateLimitOrderByField,
)
from hatchet_sdk.clients.rest.models.scheduled_workflows_order_by_field import (
    ScheduledWorkflowsOrderByField,
)
from hatchet_sdk.clients.rest.models.workflow_run_order_by_direction import (
    WorkflowRunOrderByDirection,
)
from pydantic import BaseModel, Field

import hatchet_mcp.tools.events as events
import hatchet_mcp.tools.observability as observability
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


# * list_crons — ordering filters


async def test_list_crons_parses_order_by_enums(monkeypatch):
    hatchet = MagicMock()
    hatchet.cron.aio_list = AsyncMock(return_value=_Rows())
    monkeypatch.setattr(schedules, "get_hatchet", lambda: hatchet)

    await schedules.list_crons(order_by_field="name", order_by_direction="ASC")

    kwargs = hatchet.cron.aio_list.call_args.kwargs
    assert kwargs["order_by_field"] is CronWorkflowsOrderByField.NAME
    assert kwargs["order_by_direction"] is WorkflowRunOrderByDirection.ASC


async def test_list_crons_omits_order_by_by_default(monkeypatch):
    hatchet = MagicMock()
    hatchet.cron.aio_list = AsyncMock(return_value=_Rows())
    monkeypatch.setattr(schedules, "get_hatchet", lambda: hatchet)

    await schedules.list_crons()

    kwargs = hatchet.cron.aio_list.call_args.kwargs
    assert kwargs["order_by_field"] is None
    assert kwargs["order_by_direction"] is None


async def test_list_crons_rejects_invalid_order_by_field(monkeypatch):
    hatchet = MagicMock()
    hatchet.cron.aio_list = AsyncMock(return_value=_Rows())
    monkeypatch.setattr(schedules, "get_hatchet", lambda: hatchet)

    with pytest.raises(ValueError, match="order_by_field"):
        await schedules.list_crons(order_by_field="bogus")


# * list_events — event_ids + scopes


def _patch_rest_call_with_event_api(monkeypatch, api):
    """Replace EventApi(client) with a fixed instance, and inline _rest_call.

    The handler builds `lambda client, tenant: EventApi(client).v1_event_list(...)` and
    passes it to `_rest_call`. To capture the kwargs, we patch `_rest_call` to invoke
    the lambda synchronously with stub client/tenant, and patch `EventApi` so it returns
    our captured mock instance.
    """
    monkeypatch.setattr(events, "EventApi", lambda _client: api)

    async def fake_rest_call(call: Any) -> Any:
        return call(object(), "tenant-id")

    monkeypatch.setattr(events, "_rest_call", fake_rest_call)


async def test_list_events_forwards_event_ids_and_scopes(monkeypatch):
    api = MagicMock()
    api.v1_event_list = MagicMock(return_value=_Rows())
    _patch_rest_call_with_event_api(monkeypatch, api)

    await events.list_events(event_ids=["evt-1", "evt-2"], scopes=["scope-a"])

    kwargs = api.v1_event_list.call_args.kwargs
    assert kwargs["event_ids"] == ["evt-1", "evt-2"]
    assert kwargs["scopes"] == ["scope-a"]


async def test_list_events_omits_event_ids_and_scopes_by_default(monkeypatch):
    api = MagicMock()
    api.v1_event_list = MagicMock(return_value=_Rows())
    _patch_rest_call_with_event_api(monkeypatch, api)

    await events.list_events()

    kwargs = api.v1_event_list.call_args.kwargs
    assert kwargs["event_ids"] is None
    assert kwargs["scopes"] is None


# * list_rate_limits — ordering filters


async def test_list_rate_limits_parses_order_by_enums(monkeypatch):
    hatchet = MagicMock()
    hatchet.rate_limits.aio_list = AsyncMock(return_value=_Rows())
    monkeypatch.setattr(observability, "get_hatchet", lambda: hatchet)

    await observability.list_rate_limits(
        order_by_field="limitValue", order_by_direction="desc"
    )

    kwargs = hatchet.rate_limits.aio_list.call_args.kwargs
    assert kwargs["order_by_field"] is RateLimitOrderByField.LIMITVALUE
    assert kwargs["order_by_direction"] is RateLimitOrderByDirection.DESC


async def test_list_rate_limits_omits_order_by_by_default(monkeypatch):
    hatchet = MagicMock()
    hatchet.rate_limits.aio_list = AsyncMock(return_value=_Rows())
    monkeypatch.setattr(observability, "get_hatchet", lambda: hatchet)

    await observability.list_rate_limits()

    kwargs = hatchet.rate_limits.aio_list.call_args.kwargs
    assert kwargs["order_by_field"] is None
    assert kwargs["order_by_direction"] is None


async def test_list_rate_limits_rejects_invalid_order_by_direction(monkeypatch):
    hatchet = MagicMock()
    hatchet.rate_limits.aio_list = AsyncMock(return_value=_Rows())
    monkeypatch.setattr(observability, "get_hatchet", lambda: hatchet)

    with pytest.raises(ValueError, match="order_by_direction"):
        await observability.list_rate_limits(order_by_direction="sideways")
