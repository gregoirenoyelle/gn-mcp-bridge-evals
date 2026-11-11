"""The MCP server's tools, wrapped as a `Toolbox` for one identity."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp import Client
from mcp.shared.exceptions import MCPError
from mcp.types import Tool

from gn_mcp_evals.agent.model import ToolDefinition, ToolOutcome
from gn_mcp_evals.client import connect, list_all_tools, load_identity, result_text

# Only the plugin's own abilities: the theme adds gncom-* tools to the same server,
# and they are not under test.
TOOL_PREFIX = "gn-mcp-"


def to_definition(tool: Tool) -> ToolDefinition:
    """MCP tool -> tool definition. Output schema and annotations are not sent to the model."""
    return ToolDefinition(
        name=tool.name,
        description=tool.description or "",
        input_schema=dict(tool.input_schema),
    )


class McpToolbox:
    def __init__(self, client: Client, tools: list[Tool]) -> None:
        self._client = client
        self._definitions = [to_definition(tool) for tool in tools if tool.name.startswith(TOOL_PREFIX)]
        self._names = {definition.name for definition in self._definitions}

    @property
    def definitions(self) -> list[ToolDefinition]:
        return self._definitions

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        if name not in self._names:
            return ToolOutcome(f"Unknown tool: {name}", is_error=True)
        # A refusal may surface as an error result or as a JSON-RPC error: both go back to the model.
        try:
            result = await self._client.call_tool(name, arguments)
        except MCPError as error:
            return ToolOutcome(str(error), is_error=True)
        return ToolOutcome(result_text(result), is_error=bool(result.is_error))


@asynccontextmanager
async def mcp_toolbox(identity_name: str) -> AsyncIterator[McpToolbox]:
    """An MCP connection as `identity_name`, exposing the plugin's tools."""
    async with connect(load_identity(identity_name)) as client:
        yield McpToolbox(client, await list_all_tools(client))
