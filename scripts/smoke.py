import asyncio
import json
import os
import sys
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _to_jsonable(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    return {"value": str(obj)}


async def main() -> None:
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "multi_reasoning_mcp.server"],
        env=env,
        cwd=str(root),
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            diag = await session.call_tool("diagnostics", {})
            modes = await session.call_tool("list_modes", {})
            plan = await session.call_tool(
                "orchestrate_task",
                {
                    "task": "Summarize this repo structure",
                    "context": "smoke test",
                    "constraints": "plan only",
                    "plan_only": True,
                },
            )

    print(
        json.dumps(
            {
                "diagnostics": _to_jsonable(diag),
                "modes": _to_jsonable(modes),
                "plan": _to_jsonable(plan),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
