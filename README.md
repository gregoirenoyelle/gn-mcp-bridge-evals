# gn-mcp-bridge-evals

[![Tests](https://github.com/gregoirenoyelle/gn-mcp-bridge-evals/actions/workflows/tests.yml/badge.svg)](https://github.com/gregoirenoyelle/gn-mcp-bridge-evals/actions/workflows/tests.yml)

Evals for [`gn-mcp-bridge`](https://github.com/gregoirenoyelle/gn-mcp-bridge), a WordPress plugin that exposes content abilities as an MCP server. The evals run from the outside, through that MCP server, like any MCP client would.

## What the evals prove

- Each of the plugin's 12 abilities does what it says, checked on the **site state** (WP-CLI reads the database), never on the server's answer
- Permissions hold: an identity limited to drafts is refused when it tries to publish, read another author's content or change terms, and nothing changes on the site
- No ability ships without a test: a coverage test reads `tools/list` and fails if the server exposes an ability with no eval

## Two layers

| Layer | What it tests | Model | Status |
|---|---|---|---|
| 1. Server tests | Python calls the MCP tools directly, with two test identities | none | Done, runs in CI on a throwaway `wp-env` site |
| 2. Agent evals | Claude receives an instruction and the tools; the result is checked on the site, including how it behaves when the site refuses (reports it, doesn't work around it). Several runs each, success rate per ability and per identity | Claude API | Planned, not built yet |

## Setup

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Running the suite

The tests need a WordPress site with `gn-mcp-bridge` and `mcp-adapter` active, and two test identities (see below). Two ways to get one.

### Against a local site

Create the identities on the site, fill `.env` from `.env.example` (including `WP_PATH`, the site root used for the WP-CLI state checks), then:

```bash
source .venv/bin/activate
pytest
```

### Against a throwaway `wp-env` site

This is what CI does. It needs Node and Docker, and installs nothing on your machine's WordPress:

```bash
npm ci --ignore-scripts
npx --no-install wp-env start
scripts/ci-setup.sh                 # permalinks, identities, Application Passwords -> .env.wp-env
set -a; source .env.wp-env; set +a
WP_CLI="npx --no-install wp-env run cli wp" pytest
npx --no-install wp-env stop
```

`.env.wp-env` is gitignored and its passwords only exist on the throwaway site.

### In CI

`.github/workflows/tests.yml` runs the same steps on every push to `main`, on pull requests and on demand: layer 1 only (no AI, no API key needed).

Each report states the `gn-mcp-bridge` version tested. Last validated version: 1.8.2.

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
