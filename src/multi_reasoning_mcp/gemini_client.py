from __future__ import annotations

import json
import subprocess
import time
from typing import Any

from .utils import redact_secrets


class GeminiCliRunner:
    def __init__(self, command: str = "gemini", output_format: str = "json", approval_mode: str = "yolo") -> None:
        self.command = command
        self.output_format = output_format
        self.approval_mode = approval_mode

    def run(
        self,
        prompt: str,
        cwd: str = ".",
        model: str | None = None,
        timeout_sec: int = 1800,
        allowed_tools: list[str] | None = None,
        allowed_mcp_server_names: list[str] | None = None,
    ) -> dict[str, Any]:
        start = time.time()
        cmd: list[str] = [
            self.command,
            "--output-format",
            self.output_format,
            "--approval-mode",
            self.approval_mode,
        ]
        if model:
            cmd += ["--model", model]
        if allowed_tools:
            for tool in allowed_tools:
                cmd += ["--allowed-tools", tool]
        if allowed_mcp_server_names:
            for name in allowed_mcp_server_names:
                cmd += ["--allowed-mcp-server-names", name]
        cmd.append(prompt)

        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        parsed_json = None
        if self.output_format == "json":
            try:
                parsed_json = json.loads(stdout.strip())
            except Exception:
                parsed_json = None

        return {
            "ok": proc.returncode == 0,
            "engine": "gemini_cli",
            "model": model,
            "reasoning_level": "standard",
            "stdout": redact_secrets(stdout),
            "stderr": redact_secrets(stderr),
            "parsed_json": parsed_json,
            "diagnostics": {
                "cmd": cmd,
                "cwd": cwd,
                "returncode": proc.returncode,
                "duration_sec": round(time.time() - start, 2),
            },
            "artifacts": [],
        }
