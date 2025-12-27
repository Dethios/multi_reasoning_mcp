from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


ReasoningEffort = Literal["minimal", "low", "medium", "high", "xhigh"]
Verbosity = Literal["low", "medium", "high"]
Backend = Literal["codex", "gemini", "openai", "both"]

SandboxMode = Literal["read-only", "workspace-write", "danger-full-access"]
ApprovalPolicy = Literal["untrusted", "on-failure", "never"]

AgentRole = Literal[
    "refactorer",
    "ci_fixer",
    "auditor",
    "doc_analyst",
    "file_ops",
    "data_engineer",
    "researcher",
    "reviewer",
    "optimizer",
    "general",
]


@dataclass
class RouteDecision:
    backend: Backend
    agent_role: AgentRole
    reasoning_effort: ReasoningEffort
    verbosity: Verbosity = "medium"
    codex_sandbox: SandboxMode = "read-only"
    codex_approval_policy: ApprovalPolicy = "on-failure"
    gemini_model: Optional[str] = None
    notes: str = ""


@dataclass
class ToolRunResult:
    backend: Backend
    agent_role: AgentRole
    reasoning_effort: ReasoningEffort
    verbosity: Verbosity
    output_text: str
    raw: Any = field(default=None)
    warnings: list[str] = field(default_factory=list)


@dataclass
class IndexBuildResult:
    root: str
    indexed_files: int
    skipped_files: int
    bytes_indexed: int
    db_path: str


@dataclass
class SearchHit:
    path: str
    score: float
    snippet: str


@dataclass
class SearchResults:
    query: str
    hits: list[SearchHit]
