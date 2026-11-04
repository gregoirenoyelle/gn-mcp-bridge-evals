# gn-mcp-bridge-evals

Evals for the `gn-mcp-bridge` WordPress plugin, run from the outside through its MCP server.

## Setup

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
