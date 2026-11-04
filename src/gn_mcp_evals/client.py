"""Minimal MCP client for the gn-mcp-bridge server, one identity per connection."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent, Tool

USER_AGENT = "gn-mcp-bridge-evals"


@dataclass(frozen=True)
class Identity:
    """A dedicated WordPress test user and its Application Password."""

    name: str
    user: str
    app_password: str = ""

    def __repr__(self) -> str:  # never leak the password in test output
        return f"Identity(name={self.name!r}, user={self.user!r})"


def mcp_url() -> str:
    """MCP endpoint of the test site, from WP_MCP_URL."""
    url = os.environ.get("WP_MCP_URL", "")
    if not url:
        raise RuntimeError("WP_MCP_URL is not set (copy .env.example to .env)")
    return url


def load_identity(name: str) -> Identity:
    """Read an identity from EVALS_<NAME>_USER / EVALS_<NAME>_APP_PASSWORD."""
    prefix = f"EVALS_{name.upper().replace('-', '_')}"
    user = os.environ.get(f"{prefix}_USER", "")
    password = os.environ.get(f"{prefix}_APP_PASSWORD", "")
    if not user or not password:
        raise RuntimeError(f"{prefix}_USER / {prefix}_APP_PASSWORD are not set in .env")
    return Identity(name=name, user=user, app_password=password)


def tool_name(ability: str) -> str:
    """Map an ability name to its MCP tool name: gn-mcp/create-post -> gn-mcp-create-post."""
    return ability.replace("/", "-")


@asynccontextmanager
async def connect(identity: Identity, *, mode: str = "auto") -> AsyncIterator[Client]:
    """Open an MCP connection authenticated as `identity` (HTTP Basic, Application Password)."""
    http_client = httpx2.AsyncClient(
        auth=httpx2.BasicAuth(identity.user, identity.app_password),
        headers={"User-Agent": USER_AGENT},
        timeout=httpx2.Timeout(30, read=300),
    )
    async with http_client:
        transport = streamable_http_client(mcp_url(), http_client=http_client)
        async with Client(transport, mode=mode) as client:
            yield client


async def list_all_tools(client: Client) -> list[Tool]:
    """All tools exposed by the server, following pagination."""
    tools: list[Tool] = []
    cursor: str | None = None
    while True:
        page = await client.list_tools(cursor=cursor)
        tools.extend(page.tools)
        cursor = page.next_cursor
        if cursor is None:
            return tools


def result_text(result: CallToolResult) -> str:
    """Concatenated text blocks of a tool result (for failure messages)."""
    return "\n".join(block.text for block in result.content if isinstance(block, TextContent))


def result_data(result: CallToolResult) -> Any:
    """Structured payload of a successful tool result, falling back to JSON in the text."""
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result_text(result))
