"""Capability: the full-rights identity changes posts, blocks, meta and terms,
and every change is read back from the site through WP-CLI.

Fixtures are created through WP-CLI (see conftest.fixture_post), not through
create-post, so these tests don't depend on another ability working.
"""

import uuid
from collections.abc import Iterator

import pytest
from mcp import Client

from conftest import FIXTURE_META_KEY, FixturePost
from gn_mcp_evals import site
from gn_mcp_evals.client import result_data, result_text, tool_name

pytestmark = pytest.mark.anyio

NEW_BLOCK = "<!-- wp:paragraph --><p>Inserted by evals</p><!-- /wp:paragraph -->"


async def call(client: Client, ability: str, arguments: dict):
    result = await client.call_tool(tool_name(ability), arguments)
    assert not result.is_error, result_text(result)
    return result


def stored_content(post_id: int) -> str:
    stored = site.get_post(post_id)
    assert stored is not None, f"post {post_id} not found on the site"
    return stored["post_content"]


@pytest.fixture
def throwaway_term() -> Iterator[dict]:
    """A category created through WP-CLI, deleted at teardown."""
    term = site.create_term("category", f"Evals term {uuid.uuid4().hex[:8]}", description="before")
    yield term
    site.delete_term(int(term["term_id"]), "category")


# update-post


async def test_update_post_changes_fields_on_the_site(full_client: Client, fixture_post: FixturePost) -> None:
    await call(
        full_client,
        "gn-mcp/update-post",
        {
            "id": fixture_post.id,
            "title": f"{fixture_post.title} edited",
            "excerpt": "Edited excerpt",
            "content": NEW_BLOCK,
            "categories": [fixture_post.category_slug],
            "comment_status": "closed",
        },
    )

    stored = site.get_post(fixture_post.id)
    assert stored is not None
    assert stored["post_title"] == f"{fixture_post.title} edited"
    assert stored["post_excerpt"] == "Edited excerpt"
    assert stored["post_content"] == NEW_BLOCK
    assert stored["comment_status"] == "closed"
    assert stored["post_status"] == "publish"  # untouched fields stay as they were
    assert site.post_category_slugs(fixture_post.id) == [fixture_post.category_slug]


async def test_update_post_status_to_draft(full_client: Client, fixture_post: FixturePost) -> None:
    await call(full_client, "gn-mcp/update-post", {"id": fixture_post.id, "status": "draft"})

    stored = site.get_post(fixture_post.id)
    assert stored is not None
    assert stored["post_status"] == "draft"


# update-block


async def test_update_block_replace_changes_only_the_target(full_client: Client, fixture_post: FixturePost) -> None:
    outline = result_data(await call(full_client, "gn-mcp/get-post-outline", {"id": fixture_post.id}))

    await call(
        full_client,
        "gn-mcp/update-block",
        {
            "id": fixture_post.id,
            "path": "1",
            "operation": "replace",
            "markup": '<!-- wp:heading --><h2 class="wp-block-heading">New title</h2><!-- /wp:heading -->',
            "expected_hash": outline["content_hash"],
        },
    )

    content = stored_content(fixture_post.id)
    assert "New title" in content
    assert "Section title" not in content
    # The other blocks are byte-identical.
    assert content.startswith(fixture_post.content.split("\n\n")[0])
    assert content.endswith(fixture_post.content.split("\n\n")[2])


async def test_update_block_insert_after_by_name(full_client: Client, fixture_post: FixturePost) -> None:
    await call(
        full_client,
        "gn-mcp/update-block",
        {"id": fixture_post.id, "name": "intro", "operation": "insert_after", "markup": NEW_BLOCK},
    )

    outline = result_data(await call(full_client, "gn-mcp/get-post-outline", {"id": fixture_post.id}))
    assert outline["block_count"] == 4
    content = stored_content(fixture_post.id)
    assert content.index("Intro text") < content.index("Inserted by evals") < content.index("Section title")


async def test_update_block_delete(full_client: Client, fixture_post: FixturePost) -> None:
    await call(full_client, "gn-mcp/update-block", {"id": fixture_post.id, "path": "1", "operation": "delete"})

    content = stored_content(fixture_post.id)
    assert "Section title" not in content
    assert "Intro text" in content
    assert fixture_post.token in content


async def test_update_block_refuses_a_stale_hash(full_client: Client, fixture_post: FixturePost) -> None:
    result = await full_client.call_tool(
        tool_name("gn-mcp/update-block"),
        {
            "id": fixture_post.id,
            "path": "1",
            "operation": "delete",
            "expected_hash": "0" * 32,
        },
    )

    assert result.is_error, "update-block accepted an expected_hash that doesn't match the post"
    assert stored_content(fixture_post.id) == fixture_post.content


# update-post-meta


async def test_update_post_meta_sets_updates_and_deletes(full_client: Client, fixture_post: FixturePost) -> None:
    await call(
        full_client,
        "gn-mcp/update-post-meta",
        {"id": fixture_post.id, "meta": {FIXTURE_META_KEY: "coral", "evals_size": "large"}},
    )
    assert site.get_meta(fixture_post.id, FIXTURE_META_KEY) == "coral"
    assert site.get_meta(fixture_post.id, "evals_size") == "large"

    await call(full_client, "gn-mcp/update-post-meta", {"id": fixture_post.id, "delete": ["evals_size"]})
    assert site.get_meta(fixture_post.id, "evals_size") is None
    assert site.get_meta(fixture_post.id, FIXTURE_META_KEY) == "coral"


async def test_update_post_meta_refuses_protected_keys(full_client: Client, fixture_post: FixturePost) -> None:
    result = await full_client.call_tool(
        tool_name("gn-mcp/update-post-meta"),
        {"id": fixture_post.id, "meta": {"_evals_protected": "x"}},
    )

    assert result.is_error, "update-post-meta wrote a protected (underscore) meta key"
    assert site.get_meta(fixture_post.id, "_evals_protected") is None


# update-term


async def test_update_term_changes_name_and_description(full_client: Client, throwaway_term: dict) -> None:
    term_id = int(throwaway_term["term_id"])

    await call(
        full_client,
        "gn-mcp/update-term",
        {"id": term_id, "name": f"{throwaway_term['name']} renamed", "description": "after"},
    )

    stored = site.get_term(term_id, "category")
    assert stored["name"] == f"{throwaway_term['name']} renamed"
    assert stored["description"] == "after"
    assert stored["slug"] == throwaway_term["slug"]  # the slug is not touched


# delete-post


async def test_delete_post_moves_it_to_the_trash(full_client: Client, fixture_post: FixturePost) -> None:
    """delete-post trashes (it doesn't delete for good): the post stays in the database as `trash`."""
    await call(full_client, "gn-mcp/delete-post", {"id": fixture_post.id})

    stored = site.get_post(fixture_post.id)
    assert stored is not None, "delete-post removed the post for good; the ability is documented to trash it"
    assert stored["post_status"] == "trash"
