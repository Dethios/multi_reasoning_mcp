"""
Multi-Reasoning MCP Orchestrator
================================

This MCP server:
- Keeps a Codex MCP server subprocess warm (long-lived) and reuses it across tool calls.
- Can route tasks to:
  - Codex MCP server (best for repo edits, refactors, CI fixes, code optimization)
  - Gemini CLI (best for broad doc analysis / cross-checking / extra tooling)
  - OpenAI Chat model (best for planning, audit reports, summarization, routing)

Run:
  mcp dev src/multi_reasoning_mcp/server.py
or:
  python -m multi_reasoning_mcp.server

Notes:
- This server is designed to be consumed by MCP clients (Codex CLI, Gemini CLI, MCP Inspector, etc.).
- It spawns `codex mcp-server` ONCE at startup and keeps it alive.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import asdict

from mcp.server.fastmcp import FastMCP

from .codex_client import CodexMCPClient
from .gemini_client import GeminiCliRunner
from .indexer import RepoIndex
from .openai_llm import OpenAIChat
from .router import route_task
from .types import (
    IndexBuildResult,
    RouteDecision,
    SearchResults,
    ToolRunResult,
)
from .workflows import Orchestrator


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[dict]:
    """
    Lifespan hook: start expensive resources ONCE, reuse per tool call.

    We keep Codex MCP server warm by maintaining:
      - a single long-lived `codex mcp-server` subprocess
      - a single MCP ClientSession to that subprocess
    """
    codex_bin = os.environ.get("CODEX_BIN", "codex")
    codex_args = ["mcp-server"]
    codex_env = None  # inherit current env

    codex = CodexMCPClient(command=codex_bin, args=codex_args, env=codex_env)
    await codex.start()

    gemini = GeminiCliRunner(command=os.environ.get("GEMINI_BIN", "gemini"))

    openai_model = os.environ.get("OPENAI_MODEL", "gpt-5.2")
    openai_chat = OpenAIChat(model=openai_model)

    index_db = os.environ.get("MCP_INDEX_DB", ".mcp_index.sqlite3")
    repo_index = RepoIndex(db_path=index_db)

    orchestrator = Orchestrator(
        codex=codex,
        gemini=gemini,
        openai=openai_chat,
        repo_index=repo_index,
    )

    try:
        yield {
            "codex": codex,
            "gemini": gemini,
            "openai": openai_chat,
            "repo_index": repo_index,
            "orchestrator": orchestrator,
        }
    finally:
        # graceful shutdown
        await codex.close()


mcp = FastMCP(
    name="MultiReasoningOrchestrator",
    lifespan=app_lifespan,
    # Optional: declare dependencies for `mcp dev --with ...` workflows
    dependencies=["openai", "python-dotenv"],
)


def _ctx():
    ctx = mcp.get_context()
    return ctx.request_context.lifespan_context


@mcp.tool(title="Warm status", description="Check that the warm Codex subprocess is alive and list Codex MCP tools.")
async def warm_status() -> dict:
    lc = _ctx()
    codex: CodexMCPClient = lc["codex"]
    tools = await codex.list_tools()
    return {
        "codex_alive": codex.is_started,
        "codex_tools": tools,
    }


@mcp.tool(title="Route task", description="Classify a task and choose backend + reasoning effort. Uses LLM router if OPENAI_API_KEY is set, otherwise uses heuristics.")
def route(task: str, task_type: str | None = None) -> RouteDecision:
    lc = _ctx()
    openai: OpenAIChat = lc["openai"]
    return route_task(task=task, task_type=task_type, openai=openai)


@mcp.tool(title="Codex direct", description="Run a single Codex session using the warm Codex MCP subprocess.")
async def codex_direct(
    prompt: str,
    reasoning_effort: str = "medium",
    verbosity: str = "medium",
    sandbox: str = "read-only",
    approval_policy: str = "on-failure",
    cwd: str = ".",
    include_plan_tool: bool = True,
    base_instructions: str | None = None,
) -> ToolRunResult:
    lc = _ctx()
    codex: CodexMCPClient = lc["codex"]

    text, meta = await codex.run(
        prompt=prompt,
        reasoning_effort=reasoning_effort,
        verbosity=verbosity,
        sandbox=sandbox,
        approval_policy=approval_policy,
        cwd=cwd,
        include_plan_tool=include_plan_tool,
        base_instructions=base_instructions,
    )
    return ToolRunResult(
        backend="codex",
        agent_role="general",
        reasoning_effort=reasoning_effort,  # type: ignore
        verbosity=verbosity,  # type: ignore
        output_text=text,
        raw=meta,
    )


@mcp.tool(title="Gemini direct", description="Run Gemini CLI in non-interactive mode (gemini -p).")
def gemini_direct(
    prompt: str,
    model: str | None = None,
    all_files: bool = False,
    sandbox: bool = False,
    cwd: str = ".",
    timeout_sec: int = 1800,
) -> ToolRunResult:
    lc = _ctx()
    gemini: GeminiCliRunner = lc["gemini"]

    out = gemini.run(
        prompt=prompt,
        model=model,
        all_files=all_files,
        sandbox=sandbox,
        cwd=cwd,
        timeout_sec=timeout_sec,
    )
    return ToolRunResult(
        backend="gemini",
        agent_role="general",
        reasoning_effort="medium",
        verbosity="medium",
        output_text=out["stdout"].strip(),
        raw=out,
        warnings=[out["stderr"].strip()] if out.get("stderr") else [],
    )


@mcp.tool(title="Build repo index", description="Build/update a local SQLite FTS index for fast doc/code search.")
def build_repo_index(
    root: str = ".",
    include_globs: list[str] | None = None,
    exclude_dirs: list[str] | None = None,
    max_file_bytes: int = 2_000_000,
    rebuild: bool = False,
) -> IndexBuildResult:
    lc = _ctx()
    repo_index: RepoIndex = lc["repo_index"]
    return repo_index.build(
        root=root,
        include_globs=include_globs,
        exclude_dirs=exclude_dirs,
        max_file_bytes=max_file_bytes,
        rebuild=rebuild,
    )


@mcp.tool(title="Search repo index", description="Search the local repo index (SQLite FTS).")
def search_repo_index(query: str, top_k: int = 10) -> SearchResults:
    lc = _ctx()
    repo_index: RepoIndex = lc["repo_index"]
    return repo_index.search(query=query, top_k=top_k)


@mcp.tool(title="Orchestrate", description="Main entrypoint: auto-route a task and run it via Codex, Gemini, OpenAI, or both.")
async def orchestrate(
    task: str,
    task_type: str | None = None,
    backend: str | None = None,
    reasoning_effort: str | None = None,
    verbosity: str | None = None,
    dry_run: bool = False,
) -> ToolRunResult:
    lc = _ctx()
    orchestrator: Orchestrator = lc["orchestrator"]

    result = await orchestrator.run(
        task=task,
        task_type=task_type,
        backend_override=backend,
        reasoning_override=reasoning_effort,
        verbosity_override=verbosity,
        dry_run=dry_run,
    )
    return result


if __name__ == "__main__":
    # Direct execution (stdio transport)
    mcp.run()
