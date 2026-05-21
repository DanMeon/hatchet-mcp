"""Diagnostics surface: get_server_info read tool + hatchet://server/info resource share one builder."""

import json
import re
from typing import Any

import pytest

import hatchet_mcp._shared as shared
from hatchet_mcp.resources import resource_server_info
from hatchet_mcp.tools.server_info import get_server_info

pytestmark = pytest.mark.spec("v0.2.0/reliability")


_PAYLOAD_KEYS = {
    "read_only",
    "read_tool_count",
    "mutating_tool_count",
    "server_url_source",
    "hatchet_sdk_version",
    "python_version",
}


# * AC-7 — tool returns exactly the documented schema, never the token
@pytest.mark.spec("v0.2.0/reliability#AC-7")
async def test_payload_has_exact_keys() -> None:
    info = await get_server_info()
    assert set(info.keys()) == _PAYLOAD_KEYS


@pytest.mark.spec("v0.2.0/reliability#AC-7")
async def test_payload_never_carries_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HATCHET_CLIENT_TOKEN", "SECRET-TOKEN-VAL")
    info = await get_server_info()
    assert "SECRET-TOKEN-VAL" not in json.dumps(info)
    assert info["server_url_source"] in {"token", "override"}


@pytest.mark.spec("v0.2.0/reliability#AC-7")
async def test_payload_read_only_reflects_flag(server_module: Any) -> None:
    shared._read_only = True
    assert (await get_server_info())["read_only"] is True

    shared._read_only = False
    assert (await get_server_info())["read_only"] is False


@pytest.mark.spec("v0.2.0/reliability#AC-7")
async def test_server_url_source_reflects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HATCHET_CLIENT_SERVER_URL", raising=False)
    assert (await get_server_info())["server_url_source"] == "token"

    monkeypatch.setenv("HATCHET_CLIENT_SERVER_URL", "https://hatchet.example.com")
    assert (await get_server_info())["server_url_source"] == "override"


@pytest.mark.spec("v0.2.0/reliability#AC-7")
async def test_payload_versions_well_formed() -> None:
    info = await get_server_info()
    assert isinstance(info["hatchet_sdk_version"], str) and info["hatchet_sdk_version"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", info["python_version"])


@pytest.mark.spec("v0.2.0/reliability#AC-7")
def test_get_server_info_registered_as_read_tool() -> None:
    from hatchet_mcp import server

    names = {name for _, name, _ in server.READ_TOOLS}
    assert "get_server_info" in names
    # Spec body §Decision 4 fixes the count post-this-spec at 25.
    assert len(server.READ_TOOLS) == 25


# * AC-8 — resource and tool return byte-identical JSON
@pytest.mark.spec("v0.2.0/reliability#AC-8")
async def test_resource_byte_identical_to_tool() -> None:
    tool_payload = await get_server_info()
    resource_payload = await resource_server_info()
    assert json.dumps(tool_payload, ensure_ascii=False) == resource_payload
    assert json.loads(resource_payload) == tool_payload


@pytest.mark.spec("v0.2.0/reliability#AC-8")
async def test_resource_keys_match_tool() -> None:
    tool_payload = await get_server_info()
    resource_payload = json.loads(await resource_server_info())
    assert tool_payload.keys() == resource_payload.keys() == _PAYLOAD_KEYS
