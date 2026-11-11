"""tools/list exposes every gn-mcp-bridge ability, over both protocol eras."""

import pytest

from gn_mcp_evals.client import Identity, connect, list_all_tools, tool_name

pytestmark = pytest.mark.anyio

# Abilities listed in the plugin's public README / Config::DEFAULT_CAPABILITIES.
PLUGIN_ABILITIES = [
    "gn-mcp/search-posts",
    "gn-mcp/get-post",
    "gn-mcp/get-post-outline",
    "gn-mcp/get-block",
    "gn-mcp/create-post",
    "gn-mcp/update-post",
    "gn-mcp/update-block",
    "gn-mcp/delete-post",
    "gn-mcp/get-post-meta",
    "gn-mcp/update-post-meta",
    "gn-mcp/list-categories",
    "gn-mcp/update-term",
]


@pytest.mark.parametrize(
    ("mode", "expected_version"),
    [("auto", "2026-07-28"), ("legacy", "2025-11-25")],
    ids=["sessionless-2026-07-28", "session-2025-11-25"],
)
async def test_tools_list_exposes_plugin_abilities(
    full_identity: Identity, mode: str, expected_version: str
) -> None:
    async with connect(full_identity, mode=mode) as client:
        assert client.protocol_version == expected_version
        exposed = {tool.name for tool in await list_all_tools(client)}

    missing = {tool_name(ability) for ability in PLUGIN_ABILITIES} - exposed
    assert not missing, f"abilities not exposed as MCP tools: {sorted(missing)}"
