from __future__ import annotations

import json
import os
from typing import Any, Optional

try:
    from openai import OpenAI
except Exception as e:  # pragma: no cover
    OpenAI = None  # type: ignore


class OpenAIChat:
    """
    Tiny wrapper around OpenAI Chat Completions.

    Why we keep this tiny:
    - Your MCP server should remain stable even if OpenAI SDK evolves.
    - If OPENAI_API_KEY is missing, we simply disable LLM routing and fall back to heuristics.
    """

    def __init__(self, model: str = "gpt-5.2") -> None:
        self.model = model
        self.enabled = bool(os.environ.get("OPENAI_API_KEY")) and OpenAI is not None
        self._client = OpenAI() if self.enabled else None

    def complete(
        self,
        developer: str,
        user: str,
        reasoning_effort: str = "medium",
        verbosity: str = "medium",
        response_format: Optional[dict[str, Any]] = None,
    ) -> str:
        if not self.enabled or self._client is None:
            raise RuntimeError("OpenAIChat is disabled (missing OPENAI_API_KEY or openai package).")

        kwargs: dict[str, Any] = {}
        if response_format is not None:
            kwargs["response_format"] = response_format

        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "developer", "content": developer},
                {"role": "user", "content": user},
            ],
            reasoning_effort=reasoning_effort,
            verbosity=verbosity,
            **kwargs,
        )
        return (resp.choices[0].message.content or "").strip()

    def complete_json(
        self,
        developer: str,
        user: str,
        reasoning_effort: str = "low",
        verbosity: str = "low",
    ) -> dict[str, Any]:
        """
        Uses JSON mode to reliably return parseable JSON.
        """
        txt = self.complete(
            developer=developer,
            user=user,
            reasoning_effort=reasoning_effort,
            verbosity=verbosity,
            response_format={"type": "json_object"},
        )
        return json.loads(txt)
