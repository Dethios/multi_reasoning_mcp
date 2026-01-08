from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .bridge import BridgeManager
from .codex_client import CodexCliRunner
from .gemini_client import GeminiCliRunner
from .modes_registry import ModesRegistry
from .repo_scan import repo_scan
from .router import RouteDecision, route_task
from .types import PlanSubtask, TaskPlan, ToolRunResult
from .utils import ensure_dir, json_response, now_ts, redact_secrets, render_template, safe_slug


class Orchestrator:
    def __init__(
        self,
        modes: ModesRegistry,
        codex: CodexCliRunner,
        gemini: GeminiCliRunner,
        bridge: BridgeManager | None,
        runner_config: dict[str, Any],
        root: str = ".",
    ) -> None:
        self.modes = modes
        self.codex = codex
        self.gemini = gemini
        self.bridge = bridge
        self.runner_config = runner_config
        self.root = root

    def _plan_output_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["summary", "subtasks", "acceptance_criteria"],
            "properties": {
                "summary": {"type": "string"},
                "subtasks": {"type": "array"},
                "acceptance_criteria": {"type": "array"},
            },
        }

    def _plan_prompt(self, task: str, context: str, constraints: str) -> str:
        return (
            "You are an orchestrator. Build a minimal task plan as JSON. "
            "Include subtasks with mode_id, engine, reasoning_level, depends_on, safety_level.\n\n"
            f"TASK:\n{task}\n\nCONTEXT:\n{context}\n\nCONSTRAINTS:\n{constraints}\n\n"
            "Output JSON ONLY with keys: summary, subtasks, acceptance_criteria, notes."
        )

    def _resolve_engine(self, mode_id: str, override: str | None) -> str:
        if override:
            return override
        return self.modes.get(mode_id).preferred_engine

    def _render_prompt(self, mode_id: str, task: str, context: str, constraints: str) -> str:
        mode = self.modes.get(mode_id)
        return render_template(
            mode.prompt_template,
            {
                "task": task.strip(),
                "context": context.strip() or "(none)",
                "constraints": constraints.strip() or "(none)",
            },
        )

    def _reasoning_config(self, reasoning_level: str) -> dict[str, Any]:
        codex_cfg = self.runner_config.get("codex", {})
        reasoning_map = codex_cfg.get("reasoning_map", {})
        verbosity_map = codex_cfg.get("verbosity_map", {})
        effort = reasoning_map.get(reasoning_level, "medium")
        verbosity = verbosity_map.get(reasoning_level, "medium")
        return {
            "model_reasoning_effort": effort,
            "model_verbosity": verbosity,
        }

    def _gemini_policy(self) -> tuple[list[str], list[str]]:
        gemini_cfg = self.runner_config.get("gemini", {})
        allowed_tools = list(gemini_cfg.get("allowed_tools") or [])
        allowed_servers = list(gemini_cfg.get("allowed_mcp_server_names") or [])
        return allowed_tools, allowed_servers

    def _run_dir(self, task: str) -> Path:
        base = ensure_dir(Path(self.root) / ".orchestrator" / "runs")
        slug = safe_slug(task)
        return ensure_dir(base / f"{now_ts()}_{slug}")

    def _write_artifact(self, run_dir: Path, name: str, payload: Any) -> Path:
        path = run_dir / name
        if isinstance(payload, (dict, list)):
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        else:
            path.write_text(str(payload), encoding="utf-8")
        return path

    async def plan_task(
        self,
        task: str,
        context: str,
        constraints: str,
        planner_mode_id: str | None = None,
    ) -> TaskPlan:
        planner_mode_id = planner_mode_id or "architect"
        planner_mode = self.modes.get(planner_mode_id)
        prompt = self._plan_prompt(task, context, constraints)

        if planner_mode.preferred_engine == "gemini_cli":
            result = self.gemini.run(prompt=prompt, cwd=self.root)
            parsed = result.get("parsed_json")
        else:
            result = self.codex.run(
                prompt=prompt,
                cwd=self.root,
                reasoning_level=planner_mode.reasoning_level,
                output_schema=self._plan_output_schema(),
                config_overrides=self._reasoning_config(planner_mode.reasoning_level),
            )
            parsed = result.get("parsed_json")

        if not isinstance(parsed, dict):
            decision: RouteDecision = route_task(task)
            fallback = PlanSubtask(
                id="1",
                title="Implement task",
                description=task,
                mode_id=decision.mode_id,
                engine=decision.engine,
                reasoning_level=decision.reasoning_level,
                depends_on=[],
                acceptance_criteria=["Change implemented"],
                safety_level="low",
            )
            return TaskPlan(task=task, summary="Fallback plan", subtasks=[fallback])

        subtasks = []
        for i, s in enumerate(parsed.get("subtasks", []), start=1):
            subtasks.append(
                PlanSubtask(
                    id=str(s.get("id") or i),
                    title=str(s.get("title") or f"Subtask {i}"),
                    description=str(s.get("description") or ""),
                    mode_id=str(s.get("mode_id") or "general_coder"),
                    engine=str(s.get("engine") or self._resolve_engine(str(s.get("mode_id") or "general_coder"), None)),
                    reasoning_level=str(s.get("reasoning_level") or "standard"),
                    depends_on=list(s.get("depends_on") or []),
                    acceptance_criteria=list(s.get("acceptance_criteria") or []),
                    safety_level=str(s.get("safety_level") or "low"),
                )
            )

        return TaskPlan(
            task=task,
            summary=str(parsed.get("summary") or "Plan"),
            subtasks=subtasks,
            acceptance_criteria=list(parsed.get("acceptance_criteria") or []),
            notes=list(parsed.get("notes") or []),
        )

    async def run_subtask(
        self,
        subtask: PlanSubtask,
        context: str,
        constraints: str,
        confirm_token: str | None = None,
    ) -> ToolRunResult:
        mode = self.modes.get(subtask.mode_id)
        if mode.sensitive and not confirm_token:
            return ToolRunResult(
                ok=False,
                mode_id=mode.id,
                engine=subtask.engine,
                reasoning_level=subtask.reasoning_level,
                output=json_response(
                    "Confirmation required for sensitive mode.",
                    mode_id=mode.id,
                    safety_notes=mode.safety_notes,
                ),
                warnings=["confirmation_required"],
            )

        prompt = self._render_prompt(subtask.mode_id, subtask.description or subtask.title, context, constraints)
        if subtask.engine == "gemini_cli":
            allowed_tools, allowed_servers = self._gemini_policy()
            result = self.gemini.run(
                prompt=prompt,
                cwd=self.root,
                model=mode.model,
                allowed_tools=allowed_tools,
                allowed_mcp_server_names=allowed_servers,
            )
        else:
            result = self.codex.run(
                prompt=prompt,
                cwd=self.root,
                reasoning_level=subtask.reasoning_level,
                model=mode.model,
                config_overrides=self._reasoning_config(subtask.reasoning_level),
            )

        output = result.get("parsed_json")
        if not isinstance(output, dict):
            output = {"summary": "Non-JSON output", "text": result.get("last_message") or result.get("stdout")}

        return ToolRunResult(
            ok=bool(result.get("ok")),
            mode_id=subtask.mode_id,
            engine=subtask.engine,
            reasoning_level=subtask.reasoning_level,
            output=output,
            raw=result,
            warnings=[],
        )

    async def orchestrate_task(
        self,
        task: str,
        context: str,
        constraints: str,
        plan_only: bool = True,
    ) -> dict[str, Any]:
        run_dir = self._run_dir(task)
        plan = await self.plan_task(task, context, constraints)
        plan_payload = {
            "task": plan.task,
            "summary": plan.summary,
            "subtasks": [asdict(s) for s in plan.subtasks],
            "acceptance_criteria": plan.acceptance_criteria,
            "notes": plan.notes,
        }
        self._write_artifact(run_dir, "plan.json", plan_payload)

        if plan_only:
            return json_response(
                "Plan generated.",
                plan=plan_payload,
                run_dir=str(run_dir),
            )

        results = []
        for subtask in plan.subtasks:
            result = await self.run_subtask(subtask, context, constraints)
            result_payload = {
                "ok": result.ok,
                "mode_id": result.mode_id,
                "engine": result.engine,
                "reasoning_level": result.reasoning_level,
                "output": result.output,
                "warnings": result.warnings,
            }
            self._write_artifact(run_dir, f"subtask_{subtask.id}.json", result_payload)
            results.append(result_payload)

        return json_response(
            "Plan executed.",
            plan=plan_payload,
            results=results,
            run_dir=str(run_dir),
        )


async def build_repo_scan(root: str = ".") -> dict[str, Any]:
    return json_response("Repo scan complete.", scan=repo_scan(root))
