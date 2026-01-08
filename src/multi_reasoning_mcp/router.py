from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class RouteDecision:
    mode_id: str
    engine: str
    reasoning_level: str
    notes: str


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def route_task(task: str, task_type: str | None = None) -> RouteDecision:
    t = _normalize(task)
    tt = _normalize(task_type or "")

    # Default
    mode_id = "general_coder"
    engine = "codex_cli"
    reasoning_level = "standard"
    notes = "heuristic"

    def set_(m: str, e: str | None = None, r: str | None = None, n: str | None = None) -> None:
        nonlocal mode_id, engine, reasoning_level, notes
        mode_id = m
        if e:
            engine = e
        if r:
            reasoning_level = r
        if n:
            notes = n

    if tt:
        if "architect" in tt:
            set_("architect", r="deep", n="task_type")
        elif "debug" in tt or "test" in tt:
            set_("debugger", r="deep", n="task_type")
        elif "research" in tt:
            set_("deep_researcher_stage1", e="gemini_cli", r="deep", n="task_type")
        elif "edit" in tt or "doc" in tt:
            set_("editor", r="fast", n="task_type")
        elif "finance" in tt or "budget" in tt:
            set_("financial_planner", r="standard", n="task_type")
        elif "latex" in tt:
            set_("latex_guru", r="standard", n="task_type")
        elif "therapy" in tt or "cbt" in tt or "journal" in tt:
            set_("therapist", r="standard", n="task_type")
        return RouteDecision(mode_id=mode_id, engine=engine, reasoning_level=reasoning_level, notes=notes)

    if any(k in t for k in ["architecture", "design", "adr", "interface", "boundary"]):
        set_("architect", r="deep", n="keyword")
    elif any(k in t for k in ["debug", "stack trace", "failing test", "regression"]):
        set_("debugger", r="deep", n="keyword")
    elif any(k in t for k in ["research", "sources", "citations", "literature"]):
        set_("deep_researcher_stage1", e="gemini_cli", r="deep", n="keyword")
    elif any(k in t for k in ["edit", "proofread", "style", "consistency"]):
        set_("editor", r="fast", n="keyword")
    elif any(k in t for k in ["budget", "financial", "cash flow", "roi"]):
        set_("financial_planner", r="standard", n="keyword")
    elif "latex" in t:
        set_("latex_guru", r="standard", n="keyword")
    elif any(k in t for k in ["therapy", "cbt", "journaling", "journal"]):
        set_("therapist", r="standard", n="keyword")

    return RouteDecision(mode_id=mode_id, engine=engine, reasoning_level=reasoning_level, notes=notes)
