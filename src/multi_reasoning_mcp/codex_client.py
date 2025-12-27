from __future__ import annotations

import asyncio
import json
import os
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional, Tuple

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _content_item_to_dict(item: Any) -> dict:
    # mcp content items are usually pydantic models; be resilient.
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "dict"):
        return item.dict()
    if isinstance(item, dict):
        return item
    return {"type": type(item).__name__, "value": str(item)}


def _extract_text_from_call_tool_result(result: Any) -> str:
    pieces: List[str] = []
    content = getattr(result, "content", None)

    if content is None:
        return str(result)

    for item in content:
        d = _content_item_to_dict(item)
        if d.get("type") == "text" and "text" in d:
            pieces.append(d["text"])
        elif "text" in d:
            pieces.append(str(d["text"]))
        else:
            # fall back to JSON
            pieces.append(json.dumps(d, ensure_ascii=False))
    return "\n".join(pieces).strip()


def _best_effort_conversation_id(result: Any) -> Optional[str]:
    """
    Codex MCP tool supports continuing a session via `codex-reply` with a conversationId.
    In practice, depending on Codex/MCP versions, the conversation ID may appear in:
      - metadata fields
      - streamed event payloads in result.content
      - (sometimes) not at all

    We try to locate it, but the orchestrator does not rely on it.
    """
    # Attempt 1: direct field
    cid = getattr(result, "conversationId", None) or getattr(result, "conversation_id", None)
    if isinstance(cid, str) and cid:
        return cid

    # Attempt 2: scan content for JSON that includes conversationId
    content = getattr(result, "content", None) or []
    for item in content:
        d = _content_item_to_dict(item)
        txt = d.get("text")
        if isinstance(txt, str):
            # sometimes text may be JSON lines
            for candidate in (txt,):
                try:
                    j = json.loads(candidate)
                except Exception:
                    continue
                if isinstance(j, dict) and isinstance(j.get("conversationId"), str):
                    return j["conversationId"]
    return None


class CodexMCPClient:
    """
    Long-lived MCP client to a local `codex mcp-server` subprocess.

    Key property: call `start()` once at server startup and reuse the same ClientSession
    for all subsequent tool calls.

    The MCP Python SDK example for stdio clients uses:
      - StdioServerParameters
      - stdio_client(...)
      - ClientSession(...)
      - session.initialize()
    """

    def __init__(
        self,
        command: str = "codex",
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.command = command
        self.args = args or ["mcp-server"]
        self.env = env  # if None, inherit env
        self._stack = AsyncExitStack()
        self._session: ClientSession | None = None
        self._lock = asyncio.Lock()

    @property
    def is_started(self) -> bool:
        return self._session is not None

    async def start(self) -> None:
        if self._session is not None:
            return

        params = StdioServerParameters(
            command=self.command,
            args=self.args,
            env=self.env,
        )
        read, write = await self._stack.enter_async_context(stdio_client(params))
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._session = session

    async def close(self) -> None:
        await self._stack.aclose()
        self._session = None

    async def list_tools(self) -> list[str]:
        await self.start()
        assert self._session is not None
        tools = await self._session.list_tools()
        # tools.tools is a list of Tool objects; get names robustly
        names: list[str] = []
        for t in getattr(tools, "tools", []) or []:
            if hasattr(t, "name"):
                names.append(str(t.name))
            else:
                d = _content_item_to_dict(t)
                if "name" in d:
                    names.append(str(d["name"]))
        return names

    async def run(
        self,
        prompt: str,
        reasoning_effort: str = "medium",
        verbosity: str = "medium",
        sandbox: str = "read-only",
        approval_policy: str = "on-failure",
        cwd: str = ".",
        include_plan_tool: bool = True,
        base_instructions: str | None = None,
    ) -> tuple[str, dict]:
        """
        Calls the Codex MCP tool named `codex` using the warm session.

        Tool schema documented by OpenAI includes keys like:
          - prompt
          - approval-policy
          - base-instructions
          - config
          - include-plan-tool
          - sandbox
          - cwd
        """
        await self.start()
        assert self._session is not None

        args: Dict[str, Any] = {
            "prompt": prompt,
            "sandbox": sandbox,
            "cwd": cwd,
            "approval-policy": approval_policy,
            "include-plan-tool": include_plan_tool,
            "config": {
                # let the user's Codex config.toml choose the base model;
                # we ONLY override reasoning/verbosity here by default.
                "model_reasoning_effort": reasoning_effort,
                "model_verbosity": verbosity,
            },
        }
        if base_instructions:
            args["base-instructions"] = base_instructions

        async with self._lock:
            result = await self._session.call_tool("codex", args)

        text = _extract_text_from_call_tool_result(result)
        cid = _best_effort_conversation_id(result)
        meta = {
            "conversation_id": cid,
            "raw": _content_item_to_dict(getattr(result, "model_dump", lambda: result)()),
        }
        return text, meta
