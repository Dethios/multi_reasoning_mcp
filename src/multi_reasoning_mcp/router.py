from __future__ import annotations

import re
from typing import Optional

from .openai_llm import OpenAIChat
from .types import RouteDecision


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def heuristic_route(task: str, task_type: str | None = None) -> RouteDecision:
    t = _normalize(task)
    tt = _normalize(task_type or "")

    # defaults
    backend = "codex"
    agent_role = "general"
    reasoning_effort = "medium"
    verbosity = "medium"
    codex_sandbox = "read-only"
    codex_approval_policy = "on-failure"
    gemini_model = None
    notes = "heuristic"

    def set_(**kw):
        nonlocal backend, agent_role, reasoning_effort, verbosity, codex_sandbox, codex_approval_policy, gemini_model, notes
        for k, v in kw.items():
            if v is not None:
                locals()[k]  # noop for lint
        backend = kw.get("backend", backend)
        agent_role = kw.get("agent_role", agent_role)
        reasoning_effort = kw.get("reasoning_effort", reasoning_effort)
        verbosity = kw.get("verbosity", verbosity)
        codex_sandbox = kw.get("codex_sandbox", codex_sandbox)
        codex_approval_policy = kw.get("codex_approval_policy", codex_approval_policy)
        gemini_model = kw.get("gemini_model", gemini_model)
        notes = kw.get("notes", notes)

    # If explicit task_type provided
    if tt:
        if "refactor" in tt:
            set_(agent_role="refactorer", reasoning_effort="high", codex_sandbox="workspace-write")
        elif "ci" in tt or "pipeline" in tt:
            set_(agent_role="ci_fixer", reasoning_effort="high", codex_sandbox="workspace-write")
        elif "audit" in tt:
            set_(agent_role="auditor", backend="codex", reasoning_effort="high", codex_sandbox="read-only", codex_approval_policy="untrusted")
        elif "document" in tt or "trend" in tt:
            set_(agent_role="doc_analyst", backend="gemini", reasoning_effort="high")
        elif "rename" in tt or "sort" in tt:
            set_(agent_role="file_ops", reasoning_effort="medium", codex_sandbox="workspace-write")
        elif "index" in tt or "ingest" in tt or "data" in tt:
            set_(agent_role="data_engineer", reasoning_effort="high", codex_sandbox="workspace-write")
        elif "review" in tt:
            set_(agent_role="reviewer", backend="both", reasoning_effort="high", codex_sandbox="read-only")
        elif "optimiz" in tt:
            set_(agent_role="optimizer", reasoning_effort="high", codex_sandbox="workspace-write")

        return RouteDecision(
            backend=backend, agent_role=agent_role, reasoning_effort=reasoning_effort, verbosity=verbosity,
            codex_sandbox=codex_sandbox, codex_approval_policy=codex_approval_policy,
            gemini_model=gemini_model, notes=notes
        )

    # Keyword routing
    if any(k in t for k in ["refactor", "re-architect", "cleanup", "rename symbol", "extract", "modularize"]):
        set_(agent_role="refactorer", reasoning_effort="high", codex_sandbox="workspace-write", notes="refactor heuristic")
    if any(k in t for k in ["ci", "github action", "pipeline", "build failing", "tests failing", "lint failing"]):
        set_(agent_role="ci_fixer", reasoning_effort="high", codex_sandbox="workspace-write", notes="ci heuristic")
    if any(k in t for k in ["audit", "security", "vulnerability", "threat model", "permissions"]):
        set_(agent_role="auditor", backend="codex", reasoning_effort="xhigh", codex_sandbox="read-only", codex_approval_policy="untrusted", notes="audit heuristic")
    if any(k in t for k in ["docs", "document", "trend", "themes", "summarize all", "corpus"]):
        set_(agent_role="doc_analyst", backend="gemini", reasoning_effort="high", notes="doc heuristic")
    if any(k in t for k in ["rename files", "sort files", "move files", "reorganize folders"]):
        set_(agent_role="file_ops", reasoning_effort="medium", codex_sandbox="workspace-write", notes="file ops heuristic")
    if any(k in t for k in ["ingest", "etl", "pipeline", "index", "vector", "embedding", "warehouse"]):
        set_(agent_role="data_engineer", reasoning_effort="high", codex_sandbox="workspace-write", notes="data heuristic")
    if any(k in t for k in ["code review", "review this diff", "review changes"]):
        set_(agent_role="reviewer", backend="both", reasoning_effort="high", codex_sandbox="read-only", notes="review heuristic")
    if any(k in t for k in ["optimize", "performance", "speed up", "reduce memory"]):
        set_(agent_role="optimizer", reasoning_effort="high", codex_sandbox="workspace-write", notes="opt heuristic")

    return RouteDecision(
        backend=backend,
        agent_role=agent_role,
        reasoning_effort=reasoning_effort,
        verbosity=verbosity,
        codex_sandbox=codex_sandbox,
        codex_approval_policy=codex_approval_policy,
        gemini_model=gemini_model,
        notes=notes,
    )


def llm_route(task: str, task_type: str | None, openai: OpenAIChat) -> RouteDecision:
    dev = """You are RoutingAgent for a multi-backend engineering orchestrator.

Return ONLY a JSON object with these keys:
- backend: one of ["codex","gemini","openai","both"]
- agent_role: one of ["refactorer","ci_fixer","auditor","doc_analyst","file_ops","data_engineer","researcher","reviewer","optimizer","general"]
- reasoning_effort: one of ["minimal","low","medium","high","xhigh"]
- verbosity: one of ["low","medium","high"]
- codex_sandbox: one of ["read-only","workspace-write","danger-full-access"]
- codex_approval_policy: one of ["untrusted","on-failure","never"]
- gemini_model: string or null
- notes: short string

Routing rules:
- Use codex when code changes, refactors, CI fixes, or optimization require editing/running code.
- Use gemini for broad doc analysis or when you want extra tooling/cross-check.
- Use both for high-stakes code changes: codex implements, gemini reviews.
- Use openai for pure analysis/planning/audit writeups without code execution.

Pick the LOWEST reasoning_effort that is safe; increase effort for:
- repo-wide changes, security concerns, ambiguous requirements, architectural decisions.
"""
    user = f"""TASK_TYPE: {task_type or "(none)"}

TASK:
{task}
"""

    j = openai.complete_json(developer=dev, user=user, reasoning_effort="low", verbosity="low")
    # Normalize and validate lightly with fallbacks
    backend = j.get("backend", "codex")
    agent_role = j.get("agent_role", "general")
    reasoning_effort = j.get("reasoning_effort", "medium")
    verbosity = j.get("verbosity", "medium")
    codex_sandbox = j.get("codex_sandbox", "read-only")
    codex_approval_policy = j.get("codex_approval_policy", "on-failure")
    gemini_model = j.get("gemini_model", None)
    notes = j.get("notes", "llm")

    return RouteDecision(
        backend=backend,
        agent_role=agent_role,
        reasoning_effort=reasoning_effort,
        verbosity=verbosity,
        codex_sandbox=codex_sandbox,
        codex_approval_policy=codex_approval_policy,
        gemini_model=gemini_model,
        notes=notes,
    )


def route_task(task: str, task_type: str | None, openai: OpenAIChat) -> RouteDecision:
    if openai.enabled:
        try:
            return llm_route(task=task, task_type=task_type, openai=openai)
        except Exception:
            return heuristic_route(task=task, task_type=task_type)
    return heuristic_route(task=task, task_type=task_type)
