# MCP client — endpoint, auth, SDK calls

Last updated: 2026-11-11

How the Python client talks to the `gn-mcp-bridge` MCP server. Versions checked: `gn-mcp-bridge` 1.8.2, `mcp-adapter` 0.7.1, MCP Python SDK (`mcp`) 2.3.0.

## Endpoint

- URL: `<site>/wp-json/gn-mcp/mcp` (local: `https://example.test/wp-json/gn-mcp/mcp`)
- Server declared by the plugin on `mcp_adapter_init`, HTTP transport only
- mcp-adapter's default server (`/wp-json/mcp/mcp-adapter-default-server`) is disabled by the plugin: `gn-mcp` is the only surface

## Authentication

- HTTP Basic: `Authorization: Basic base64(<login>:<application-password>)`
- No credentials or a bad Application Password → `401`
- Transport guard: the endpoint requires the `read` capability by default (filter `gn_mcp_bridge_transport_capability`)
- Then each ability has its own `permission_callback`, reading its capability from `Config::ability_capability()`

## Protocol versions

The server speaks both eras:

- `2025-11-25` (session-based): `initialize` returns an `Mcp-Session-Id` header; later calls must repeat it plus `MCP-Protocol-Version: 2025-11-25`, or the server replies `400 -32600`
- `2026-07-28` (sessionless): no `initialize`; `server/discover` instead, version and capabilities in `params._meta` of each request

The SDK handles both. `Client(...)` in default `mode="auto"` sends one `server/discover` probe and falls back to `initialize` if it fails. Against `mcp-adapter` 0.7.1 it should land on `2026-07-28`; `client.protocol_version` tells which one was negotiated, and every test report should record it. `mode="legacy"` forces the `initialize` handshake (useful to cover the session path Claude Code uses).

## SDK calls (v2 API)

Headers, auth and timeouts go on an `httpx2.AsyncClient` passed to the transport. `streamable_http_client` has no `headers=` or `auth=` keyword (v1's `streamablehttp_client` is removed).

```python
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

http_client = httpx2.AsyncClient(
    auth=(login, app_password),          # Basic auth
    timeout=httpx2.Timeout(30, read=300),  # keep the SDK defaults; httpx2's bare default is 5 s
)

async with http_client:
    transport = streamable_http_client(url, http_client=http_client)
    async with Client(transport) as client:
        tools = await client.list_tools()
        result = await client.call_tool("gn-mcp-create-post", {"title": "...", "status": "draft"})
```

Confirmed against the local site (implemented in `src/gn_mcp_evals/client.py`):

- Auth: `httpx2.BasicAuth(login, app_password)`
- `list_tools()` pagination: loop on `next_cursor` until `None`
- Local `.test` TLS works as-is: `httpx2` uses the OS trust store, which has Valet's certificate
- `mode="auto"` lands on `2026-07-28`; `mode="legacy"` on `2025-11-25`. Both expose the same tools

### Reading results

- `call_tool()` returns `is_error`, `content` (text for the model) and `structured_content` (for code)
- A tool failure is **not** an exception: it comes back with `is_error=True`
- `MCPError` is raised only when the server answers with a JSON-RPC error
- A refused `permission_callback` comes back as a result with `is_error=True` and a **localized** message (e.g. "Droit refusé" on a French site). Never assert on the text. The security tests accept either shape (error result or `MCPError`), then check the site state

## Site state checks

`src/gn_mcp_evals/site.py` reads the site through WP-CLI (`WP_PATH`, `WP_CLI`), independently of the MCP server under test. Each test uses a unique post title; teardown deletes the posts it tracked plus any post left with that title (e.g. one created despite a refusal).

## Tool names

Abilities are named `gn-mcp/<name>`. mcp-adapter exposes them as MCP tools with the slash replaced: `gn-mcp-<name>` (e.g. `gn-mcp-create-post`).

## Abilities and default capabilities

From `Config::DEFAULT_CAPABILITIES` (12 plugin abilities):

| Ability | Default capability |
|---|---|
| `gn-mcp/search-posts` | `read` |
| `gn-mcp/get-post` | `edit_others_posts` |
| `gn-mcp/get-post-outline` | `edit_others_posts` |
| `gn-mcp/get-block` | `edit_others_posts` |
| `gn-mcp/create-post` | `edit_posts` (+ the post type's `publish_posts` when `status` is `publish`) |
| `gn-mcp/update-post` | `edit_posts` |
| `gn-mcp/update-block` | `edit_posts` |
| `gn-mcp/delete-post` | `delete_posts` |
| `gn-mcp/get-post-meta` | `edit_posts` |
| `gn-mcp/update-post-meta` | `edit_posts` |
| `gn-mcp/list-categories` | `read` |
| `gn-mcp/update-term` | `manage_options` |

Allowed post types: `post`, `page`, `wp_block`, plus `wp_navigation` for users with `edit_theme_options`.

Consequence for the test identities: a WordPress **Contributor** (`edit_posts`, `delete_posts`, no `publish_posts`) is the natural "drafts only" identity. `create-post` with `status: publish` is refused by the publish check.

## Theme-side abilities on the local site

A theme or another plugin can add abilities to the `gn-mcp` server through the `gn_mcp_bridge_exposed_abilities` filter. On the author's local site, the active theme adds three, so `tools/list` returns 15 tools instead of 12.

They belong to the site, not to the plugin. The coverage test only counts the plugin's tools (`gn-mcp-` prefix) and ignores the rest.
