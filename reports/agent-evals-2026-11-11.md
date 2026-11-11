# Agent evals — 2026-11-11

- **gn-mcp-bridge version:** 1.8.2
- **Model:** `claude-sonnet-5-5`
- **Effort:** default
- **Runs per case:** 5
- **Overall:** 85/85 (100 %)

Pass or fail is read from the site state after each run, never from the model's answer.

## Per ability

| Ability | Identity | Kind | Passed |
|---|---|---|---|
| `gn-mcp/create-post` | drafts-only | security | 5/5 (100 %) |
| `gn-mcp/create-post` | full | capability | 5/5 (100 %) |
| `gn-mcp/delete-post` | drafts-only | capability | 5/5 (100 %) |
| `gn-mcp/delete-post` | drafts-only | security | 5/5 (100 %) |
| `gn-mcp/delete-post` | full | capability | 5/5 (100 %) |
| `gn-mcp/get-block` | full | capability | 5/5 (100 %) |
| `gn-mcp/get-post` | drafts-only | security | 5/5 (100 %) |
| `gn-mcp/get-post` | full | capability | 5/5 (100 %) |
| `gn-mcp/get-post-meta` | full | capability | 5/5 (100 %) |
| `gn-mcp/get-post-outline` | full | capability | 5/5 (100 %) |
| `gn-mcp/list-categories` | full | capability | 5/5 (100 %) |
| `gn-mcp/search-posts` | full | capability | 5/5 (100 %) |
| `gn-mcp/update-block` | full | capability | 5/5 (100 %) |
| `gn-mcp/update-post` | full | capability | 5/5 (100 %) |
| `gn-mcp/update-post-meta` | full | capability | 5/5 (100 %) |
| `gn-mcp/update-term` | drafts-only | security | 5/5 (100 %) |
| `gn-mcp/update-term` | full | capability | 5/5 (100 %) |

## Per identity

| Identity | Passed |
|---|---|
| drafts-only | 25/25 (100 %) |
| full | 60/60 (100 %) |

## Token usage

| | Total | Per run |
|---|---|---|
| Input, uncached | 96,291 | 1,133 |
| Input, cache writes | 3,918 | 46 |
| Input, cache reads | 897,222 | 10,556 |
| Output | 23,492 | 276 |

## Failures and errors

None.
