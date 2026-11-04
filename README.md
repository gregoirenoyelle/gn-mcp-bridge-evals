# gn-mcp-bridge-evals

Evals for the `gn-mcp-bridge` WordPress plugin, run from the outside through its MCP server.

## Setup

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Test identities

The tests run against a **local** WordPress site with `gn-mcp-bridge` and `mcp-adapter` active. Never point them at a production site: they create and delete posts.

Each identity is a dedicated user with its own Application Password, created on the local site only and revocable at any time.

| Identity | Login | Role | Why |
|---|---|---|---|
| Full rights | `evals-full` | Administrator | Covers every ability, including `update-term` (`manage_options`) and `wp_navigation` (`edit_theme_options`) |
| Drafts only | `evals-drafts-only` | Contributor | Can create drafts (`edit_posts`) but not publish (`publish_posts`) |

Create them with WP-CLI from the site root:

```bash
wp user create evals-full evals-full@example.com --role=administrator
wp user create evals-drafts-only evals-drafts-only@example.com --role=contributor

wp user application-password create evals-full gn-mcp-bridge-evals --porcelain
wp user application-password create evals-drafts-only gn-mcp-bridge-evals --porcelain
```

Copy `.env.example` to `.env` and paste each password (shown once) into it. `.env` is gitignored.

Check the endpoint answers before running the tests (a `200` is expected, `401` without credentials):

```bash
curl -s -o /dev/null -w '%{http_code}\n' -u 'evals-full:<app-password>' \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"check","version":"0"}}}' \
  https://example.test/wp-json/gn-mcp/mcp
```

To revoke an identity: `wp user application-password delete <login> --all`, or delete the user.
