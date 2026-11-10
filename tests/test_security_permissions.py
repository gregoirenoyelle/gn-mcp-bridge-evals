"""Security: the drafts-only identity (Contributor) is refused what its role doesn't allow,
and the site state is unchanged after each refusal.

Expected refusals follow gn-mcp-bridge's default capability map:
- get-post requires `edit_others_posts` (Contributor: no)
- update-term requires `manage_options` (Contributor: no)
- delete-post requires `delete_posts` (Contributor: yes), then the per-post `delete_post`
  meta capability: allowed on its own draft, refused on another author's post.

Fixture posts are created through WP-CLI with an explicit author, so ownership is known.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from mcp import Client
from mcp.shared.exceptions import MCPError

from conftest import FixturePost
from gn_mcp_evals import site
from gn_mcp_evals.client import Identity, result_text, tool_name

pytestmark = pytest.mark.anyio

CONTENT = "<!-- wp:paragraph --><p>evals</p><!-- /wp:paragraph -->"


async def call_tool(client: Client, ability: str, arguments: dict[str, Any]) -> tuple[bool, str]:
    """Run an ability and return (refused, detail). A refusal may surface as an error
    result or as a JSON-RPC error: both count as a refusal."""
    try:
        result = await client.call_tool(tool_name(ability), arguments)
    except MCPError as error:
        return True, str(error)
    return result.is_error, result_text(result)


@pytest.fixture
def draft_by(request: pytest.FixtureRequest) -> Iterator[Any]:
    """Factory: a draft owned by the given identity, created through WP-CLI, deleted for good at teardown."""
    ids: list[int] = []

    def make(identity: Identity) -> int:
        post_id = site.create_post(
            f"evals {request.node.name} {uuid.uuid4().hex[:8]}",
            CONTENT,
            status="draft",
            author=identity.user,
        )
        ids.append(post_id)
        return post_id

    yield make
    for post_id in ids:
        site.delete_post(post_id)


@pytest.fixture
def throwaway_term() -> Iterator[dict]:
    """A category created through WP-CLI, deleted at teardown."""
    term = site.create_term("category", f"Evals term {uuid.uuid4().hex[:8]}", description="before")
    yield term
    site.delete_term(int(term["term_id"]), "category")


async def test_drafts_only_cannot_read_a_post_with_get_post(
    drafts_only_client: Client, fixture_post: FixturePost
) -> None:
    refused, detail = await call_tool(drafts_only_client, "gn-mcp/get-post", {"id": fixture_post.id})

    assert refused, f"get-post not refused for drafts-only: {detail}"
    assert fixture_post.token not in detail, "refusal leaked the post content"


async def test_drafts_only_cannot_update_a_term(drafts_only_client: Client, throwaway_term: dict) -> None:
    term_id = int(throwaway_term["term_id"])

    refused, detail = await call_tool(
        drafts_only_client,
        "gn-mcp/update-term",
        {"id": term_id, "name": f"{throwaway_term['name']} hacked", "description": "after"},
    )

    stored = site.get_term(term_id, "category")
    assert stored["name"] == throwaway_term["name"], "refused call still renamed the term"
    assert stored["description"] == "before", "refused call still changed the description"
    assert refused, f"update-term not refused for drafts-only: {detail}"


async def test_drafts_only_cannot_delete_another_authors_post(
    drafts_only_client: Client, full_identity: Identity, draft_by
) -> None:
    """A draft owned by evals-full: the only reason to refuse is that it belongs to someone else."""
    post_id = draft_by(full_identity)

    refused, detail = await call_tool(drafts_only_client, "gn-mcp/delete-post", {"id": post_id})

    stored = site.get_post(post_id)
    assert stored is not None, "another author's post was deleted for good"
    assert stored["post_status"] == "draft", f"another author's post was moved to {stored['post_status']}"
    assert refused, f"delete-post not refused for drafts-only: {detail}"


async def test_drafts_only_can_delete_its_own_draft(
    drafts_only_client: Client, drafts_only_identity: Identity, draft_by
) -> None:
    """Control: the refusal above is about ownership, not about delete-post being closed to Contributors."""
    post_id = draft_by(drafts_only_identity)

    refused, detail = await call_tool(drafts_only_client, "gn-mcp/delete-post", {"id": post_id})

    assert not refused, detail
    stored = site.get_post(post_id)
    assert stored is not None and stored["post_status"] == "trash", f"own draft not trashed: {stored}"
