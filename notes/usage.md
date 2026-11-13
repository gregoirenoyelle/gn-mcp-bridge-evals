# Using the evals

Last updated: 2026-11-13

When and how to run this suite: pointing it at another site, what CI adds, why layer 2 calls the Claude API, and where the results go.

## Running it against another site

Nothing in the code is tied to one site. The target is set entirely in `.env`:

```bash
WP_MCP_URL=https://other-site.test/wp-json/gn-mcp/mcp
EVALS_FULL_USER=evals-full
EVALS_FULL_APP_PASSWORD=...
EVALS_DRAFTS_ONLY_USER=evals-drafts-only
EVALS_DRAFTS_ONLY_APP_PASSWORD=...
WP_PATH=/path/to/other-site
```

Steps for a new site:

1. Activate `gn-mcp-bridge` and `mcp-adapter` on it
2. Create the two test users and their Application Passwords (see "Test identities" in the README)
3. Fill a `.env` and run `pytest` (layer 1) or `python -m gn_mcp_evals.agent` (layer 2)

To keep several sites side by side, use one env file per site (`.env.<site>`, gitignored by the `.env.*` rule) and load the one you need:

```bash
set -a; source .env.other-site; set +a
pytest
```

Two constraints:

- **Local or throwaway sites only.** The suite creates, edits and deletes posts and terms
- **WP-CLI access is required.** Every check reads the site state through WP-CLI, independently of the MCP server. Set `WP_PATH` to the site root, or `WP_CLI` to a wrapper such as `npx --no-install wp-env run cli wp`. A remote site reachable only over HTTP cannot be checked, so this is a test suite for the plugin, not a monitoring tool for a live site

## Local runs vs CI

A local run is enough to validate a release. CI adds three things:

| | Local | CI (`wp-env`) |
|---|---|---|
| Site | Your dev site, with whatever it already holds | A fresh WordPress every run: a pass cannot depend on leftovers (old posts, options, other plugins) |
| Trigger | When you remember | Every push to `main`, every pull request, or on demand |
| Visibility | Only you | The badge and the run logs are public proof that the suite runs |

What CI runs:

- **Job 1:** layer 1, the server tests (`pytest -m "not slow"`)
- **Job 2:** the agent cases with the scripted model (`pytest -m slow`). No API key, no cost, not on pull requests

Layer 2 with a real model is never run in CI. It costs money, results vary between runs, and it would put an API key in CI.

What CI does **not** do: a release of `gn-mcp-bridge` does not trigger this workflow. The plugin version under test is pinned in `.wp-env.json` and bumped by hand. A cross-repo trigger (`repository_dispatch` from the plugin's release workflow) is possible later for layer 1.

## Why layer 2 calls the Claude API

An interactive coding agent such as Claude Code is the wrong tool for a measurement:

- **Controlled conditions.** The runner sends a fixed model, a neutral system prompt, only the plugin's tools and a turn cap. An interactive agent adds its own system prompt, project instructions, memory, skills and other MCP servers, and the result would mix all of them
- **Volume and automatic grading.** 17 cases × 5 runs is 85 runs, each followed by a check on the site state. That cannot be done by hand
- **Model comparison.** `--model` and `--effort` switch the model and effort level, and the report counts tokens per run
- **Real usage.** People building on `gn-mcp-bridge` will call a model API with these MCP tools. The eval reproduces that setting

An interactive agent is still the right tool to explore the plugin by hand. The API runner is what turns that into a repeatable number.

## Where the results go

| Run | Output | Content |
|---|---|---|
| Layer 1, local | Terminal (`pytest -v` for one line per test) | Standard pytest output |
| Layer 1, CI | GitHub, Actions tab, job log | Same, plus the plugin versions under test. Not saved as a file |
| Layer 2, report | Terminal, or a file with `--out report.md` | Success rate per ability and per identity, plugin version, model, token usage, and for each failure: reason, stop reason, tool calls, excerpt of the final answer |
| Layer 2, full runs | A file with `--json runs.json` | Every run, passes included: status, reason, stop reason, turns, tokens, each tool call with its arguments, whether it was refused and the site's exact answer, the model's final answer |

A complete release run:

```bash
python -m gn_mcp_evals.agent --model claude-sonnet-5-5 --runs 5 \
  --out reports/agent-evals-YYYY-MM-DD.md \
  --json reports/agent-evals-YYYY-MM-DD.json
```

The JSON keeps the raw answers from the test site (post content, IDs). Read it before committing it.

Read a JSON file quickly with `jq`:

```bash
# Failed runs only
jq '.runs[] | select(.status != "pass") | {case, run, detail}' runs.json

# Tools called in each run
jq '.runs[] | {case, run, tools: [.tool_calls[].name]}' runs.json
```
