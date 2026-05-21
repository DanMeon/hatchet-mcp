"""Input parsers in _shared.py: ISO datetime, v1 status enum, and generic enum-list validation.

These guard LLM/client-supplied strings — datetimes and status names — and must raise on
bad input rather than passing it through, so the boundary behavior is pinned here.
"""

from datetime import timedelta, timezone

import pytest
from hatchet_sdk.clients.rest.models.scheduled_run_status import ScheduledRunStatus
from hatchet_sdk.clients.rest.models.v1_task_status import V1TaskStatus

import hatchet_mcp._shared as shared


# * _parse_dt


@pytest.mark.parametrize("value", [None, "", "   "])
def test_parse_dt_blank_is_none(value):
    assert shared._parse_dt(value, field="since") is None


def test_parse_dt_z_suffix_is_utc():
    dt = shared._parse_dt("2026-05-19T00:00:00Z", field="since")
    assert dt is not None
    assert dt.utcoffset() == timedelta(0)


def test_parse_dt_naive_assumed_utc():
    dt = shared._parse_dt("2026-05-19T00:00:00", field="since")
    assert dt is not None
    assert dt.tzinfo is timezone.utc


def test_parse_dt_preserves_explicit_offset():
    dt = shared._parse_dt("2026-05-19T09:00:00+09:00", field="since")
    assert dt is not None
    assert dt.utcoffset() == timedelta(hours=9)


def test_parse_dt_invalid_raises_with_field():
    with pytest.raises(ValueError, match="since"):
        shared._parse_dt("not-a-date", field="since")


# * _parse_statuses (v1)


@pytest.mark.parametrize("value", [None, []])
def test_parse_statuses_empty_is_none(value):
    assert shared._parse_statuses(value) is None


def test_parse_statuses_valid():
    assert shared._parse_statuses(["RUNNING", "FAILED"]) == [
        V1TaskStatus.RUNNING,
        V1TaskStatus.FAILED,
    ]


def test_parse_statuses_unknown_raises():
    with pytest.raises(ValueError, match="Invalid run status"):
        shared._parse_statuses(["BOGUS"])


# * _parse_enum_list (generic)


@pytest.mark.parametrize("value", [None, []])
def test_parse_enum_list_empty_is_none(value):
    assert (
        shared._parse_enum_list(value, ScheduledRunStatus, field="scheduled status")
        is None
    )


def test_parse_enum_list_valid():
    assert shared._parse_enum_list(
        ["PENDING", "SCHEDULED"], ScheduledRunStatus, field="scheduled status"
    ) == [ScheduledRunStatus.PENDING, ScheduledRunStatus.SCHEDULED]


def test_parse_enum_list_unknown_raises_with_field():
    with pytest.raises(ValueError, match="scheduled status"):
        shared._parse_enum_list(["BOGUS"], ScheduledRunStatus, field="scheduled status")


def test_parse_enum_list_works_with_v1_task_status():
    assert shared._parse_enum_list(["QUEUED"], V1TaskStatus, field="status") == [
        V1TaskStatus.QUEUED
    ]
