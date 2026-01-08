#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_ROOT="$(cd "$ROOT/../.." && pwd)"

cat <<EOF
# Paste into ~/.codex/config.toml

[mcp_servers.multi_reasoning_mcp]
command = "$ROOT/.venv/bin/python"
args = ["-m", "multi_reasoning_mcp.server"]
cwd = "$ROOT"
enabled = true

[mcp_servers.multi_reasoning_mcp.env]
PYTHONPATH = "$ROOT/src"
MCP_INDEX_DB = "$ROOT/.mcp_index.sqlite3"
MCP_WORKSPACE_ROOT = "$WORKSPACE_ROOT"

[mcp_servers.workspace_memory]
command = "python"
args = ["-m", "workspace_memory.server"]
cwd = "$WORKSPACE_ROOT/services/mcp_workspace_memory"
enabled = true

[mcp_servers.workspace_memory.env]
PYTHONPATH = "$WORKSPACE_ROOT/services/mcp_workspace_memory/src"
WORKSPACE_MEMORY_CONFIG = "$WORKSPACE_ROOT/services/mcp_workspace_memory/config.toml"
EOF
