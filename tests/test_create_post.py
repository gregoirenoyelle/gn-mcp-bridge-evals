"""Capability: the full-rights identity creates a draft, and the draft really exists on the site."""

import pytest
from mcp import Client

from gn_mcp_evals import site
from gn_mcp_evals.client import result_data, result_text, tool_name

pytestmark = pytest.mark.anyio


async def test_full_identity_creates_a_draft(
    full_client: Client, unique_title: str, created_posts: list[int]
) -> None:
    result = await full_client.call_tool(
        tool_name("gn-mcp/create-post"),
        {"title": unique_title, "content": "<!-- wp:paragraph --><p>evals</p><!-- /wp:paragraph -->"},
    )
    assert not result.is_error, result_text(result)
    post_id = int(result_data(result)["id"])
    created_posts.append(post_id)

    # Checked on the site, not on the tool response.
    stored = site.get_post(post_id)
    assert stored is not None, f"post {post_id} reported as created but not found on the site"
    assert stored["post_title"] == unique_title
    assert stored["post_status"] == "draft"
    assert stored["post_type"] == "post"
