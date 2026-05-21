"""Read-only gate: 24 read tools always; 17 mutating only after registration; handlers refuse in read-only."""

import pytest
from mcp.types import ToolAnnotations

import hatchet_mcp._shared as shared
import hatchet_mcp.app as app
import hatchet_mcp.server as server

# (handler name, minimal valid kwargs) for every mutating tool — kept in sync with MUTATING_TOOLS.
_MUTATING_CALLS = [
    ("trigger_workflow", {"workflow_name": "wf"}),
    ("cancel_runs", {"run_ids": ["r1"]}),
    ("replay_runs", {"run_ids": ["r1"]}),
    ("restore_task", {"task_id": "t1"}),
    ("push_event", {"key": "user:created"}),
    ("pause_workflow", {"workflow_id": "wf1"}),
    ("resume_workflow", {"workflow_id": "wf1"}),
    ("pause_worker", {"worker_id": "wk1"}),
    ("resume_worker", {"worker_id": "wk1"}),
    ("create_cron", {"workflow_name": "wf", "cron_name": "c", "expression": "@daily"}),
    ("delete_cron", {"cron_id": "c1"}),
    ("create_scheduled", {"workflow_name": "wf", "trigger_at": "2026-05-21T09:00:00Z"}),
    ("delete_scheduled", {"scheduled_id": "s1"}),
    ("reschedule", {"scheduled_id": "s1", "trigger_at": "2026-05-21T09:00:00Z"}),
    ("create_filter", {"workflow_id": "wf1", "expression": "true", "scope": "s"}),
    ("update_filter", {"filter_id": "f1"}),
    ("delete_filter", {"filter_id": "f1"}),
]

_FN_BY_NAME = {name: fn for fn, name, _, _ in server.MUTATING_TOOLS}


def _tool_names():
    return {t.name for t in app.mcp._tool_manager.list_tools()}


def _mutating_names():
    return {name for _, name, _, _ in server.MUTATING_TOOLS}


def test_read_only_registers_exactly_24(server_module):
    names = _tool_names()
    assert len(names) == 24
    assert names.isdisjoint(_mutating_names())


def test_read_write_registers_all_41(server_module):
    server.register_mutating_tools(app.mcp)
    names = _tool_names()
    assert len(names) == 41
    assert _mutating_names().issubset(names)


def test_mutating_catalog_has_17_unique():
    names = [name for _, name, _, _ in server.MUTATING_TOOLS]
    assert len(names) == 17
    assert len(set(names)) == 17


def test_register_marks_every_mutating_tool_destructive(server_module, monkeypatch):
    captured: list[tuple[str, ToolAnnotations]] = []

    def fake_add_tool(fn, name, description, annotations):
        captured.append((name, annotations))

    monkeypatch.setattr(app.mcp, "add_tool", fake_add_tool)
    server.register_mutating_tools(app.mcp)

    assert len(captured) == 17
    for _name, ann in captured:
        assert ann.readOnlyHint is False
        assert ann.destructiveHint is True


def test_mutating_calls_cover_catalog():
    covered = {name for name, _ in _MUTATING_CALLS}
    assert covered == _mutating_names()


@pytest.mark.parametrize(("fn_name", "kwargs"), _MUTATING_CALLS)
async def test_mutating_handler_refuses_in_read_only(server_module, fn_name, kwargs):
    shared._read_only = True
    handler = _FN_BY_NAME[fn_name]
    with pytest.raises(RuntimeError) as excinfo:
        await handler(**kwargs)
    assert "read-only" in str(excinfo.value).lower()
