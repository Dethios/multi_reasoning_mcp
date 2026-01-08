# Multi-Reasoning MCP Orchestrator (Codex + Gemini)

This project provides an MCP server that:

- Keeps a **warm** `codex mcp-server` subprocess alive (no respawn per call).
- Routes tasks to **Codex** and **Gemini CLI** (CLI-only, no model APIs).
- Automatically selects **reasoning effort** and **verbosity** for Codex runs.
- Includes a simple SQLite FTS **repo index** for fast repo-wide search.

## Run

```bash
pip install -r requirements.txt
mcp dev src/multi_reasoning_mcp/server.py
```

Then connect from:
- Codex CLI via `codex mcp add ...`
- Gemini CLI via `gemini mcp add ...`
- MCP Inspector via `mcp dev ...` then open inspector UI

## Connect (Codex CLI)

From the workspace root:

```bash
cd projects/multi_reasoning_mcp
codex mcp add multi_reasoning_mcp \
  --env PYTHONPATH="$PWD/src" \
  --env MCP_INDEX_DB="$PWD/.mcp_index.sqlite3" \
  -- python -m multi_reasoning_mcp.server
```

## Connect (Gemini CLI)

From the workspace root:

```bash
cd projects/multi_reasoning_mcp
gemini mcp add -t stdio -s project \
  -e PYTHONPATH="$PWD/src" \
  -e MCP_INDEX_DB="$PWD/.mcp_index.sqlite3" \
  multi_reasoning_mcp python -m multi_reasoning_mcp.server
```

## Connect (VS Code)

The workspace-level `.vscode/mcp.json` includes a `local/multi_reasoning_mcp` entry
that points at this server. Reload VS Code after changes.

## Environment Variables

- `CODEX_BIN` (defaults to `codex`)
- `GEMINI_BIN` (defaults to `gemini`)
- `MCP_INDEX_DB` (defaults to `.mcp_index.sqlite3`)
