"""
Multi-Reasoning MCP Orchestrator (CLI-only)
"""
from __future__ import annotations

# Allow running via `mcp run path/to/server.py` without package context.
if __package__ in (None, ""):
    from pathlib import Path
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "multi_reasoning_mcp"

import os
import platform
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from mcp.server.fastmcp import FastMCP

from .bridge import BridgeManager, BridgeServerConfig, result_to_dict
from .config_loader import load_yaml
from .codex_client import CodexCliRunner
from .gemini_client import GeminiCliRunner
from .modes_registry import ModesRegistry
from .orchestrator import Orchestrator, build_repo_scan
from .patcher import apply_patch_text
from .repo_scan import repo_scan
from .types import PlanSubtask
from .utils import json_response, redact_secrets


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _workspace_root() -> Path:
    # default: monorepo root
    return Path(__file__).resolve().parents[4]


def _expand_vars(value: str, project_root: Path, workspace_root: Path) -> str:
    return (
        value.replace("${PROJECT_ROOT}", str(project_root))
        .replace("${WORKSPACE_ROOT}", str(workspace_root))
    )


def _load_runner_config(project_root: Path) -> dict[str, Any]:
    cfg_path = project_root / "config" / "llm_runners.yaml"
    return load_yaml(cfg_path)


def _load_bridge_config(project_root: Path, workspace_root: Path) -> list[BridgeServerConfig]:
    cfg_path = project_root / "config" / "mcp_bridge.yaml"
    raw = load_yaml(cfg_path)
    servers = []
    for name, entry in (raw.get("servers") or {}).items():
        env = {k: _expand_vars(str(v), project_root, workspace_root) for k, v in (entry.get("env") or {}).items()}
        command = _expand_vars(str(entry.get("command", "")), project_root, workspace_root)
        args = [
            _expand_vars(str(a), project_root, workspace_root) for a in (entry.get("args") or [])
        ]
        servers.append(
            BridgeServerConfig(
                name=name,
                command=command,
                args=args,
                env=env or None,
                cwd=_expand_vars(str(entry.get("cwd")), project_root, workspace_root) if entry.get("cwd") else None,
                allowed_tools=list(entry.get("allowed_tools") or []),
                enabled=bool(entry.get("enabled", True)),
            )
        )
    return servers


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    project_root = _project_root()
    workspace_root = Path(os.environ.get("MCP_WORKSPACE_ROOT", "") or _workspace_root())

    runner_cfg = _load_runner_config(project_root)
    codex_cfg = runner_cfg.get("codex", {})
    gemini_cfg = runner_cfg.get("gemini", {})

    codex = CodexCliRunner(
        command=os.environ.get("CODEX_BIN", codex_cfg.get("command", "codex")),
        sandbox=codex_cfg.get("sandbox", "read-only"),
        approval_policy=codex_cfg.get("approval_policy", "never"),
    )
    gemini = GeminiCliRunner(
        command=os.environ.get("GEMINI_BIN", gemini_cfg.get("command", "gemini")),
        output_format=gemini_cfg.get("output_format", "json"),
        approval_mode=gemini_cfg.get("approval_mode", "yolo"),
    )

    modes = ModesRegistry(project_root / "modes" / "modes.yaml")
    bridge_servers = _load_bridge_config(project_root, workspace_root)
    bridge = BridgeManager(bridge_servers) if bridge_servers else None

    orchestrator = Orchestrator(
        modes=modes,
        codex=codex,
        gemini=gemini,
        bridge=bridge,
        runner_config=runner_cfg,
        root=str(project_root),
    )

    try:
        yield {
            "project_root": project_root,
            "workspace_root": workspace_root,
            "runner_cfg": runner_cfg,
            "codex": codex,
            "gemini": gemini,
            "modes": modes,
            "bridge": bridge,
            "orchestrator": orchestrator,
        }
    finally:
        if bridge:
            await bridge.close()


mcp = FastMCP(name="MultiReasoningOrchestrator", lifespan=app_lifespan)


def _ctx() -> dict[str, Any]:
    ctx = mcp.get_context()
    return ctx.request_context.lifespan_context


