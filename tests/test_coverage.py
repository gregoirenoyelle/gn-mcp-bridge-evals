"""Coverage: every ability the server exposes has an eval.

The exposed abilities come from the live MCP `tools/list`, not from a copy of the
plugin's docs, so a new ability in gn-mcp-bridge shows up here as uncovered.

COVERED_ABILITIES is maintained by hand: add an ability once a test in this
folder exercises it and checks the result on the site state.
"""

import pytest

from gn_mcp_evals.agent.cases import CASES
from gn_mcp_evals.client import Identity, connect, list_all_tools, tool_name

pytestmark = pytest.mark.anyio

# Only the plugin's own abilities; the theme adds gncom-* tools to the same server.
TOOL_PREFIX = "gn-mcp-"

COVERED_ABILITIES = {
    "gn-mcp/create-post",  # tests/test_create_post.py, tests/test_security_publish.py
    "gn-mcp/search-posts",  # tests/test_read_abilities.py
    "gn-mcp/get-post",  # tests/test_read_abilities.py
    "gn-mcp/get-post-outline",  # tests/test_read_abilities.py
    "gn-mcp/get-block",  # tests/test_read_abilities.py
    "gn-mcp/get-post-meta",  # tests/test_read_abilities.py
    "gn-mcp/list-categories",  # tests/test_read_abilities.py
    "gn-mcp/update-post",  # tests/test_write_abilities.py
    "gn-mcp/update-block",  # tests/test_write_abilities.py
    "gn-mcp/update-post-meta",  # tests/test_write_abilities.py
    "gn-mcp/update-term",  # tests/test_write_abilities.py
    "gn-mcp/delete-post",  # tests/test_write_abilities.py
}


async def exposed_plugin_tools(identity: Identity) -> set[str]:
    async with connect(identity) as client:
        return {tool.name for tool in await list_all_tools(client) if tool.name.startswith(TOOL_PREFIX)}


async def test_registry_only_lists_exposed_abilities(full_identity: Identity) -> None:
    """A renamed or removed ability must not linger in the registry."""
    exposed = await exposed_plugin_tools(full_identity)
    stale = {tool_name(ability) for ability in COVERED_ABILITIES} - exposed
    assert not stale, f"registry lists abilities the server no longer exposes: {sorted(stale)}"


async def test_every_exposed_ability_has_an_eval(full_identity: Identity) -> None:
    exposed = await exposed_plugin_tools(full_identity)
    uncovered = exposed - {tool_name(ability) for ability in COVERED_ABILITIES}
    assert not uncovered, f"{len(uncovered)} abilities without an eval: {sorted(uncovered)}"


async def test_every_exposed_ability_has_an_agent_case(full_identity: Identity) -> None:
    """Layer 2: same rule, read from the agent cases themselves (no hand-kept list)."""
    exposed = await exposed_plugin_tools(full_identity)
    in_cases = {tool_name(case.ability) for case in CASES}
    assert not exposed - in_cases, f"abilities without an agent case: {sorted(exposed - in_cases)}"
    assert not in_cases - exposed, f"agent cases for abilities the server no longer exposes: {sorted(in_cases - exposed)}"
