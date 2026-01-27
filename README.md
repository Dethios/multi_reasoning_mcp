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

To generate a `~/.codex/config.toml` snippet that matches this repo’s paths:

```bash
projects/multi_reasoning_mcp/scripts/codex_config_snippet.sh
```

---

## Gemini CLI

Add the orchestrator MCP server:

```bash
cd projects/multi_reasoning_mcp
gemini mcp add -t stdio -s project \
  -e PYTHONPATH="$PWD/src" \
  multi_reasoning_mcp python -m multi_reasoning_mcp.server
```

Gemini runner config lives in `config/llm_runners.yaml`. You can enable:
- `extensions`: explicit Gemini extensions list
- `include_directories`: additional folders for large-context ingestion
- `allowed_tools` / `allowed_mcp_server_names`: guardrails for tools

---

## MCP tools exposed

- `diagnostics()`
- `list_modes()`
- `repo_scan_tool(options)`
- `orchestrate_task(task, context, constraints, plan_only)`
- `run_subtask(subtask_spec, context, constraints, confirm_token?)`
- `apply_patch(patch_text, safety_level, confirm_token?)`
- `memory_search(...)` (workspace bridge)
- `memory_remember(...)` (workspace bridge)
- `context7_resolve_library_id(query, library_name)` (bridge)
- `context7_query_docs(library_id, query)` (bridge)
- `playwright_navigate(params)` (bridge)
- `playwright_screenshot(params)` (bridge)
- `playwright_click(params)` (bridge)
- `memory_create_entities(...)` (bridge)
- `memory_create_relations(...)` (bridge)
- `memory_add_observations(...)` (bridge)
- `memory_delete_entities(...)` (bridge)
- `memory_delete_observations(...)` (bridge)
- `memory_delete_relations(...)` (bridge)
- `memory_read_graph()` (bridge)
- `memory_search_nodes(query)` (bridge)
- `memory_open_nodes(names)` (bridge)
- `bridge_health()` (bridge)

All outputs are JSON with a human-readable `summary` field.

### Tool naming

- `repo_scan_tool` is the canonical repo scan tool name.
- Bridge wrapper tools are prefixed with the server name (`context7_*`, `playwright_*`, `memory_*`).

### Allowlist policy

Tool access is gated by:

1) The global allowlist in `config/llm_runners.yaml` (`gemini.allowed_tools` and `gemini.allowed_mcp_server_names`).
2) The per-mode allowlist in `modes/modes.yaml`.

The effective toolset is the intersection of both lists. If either list is empty, no tools are available.

---

## Safety gates

`apply_patch` requires a confirmation token for risky patches (deletes, renames, bulk changes, large diffs). The server returns the required token, derived from the patch content:

```text
CONFIRM_<first8-of-sha256>
```

Re-run `apply_patch` with that token to proceed.

Sensitive modes (`financial_planner`, `therapist`) also require a confirmation token for execution via `run_subtask`.

---

## Roo and orchestrator modes

Roo modes are distinct from orchestrator modes. Routing uses the keyword heuristics described in
`src/multi_reasoning_mcp/router.py`. A common mapping is:

| Roo mode | Orchestrator mode |
| --- | --- |
| Architect | `architect` |
| Code / Executor | `general_coder` |
| Debug | `debugger` |
| Ask (research) | `deep_researcher_stage1` |
| Ask (editing/docs) | `editor` |
| Planner / Orchestrator | `architect` (plan-only) |
| Verifier | `editor` or `debugger` |

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

## Bridge MCP integration

This orchestrator can bridge to repo-scoped workspace memory and optional external MCP servers. The default bridge
config lives in:

```text
projects/multi_reasoning_mcp/config/mcp_bridge.yaml
```

Bridge entries include:

- `workspace_memory` (repo-scoped memory and docs)
- `context7` (library docs)
- `playwright` (browser automation)
- `memory` (upstream knowledge graph)

Use `workspace_memory` for repo context and the `memory` bridge for durable, cross-repo notes. Keep them separate.

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
