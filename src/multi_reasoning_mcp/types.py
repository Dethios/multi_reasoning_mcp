from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ReasoningLevel = Literal["fast", "standard", "deep"]
Engine = Literal["codex_cli", "gemini_cli", "none"]
SafetyLevel = Literal["low", "medium", "high"]


@dataclass
class PlanSubtask:
    id: str
    title: str
    description: str
    mode_id: str
    engine: Engine
    reasoning_level: ReasoningLevel
    depends_on: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    safety_level: SafetyLevel = "low"


@dataclass
class TaskPlan:
    task: str
    summary: str
    subtasks: list[PlanSubtask]
    acceptance_criteria: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ToolRunResult:
    ok: bool
    mode_id: str
    engine: Engine
    reasoning_level: ReasoningLevel
    output: dict[str, Any]
    raw: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
