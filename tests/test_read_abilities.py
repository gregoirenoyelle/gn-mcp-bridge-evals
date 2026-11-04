"""Capability: the full-rights identity reads posts, blocks, meta and categories,
and what comes back matches the post as stored on the site.

The fixture post is created through WP-CLI, not through create-post, so these
tests don't depend on another ability working.
"""

import hashlib

import pytest
from mcp import Client

from conftest import FIXTURE_META_KEY, FIXTURE_META_VALUE, FixturePost
from gn_mcp_evals import site
from gn_mcp_evals.client import result_data, result_list, result_text, tool_name

pytestmark = pytest.mark.anyio


async def call(client: Client, ability: str, arguments: dict):
    result = await client.call_tool(tool_name(ability), arguments)
    assert not result.is_error, result_text(result)
    return result


async def test_search_posts_finds_the_published_fixture(full_client: Client, fixture_post: FixturePost) -> None:
    rows = result_list(await call(full_client, "gn-mcp/search-posts", {"keyword": fixture_post.token}))

    assert [row["id"] for row in rows] == [fixture_post.id]
    assert rows[0]["title"] == fixture_post.title
    assert rows[0]["categories"] == [fixture_post.category_name]


async def test_search_posts_filters_by_category(full_client: Client, fixture_post: FixturePost) -> None:
    rows = result_list(await call(full_client, "gn-mcp/search-posts", {"category": fixture_post.category_slug}))

    assert [row["id"] for row in rows] == [fixture_post.id]


async def test_search_posts_ignores_drafts(full_client: Client, fixture_post: FixturePost) -> None:
    """search-posts only returns published posts: the same fixture as a draft is not found."""
    site.wp("post", "update", str(fixture_post.id), "--post_status=draft")

    rows = result_list(await call(full_client, "gn-mcp/search-posts", {"keyword": fixture_post.token}))

    assert rows == []


async def test_get_post_returns_the_stored_post(full_client: Client, fixture_post: FixturePost) -> None:
    data = result_data(await call(full_client, "gn-mcp/get-post", {"id": fixture_post.id}))
    stored = site.get_post(fixture_post.id)

    assert stored is not None
    assert data["id"] == fixture_post.id
    assert data["title"] == stored["post_title"]
    assert data["content"] == stored["post_content"]
    assert data["status"] == stored["post_status"] == "publish"
    assert data["categories"] == [fixture_post.category_name]


async def test_get_post_by_slug(full_client: Client, fixture_post: FixturePost) -> None:
    stored = site.get_post(fixture_post.id)
    assert stored is not None

    data = result_data(await call(full_client, "gn-mcp/get-post", {"slug": stored["post_name"]}))

    assert data["id"] == fixture_post.id


async def test_get_post_outline_matches_the_stored_blocks(full_client: Client, fixture_post: FixturePost) -> None:
    data = result_data(await call(full_client, "gn-mcp/get-post-outline", {"id": fixture_post.id}))
    stored = site.get_post(fixture_post.id)

    assert stored is not None
    assert data["content_hash"] == hashlib.md5(stored["post_content"].encode()).hexdigest()
    assert data["bytes"] == len(stored["post_content"].encode())
    assert data["block_count"] == 3
    assert [(b["path"], b["blockName"]) for b in data["blocks"]] == [
        ("0", "core/paragraph"),
        ("1", "core/heading"),
        ("2", "core/paragraph"),
    ]
    # The editor's "Rename" field is exposed as the block name.
    assert data["blocks"][0]["name"] == "intro"


async def test_get_block_by_path_and_by_name(full_client: Client, fixture_post: FixturePost) -> None:
    by_path = result_data(await call(full_client, "gn-mcp/get-block", {"id": fixture_post.id, "path": "1"}))
    by_name = result_data(await call(full_client, "gn-mcp/get-block", {"id": fixture_post.id, "name": "intro"}))

    # The returned markup is the exact slice of the stored content.
    assert by_path["markup"] in fixture_post.content
    assert "Section title" in by_path["markup"]
    assert by_path["block"]["blockName"] == "core/heading"
    assert by_name["markup"] in fixture_post.content
    assert "Intro text" in by_name["markup"]
    assert by_name["block"]["path"] == "0"


async def test_get_post_meta_returns_the_stored_value(full_client: Client, fixture_post: FixturePost) -> None:
    data = result_data(await call(full_client, "gn-mcp/get-post-meta", {"id": fixture_post.id}))

    assert data["meta"] == {FIXTURE_META_KEY: FIXTURE_META_VALUE}
    assert data["meta"][FIXTURE_META_KEY] == site.get_meta(fixture_post.id, FIXTURE_META_KEY)


async def test_list_categories_includes_the_fixture_category(full_client: Client, fixture_post: FixturePost) -> None:
    rows = result_list(await call(full_client, "gn-mcp/list-categories", {}))
    ours = [row for row in rows if row["slug"] == fixture_post.category_slug]

    stored = site.get_term(fixture_post.category_id, "category")
    assert ours == [{"name": stored["name"], "slug": stored["slug"], "count": int(stored["count"])}]
    assert ours[0]["count"] == 1
