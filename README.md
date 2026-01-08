# Multi-Reasoning MCP Orchestrator (CLI-only)

This MCP server orchestrates multi-agent workflows using **Codex CLI** and **Gemini CLI** only (no model APIs). It plans tasks, routes subtasks to modes, and applies changes via a deterministic patch gate.

## Highlights

- CLI-only execution (Codex CLI + Gemini CLI)
- Modes registry (`modes/modes.yaml`) with prompts, schemas, and safety flags
- Orchestrator with plan-only vs plan-and-execute
- Deterministic patch application with confirmation token
- Optional bridge to workspace memory MCP (`services/mcp_workspace_memory`)

---

## Setup

```bash
cd projects/multi_reasoning_mcp
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Run the MCP server (stdio)

```bash
cd projects/multi_reasoning_mcp
. .venv/bin/activate
python -m multi_reasoning_mcp.server
```

---

## VS Code integration

This repo supports **both**:
1) Opening the monorepo root (`~/dev-workspace`), and
2) Opening the project folder (`~/dev-workspace/projects/multi_reasoning_mcp`).

### Monorepo root

Workspace MCP config: `.vscode/mcp.json` includes:
- `local/multi_reasoning_mcp`
- `local/workspace_memory`

### Project folder only

Project MCP config: `projects/multi_reasoning_mcp/.vscode/mcp.json`

Reload VS Code after edits to `mcp.json`.

---

## Codex VS Code extension + Codex CLI

Codex uses `~/.codex/config.toml` (shared by the extension and CLI). A helper is provided:

```bash
projects/multi_reasoning_mcp/scripts/register_codex_mcp.sh
```

This registers:
- `multi_reasoning_mcp`
- `workspace_memory`

---

## Gemini CLI

Add the orchestrator MCP server:

```bash
cd projects/multi_reasoning_mcp
gemini mcp add -t stdio -s project \
  -e PYTHONPATH="$PWD/src" \
  multi_reasoning_mcp python -m multi_reasoning_mcp.server
```

---

## MCP tools exposed

- `diagnostics()`
- `list_modes()`
- `repo_scan(options)`
- `orchestrate_task(task, context, constraints, plan_only)`
- `run_subtask(subtask_spec, context, constraints, confirm_token?)`
- `apply_patch(patch_text, safety_level, confirm_token?)`
- `memory_search(...)` (bridge)
- `memory_remember(...)` (bridge)

All outputs are JSON with a human-readable `summary` field.

---

## Safety gates

`apply_patch` requires a confirmation token for risky patches (deletes, renames, bulk changes, large diffs). The server returns the required token, derived from the patch content:

```
CONFIRM_<first8-of-sha256>
```

Re-run `apply_patch` with that token to proceed.

Sensitive modes (`financial_planner`, `therapist`) also require a confirmation token for execution via `run_subtask`.

---

## Examples

### Plan-only orchestration

```json
{"task":"Refactor module X","context":"repo root","constraints":"no behavior change","plan_only":true}
```

### Execute a subtask

```json
{
  "subtask_spec": {
    "id": "1",
    "title": "Refactor module X",
    "description": "Refactor module X for clarity",
    "mode_id": "general_coder",
    "engine": "codex_cli",
    "reasoning_level": "standard"
  },
  "context": "repo root",
  "constraints": "no behavior change"
}
```

### Deep research (stage 1 + stage 2)

- Stage 1: run `deep_researcher_stage1` to gather sources.
- Stage 2: run `deep_researcher_stage2_packet` to generate a paste-ready packet for GPT-5.2 Pro (manual run).

### Editor pass

Use `editor` mode for docs formatting and consistency.

### Finance mode

Use `financial_planner` with explicit assumptions. Output is informational only (not financial advice).

### Therapist mode

Use `therapist` mode for CBT-style exercises. Output includes disclaimers and crisis notes.

---

## Smoke test

```bash
projects/multi_reasoning_mcp/scripts/smoke.sh
```

---

## Memory MCP integration

This orchestrator can bridge to `services/mcp_workspace_memory` if configured. The default bridge config lives in:

```
projects/multi_reasoning_mcp/config/mcp_bridge.yaml
```

If the memory server is not installed/configured, bridge calls return a structured error.

To enable the memory server locally:

```bash
cd services/mcp_workspace_memory
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m workspace_memory.server
```

---

## Files of interest

- `src/multi_reasoning_mcp/server.py`
- `src/multi_reasoning_mcp/orchestrator.py`
- `src/multi_reasoning_mcp/codex_client.py`
- `src/multi_reasoning_mcp/gemini_client.py`
- `modes/modes.yaml`
- `config/llm_runners.yaml`
- `config/mcp_bridge.yaml`
- `scripts/smoke.sh`
