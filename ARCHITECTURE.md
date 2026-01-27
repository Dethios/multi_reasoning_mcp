# Architecture

## Overview

The orchestrator is a CLI-only MCP server that plans tasks, routes subtasks to mode personas, and applies changes through a deterministic patch gate. It never calls model APIs; all LLM work is done via **Codex CLI** and **Gemini CLI** subprocesses.

## Components

- `server.py`: MCP entrypoint exposing tools (diagnostics, list_modes, repo_scan_tool, orchestrate_task, run_subtask, apply_patch, bridge health, workspace memory bridge, context7/playwright/memory bridges).
- `modes/modes.yaml`: Mode registry with prompt templates, safety flags, output schemas, and preferred engines.
- `codex_client.py`: Codex CLI runner (`codex exec`) with non-interactive configuration.
- `gemini_client.py`: Gemini CLI runner (`gemini --output-format json`) with non-interactive approval mode.
- `orchestrator.py`: Planning + execution engine, run logs under `.orchestrator/runs/`.
- `patcher.py`: Deterministic patch application with confirmation token gate.
- `bridge.py`: Optional MCP bridge to workspace memory.
- `config/*.yaml`: Runtime defaults for runner and bridge behavior.

## Data Flow

1) `orchestrate_task` builds a JSON plan (plan-only or plan-and-execute).
2) Each subtask selects a mode and engine (Codex or Gemini CLI).
3) The mode prompt requests JSON output and (if needed) a unified diff.
4) Patches are applied only through `apply_patch`, guarded by confirm tokens.
5) Run artifacts are stored under `.orchestrator/runs/<timestamp>_<slug>/`.

## Mode Routing Heuristic

The router uses keyword-based heuristics to map tasks to modes:
- architecture/design -> `architect`
- debugging/tests -> `debugger`
- research/sources -> `deep_researcher_stage1`
- editing/docs -> `editor`
- finance -> `financial_planner`
- latex -> `latex_guru`
- therapy/journaling -> `therapist`

If no match, it defaults to `general_coder`.

## Roo and Orchestrator Mode Mapping

Roo modes are distinct from orchestrator modes, but the router heuristics align them in practice:

| Roo mode | Orchestrator mode |
| --- | --- |
| Architect | `architect` |
| Code / Executor | `general_coder` |
| Debug | `debugger` |
| Ask (research) | `deep_researcher_stage1` |
| Ask (editing/docs) | `editor` |
| Planner / Orchestrator | `architect` (plan-only) |
| Verifier | `editor` or `debugger` |

## CLI Runner Behavior

### Codex CLI

- Non-interactive: `codex --ask-for-approval never exec`
- Sandbox: `--sandbox read-only`
- Output: JSONL events + `--output-last-message` for final text
- Reasoning/verbosity mapped from `config/llm_runners.yaml`

### Gemini CLI

- Non-interactive output: `--output-format json`
- Approval: `--approval-mode yolo` (avoids prompt hang)
- Optional config:
  - `extensions` for explicit tool availability
  - `include_directories` for large-context ingestion
  - `allowed_tools` / `allowed_mcp_server_names` for guardrails

## Tool Naming

- `repo_scan_tool` is the canonical repo scan tool name.
- Bridge wrapper tools are prefixed with the server name (`context7_*`, `playwright_*`, `memory_*`).

## Allowlist Policy

Tool access is gated by a global allowlist in `config/llm_runners.yaml` and per-mode allowlists in
`modes/modes.yaml`. The effective toolset is the intersection of both lists; if either list is empty,
no tools are available.

## Safety Gates

- `apply_patch` checks for deletes, renames, bulk changes, and large diffs.
- Risky patches require a confirmation token derived from the patch content.
- Sensitive modes (`financial_planner`, `therapist`) require an explicit confirmation token before execution.

## Bridge MCP Integration

Two modes of integration are supported:

1) **Peer MCP server**: listed in `.vscode/mcp.json` for direct tool access.
2) **Bridge**: this orchestrator starts MCP clients via `config/mcp_bridge.yaml` and exposes wrapper tools for
   `workspace_memory`, `context7`, `playwright`, and `memory`.

The bridge is optional and fails safely if the memory server is not installed.

## Definition of Done

- OpenAI API usage removed from runtime path.
- Modes registry loaded from `modes/modes.yaml`.
- CLI runners for Codex and Gemini implemented (non-interactive).
- MCP tools exposed as specified.
- Safety gate in `apply_patch` with confirmation token.
- VS Code integration files for monorepo root and project folder.
- Smoke script + minimal pytest suite.
- README and ARCHITECTURE updated.
