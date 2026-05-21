"""Reusable operator prompts that orchestrate the read tools for common workflows.

They add no mutating surface — each explicitly instructs against mutation. ``register`` is
called from server/main (and from the test harness).
"""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field


def prompt_triage_failed_runs(
    hours: Annotated[str, Field(description="Look-back window in hours.")] = "24",
) -> str:
    return (
        f"Triage Hatchet workflow runs that FAILED in the last {hours} hours.\n\n"
        "Steps:\n"
        f'1. Call list_runs with statuses=["FAILED"] and `since` set to {hours} hours ago '
        "(ISO 8601, UTC).\n"
        "2. Group the failures by workflow to find the biggest offenders.\n"
        "3. For the most significant failures, call get_run for the task tree and "
        "get_task_logs for the failing task's error output; use get_trace if deeper "
        "context is needed.\n"
        "4. Summarize which workflows are failing, the common error signatures, and a "
        "recommended next action. Do not trigger, cancel, replay, or mutate anything."
    )


def prompt_debug_run(
    workflow_run_id: Annotated[
        str, Field(description="The workflow run external ID (UUID) to debug.")
    ],
) -> str:
    return (
        f"Debug Hatchet workflow run {workflow_run_id}.\n\n"
        "Steps:\n"
        f"1. Call get_run for {workflow_run_id} to see the task tree, inputs, and which "
        "task(s) failed or stalled.\n"
        f"2. Call get_run_timings for {workflow_run_id} to spot slow or stuck tasks in the "
        "waterfall.\n"
        "3. For each failing task, call get_task_logs to read its error output.\n"
        f"4. If the cause is still unclear, call get_trace for {workflow_run_id} to inspect "
        "the OpenTelemetry spans.\n"
        "5. Report the root cause and a recommended fix. Do not mutate anything."
    )


def prompt_tenant_health(
    hours: Annotated[
        str, Field(description="Look-back window in hours for task metrics.")
    ] = "24",
) -> str:
    return (
        "Assess the operational health of this Hatchet tenant.\n\n"
        "Steps:\n"
        "1. Call get_queue_metrics to see per-queue backlog depth.\n"
        f"2. Call get_task_metrics over the last {hours} hours for task counts by status "
        "(watch the failed/cancelled share).\n"
        "3. Call list_workers to check how many workers are active and their free slots.\n"
        "4. Summarize backlog, failure rate, and worker capacity, and flag anything that "
        "needs attention. Do not mutate anything."
    )


def register(mcp: FastMCP) -> None:
    """Register every operator prompt on the given server."""
    mcp.prompt(
        name="triage_failed_runs",
        description="Investigate workflow runs that failed recently and summarize likely causes.",
    )(prompt_triage_failed_runs)
    mcp.prompt(
        name="debug_run",
        description="Walk through diagnosing a single workflow run by ID.",
    )(prompt_debug_run)
    mcp.prompt(
        name="tenant_health",
        description="Summarize the operational health of the tenant from metrics and workers.",
    )(prompt_tenant_health)
