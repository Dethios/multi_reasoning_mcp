#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_ROOT="$(cd "$ROOT/../.." && pwd)"

codex mcp add multi_reasoning_mcp \
  --env PYTHONPATH="$ROOT/src" \
  --env MCP_INDEX_DB="$ROOT/.mcp_index.sqlite3" \
  --env MCP_WORKSPACE_ROOT="$WORKSPACE_ROOT" \
  -- "$ROOT/.venv/bin/python" -m multi_reasoning_mcp.server

codex mcp add workspace_memory \
  --env PYTHONPATH="$WORKSPACE_ROOT/services/mcp_workspace_memory/src" \
  --env WORKSPACE_MEMORY_CONFIG="$WORKSPACE_ROOT/services/mcp_workspace_memory/config.toml" \
  -- python -m workspace_memory.server
