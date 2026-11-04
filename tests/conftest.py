"""Shared fixtures: test identities, MCP connections, unique titles and site cleanup."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from dotenv import load_dotenv
from mcp import Client

from gn_mcp_evals import site
from gn_mcp_evals.client import Identity, connect, load_identity

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _identity(name: str) -> Identity:
    if not os.environ.get("WP_MCP_URL"):
        pytest.skip("WP_MCP_URL not set: no test site configured (see .env.example)")
    return load_identity(name)


@pytest.fixture(scope="session")
def full_identity() -> Identity:
    return _identity("full")


@pytest.fixture(scope="session")
def drafts_only_identity() -> Identity:
    return _identity("drafts-only")


@pytest.fixture
async def full_client(full_identity: Identity) -> AsyncIterator[Client]:
    async with connect(full_identity) as client:
        yield client


@pytest.fixture
async def drafts_only_client(drafts_only_identity: Identity) -> AsyncIterator[Client]:
    async with connect(drafts_only_identity) as client:
        yield client


@pytest.fixture
def unique_title(request: pytest.FixtureRequest) -> str:
    """A post title no other post on the site has, so state checks can find exactly ours."""
    return f"evals {request.node.name} {uuid.uuid4().hex[:8]}"


@pytest.fixture
def created_posts(unique_title: str) -> Iterator[list[int]]:
    """Post IDs a test created. All of them, plus any post left with the test's
    unique title (e.g. created despite a refusal), are deleted at teardown."""
    ids: list[int] = []
    yield ids
    leftovers = {post["ID"] for post in site.find_posts(unique_title)}
    for post_id in set(ids) | leftovers:
        site.delete_post(post_id)
