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
