from __future__ import annotations

import subprocess
from typing import Any, Optional


class GeminiCliRunner:
    """
    Lightweight wrapper around Gemini CLI in non-interactive mode.

    Gemini CLI supports:
      - `gemini -p "prompt"` (non-interactive / scripting)
      - piping stdin: `echo "..." | gemini`
      - `--model <model_name>`
      - `--all-files` to include all project files as context
      - `--sandbox` to run tools in a sandbox
    """

    def __init__(self, command: str = "gemini") -> None:
        self.command = command

    def run(
        self,
        prompt: str,
        model: Optional[str] = None,
        all_files: bool = False,
        sandbox: bool = False,
        cwd: str = ".",
        timeout_sec: int = 1800,
    ) -> dict[str, Any]:
        cmd = [self.command, "--prompt", prompt]
        if model:
            cmd += ["--model", model]
        if all_files:
            cmd += ["--all-files"]
        if sandbox:
            cmd += ["--sandbox"]

        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        return {
            "cmd": cmd,
            "cwd": cwd,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
