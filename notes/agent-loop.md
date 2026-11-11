# Agent loop — Anthropic SDK and MCP tool mapping

Last updated: 2026-11-11

How layer 2 (agent evals) talks to Claude and maps the MCP tools. Checked against the Anthropic Python SDK docs (context7) on 2026-11-11. Latest SDK on PyPI at that date: `anthropic` 2.8.0.

## Dependency

- Optional extra `agent` in `pyproject.toml`: `anthropic>=2.8,<3`. Layer 1 CI does not install it
- Install for layer 2: `pip install -e ".[agent,dev]"`
- The key comes from the `ANTHROPIC_API_KEY` environment variable only (the SDK reads it by default)

## Manual tool-use loop

1. Call `client.messages.create(model=..., max_tokens=..., system=[...], tools=[...], tool_choice={"type": "auto"}, messages=[...])`
2. Append the **full** `response.content` as the next `assistant` message (thinking blocks must go back unchanged)
3. If `stop_reason == "tool_use"`: for each `tool_use` block, call the MCP tool and build a `tool_result` block, then send all results in **one** `user` message
4. Repeat until `stop_reason` is something else, or the turn cap is reached

Tool result block:

```python
{"type": "tool_result", "tool_use_id": block.id, "content": text, "is_error": True}  # is_error only on failure
```

- Every `tool_use` needs a matching `tool_result`, even when skipped: answer it with `is_error: True`
- Tool errors (a refusal by the site, a 4xx) go back to the model as `is_error: True` with the error text. That is the behavior layer 2 measures, so the loop must not hide them

## Stop reasons to handle

| `stop_reason` | Action |
|---|---|
| `end_turn` | Normal end, record the final text |
| `tool_use` | Run the tools, continue |
| `max_tokens` | Stop the run, mark it as truncated |
| `refusal` | Stop the run, record it (the model refused, not the site) |
| `pause_turn` | Send the response back as-is to continue |
| `model_context_window_exceeded` | Stop the run, mark it as failed |
| `stop_sequence` | Not used here |

## Usage and cost

- `response.usage`: `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` (the cache fields can be `None`)
- With API version 2026-10-21, total input = `input_tokens` + `cache_creation_input_tokens` + `cache_read_input_tokens`. Sum the three, and record them separately in the report
- `output_tokens` already includes thinking tokens
- Sum `usage` over all turns of a run, then over runs

## Prompt caching

- `cache_control: {"type": "ephemeral"}` on the **last tool** of the `tools` list caches all the tool definitions
- Same on the last block of `system` (a list of text blocks, not a plain string)
- The 12 tool definitions are identical across runs of the same identity, so they are read from the cache after the first call

## Effort

- `output_config={"effort": "low" | "medium" | "high" | "xhigh" | "max"}`; the report states the level used

## MCP tool → Claude tool definition

Source: `list_all_tools()` in `src/gn_mcp_evals/client.py` returns MCP `Tool` objects.

| MCP `Tool` | Claude tool |
|---|---|
| `name` (e.g. `gn-mcp-create-post`) | `name` (same; matches the Claude pattern `^[a-zA-Z0-9_-]{1,64}$`) |
| `description` | `description` |
| `input_schema` | `input_schema` (JSON Schema, passed as-is) |
| `output_schema`, `annotations` | Not sent |

Calling: `client.call_tool(block.name, block.input)` on the MCP connection of the identity under test. A `CallToolResult` with `is_error` true maps to `is_error: True`; the content comes from `result_text(result)`.

## To check in Phase D

- That the tool names returned by the server all match the Claude name pattern
- That the schemas the server returns are accepted as-is (no unsupported keywords)
- Whether the 5.5 models reject forced tool use (`tool_choice: any` / `tool`), as the plan assumes: stay on `auto`, which makes this irrelevant
