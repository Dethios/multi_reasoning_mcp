from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _content_item_to_dict(item: Any) -> dict:
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "dict"):
        return item.dict()
    if isinstance(item, dict):
        return item
    return {"type": type(item).__name__, "value": str(item)}


def result_to_dict(result: Any) -> dict:
    if hasattr(result, "model_dump"):
        raw = result.model_dump()
    elif hasattr(result, "dict"):
        raw = result.dict()
    else:
        raw = {}
    content = getattr(result, "content", None)
    if content is None:
        return raw or {"result": str(result)}
    items = [_content_item_to_dict(i) for i in content]
    return {"content": items, "raw": raw}


@dataclass
class BridgeServerConfig:
    name: str
    command: str
    args: list[str]
    env: dict[str, str] | None
    cwd: str | None
    allowed_tools: list[str]
    enabled: bool = True


class BridgeClient:
    def __init__(self, config: BridgeServerConfig) -> None:
        self.config = config
        self._stack = AsyncExitStack()
        self._session: ClientSession | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._session is not None:
            return
        params = StdioServerParameters(
            command=self.config.command,
            args=self.config.args,
            env=self.config.env,
            cwd=self.config.cwd,
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
        names: list[str] = []
        for t in getattr(tools, "tools", []) or []:
            if hasattr(t, "name"):
                names.append(str(t.name))
            elif isinstance(t, dict) and "name" in t:
                names.append(str(t["name"]))
        return names

    async def call(self, tool: str, args: dict[str, Any]) -> Any:
        await self.start()
        assert self._session is not None
        async with self._lock:
            return await self._session.call_tool(tool, args)


class BridgeManager:
    def __init__(self, servers: list[BridgeServerConfig]) -> None:
        self._servers = {s.name: s for s in servers if s.enabled}
        self._clients: dict[str, BridgeClient] = {}

    def available_servers(self) -> list[str]:
        return sorted(self._servers.keys())

    def get_allowed_tools(self, name: str) -> list[str]:
        return list(self._servers[name].allowed_tools)

    async def _get_client(self, name: str) -> BridgeClient:
        if name not in self._servers:
            raise KeyError(f"Unknown bridge server: {name}")
        if name not in self._clients:
            self._clients[name] = BridgeClient(self._servers[name])
        return self._clients[name]

    async def call(self, name: str, tool: str, args: dict[str, Any]) -> Any:
        client = await self._get_client(name)
        return await client.call(tool, args)

    async def close(self) -> None:
        for client in self._clients.values():
            await client.close()
        self._clients = {}
