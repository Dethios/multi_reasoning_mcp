from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ModeSpec:
    id: str
    name: str
    purpose: str
    preferred_engine: str
    model: str | None
    reasoning_level: str
    prompt_template: str
    allowed_tools: list[str]
    sensitive: bool
    safety_notes: str
    output_schema: dict[str, Any]


class ModesRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._modes: dict[str, ModeSpec] = {}
        self._version: int | None = None

    def load(self) -> None:
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        version = int(raw.get("version", 1))
        modes = {}
        for item in raw.get("modes", []):
            spec = ModeSpec(
                id=str(item.get("id")),
                name=str(item.get("name")),
                purpose=str(item.get("purpose")),
                preferred_engine=str(item.get("preferred_engine")),
                model=item.get("model"),
                reasoning_level=str(item.get("reasoning_level")),
                prompt_template=str(item.get("prompt_template")),
                allowed_tools=list(item.get("allowed_tools") or []),
                sensitive=bool(item.get("sensitive")),
                safety_notes=str(item.get("safety_notes")),
                output_schema=dict(item.get("output_schema") or {}),
            )
            if not spec.id:
                raise ValueError("Mode entry missing id")
            modes[spec.id] = spec
        self._modes = modes
        self._version = version

    @property
    def version(self) -> int:
        if self._version is None:
            self.load()
        return int(self._version or 1)

    def all_modes(self) -> list[ModeSpec]:
        if not self._modes:
            self.load()
        return list(self._modes.values())

    def get(self, mode_id: str) -> ModeSpec:
        if not self._modes:
            self.load()
        if mode_id not in self._modes:
            raise KeyError(f"Unknown mode: {mode_id}")
        return self._modes[mode_id]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "modes": [self._mode_to_dict(m) for m in self.all_modes()],
        }

    @staticmethod
    def _mode_to_dict(mode: ModeSpec) -> dict[str, Any]:
        return {
            "id": mode.id,
            "name": mode.name,
            "purpose": mode.purpose,
            "preferred_engine": mode.preferred_engine,
            "model": mode.model,
            "reasoning_level": mode.reasoning_level,
            "prompt_template": mode.prompt_template,
            "allowed_tools": mode.allowed_tools,
            "sensitive": mode.sensitive,
            "safety_notes": mode.safety_notes,
            "output_schema": mode.output_schema,
        }
