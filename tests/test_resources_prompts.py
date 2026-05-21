"""Read-only resources and operator prompts: registration, no template collision, delegation."""

from unittest.mock import AsyncMock, MagicMock

from mcp.types import TextContent
from pydantic import BaseModel, Field

import hatchet_mcp.app as app
import hatchet_mcp.tools.workflows as workflows


class _Aliased(BaseModel):
    name: str = Field(alias="workflowName")


async def test_static_resources_registered():
    uris = {str(r.uri) for r in await app.mcp.list_resources()}
    assert "hatchet://workflows" in uris
    assert "hatchet://workers" in uris


async def test_resource_templates_registered():
    templates = {t.uriTemplate for t in await app.mcp.list_resource_templates()}
    assert "hatchet://workflows/{workflow_id}" in templates
    assert "hatchet://runs/{workflow_run_id}" in templates
    assert "hatchet://runs/{workflow_run_id}/status" in templates


def test_run_templates_do_not_collide():
    internal = list(app.mcp._resource_manager._templates.values())
    run_hits = [
        t.uri_template for t in internal if t.matches("hatchet://runs/abc") is not None
    ]
    status_hits = [
        t.uri_template
        for t in internal
        if t.matches("hatchet://runs/abc/status") is not None
    ]
    assert run_hits == ["hatchet://runs/{workflow_run_id}"]
    assert status_hits == ["hatchet://runs/{workflow_run_id}/status"]


async def test_resource_delegates_with_by_alias(monkeypatch):
    hatchet = MagicMock()
    hatchet.workflows.aio_get = AsyncMock(return_value=_Aliased(workflowName="wf"))
    monkeypatch.setattr(workflows, "get_hatchet", lambda: hatchet)

    contents = await app.mcp.read_resource("hatchet://workflows/wf1")
    body = list(contents)[0].content

    assert body == '{"workflowName": "wf"}'
    hatchet.workflows.aio_get.assert_awaited_once_with("wf1")


async def test_prompts_registered():
    names = {p.name for p in await app.mcp.list_prompts()}
    assert {"triage_failed_runs", "debug_run", "tenant_health"} <= names


async def test_debug_run_prompt_includes_run_id():
    result = await app.mcp.get_prompt("debug_run", {"workflow_run_id": "RUN-1"})
    content = result.messages[0].content
    assert isinstance(content, TextContent)
    assert "RUN-1" in content.text
    assert "get_run" in content.text
