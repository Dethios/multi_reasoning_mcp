from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Optional

from .codex_client import CodexMCPClient
from .gemini_client import GeminiCliRunner
from .indexer import RepoIndex
from .openai_llm import OpenAIChat
from .prompts import ROLE_INSTRUCTIONS
from .router import route_task
from .types import RouteDecision, ToolRunResult


def _join(*parts: str) -> str:
    return "\n\n".join([p.strip() for p in parts if p and p.strip()]).strip()


class Orchestrator:
    """
    High-level workflow engine:
    - Routes the task
    - Selects reasoning level / sandbox / approvals
    - Applies an agent prompt template
    - Executes via the chosen backend(s)
    """

    def __init__(
        self,
        codex: CodexMCPClient,
        gemini: GeminiCliRunner,
        openai: OpenAIChat,
        repo_index: RepoIndex,
    ) -> None:
        self.codex = codex
        self.gemini = gemini
        self.openai = openai
        self.repo_index = repo_index

    async def run(
        self,
        task: str,
        task_type: str | None = None,
        backend_override: str | None = None,
        reasoning_override: str | None = None,
        verbosity_override: str | None = None,
        dry_run: bool = False,
    ) -> ToolRunResult:
        decision: RouteDecision = route_task(task=task, task_type=task_type, openai=self.openai)

        if backend_override:
            decision.backend = backend_override  # type: ignore
        if reasoning_override:
            decision.reasoning_effort = reasoning_override  # type: ignore
        if verbosity_override:
            decision.verbosity = verbosity_override  # type: ignore

        role_preamble = ROLE_INSTRUCTIONS.get(decision.agent_role, ROLE_INSTRUCTIONS["general"])

        # Add a small policy wrapper that standardizes outputs and reduces failure modes
        policy = """Global constraints:
- If you plan to edit files or run commands, state that in the plan.
- Prefer small, reversible changes.
- Never delete data unless explicitly asked.
- Always end with a short verification checklist.
"""

        full_prompt = _join(
            role_preamble,
            policy,
            f"TASK:\n{task}",
            "If you need clarification, make a best-effort assumption and list it explicitly.",
        )

        if dry_run:
            return ToolRunResult(
                backend=decision.backend,
                agent_role=decision.agent_role,
                reasoning_effort=decision.reasoning_effort,
                verbosity=decision.verbosity,
                output_text="DRY RUN\n\nRoute decision:\n" + str(asdict(decision)) + "\n\nPrompt:\n" + full_prompt,
                raw={"route": asdict(decision)},
            )

        if decision.backend == "codex":
            text, meta = await self.codex.run(
                prompt=full_prompt,
                reasoning_effort=decision.reasoning_effort,
                verbosity=decision.verbosity,
                sandbox=decision.codex_sandbox,
                approval_policy=decision.codex_approval_policy,
                cwd=".",
                include_plan_tool=True,
            )
            return ToolRunResult(
                backend="codex",
                agent_role=decision.agent_role,
                reasoning_effort=decision.reasoning_effort,
                verbosity=decision.verbosity,
                output_text=text,
                raw={"route": asdict(decision), "codex": meta},
            )

        if decision.backend == "gemini":
            out = self.gemini.run(
                prompt=full_prompt,
                model=decision.gemini_model,
                all_files=(decision.agent_role in ("doc_analyst", "auditor")),
                sandbox=False,
                cwd=".",
                timeout_sec=1800,
            )
            return ToolRunResult(
                backend="gemini",
                agent_role=decision.agent_role,
                reasoning_effort=decision.reasoning_effort,
                verbosity=decision.verbosity,
                output_text=out["stdout"].strip(),
                raw={"route": asdict(decision), "gemini": out},
                warnings=[out["stderr"].strip()] if out.get("stderr") else [],
            )

        if decision.backend == "openai":
            # Pure LLM response (no tool execution)
            if not self.openai.enabled:
                return ToolRunResult(
                    backend="openai",
                    agent_role=decision.agent_role,
                    reasoning_effort=decision.reasoning_effort,
                    verbosity=decision.verbosity,
                    output_text="OpenAI backend requested but OPENAI_API_KEY is not set. Re-run with OPENAI_API_KEY or use codex/gemini backend.",
                    raw={"route": asdict(decision)},
                    warnings=["OPENAI_API_KEY missing"],
                )

            txt = self.openai.complete(
                developer=f"You are {decision.agent_role}. Follow the instructions in the user message.",
                user=full_prompt,
                reasoning_effort=decision.reasoning_effort,
                verbosity=decision.verbosity,
            )
            return ToolRunResult(
                backend="openai",
                agent_role=decision.agent_role,
                reasoning_effort=decision.reasoning_effort,
                verbosity=decision.verbosity,
                output_text=txt,
                raw={"route": asdict(decision)},
            )

        if decision.backend == "both":
            # Codex first (implementation), then Gemini review (cross-check).
            # If you want a different composition, adjust here.
            text1, meta1 = await self.codex.run(
                prompt=full_prompt,
                reasoning_effort=decision.reasoning_effort,
                verbosity=decision.verbosity,
                sandbox=decision.codex_sandbox,
                approval_policy=decision.codex_approval_policy,
                cwd=".",
                include_plan_tool=True,
            )

            review_prompt = _join(
                ROLE_INSTRUCTIONS["reviewer"],
                "Review the following Codex output and propose fixes or risks.",
                "CODEX OUTPUT:",
                text1,
            )
            out2 = self.gemini.run(
                prompt=review_prompt,
                model=decision.gemini_model,
                all_files=False,
                sandbox=False,
                cwd=".",
                timeout_sec=1800,
            )

            combined = _join(
                "=== CODEX ===",
                text1,
                "=== GEMINI REVIEW ===",
                out2["stdout"].strip(),
            )

            warnings = []
            if out2.get("stderr"):
                warnings.append(out2["stderr"].strip())

            return ToolRunResult(
                backend="both",
                agent_role=decision.agent_role,
                reasoning_effort=decision.reasoning_effort,
                verbosity=decision.verbosity,
                output_text=combined,
                raw={"route": asdict(decision), "codex": meta1, "gemini": out2},
                warnings=warnings,
            )

        # fallback
        return ToolRunResult(
            backend="openai",
            agent_role="general",
            reasoning_effort="medium",
            verbosity="medium",
            output_text=f"Unknown backend '{decision.backend}'.",
            raw={"route": asdict(decision)},
            warnings=["Unknown backend"],
        )
