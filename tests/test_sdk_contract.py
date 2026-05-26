"""SDK contract tests.

We hard-code SDK Pydantic model alias names in a few places (the minimal_output
projection on list_runs, the drop list on list_events). When the SDK renames a field
in a minor bump, set-based filters silently drop nothing and the projection becomes
useless — no exception, no test failure. These tests pin every hard-coded alias to
the live SDK schema so the rename surfaces as a real test failure.
"""

from hatchet_sdk.clients.rest.models.v1_event import V1Event
from hatchet_sdk.clients.rest.models.v1_task_summary import V1TaskSummary

from hatchet_mcp.tools.runs import _RUN_SUMMARY_FIELDS

# Drop list lives inline in tools/events.py:list_events; redeclare here so a rename
# in either side fails this test loudly.
_EVENT_MINIMAL_DROPS = frozenset({"payload", "triggeredRuns", "additionalMetadata"})


def _aliases_of(model_cls: type) -> set[str]:
    """Return the camelCase aliases (preferred) or field names exposed by a Pydantic model."""
    return {(info.alias or name) for name, info in model_cls.model_fields.items()}


def test_run_summary_fields_exist_on_v1_task_summary():
    """_RUN_SUMMARY_FIELDS must match aliases on V1TaskSummary — SDK rename → test fails."""
    aliases = _aliases_of(V1TaskSummary)
    missing = _RUN_SUMMARY_FIELDS - aliases
    assert not missing, (
        f"SDK rename broke _RUN_SUMMARY_FIELDS — {missing!r} no longer on V1TaskSummary. "
        f"Available aliases include: {sorted(aliases)!r}"
    )


def test_event_minimal_drop_fields_exist_on_v1_event():
    """list_events minimal_output drops three fields by alias — SDK rename → test fails."""
    aliases = _aliases_of(V1Event)
    missing = _EVENT_MINIMAL_DROPS - aliases
    assert not missing, (
        f"SDK rename broke list_events drop set — {missing!r} no longer on V1Event. "
        f"Available aliases include: {sorted(aliases)!r}"
    )
