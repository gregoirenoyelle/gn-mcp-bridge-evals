"""Read and clean up the test site's state through WP-CLI, independently of the MCP server.

Checks never trust the tool response alone: what a test asserts is read back here.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from typing import Any


def _wp_command() -> list[str]:
    """WP-CLI command prefix: WP_CLI (default `wp`) plus --path=WP_PATH when set."""
    command = shlex.split(os.environ.get("WP_CLI", "wp"))
    path = os.environ.get("WP_PATH", "")
    if path:
        command.append(f"--path={path}")
    return command


def wp(*args: str) -> str:
    """Run a WP-CLI command against the test site and return its stdout."""
    completed = subprocess.run(
        [*_wp_command(), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"wp {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout


def get_post(post_id: int) -> dict[str, Any] | None:
    """Post fields as stored in the database, or None if the post does not exist."""
    try:
        out = wp("post", "get", str(post_id), "--format=json")
    except RuntimeError:
        return None
    return json.loads(out)


def find_posts(title: str, status: str = "any") -> list[dict[str, Any]]:
    """Posts with this exact title (any post type allowed over MCP), in the given status."""
    out = wp(
        "post", "list",
        "--post_type=post,page,wp_block",
        f"--post_status={status}",
        f"--title={title}",
        "--fields=ID,post_title,post_status,post_type",
        "--format=json",
    )
    return json.loads(out)


def delete_post(post_id: int) -> None:
    """Delete a post for good (bypassing the trash). Silent if it is already gone."""
    try:
        wp("post", "delete", str(post_id), "--force")
    except RuntimeError:
        pass


def plugin_version(slug: str = "gn-mcp-bridge") -> str:
    """Version of a plugin installed on the test site."""
    return wp("plugin", "get", slug, "--field=version").strip()


def user_id(login: str) -> int:
    """ID of a user on the test site, by login."""
    return int(wp("user", "get", login, "--field=ID").strip())


def create_post(
    title: str,
    content: str = "",
    status: str = "publish",
    post_type: str = "post",
    author: str | None = None,
) -> int:
    """Create a post straight through WP-CLI (fixtures: independent from the MCP abilities under test).

    `author` is a user login; ownership matters for the per-post permission checks.
    """
    args = [
        "post", "create",
        f"--post_title={title}",
        f"--post_content={content}",
        f"--post_status={status}",
        f"--post_type={post_type}",
        "--porcelain",
    ]
    if author:
        args.append(f"--post_author={user_id(author)}")
    return int(wp(*args).strip())


def get_meta(post_id: int, key: str) -> Any | None:
    """A post meta value as stored (JSON-decoded when it is JSON), or None if the key is not set."""
    try:
        out = wp("post", "meta", "get", str(post_id), key, "--format=json")
    except RuntimeError:
        return None
    return json.loads(out)


def set_meta(post_id: int, key: str, value: str) -> None:
    wp("post", "meta", "update", str(post_id), key, value)


def create_term(taxonomy: str, name: str, description: str = "") -> dict[str, Any]:
    """Create a term and return it as stored (term_id, name, slug, description)."""
    out = wp("term", "create", taxonomy, name, f"--description={description}", "--porcelain")
    return get_term(int(out.strip()), taxonomy)


def get_term(term_id: int, taxonomy: str) -> dict[str, Any]:
    return json.loads(wp("term", "get", taxonomy, str(term_id), "--format=json"))


def delete_term(term_id: int, taxonomy: str) -> None:
    """Delete a term. Silent if it is already gone."""
    try:
        wp("term", "delete", taxonomy, str(term_id))
    except RuntimeError:
        pass


def set_post_categories(post_id: int, *slugs: str) -> None:
    wp("post", "term", "set", str(post_id), "category", *slugs)


def post_category_slugs(post_id: int) -> list[str]:
    out = wp("post", "term", "list", str(post_id), "category", "--field=slug", "--format=json")
    return sorted(json.loads(out))
