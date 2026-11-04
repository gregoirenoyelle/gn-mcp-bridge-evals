"""Security: the drafts-only identity cannot publish, and nothing is published on the site."""

import pytest
from mcp import Client
from mcp.shared.exceptions import MCPError

from gn_mcp_evals import site
from gn_mcp_evals.client import result_data, result_text, tool_name

pytestmark = pytest.mark.anyio

CONTENT = "<!-- wp:paragraph --><p>evals</p><!-- /wp:paragraph -->"


async def test_drafts_only_cannot_publish(
    drafts_only_client: Client, unique_title: str, created_posts: list[int]
) -> None:
    # A refusal may surface as an error result or as a JSON-RPC error: both are a refusal.
    try:
        result = await drafts_only_client.call_tool(
            tool_name("gn-mcp/create-post"),
            {"title": unique_title, "content": CONTENT, "status": "publish"},
        )
        refused = result.is_error
        detail = result_text(result)
    except MCPError as error:
        refused, detail = True, str(error)

    # The site state is what matters: no post with this title, published or not.
    published = site.find_posts(unique_title, status="publish")
    assert not published, f"drafts-only identity published a post: {published}"
    assert not site.find_posts(unique_title), "refused call still created a post"
    assert refused, f"publish not reported as refused: {detail}"


async def test_drafts_only_can_still_create_a_draft(
    drafts_only_client: Client, unique_title: str, created_posts: list[int]
) -> None:
    """Control: the refusal above is about publishing, not about the identity being locked out."""
    result = await drafts_only_client.call_tool(
        tool_name("gn-mcp/create-post"),
        {"title": unique_title, "content": CONTENT},
    )
    assert not result.is_error, result_text(result)
    post_id = int(result_data(result)["id"])
    created_posts.append(post_id)

    stored = site.get_post(post_id)
    assert stored is not None
    assert stored["post_status"] == "draft"