@mcp.tool(title="Diagnostics", description="Check CLI availability and basic environment info.")
async def diagnostics() -> dict[str, Any]:
    def _run(cmd: list[str]) -> dict[str, Any]:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return {
                "ok": proc.returncode == 0,
                "stdout": redact_secrets(proc.stdout.strip()),
                "stderr": redact_secrets(proc.stderr.strip()),
                "returncode": proc.returncode,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    codex_info = _run(["codex", "--version"])
    gemini_info = _run(["gemini", "--version"])

    home = Path.home()
    codex_cfg = home / ".codex" / "config.toml"
    gemini_cfg = home / ".gemini" / "settings.json"

    return json_response(
        "Diagnostics complete.",
        codex=codex_info,
        gemini=gemini_info,
        platform={
            "system": platform.system(),
            "release": platform.release(),
            "python": platform.python_version(),
        },
        auth_hints={
            "codex_config_present": codex_cfg.exists(),
            "gemini_config_present": gemini_cfg.exists(),
        },
    )


@mcp.tool(title="List modes", description="Return available modes and metadata.")
async def list_modes() -> dict[str, Any]:
    modes: ModesRegistry = _ctx()["modes"]
    return json_response("Modes loaded.", registry=modes.to_dict())


@mcp.tool(title="Repo scan", description="Scan repository structure and stack.")
async def repo_scan_tool(options: dict[str, Any] | None = None) -> dict[str, Any]:
    options = options or {}
    root = options.get("root", str(_ctx()["project_root"]))
    max_depth = int(options.get("max_depth", 3))
    max_files = int(options.get("max_files", 2000))
    return json_response("Repo scan complete.", scan=repo_scan(root, max_depth=max_depth, max_files=max_files))


@mcp.tool(title="Orchestrate task", description="Create a plan and optionally execute subtasks.")
async def orchestrate_task(
    task: str,
    context: str = "",
    constraints: str = "",
    plan_only: bool = True,
) -> dict[str, Any]:
    orchestrator: Orchestrator = _ctx()["orchestrator"]
    return await orchestrator.orchestrate_task(task, context, constraints, plan_only)


@mcp.tool(title="Run subtask", description="Run a single subtask using the selected mode and engine.")
async def run_subtask(subtask_spec: dict[str, Any], context: str = "", constraints: str = "", confirm_token: str | None = None) -> dict[str, Any]:
    orchestrator: Orchestrator = _ctx()["orchestrator"]
    subtask = PlanSubtask(
        id=str(subtask_spec.get("id", "1")),
        title=str(subtask_spec.get("title", "Subtask")),
        description=str(subtask_spec.get("description", "")),
        mode_id=str(subtask_spec.get("mode_id", "general_coder")),
        engine=str(subtask_spec.get("engine", "codex_cli")),
        reasoning_level=str(subtask_spec.get("reasoning_level", "standard")),
        depends_on=list(subtask_spec.get("depends_on") or []),
        acceptance_criteria=list(subtask_spec.get("acceptance_criteria") or []),
        safety_level=str(subtask_spec.get("safety_level", "low")),
    )
    result = await orchestrator.run_subtask(subtask, context, constraints, confirm_token)
    return json_response(
        "Subtask completed." if result.ok else "Subtask failed.",
        ok=result.ok,
        mode_id=result.mode_id,
        engine=result.engine,
        reasoning_level=result.reasoning_level,
        output=result.output,
        warnings=result.warnings,
    )


@mcp.tool(title="Apply patch", description="Apply a unified diff with safety gates.")
async def apply_patch(patch_text: str, safety_level: str = "low", confirm_token: str | None = None) -> dict[str, Any]:
    project_root = _ctx()["project_root"]
    result = apply_patch_text(patch_text, root=str(project_root), safety_level=safety_level, confirm_token=confirm_token)
    return result


# Optional bridge tools for workspace memory
@mcp.tool(title="Memory search", description="Bridge to workspace_memory memory.search.")
async def memory_search(query: str, project_id: str | None = None, tags: list[str] | None = None, limit: int = 10) -> dict[str, Any]:
    bridge: BridgeManager | None = _ctx().get("bridge")
    if not bridge:
        return json_response("Bridge not configured.", ok=False)
    try:
        result = await bridge.call("workspace_memory", "memory.search", {
            "query": query,
            "project_id": project_id,
            "tags": tags,
            "limit": limit,
        })
        return json_response("Memory search complete.", result=result_to_dict(result))
    except Exception as e:
        return json_response("Memory search failed.", ok=False, error=str(e))


@mcp.tool(title="Memory remember", description="Bridge to workspace_memory memory.remember.")
async def memory_remember(item: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    bridge: BridgeManager | None = _ctx().get("bridge")
    if not bridge:
        return json_response("Bridge not configured.", ok=False)
    try:
        result = await bridge.call("workspace_memory", "memory.remember", {
            "item": item,
            "project_id": project_id,
        })
        return json_response("Memory stored.", result=result_to_dict(result))
    except Exception as e:
        return json_response("Memory store failed.", ok=False, error=str(e))


@mcp.tool(title="Context7 resolve library id", description="Bridge to context7 resolve-library-id.")
async def context7_resolve_library_id(query: str, library_name: str) -> dict[str, Any]:
    bridge: BridgeManager | None = _ctx().get("bridge")
    if not bridge:
        return json_response("Bridge not configured.", ok=False)
    try:
        result = await bridge.call("context7", "resolve-library-id", {
            "query": query,
            "libraryName": library_name,
        })
        return json_response("Context7 library id resolved.", result=result_to_dict(result))
    except Exception as e:
        return json_response("Context7 resolve failed.", ok=False, error=str(e))


@mcp.tool(title="Context7 query docs", description="Bridge to context7 query-docs.")
async def context7_query_docs(library_id: str, query: str) -> dict[str, Any]:
    bridge: BridgeManager | None = _ctx().get("bridge")
    if not bridge:
        return json_response("Bridge not configured.", ok=False)
    try:
        result = await bridge.call("context7", "query-docs", {
            "libraryId": library_id,
            "query": query,
        })
        return json_response("Context7 docs query complete.", result=result_to_dict(result))
    except Exception as e:
        return json_response("Context7 query failed.", ok=False, error=str(e))


@mcp.tool(title="Playwright navigate", description="Bridge to playwright_navigate.")
async def playwright_navigate(params: dict[str, Any]) -> dict[str, Any]:
    bridge: BridgeManager | None = _ctx().get("bridge")
    if not bridge:
        return json_response("Bridge not configured.", ok=False)
    try:
        result = await bridge.call("playwright", "playwright_navigate", params)
        return json_response("Playwright navigate complete.", result=result_to_dict(result))
    except Exception as e:
        return json_response("Playwright navigate failed.", ok=False, error=str(e))


@mcp.tool(title="Playwright screenshot", description="Bridge to playwright_screenshot.")
async def playwright_screenshot(params: dict[str, Any]) -> dict[str, Any]:
    bridge: BridgeManager | None = _ctx().get("bridge")
    if not bridge:
        return json_response("Bridge not configured.", ok=False)
    try:
        result = await bridge.call("playwright", "playwright_screenshot", params)
        return json_response("Playwright screenshot complete.", result=result_to_dict(result))
    except Exception as e:
        return json_response("Playwright screenshot failed.", ok=False, error=str(e))


@mcp.tool(title="Playwright click", description="Bridge to playwright_click.")
async def playwright_click(params: dict[str, Any]) -> dict[str, Any]:
    bridge: BridgeManager | None = _ctx().get("bridge")
    if not bridge:
        return json_response("Bridge not configured.", ok=False)
    try:
        result = await bridge.call("playwright", "playwright_click", params)
        return json_response("Playwright click complete.", result=result_to_dict(result))
    except Exception as e:
        return json_response("Playwright click failed.", ok=False, error=str(e))


@mcp.tool(title="Memory create entities", description="Bridge to memory create_entities.")
async def memory_create_entities(entities: list[dict[str, Any]]) -> dict[str, Any]:
    bridge: BridgeManager | None = _ctx().get("bridge")
    if not bridge:
        return json_response("Bridge not configured.", ok=False)
    try:
        result = await bridge.call("memory", "create_entities", {"entities": entities})
        return json_response("Memory entities created.", result=result_to_dict(result))
    except Exception as e:
        return json_response("Memory create entities failed.", ok=False, error=str(e))


@mcp.tool(title="Memory create relations", description="Bridge to memory create_relations.")
async def memory_create_relations(relations: list[dict[str, Any]]) -> dict[str, Any]:
    bridge: BridgeManager | None = _ctx().get("bridge")
    if not bridge:
        return json_response("Bridge not configured.", ok=False)
    try:
        result = await bridge.call("memory", "create_relations", {"relations": relations})
        return json_response("Memory relations created.", result=result_to_dict(result))
    except Exception as e:
        return json_response("Memory create relations failed.", ok=False, error=str(e))


@mcp.tool(title="Memory add observations", description="Bridge to memory add_observations.")
async def memory_add_observations(observations: list[dict[str, Any]]) -> dict[str, Any]:
    bridge: BridgeManager | None = _ctx().get("bridge")
    if not bridge:
        return json_response("Bridge not configured.", ok=False)
    try:
        result = await bridge.call("memory", "add_observations", {"observations": observations})
        return json_response("Memory observations added.", result=result_to_dict(result))
    except Exception as e:
        return json_response("Memory add observations failed.", ok=False, error=str(e))


@mcp.tool(title="Memory delete entities", description="Bridge to memory delete_entities.")
async def memory_delete_entities(entity_names: list[str]) -> dict[str, Any]:
    bridge: BridgeManager | None = _ctx().get("bridge")
    if not bridge:
        return json_response("Bridge not configured.", ok=False)
    try:
        result = await bridge.call("memory", "delete_entities", {"entityNames": entity_names})
        return json_response("Memory entities deleted.", result=result_to_dict(result))
    except Exception as e:
        return json_response("Memory delete entities failed.", ok=False, error=str(e))


@mcp.tool(title="Memory delete observations", description="Bridge to memory delete_observations.")
async def memory_delete_observations(deletions: list[dict[str, Any]]) -> dict[str, Any]:
    bridge: BridgeManager | None = _ctx().get("bridge")
    if not bridge:
        return json_response("Bridge not configured.", ok=False)
    try:
        result = await bridge.call("memory", "delete_observations", {"deletions": deletions})
        return json_response("Memory observations deleted.", result=result_to_dict(result))
    except Exception as e:
        return json_response("Memory delete observations failed.", ok=False, error=str(e))


@mcp.tool(title="Memory delete relations", description="Bridge to memory delete_relations.")
async def memory_delete_relations(relations: list[dict[str, Any]]) -> dict[str, Any]:
    bridge: BridgeManager | None = _ctx().get("bridge")
    if not bridge:
        return json_response("Bridge not configured.", ok=False)
    try:
        result = await bridge.call("memory", "delete_relations", {"relations": relations})
        return json_response("Memory relations deleted.", result=result_to_dict(result))
    except Exception as e:
        return json_response("Memory delete relations failed.", ok=False, error=str(e))


@mcp.tool(title="Memory read graph", description="Bridge to memory read_graph.")
async def memory_read_graph() -> dict[str, Any]:
    bridge: BridgeManager | None = _ctx().get("bridge")
    if not bridge:
        return json_response("Bridge not configured.", ok=False)
    try:
        result = await bridge.call("memory", "read_graph", {})
        return json_response("Memory graph read.", result=result_to_dict(result))
    except Exception as e:
        return json_response("Memory read graph failed.", ok=False, error=str(e))


@mcp.tool(title="Memory search nodes", description="Bridge to memory search_nodes.")
async def memory_search_nodes(query: str) -> dict[str, Any]:
    bridge: BridgeManager | None = _ctx().get("bridge")
    if not bridge:
        return json_response("Bridge not configured.", ok=False)
    try:
        result = await bridge.call("memory", "search_nodes", {"query": query})
        return json_response("Memory search complete.", result=result_to_dict(result))
    except Exception as e:
        return json_response("Memory search failed.", ok=False, error=str(e))


@mcp.tool(title="Memory open nodes", description="Bridge to memory open_nodes.")
async def memory_open_nodes(names: list[str]) -> dict[str, Any]:
    bridge: BridgeManager | None = _ctx().get("bridge")
    if not bridge:
        return json_response("Bridge not configured.", ok=False)
    try:
        result = await bridge.call("memory", "open_nodes", {"names": names})
        return json_response("Memory nodes opened.", result=result_to_dict(result))
    except Exception as e:
        return json_response("Memory open nodes failed.", ok=False, error=str(e))


@mcp.tool(title="Bridge health", description="Check workspace_memory bridge connectivity.")
async def bridge_health() -> dict[str, Any]:
    bridge: BridgeManager | None = _ctx().get("bridge")
    if not bridge:
        return json_response("Bridge not configured.", ok=False)
    try:
        result = await bridge.call("workspace_memory", "project.list", {})
        allowed = bridge.get_allowed_tools("workspace_memory")
        return json_response(
            "Bridge healthy.",
            ok=True,
            allowed_tools=allowed,
            result=result_to_dict(result),
        )
    except Exception as e:
        return json_response("Bridge check failed.", ok=False, error=str(e))


if __name__ == "__main__":
    mcp.run()
