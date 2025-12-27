# Multi-Reasoning MCP Orchestrator (Codex + Gemini)

This project provides an MCP server that:

- Keeps a **warm** `codex mcp-server` subprocess alive (no respawn per call).
- Routes tasks to **Codex**, **Gemini CLI**, **OpenAI Chat**, or **both**.
- Automatically selects **reasoning effort** and **verbosity** for GPT-5.2 style models.
- Includes a simple SQLite FTS **repo index** for fast repo-wide search.

## Run

```bash
pip install -r requirements.txt
mcp dev src/multi_reasoning_mcp/server.py
```

Then connect from:
- Codex CLI via `codex mcp add ...`
- Gemini CLI via `~/.gemini/settings.json`
- MCP Inspector via `mcp dev ...` then open inspector UI

## Environment Variables

- `OPENAI_API_KEY` (enables OpenAI routing + analysis)
- `CODEX_BIN` (defaults to `codex`)
- `GEMINI_BIN` (defaults to `gemini`)
- `OPENAI_MODEL` (defaults to `gpt-5.2`)
- `MCP_INDEX_DB` (defaults to `.mcp_index.sqlite3`)
