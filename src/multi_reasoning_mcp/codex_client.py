from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .utils import redact_secrets


class CodexCliRunner:
    def __init__(self, command: str = "codex", sandbox: str = "read-only", approval_policy: str = "never") -> None:
        self.command = command
        self.sandbox = sandbox
        self.approval_policy = approval_policy

    def run(
        self,
        prompt: str,
        cwd: str = ".",
        reasoning_level: str = "standard",
        model: str | None = None,
        timeout_sec: int = 1800,
        output_schema: dict[str, Any] | None = None,
        config_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        start = time.time()
        config_overrides = config_overrides or {}

        cmd: list[str] = [
            self.command,
            "--ask-for-approval",
            self.approval_policy,
            "exec",
            "--sandbox",
            self.sandbox,
            "-C",
            cwd,
            "--json",
        ]

        if model:
            cmd += ["-m", model]

        # map reasoning/verbosity via config overrides if provided
        for key, value in config_overrides.items():
            cmd += ["-c", f"{key}={json.dumps(value)}"]

        output_schema_path = None
        if output_schema is not None:
            fd, path = tempfile.mkstemp(prefix="codex_schema_", suffix=".json")
            Path(path).write_text(json.dumps(output_schema), encoding="utf-8")
            output_schema_path = path
            cmd += ["--output-schema", path]

        last_message_path = None
        try:
            fd, path = tempfile.mkstemp(prefix="codex_last_", suffix=".txt")
            last_message_path = path
            cmd += ["--output-last-message", path]

            proc = subprocess.run(
                cmd,
                input=prompt,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            last_message = ""
            if last_message_path and Path(last_message_path).exists():
                last_message = Path(last_message_path).read_text(encoding="utf-8", errors="ignore")

            parsed_json = None
            try:
                parsed_json = json.loads(last_message.strip())
            except Exception:
                parsed_json = None

            return {
                "ok": proc.returncode == 0,
                "engine": "codex_cli",
                "model": model,
                "reasoning_level": reasoning_level,
                "stdout": redact_secrets(stdout),
                "stderr": redact_secrets(stderr),
                "last_message": redact_secrets(last_message),
                "parsed_json": parsed_json,
                "diagnostics": {
                    "cmd": cmd,
                    "cwd": cwd,
                    "returncode": proc.returncode,
                    "duration_sec": round(time.time() - start, 2),
                },
                "artifacts": [p for p in [last_message_path, output_schema_path] if p],
            }
        finally:
            # leave artifacts for inspection; callers can clean up if desired
            pass
